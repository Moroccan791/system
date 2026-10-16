#!/usr/bin/env python3
"""Authoring prep: pick the hook window and tighten dead air BEFORE
graphics are authored (Part 4). Pure functions over transcript words.

Hook score: a window opening on a number/percent, a question, or a
strong-claim word beats a lead-in every time. Dead pauses over the
threshold are compressed to a breath; word times are remapped so the
timeline authored afterwards is already tight.

Usage: python motion/prep.py <transcript.json> [--window 28]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STRONG = set("never always crazy secret nobody everybody stop wait "
             "wrong best worst first only free win lose hack truth".split())
NUM = re.compile(r"\d|percent|%|dollars?|bucks", re.I)


def _sentences(words: list[dict]) -> list[list[dict]]:
    out, cur = [], []
    for w in words:
        cur.append(w)
        if str(w["text"]).strip().endswith((".", "?", "!")):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def pick_hook(words: list[dict], window: float = 28.0) -> dict:
    """Best-scoring sentence to open on; ties break to the earliest."""
    best = {"score": -1, "start": words[0]["start"]}
    for sent in _sentences(words):
        start = sent[0]["start"]
        if start + 4 > words[-1]["end"]:
            continue
        text = " ".join(str(w["text"]) for w in sent)
        score = 0.0
        if NUM.search(text):
            score += 3
        if text.strip().endswith("?"):
            score += 2
        score += sum(1 for w in sent
                     if str(w["text"]).lower().strip(".,!?") in STRONG)
        score += max(0.0, 1.5 - start / 120.0)  # earlier beats later
        if score > best["score"]:
            best = {"score": round(score, 2), "start": start,
                    "end": round(start + window, 2),
                    "opener": text[:90]}
    return best


def tighten(words: list[dict], max_pause: float = 0.55,
            keep: float = 0.18) -> tuple[list[dict], list[dict]]:
    """Compress dead air; returns (remapped words, removed intervals)."""
    removed, shift, out = [], 0.0, []
    prev_end = None
    for w in words:
        if prev_end is not None:
            gap = w["start"] - prev_end
            if gap > max_pause:
                removed.append({"from": round(prev_end + keep, 3),
                                "to": round(w["start"], 3),
                                "dur": round(gap - keep, 3)})
                shift += gap - keep
        out.append({**w, "start": round(w["start"] - shift, 3),
                    "end": round(w["end"] - shift, 3)})
        prev_end = w["end"]
    return out, removed


def main() -> int:
    words = json.loads(Path(sys.argv[1]).read_text())
    if isinstance(words, dict):
        words = words.get("words") or []
    window = float(sys.argv[sys.argv.index("--window") + 1]) \
        if "--window" in sys.argv else 28.0
    tight, removed = tighten(words)
    print(json.dumps({"hook": pick_hook(words, window),
                      "removed": removed,
                      "removed_total_s": round(
                          sum(r["dur"] for r in removed), 2)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
