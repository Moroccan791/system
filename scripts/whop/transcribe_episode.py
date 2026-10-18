#!/usr/bin/env python3
"""Transcribe the whole episode with word timings, in chunks, and merge.

    python scripts/whop/transcribe_episode.py

Output: work/street/asr/episode_transcript.json
  { "words": [ {text,start,end,...}, ... ] }  with absolute source times
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/user/system")
ASR = ROOT / "work" / "street" / "asr"
WAV = ASR / "episode16k.wav"
CHUNK = 600.0            # seconds per chunk
PY = str(ROOT / ".venv" / "bin" / "python")


def ffmpeg() -> str:
    out = subprocess.run([PY, "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
                         capture_output=True, text=True).stdout.strip()
    return out


def main() -> int:
    import wave
    ASR.mkdir(parents=True, exist_ok=True)
    if not WAV.exists():
        print("missing episode wav - extract it first", file=sys.stderr)
        return 1
    with wave.open(str(WAV)) as w:
        total = w.getnframes() / w.getframerate()
    n = int(total // CHUNK) + 1
    ff = ffmpeg()
    words = []
    for i in range(n):
        start = i * CHUNK
        cw = ASR / f"chunk_{i:02d}.wav"
        cj = ASR / f"chunk_{i:02d}.json"
        if not cw.exists():
            subprocess.run([ff, "-y", "-v", "error", "-ss", str(start), "-t", str(CHUNK),
                            "-i", str(WAV), "-ac", "1", "-ar", "16000",
                            "-c:a", "pcm_s16le", str(cw)], check=True)
        if not cj.exists():
            print(f"[{i+1}/{n}] transcribing {start:.0f}s+", flush=True)
            r = subprocess.run([PY, "-m", "clipper", "transcribe", str(cw),
                                "--asr", "moonshine", "--out", str(cj)],
                               capture_output=True, text=True)
            if r.returncode != 0:
                print("chunk failed", i, r.stderr[-500:], flush=True)
                continue
        try:
            d = json.loads(cj.read_text())
        except Exception:
            print("bad json", cj, flush=True)
            continue
        cw_words = d.get("words") or []
        for w in cw_words:
            w["start"] = round(w["start"] + start, 3)
            w["end"] = round(w["end"] + start, 3)
            w["chunk"] = i
        words.extend(cw_words)
        print(f"  chunk {i}: {len(cw_words)} words (total {len(words)})", flush=True)
    words.sort(key=lambda w: w["start"])
    out = ASR / "episode_transcript.json"
    out.write_text(json.dumps({
        "text": " ".join(w["text"] for w in words),
        "duration": total,
        "provider": "moonshine",
        "words": words,
    }, indent=1))
    print("wrote", out, len(words), "words over", round(total, 1), "s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
