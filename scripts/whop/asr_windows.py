#!/usr/bin/env python3
"""Transcribe just the picked windows of an episode, with source times.

    .venv/bin/python scripts/whop/asr_windows.py \
        --source work/two_bears/full.mp4 \
        --picks campaigns/two_bears_ep344/picks.json \
        --out work/two_bears/asr/windows.json

The episode is 66 minutes; the four posts cover 132 seconds of it. Transcribing
the whole thing to caption two minutes is a waste of the one expensive step in
the pipeline, so each pick's span is cut out (with a little air either side, so
the caption matcher has neighbouring words to anchor against), transcribed, and
its word times shifted back onto the source clock. The result is a normal
`{"words": [...]}` transcript - the same shape `tight_base.py` and
`build_whop_clip.py` already read - covering every picked window.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAD = 1.5        # seconds of context either side of a pick


def ffmpeg() -> str:
    return subprocess.run([sys.executable, "-c",
                           "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="work/two_bears/full.mp4")
    ap.add_argument("--picks", default="campaigns/two_bears_ep344/picks.json")
    ap.add_argument("--out", default="work/two_bears/asr/windows.json")
    args = ap.parse_args()

    source = ROOT / args.source
    picks = json.loads((ROOT / args.picks).read_text())
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg()

    words: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        for pick in picks:
            slug = pick["slug"]
            t0 = max(0.0, float(pick["start"]) - PAD)
            t1 = float(pick["end"]) + PAD
            dur = t1 - t0
            wav = tmpd / f"{slug}.wav"
            chk = tmpd / f"{slug}.json"
            subprocess.run([ff, "-y", "-v", "error", "-ss", f"{t0:.3f}",
                            "-t", f"{dur:.3f}", "-i", str(source),
                            "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                            str(wav)], check=True)
            done = subprocess.run([sys.executable, "-m", "clipper", "transcribe",
                                   str(wav), "--asr", "moonshine", "--out", str(chk)],
                                  capture_output=True, text=True, cwd=str(ROOT))
            if done.returncode != 0:
                print(done.stdout[-2000:], done.stderr[-2000:], file=sys.stderr)
                return done.returncode
            got = json.loads(chk.read_text())
            got = got.get("words", got) if isinstance(got, dict) else got
            for w in got:
                words.append({"text": w["text"],
                              "start": round(float(w["start"]) + t0, 3),
                              "end": round(float(w["end"]) + t0, 3)})
            print(f"{slug}: {len(got)} words  {t0:.1f}-{t1:.1f}s", flush=True)

    words.sort(key=lambda w: w["start"])
    out.write_text(json.dumps({"words": words}, indent=1) + "\n")
    print(f"{out}: {len(words)} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
