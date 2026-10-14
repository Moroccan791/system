"""Stage 2 - pick the moments worth cutting out of a long recording.

Reads a raw file (and a transcript if one exists) and writes
`work/<name>/candidates.json`: ranked windows with their reasons, ready for the
edit stage to assemble and the export stage to render. Nothing here depends on
a specific ASR provider or on a transcript existing at all.
"""
from __future__ import annotations

import math
from pathlib import Path

from .. import config
from ..util import jsonio, log
from . import energy as energy_mod
from . import hooks as hooks_mod
from . import score as score_mod


HOOK_TEXT_SCORE = 0.35        # a sentence scoring this reads like a hook
MAX_BREATH_SECONDS = 1.2      # a longer silence means "different moment", do not bridge it
MAX_PAD_SECONDS = 2.5         # most room tone we will add to reach the floor


def load_transcript(source) -> list | None:
    """A transcript can be a path, a parsed dict, or already `Word` objects."""
    if source is None:
        return None
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            log.warn("transcript not found, selecting on audio alone", path=str(path))
            return None
        data = jsonio.load(path, None)
    elif isinstance(source, dict):
        data = source
    else:
        return list(source)
    if not data:
        return None
    from ..asr.base import Word

    return [Word.from_dict(w) if isinstance(w, dict) else w for w in (data.get("words") or [])]


def find_transcript(media: Path, campaign: str | None = None) -> Path | None:
    """Where a transcript for `media` would be, wherever it was put."""
    candidates = [
        media.with_suffix(".transcript.json"),
        config.WORK / media.stem / "transcript.json",
    ]
    if campaign:
        candidates.append(config.WORK / campaign / "transcripts" / f"{media.stem}.json")
    for path in candidates:
        if path.exists():
            return path
    return None


def select_candidates(media: str | Path, *, transcript=None, platform: str = "tiktok",
                      min_seconds: float | None = None, max_seconds: float | None = None,
                      top: int = 5, campaign: str | None = None,
                      save: bool = True, work_dir: Path | None = None,
                      rules: dict | None = None, keep_rejected: bool = False) -> dict:
    """Score one recording and return its candidate clips.

    `rules` (see clipper/guideline.py) is the campaign brief: it sets the clip
    length window, drops moments that break a campaign rule, lifts the ones that
    fit, and records a compliance block on every candidate. Without a rule file
    the platform's own window is used and only the generic hook rules apply.
    """
    from .. import guideline as guideline_mod

    media = Path(media)
    if not media.exists():
        raise FileNotFoundError(media)
    rules = rules if rules is not None else {}
    lo, hi = score_mod.TARGET_LENGTHS.get(platform, score_mod.TARGET_LENGTHS["tiktok"])
    if rules.get("path"):
        lo, hi = guideline_mod.clip_length(rules)
    min_seconds = float(min_seconds if min_seconds is not None else lo)
    max_seconds = float(max_seconds if max_seconds is not None else hi)
    if max_seconds < min_seconds:
        raise ValueError("max_seconds must be >= min_seconds")

    try:
        curve = energy_mod.energy_curve(media)
    except Exception as exc:                    # no audio track at all
        log.warn("no audio to select from", file=media.name, err=type(exc).__name__)
        return {
            "version": 1, "campaign": campaign,
            "source": {"file": str(media), "name": media.name, "duration": 0.0},
            "mode": "no-audio", "note": "the file has no audio track to analyse",
            "target": {"platform": platform, "min_seconds": min_seconds, "max_seconds": max_seconds},
            "analysis": {"baseline_db": None, "peak_db": None, "hot_spots": [],
                         "sentences": 0, "words": 0},
            "candidates": [],
        }
    spots = energy_mod.hot_spots(curve)

    words = load_transcript(transcript)
    if words is None and transcript is None:
        found = find_transcript(media, campaign)
        if found:
            words = load_transcript(found)
            if words:
                log.info("using transcript", path=str(found))

    units = hooks_mod.sentence_units(words) if words else []
    if units:
        scored = score_mod.score_units(units, curve, spots)
        candidates = score_mod.build_candidates(scored, curve, min_seconds=min_seconds,
                                                max_seconds=max_seconds, top=top, spots=spots)
        mode = "transcript+audio"
    else:
        scored = []
        candidates = score_mod.build_from_energy(curve, spots, min_seconds=min_seconds,
                                                 max_seconds=max_seconds, top=top)
        mode = "audio-only"

    # the campaign's rules decide what survives, and say so per candidate
    effective = config.deep_merge(rules, {"clip": {"min_seconds": min_seconds,
                                                   "max_seconds": max_seconds}})
    kept: list[dict] = []
    rejected: list[dict] = []
    for window in candidates:
        window, hook_at = _hook_anchor(window, words or [], effective, min_seconds)
        window = _grow_to_floor(window, words or [], effective, min_seconds,
                                curve["duration"])
        verdict = guideline_mod.text_verdict(window.get("text"), effective)
        if verdict["boost"]:
            window["score"] = round(min(1.0, window["score"] + 0.04 * len(verdict["boost"])), 3)
            window["reasons"] = window["reasons"] + verdict["reasons"][:len(verdict["boost"])]
        window["compliance"] = guideline_mod.compliance(window, effective, hook_at=hook_at)
        if verdict["reject"] and not keep_rejected:
            window["rejected_for"] = verdict["banned"]
            window["reasons"] = window["reasons"] + verdict["reasons"]
            rejected.append(window)
            log.debug("dropped a moment that breaks the campaign rules",
                      at=f"{window['start']:.1f}s", why=verdict["banned"][0])
            continue
        kept.append(window)
    candidates = kept

    payload = {
        "version": 1,
        "campaign": campaign,
        "source": {"file": str(media), "name": media.name, "duration": curve["duration"]},
        "mode": mode,
        "target": {"platform": platform, "min_seconds": min_seconds, "max_seconds": max_seconds},
        "analysis": {
            "baseline_db": round(curve["baseline_db"], 1),
            "peak_db": round(curve["peak_db"], 1),
            "hot_spots": spots,
            "sentences": len(units),
            "words": len(words) if words else 0,
        },
        "candidates": candidates,
        "rejected": rejected,
        "guideline": {"path": rules.get("path"), "campaign": rules.get("campaign"),
                      "clip": {"min_seconds": min_seconds, "max_seconds": max_seconds}},
    }
    if save:
        out_dir = Path(work_dir) if work_dir else (config.WORK / (campaign or media.stem))
        payload["written"] = str(write_candidates(out_dir, media, payload))
    return payload


