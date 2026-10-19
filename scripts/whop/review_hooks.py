#!/usr/bin/env python3
"""Shortlist verbatim spoken openings for human review; never rewrites speech.

Usage: python scripts/whop/review_hooks.py path/to/word-transcript.json [--top 8]

This ranks the actual first sentences of candidate sections for review. It is
not a retention predictor and does not authorize a new hook or edit. For new
campaign material, inspect the full episode, choose a real opening, and retain
the complete thought and its genuine closing line.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.whop.pick_clips import score_open, sentences  # noqa: E402


def shortlist(words: list[dict], limit: int = 8) -> list[dict]:
    candidates = []
    for index, sentence in enumerate(sentences(words)):
        score, reasons = score_open(sentence)
        if score <= 0:
            continue
        candidates.append({
            "start": round(float(sentence[0]["start"]), 2),
            "end": round(float(sentence[-1]["end"]), 2),
            "verbatim": " ".join(str(w["text"]) for w in sentence),
            "score": round(score, 2),
            "reasons": reasons,
            "sentence_index": index,
        })
    return sorted(candidates, key=lambda item: (-item["score"], item["start"]))[:limit]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("transcript", help="word-level transcript JSON")
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args()
    data = json.loads(Path(args.transcript).read_text())
    words = data.get("words", []) if isinstance(data, dict) else data
    if not words:
        ap.error("transcript contains no words")
    for rank, item in enumerate(shortlist(words, args.top), 1):
        print(f"{rank}. {item['start']:.2f}-{item['end']:.2f}s "
              f"score={item['score']:.2f} [{', '.join(item['reasons'])}]")
        print(f"   VERBATIM: {item['verbatim']}")
    print("\nHeuristic shortlist only—not a retention prediction. Review the full "
          "episode, keep the line verbatim, and preserve the thought's real close.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
