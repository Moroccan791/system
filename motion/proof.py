#!/usr/bin/env python3
"""Proof assets -> proof timeline items (the receipt layer).

    python motion/proof.py <transcript.json> <proof.json> <out.json>

The highest-level edits never let a claim float: the moment a result
is spoken, the receipt is on screen and the spoken clause highlights
inside it. This module is the asset side of that grammar. A proof
asset is data the campaign supplies (never invented by the editor):

    [{"name": "Sarah Johnson", "role": "Student",
      "match": "posting consistently",
      "text": "I've been posting consistently on Instagram for
               36 days straight, with 936 followers",
      "hot": ["36 days straight", "936 followers"],
      "value": 7000, "prefix": "$", "valueLabel": "Automated sales",
      "src": "campaigns/x/proof/sarah.png",          (optional)
      "hotBox": [0.08, 0.55, 0.84, 0.18], "accent2": "#38E1FF"}]

`match` (or the first hot phrase) is located in the transcript; the
card lands 0.15 s before it is spoken, every hot phrase highlights at
its own spoken moment, and a supplied value counts up inside the
card. Unmatched assets are reported, never silently dropped. Used
standalone it writes {"items": [...]}; motion/decide.py --proof
folds the same items into a draft timeline (replacing the poster
stacks they overlap - the card IS the caption for that beat).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def norm(tok: str) -> str:
    return re.sub(r"[^a-z0-9'$%]", "", str(tok).lower())


def _find(words: list[dict], phrase: str, start: int = 0):
    """Index of the word where `phrase` starts in `words`, or None."""
    want = [norm(t) for t in phrase.split() if norm(t)]
    if not want:
        return None
    toks = [norm(w["text"]) for w in words]
    for i in range(start, len(toks) - len(want) + 1):
        if toks[i:i + len(want)] == want:
            return i
    return None


def _segments(text: str, hot: list[str]) -> list[tuple[str, bool]]:
    """Split card text into (segment, is_hot) in reading order."""
    if not text:
        return []
    spans = []
    low = text.lower()
    for h in hot or []:
        j = low.find(h.lower())
        if j >= 0:
            spans.append((j, j + len(h)))
    spans.sort()
    out, pos = [], 0
    for a, b in spans:
        if a < pos:
            continue
        if a > pos:
            out.append((text[pos:a].strip(), False))
        out.append((text[a:b], True))
        pos = b
    if pos < len(text):
        out.append((text[pos:].strip(), False))
    return [(t, h) for t, h in out if t]


def build_proof_items(words: list[dict], assets: list[dict]):
    """(items, notes): one proof item per asset found in the speech."""
    items, notes = [], []
    for a in assets:
        anchor = a.get("match") or (a.get("hot") or [None])[0] or a.get("text", "")[:40]
        i = _find(words, anchor) if anchor else None
        if i is None:
            notes.append(f"proof {a.get('name') or a.get('src') or '?'}: "
                         f"anchor {anchor!r} not spoken - skipped")
            continue
        at = max(0.0, float(words[i]["start"]) - 0.15)
        phrases, cur = [], at
        for text, hot in _segments(a.get("text") or anchor, a.get("hot") or []):
            j = _find(words, text, i)
            pat = float(words[j]["start"]) if j is not None else cur + 0.55
            phrases.append({"text": text, "at": round(pat, 3),
                            **({"hot": True} if hot else {})})
            cur = pat
        if not phrases:
            phrases = [{"text": anchor, "at": round(at, 3), "hot": True}]
        until = max(p["at"] for p in phrases) + 1.7
        if a.get("value") is not None:
            until = max(until, at + float(a.get("countDur") or 0.9) + 1.1)
        item = {"type": "proof", "at": round(at, 3),
                "until": round(min(until, at + 6.5), 3),
                "phrases": phrases}
        for k in ("name", "role"):
            if a.get(k):
                item["title" if k == "name" else "sub"] = a[k]
        for k in ("src", "hotBox", "hotAt", "value", "prefix", "suffix",
                  "decimals", "countDur", "valueLabel", "accent2", "zone"):
            if a.get(k) is not None:
                item[k] = a[k]
        if a.get("src") and a.get("hotBox") and item.get("hotAt") is None:
            # the box lands when the first hot phrase is spoken
            hot = next((p for p in phrases if p.get("hot")), None)
            if hot:
                item["hotAt"] = hot["at"]
        items.append(item)
        notes.append(f"proof @{at:6.2f}  {a.get('name') or a.get('src') or ''} "
                     f"({len(phrases)} phrases, "
                     f"{sum(1 for p in phrases if p.get('hot'))} hot)")
    return items, notes


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    tr = json.loads(Path(sys.argv[1]).read_text())
    words = tr.get("words", tr if isinstance(tr, list) else [])
    assets = json.loads(Path(sys.argv[2]).read_text())
    if isinstance(assets, dict):
        assets = assets.get("proof") or assets.get("assets") or []
    items, notes = build_proof_items(words, assets)
    Path(sys.argv[3]).write_text(json.dumps({"items": items}, indent=2))
    for n in notes:
        print(f"  {n}")
    print(f"proof: {len(items)} items -> {sys.argv[3]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