def _hook_anchor(window: dict, words: list, rules: dict, min_seconds: float) -> tuple[dict, float | None]:
    """Move the start so the campaign's hook window is respected.

    A clip can grow a long lead-in while the window is being built, which pushes
    the sentence that makes people stop scrolling past the campaign's "first few
    seconds" rule. Trimming the lead-in (never below the length floor) fixes that
    without touching the moment itself.
    """
    from .. import guideline as guideline_mod

    if not words:
        return window, None
    best = _best_hook(words, window["start"], window["end"])
    if best is None:
        return window, None
    within = float((rules.get("hook") or {}).get("within_seconds") or 5.0)
    hook_at = round(float(best["start"]) - window["start"], 3)
    if hook_at <= within:
        return window, hook_at
    new_start = max(window["start"], round(float(best["start"]) - 0.6, 3))
    if window["end"] - new_start < score_mod.length_floor(min_seconds):
        return window, hook_at                      # cannot trim, so report it honestly
    trimmed = {**window, "start": round(new_start, 3),
               "duration": round(window["end"] - new_start, 3),
               "reasons": window["reasons"] + [
                   f"lead-in trimmed so the hook lands {within:.0f}s in, not {hook_at:.1f}s"]}
    log.debug("trimmed a lead-in to respect the campaign hook window",
              was=f"{window['start']:.1f}s", now=f"{new_start:.1f}s")
    return trimmed, round(float(best["start"]) - new_start, 3)


def _best_hook(words: list, start: float, end: float) -> dict | None:
    """The earliest sentence inside the window that reads like a scroll-stopper."""
    inside = [w for w in words
              if float(w.start) >= start - 0.01 and float(w.end) <= end + 0.01]
    if not inside:
        return None
    best = None
    for unit in hooks_mod.sentence_units(inside):
        score, _ = hooks_mod.score_text(unit["text"])
        if score >= HOOK_TEXT_SCORE and (best is None or unit["start"] < best["start"]):
            best = unit
    return best


def _text_between(words: list, start: float, end: float) -> str:
    return " ".join(str(w.text) for w in words
                    if float(w.end) > start + 0.01 and float(w.start) < end - 0.01)


