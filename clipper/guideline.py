"""Campaign rules: what this campaign will and will not accept.

Style is *learned* from the references (stage 1). Rules are not learnable - they
come from the campaign brief - so they live in a file:

    campaigns/<name>/campaign.json      yours, gitignored
    samples/<name>/campaign.json        for the sample campaigns

This module is the engine (matching, verdicts, compliance); the campaign's own
words live in that JSON. Nothing here is specific to one campaign.

A rule file looks like this (every field optional):

    {
      "clip":    { "min_seconds": 20, "max_seconds": 180 },
      "hook":    { "within_seconds": 5 },
      "format":  { "aspect": "9:16", "captions_required": true },
      "topics":  { "approved": ["dating", "confidence"], "banned": ["politic", "money"] },
      "entities":{ "banned": ["dan bilzerian"] },
      "phrases": { "banned": ["you live in a country*"] },
      "tone":    { "warn": ["all women are"] },
      "brand":   { "face_min_coverage": 0.5, "notes": ["Michael must appear in 50% of the clip"] }
    }

Phrases take `*` wildcards. Everything is matched case- and punctuation-blind,
so "You live in a country..." in a brief matches "you live in a country where".
"""
from __future__ import annotations

import re
from pathlib import Path

from . import config
from .util import jsonio, log

DEFAULT_RULES: dict = {
    "version": 1,
    "campaign": None,
    "clip": {"min_seconds": 15.0, "max_seconds": 60.0},
    "hook": {"within_seconds": 5.0},
    "format": {"aspect": "9:16", "captions_required": True},
    "topics": {"approved": [], "banned": []},
    "entities": {"banned": []},
    "phrases": {"banned": []},
    "tone": {"warn": []},
    "brand": {"face_min_coverage": None, "notes": []},
    "platforms": {},
}

TEMPLATE = {
    "version": 1,
    "campaign": "",
    "clip": {"min_seconds": 20, "max_seconds": 180},
    "hook": {"within_seconds": 5},
    "format": {"aspect": "9:16", "captions_required": True},
    "topics": {"approved": [], "banned": []},
    "entities": {"banned": []},
    "phrases": {"banned": []},
    "tone": {"warn": []},
    "brand": {"face_min_coverage": None, "notes": []},
}

_WORD = re.compile(r"[^a-z0-9]+")


def normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse spaces - so matching is about words."""
    return _WORD.sub(" ", str(text or "").lower()).strip()


def _wildcard(pattern: str) -> re.Pattern:
    parts = [re.escape(p) for p in normalise(pattern).split("*")]
    return re.compile(r"\b" + r"\w*".join(parts))


def phrase_hits(text: str, patterns) -> list[str]:
    """Which banned phrases appear (wildcards allowed), as written in the rules."""
    haystack = normalise(text)
    if not haystack:
        return []
    return [p for p in patterns or [] if _wildcard(p).search(haystack)]


def keyword_hits(text: str, keywords) -> list[str]:
    """Substring match on normalised text: 'politic' catches 'politics', 'political'."""
    haystack = normalise(text)
    return [k for k in keywords or [] if k and normalise(k) in haystack]


def load(campaign: str | None = None, path: str | Path | None = None) -> dict:
    """The rules for a campaign, or the built-in defaults."""
    if path:
        data = jsonio.load(path, {}) or {}
        data.setdefault("path", str(path))
        return merge(data)
    if campaign:
        for candidate in (config.CAMPAIGNS / campaign / "campaign.json",
                          config.SAMPLES / campaign / "campaign.json"):
            if candidate.exists():
                data = jsonio.load(candidate, {}) or {}
                data.setdefault("path", str(candidate))
                data.setdefault("campaign", campaign)
                log.info("using campaign rules", path=str(candidate))
                return merge(data)
    return merge({"campaign": campaign, "path": None})


def merge(data: dict) -> dict:
    """Fill a rule file out to the full shape without losing what it says.

    Every public helper runs its input through here first, so a partial dict
    (a test fixture, or a hand-written stub) behaves exactly like a loaded file
    instead of silently skipping the checks it happens not to mention.
    """
    guided = {k: v for k, v in (data or {}).items()
              if k in ("clip", "hook", "format", "topics", "entities", "phrases", "tone", "brand")}
    merged = config.deep_merge(DEFAULT_RULES, guided)
    merged["campaign"] = (data or {}).get("campaign")
    merged["path"] = (data or {}).get("path")
    return merged


def save(rules: dict, path: str | Path) -> Path:
    path = Path(path)
    jsonio.save(path, rules)
    return path


def scaffold(campaign: str, path: str | Path | None = None) -> Path:
    """Write a commented starting point for a campaign's rules."""
    target = Path(path) if path else (config.CAMPAIGNS / campaign / "campaign.json")
    template = dict(TEMPLATE)
    template["campaign"] = campaign
    return save(template, target)


