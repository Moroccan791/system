#!/usr/bin/env python3
"""Transcribe a long episode in windows, saving as it goes.

A 66-minute episode broke the single-pass approach: the decoded audio plus the
model plus 2,300 words is more than the sandbox will hold, and the process was
killed with nothing saved. Windows bound the memory and make the job resumable:
each window is written to disk before the next one starts, so a kill costs one
window, not the episode.

    transcribe_long.py work/two_bears/full.mp4 --out work/two_bears/asr/episode.json
"""
from __future__ import annotations

import argparse
import gc
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

#: 60s, measured: a 60s window transcribes in ~14s and holds the process at
#: ~1.4GB (the model dominates). At 300s the box - 3.9GB total - was killed
#: twice. The window is not about audio size, it is about the provider's own
#: footprint, so it stays small and the model is reloaded per window.
WINDOW = 60.0
OVERLAP = 1.0           # keeps a word from being cut in half at the boundary


def duration(path: Path) -> float:
    from clipper.ffmpeg import decode_audio
    import wave  # noqa: F401
    ff = subprocess.run([sys.executable, "-c",
                         "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
                        capture_output=True, text=True).stdout.strip()
    res = subprocess.run([ff, "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True, errors="ignore")
    for line in res.stderr.splitlines():
        if line.strip().startswith("Duration:"):
            hms = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = hms.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def wav_window(src: Path, start: float, length: float, out: Path) -> Path:
    ff = subprocess.run([sys.executable, "-c",
                         "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
                        capture_output=True, text=True).stdout.strip()
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(src),
                    "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out)],
                   check=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--window", type=float, default=WINDOW)
    args = ap.parse_args()

    import wave
    import numpy as np
    from clipper.asr.moonshine import MoonshineProvider

    src = Path(args.source)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    total = duration(src)
    done = 0.0
    words: list[dict] = []

    def save() -> None:
        out.write_text(json.dumps({"words": words, "source": str(src),
                                   "duration": round(total, 2),
                                   "transcribed_to": round(done, 2)}))

    tmp = out.with_suffix(".wav")
    i = 0
    while done < total:
        length = min(args.window + OVERLAP, total - done)
        wav_window(src, done, length, tmp)
        with wave.open(str(tmp)) as w:
            raw = w.readframes(w.getnframes())
        audio = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
        # fresh provider per window: its buffers are what grows, and loading
        # the model costs ~1s against a 14s window
        tr = MoonshineProvider(chunk_seconds=6.0,
                               isolate_chunks=False).transcribe(audio, 16000)
        for w_ in tr.words:
            start = done + float(w_.start)
            if start < done - 0.01:          # from the overlap
                continue
            words.append({"text": w_.text, "start": round(start, 3),
                          "end": round(done + float(w_.end), 3)})
        del tr, audio, raw
        gc.collect()
        done += args.window
        i += 1
        save()
        print(f"window {i} done, {done:.0f}/{total:.0f}s, {len(words)} words", flush=True)
    tmp.unlink(missing_ok=True)
    save()
    print(f"TRANSCRIBE_DONE words={len(words)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
