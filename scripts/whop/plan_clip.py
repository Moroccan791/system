#!/usr/bin/env python3
"""Turn a chosen source window into a build spec: silence drops, per-shot
framing, splits.  Used with build_whop_clip.py.

    python scripts/whop/plan_clip.py --start 2759.4 --end 2790.2 --post post2

Prints the spec fields (drops / crops / splits) and a plan skeleton with
the transcript sentences inside the window, so the beats can be written
from the real words.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/user/system")
SRC = ROOT / "work" / "street" / "raw" / "street_full.mp4"
EPISODE = ROOT / "work" / "street" / "asr" / "episode_transcript.json"

# the speaker sits right of centre in this interview setup
MCU = [790, 90, 480, 854]
MCU_ALT = [1080, 90, 480, 854]
TWO_SHOT = [560, 90, 760, 854]


def ffmpeg() -> str:
    return subprocess.run([str(ROOT / ".venv/bin/python"), "-c",
                           "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
                          capture_output=True, text=True).stdout.strip()


def silences(ff, start, end, thresh=-32, min_dur=0.30):
    """Acoustic silences inside the window (absolute source times)."""
    r = subprocess.run([ff, "-v", "info", "-ss", str(start), "-t", str(end - start),
                        "-i", str(SRC), "-af",
                        f"silencedetect=noise={thresh}dB:d={min_dur}",
                        "-f", "null", "-"], capture_output=True, text=True)
    out = []
    for m in re.finditer(r"silence_start: ([\d.]+)\s*\|.*?silence_end: ([\d.]+)", r.stderr):
        s = float(m.group(1)) + start
        e = float(m.group(2)) + start
        if e - s >= min_dur:
            out.append([round(s, 2), round(e, 2)])
    return out


def shots(ff, start, end, thresh=0.30):
    """Shot changes inside the window (absolute source times)."""
    r = subprocess.run([ff, "-v", "info", "-ss", str(start), "-t", str(end - start),
                        "-i", str(SRC), "-vf",
                        f"select='gt(scene,{thresh})',showinfo",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    out = []
    for m in re.finditer(r"pts_time:([\d.]+)", r.stderr):
        out.append(round(float(m.group(1)) + start, 2))
    return out


def sentences(words, gap=0.32):
    out, cur = [], []
    for w in words:
        if cur and w["start"] - cur[-1]["end"] >= gap:
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--post", default="post2")
    ap.add_argument("--no-drops", action="store_true")
    a = ap.parse_args()

    ff = ffmpeg()
    cuts = shots(ff, a.start, a.end)
    drops = [] if a.no_drops else silences(ff, a.start, a.end)

    data = json.loads(EPISODE.read_text())
    words = [w for w in data["words"]
             if w["start"] >= a.start - 0.05 and w["end"] <= a.end + 0.05]
    sents = sentences(words)

    print(f"window {a.start}-{a.end} ({round(a.end - a.start, 1)}s)")
    print("shot cuts:", cuts)
    print("silences :", drops)
    print("\nsentences in the window:")
    for s in sents:
        txt = " ".join(w["text"] for w in s)
        print(f"  {s[0]['start']:8.2f}  {txt}")
    spec = {
        "post": a.post,
        "span": [a.start, a.end],
        "drops": drops,
        "shot_cuts": cuts,
    }
    out = ROOT / "work" / "street" / a.post
    out.mkdir(parents=True, exist_ok=True)
    (out / "window.json").write_text(json.dumps(spec, indent=2))
    print("\nwrote", out / "window.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