def clip_length(rules: dict | None) -> tuple[float, float]:
    clip = merge(rules)["clip"]
    lo = float(clip.get("min_seconds") or DEFAULT_RULES["clip"]["min_seconds"])
    hi = float(clip.get("max_seconds") or DEFAULT_RULES["clip"]["max_seconds"])
    return lo, (hi if hi >= lo else lo)


def text_verdict(text: str, rules: dict | None = None) -> dict:
    """Does this text break a campaign rule, or fit it?"""
    rules = merge(rules)
    banned, boosted, warned = [], [], []
    for phrase in phrase_hits(text, (rules.get("phrases") or {}).get("banned")):
        banned.append(f"a topic the campaign has retired: \u201c{phrase}\u201d")
    for topic in keyword_hits(text, (rules.get("topics") or {}).get("banned")):
        banned.append(f"a banned topic: {topic}")
    for entity in keyword_hits(text, (rules.get("entities") or {}).get("banned")):
        banned.append(f"a banned name: {entity}")
    for marker in keyword_hits(text, (rules.get("tone") or {}).get("warn")):
        warned.append(f"reads like one of the campaign's no-go framings: {marker}")
    for topic in keyword_hits(text, (rules.get("topics") or {}).get("approved")):
        boosted.append(f"an approved topic: {topic}")
    return {
        "reject": bool(banned),
        "banned": banned,
        "boost": boosted,
        "warn": warned,
        "reasons": [f"off-campaign: {b}" for b in banned]
                   + [f"on-campaign: {b}" for b in boosted]
                   + [f"check by hand: {w}" for w in warned],
    }


def length_verdict(seconds: float, rules: dict | None = None) -> tuple[bool, str]:
    lo, hi = clip_length(rules)
    if seconds < lo - 0.05:
        return False, f"{seconds:.1f}s is under the campaign minimum of {lo:.0f}s"
    if seconds > hi + 0.05:
        return False, f"{seconds:.1f}s is over the campaign maximum of {hi:.0f}s"
    return True, f"{seconds:.1f}s is inside the campaign's {lo:.0f}-{hi:.0f}s window"


def hook_verdict(text: str, offset: float, rules: dict | None = None) -> tuple[bool, str]:
    """Is the hook close enough to the start to survive the first seconds?"""
    from .select.hooks import score_text

    rules = merge(rules)
    within = float(rules["hook"]["within_seconds"] or 5.0)
    first_words = normalise(text)[:200]
    score, _ = score_text(first_words)
    if offset <= within:
        return True, f"the hook lands {offset:.1f}s in (campaign wants <{within:.0f}s)"
    return False, f"the hook only lands {offset:.1f}s in (campaign wants <{within:.0f}s)"


def compliance(candidate: dict, rules: dict | None = None, *, hook_at: float | None = None) -> dict:
    """Every campaign check we can make offline, with the numbers behind them."""
    rules = merge(rules)
    checks: list[dict] = []
    notes: list[str] = list((rules.get("brand") or {}).get("notes") or [])

    ok, why = length_verdict(float(candidate.get("duration") or 0), rules)
    checks.append({"check": "length", "pass": ok, "detail": why})

    verdict = text_verdict(candidate.get("text") or "", rules)
    checks.append({"check": "topics", "pass": not verdict["reject"],
                   "detail": "; ".join(verdict["reasons"]) or "nothing off-campaign found"})

    if hook_at is not None:
        ok, why = hook_verdict(candidate.get("text") or "", hook_at, rules)
        checks.append({"check": "hook", "pass": ok, "detail": why})

    captions = (rules.get("format") or {}).get("captions_required")
    aspect = (rules.get("format") or {}).get("aspect")
    if captions is not None or aspect:
        checks.append({"check": "format", "pass": True,
                       "detail": f"{aspect or 'as filmed'}"
                                 + (", burned-in captions required (stage 3 does this)"
                                    if captions else "")})

    face = (rules.get("brand") or {}).get("face_min_coverage")
    if face:
        notes.append(f"brand rule: a face must be on screen for at least {face * 100:.0f}% "
                     f"of the clip - not measured (no offline face detector installed)")
    return {
        "pass": all(c["pass"] for c in checks),
        "checks": checks,
        "notes": notes,
        "warnings": verdict["warn"],
        "boost": verdict["boost"],
    }


def load_for_media(media: Path, campaign: str | None = None) -> dict:
    """Rules for a file: the campaign's, or the built-in defaults."""
    return load(campaign) if campaign else load(None)