def _grow_to_floor(window: dict, words: list, rules: dict, min_seconds: float,
                   source_duration: float | None) -> dict:
    """Grow a moment that is a breath short of the campaign's minimum.

    A window can land just under the floor - 18.5s against a 20s minimum, say -
    because the moment ends there, not because it is bad. Dropping it throws
    away the best material in the file, so instead: borrow the following
    sentence, then the preceding one, and only when speech cannot close the gap
    pad with the room tone that was there anyway. The pad is capped
    (`MAX_PAD_SECONDS`) so a 9s window is still reported as too short rather
    than faked into a long one, and every step refuses to buy length with an
    off-campaign topic.
    """
    from .. import guideline as guideline_mod

    floor = float(min_seconds)          # the campaign's own minimum, not the builder's soft floor
    start, end = float(window["start"]), float(window["end"])
    if end - start >= floor - 0.05 or not words:
        return window
    source_end = float(source_duration or end)
    within = float((rules.get("hook") or {}).get("within_seconds") or 5.0)

    # 1. the following sentence, if it stays on campaign
    for word in words:
        if float(word.start) >= min(start + floor, source_end):
            break
        if float(word.end) <= end + 0.01:
            continue
        if guideline_mod.text_verdict(_text_between(words, start, float(word.end)), rules)["reject"]:
            break
        end = round(float(word.end), 3)

    # 2. the sentence before it, as long as the hook keeps landing in time
    while end - start < floor - 0.05:
        earlier = [w for w in words if float(w.end) <= start + 0.01]
        if not earlier:
            break
        word = earlier[-1]
        if start - float(word.end) > MAX_BREATH_SECONDS:      # a gap that means "new moment"
            break
        new_start = round(float(word.start) - 0.25, 3)
        if new_start >= start - 0.01:
            break
        if guideline_mod.text_verdict(_text_between(words, new_start, end), rules)["reject"]:
            break
        hook = _best_hook(words, new_start, end)
        if hook is not None and float(hook["start"]) - new_start > within:
            break
        start = new_start

    # 3. room tone, capped - never fake a short moment into a long one
    short_by = floor - (end - start)
    if 0 < short_by <= MAX_PAD_SECONDS:
        end = round(min(start + floor, source_end), 3)

    if end - start < floor - 0.05:
        return window                                        # still short: say so, do not hide it

    grown = {**window, "start": start, "end": end,
             "duration": round(end - start, 3),
             "text": _text_between(words, start, end) or window.get("text"),
             "reasons": window["reasons"] + [
                 f"grown from {float(window['duration']):.1f}s to {end - start:.1f}s "
                 f"to meet the campaign's {min_seconds:.0f}s minimum"]}
    log.debug("grew a moment up to the campaign floor",
              was=f"{window['start']:.1f}-{window['end']:.1f}s",
              now=f"{start:.1f}-{end:.1f}s")
    return grown


def write_candidates(out_dir: Path, media: Path, payload: dict) -> Path:
    """`work/<campaign>/candidates/<stem>.json` + a readable report."""
    folder = Path(out_dir) / "candidates"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{media.stem}.json"
    jsonio.save(path, payload)
    report = folder / f"{media.stem}.report.md"
    report.write_text(render_report(payload), encoding="utf-8")
    log.info("candidates written", path=str(path), count=len(payload["candidates"]),
             mode=payload["mode"])
    return path


def render_report(payload: dict) -> str:
    lines = [
        f"# candidates - {payload['source']['name']}",
        "",
        f"- mode: `{payload['mode']}`",
        f"- duration: {payload['source']['duration']:.1f}s, "
        f"baseline {payload['analysis']['baseline_db']} dB, peak {payload['analysis']['peak_db']} dB",
        f"- target: {payload['target']['min_seconds']:.0f}-{payload['target']['max_seconds']:.0f}s "
        f"({payload['target']['platform']})",
        f"- loud stretches: {len(payload['analysis']['hot_spots'])}",
        "",
    ]
    for c in payload["candidates"]:
        lines += [
            f"## {c['id']} {fmt_time(c['start'])} - {fmt_time(c['end'])} "
            f"({c['duration']:.1f}s, score {c['score']:.2f})",
            "",
        ]
        if c.get("text"):
            lines += [f"> {c['text']}", ""]
        for reason in c.get("reasons", []):
            lines.append(f"- {reason}")
        compliance = c.get("compliance") or {}
        for check in compliance.get("checks", []):
            lines.append(f"- {'PASS' if check['pass'] else 'FAIL'} {check['check']}: {check['detail']}")
        for note in compliance.get("notes", []):
            lines.append(f"- note: {note}")
        lines.append("")
    rejected = payload.get("rejected") or []
    if rejected:
        lines += ["## dropped by the campaign rules", ""]
        for c in rejected:
            lines += [f"- {fmt_time(c['start'])} - {fmt_time(c['end'])} "
                      f"({c['duration']:.1f}s): " + "; ".join(c.get("rejected_for", [])), ""]
    guidance = payload.get("guideline") or {}
    if guidance.get("path"):
        lines += ["", f"_rules from {guidance['path']}_"]
    return "\n".join(lines)


def fmt_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:04.1f}"


def select_campaign(campaign: str, **kwargs) -> list[dict]:
    """Run selection over every raw file of a campaign, with its rules if it has any."""
    from .. import guideline as guideline_mod

    kwargs.setdefault("rules", guideline_mod.load(campaign))
    from ..ingest.scan import scan_campaign

    manifest = scan_campaign(campaign)
    medias = [r for r in manifest.get("raw", [])]
    if not medias:
        raise RuntimeError(f"campaign '{campaign}' has no files in raw/")
    results = []
    for entry in medias:
        media = Path(entry["path"]) if isinstance(entry, dict) else Path(entry)
        if media.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
            continue
        log.step("select", file=media.name)
        results.append(select_candidates(media, campaign=campaign, **kwargs))
    if not results:
        raise RuntimeError(f"campaign '{campaign}' has no video files in raw/")
    return results


def best_overall(results: list[dict], top: int = 5) -> list[dict]:
    """Flatten several files' candidates, keeping score order."""
    flat = []
    for payload in results:
        for c in payload["candidates"]:
            flat.append({**c, "file": payload["source"]["name"],
                         "duration_total": payload["source"]["duration"]})
    flat.sort(key=lambda c: -c["score"])
    return flat[:top]


def rounded_seconds(value: float) -> float:
    return math.floor(value * 1000) / 1000.0
