#!/usr/bin/env python3
"""Print the episode transcript as timecoded sentences, so the beats
can be written from the real words.

    python scripts/whop/dump_transcript.py --from 1800 --to 2400
    python scripts/whop/dump_transcript.py --all
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

EPISODE = Path("/home/user/system/work/street/asr/episode_transcript.json")


def sentences(words, gap=0.25, max_words=16):
    out, cur = [], []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] >= gap or len(cur) >= max_words):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", default=str(EPISODE))
    ap.add_argument("--from", dest="a", type=float, default=0.0)
    ap.add_argument("--to", dest="b", type=float, default=1e9)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    data = json.loads(Path(a.transcript).read_text())
    words = [w for w in data["words"] if a.a <= w["start"] <= a.b]
    print(f"{len(words)} words, {words[0]['start']:.1f}s - {words[-1]['end']:.1f}s\n")
    for i, s in enumerate(sentences(words)):
        txt = " ".join(w["text"] for w in s)
        print(f"[{i:3d}] {s[0]['start']:8.2f} {txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
