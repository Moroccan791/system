#!/usr/bin/env python3
"""Authoring prep: pick the hook window and tighten dead air BEFORE
graphics are authored (Part 4). Pure functions over transcript words.

Hook score: a window opening on a number/percent, a question, or a
strong-claim word beats a lead-in every time. Dead pauses over the
threshold are compressed to a breath; word times are remapped so the
timeline authored afterwards is already tight.

Usage: python motion/prep.py <transcript.json> [--window 28] [--max-pause 0.30] [--keep 0.18]
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


def tighten(words: list[dict], max_pause: float = 0.30,
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
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript", help="word-level transcript JSON")
    ap.add_argument("--window", type=float, default=28.0,
                    help="suggested source-window duration (default: 28s)")
    ap.add_argument("--max-pause", type=float, default=0.30,
                    help="compress pauses longer than this (default: 0.30s)")
    ap.add_argument("--keep", type=float, default=0.18,
                    help="retain this much breath at each tightened pause (default: 0.18s)")
    args = ap.parse_args()
    data = json.loads(Path(args.transcript).read_text())
    words = data.get("words", []) if isinstance(data, dict) else data
    if not words:
        ap.error("transcript contains no words")
    tight, removed = tighten(words, max_pause=args.max_pause, keep=args.keep)
    print(json.dumps({"hook": pick_hook(words, args.window),
                      "removed": removed,
                      "removed_total_s": round(sum(r["dur"] for r in removed), 2),
                      "tightened_word_count": len(tight),
                      "window_s": args.window,
                      "max_pause_s": args.max_pause,
                      "kept_breath_s": args.keep}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
