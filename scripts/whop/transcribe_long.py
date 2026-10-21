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
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

#: 60s windows, and **one process per window**. Measured: a fresh provider in
#: the same process is not enough - window 1 succeeded, window 2 was killed by
#: the OOM killer at 3.9GB, because the native provider's memory is not
#: returned when the object is dropped. A child process per window makes the
#: release unconditional: the OS reclaims everything on exit.
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


def transcribe_window(src: Path, start: float, length: float, window: float) -> list[dict]:
    """One window, in this process. Called by a short-lived child."""
    import wave
    import numpy as np
    from clipper.asr.moonshine import MoonshineProvider

    wav = Path("/tmp") / f"tb_window_{int(start)}.wav"
    wav_window(src, start, length, wav)
    try:
        with wave.open(str(wav)) as w:
            raw = w.readframes(w.getnframes())
        audio = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
        tr = MoonshineProvider(chunk_seconds=6.0, isolate_chunks=False).transcribe(audio, 16000)
        out = []
        for item in tr.words:
            t0 = start + float(item.start)
            if t0 < start - 0.01:
                continue                      # from the overlap carry-in
            out.append({"text": item.text, "start": round(t0, 3),
                        "end": round(start + float(item.end), 3)})
        return out
    finally:
        wav.unlink(missing_ok=True)


def _load(out: Path) -> dict:
    if out.exists():
        try:
            return json.loads(out.read_text())
        except json.JSONDecodeError:
            pass
    return {"words": [], "transcribed_to": 0.0}


def _store(out: Path, data: dict) -> None:
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(out)                      # never leave a half-written transcript


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--window", type=float, default=WINDOW)
    ap.add_argument("--one", type=float, default=None,
                    help="internal: transcribe just this window and exit")
    args = ap.parse_args()

    src = Path(args.source)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    total = duration(src)

    if args.one is not None:
        start = args.one
        length = min(args.window + OVERLAP, total - start)
        if length <= 1:
            return 0
        words = transcribe_window(src, start, length, args.window)
        data = _load(out)
        data["source"] = str(src)
        data["duration"] = round(total, 2)
        data["words"] = [w for w in data["words"] if w["start"] < start - 1e-6] + words
        data["words"].sort(key=lambda w: w["start"])
        data["transcribed_to"] = round(min(total, start + args.window), 2)
        _store(out, data)
        print(f"window {start:.0f}-{start + args.window:.0f}s: {len(words)} words", flush=True)
        return 0

    data = _load(out)
    done = float(data.get("transcribed_to") or 0.0)
    if done:
        print(f"resuming at {done:.0f}s", flush=True)
    while done < total - 1:
        # The child dies with SIGKILL when the box runs short of memory - the
        # model's native allocation does not shrink, so a second window in the
        # same process is fatal, and a render running alongside it can starve
        # the first. A killed window is retried rather than ending the run:
        # the parent's only job is to keep the file advancing.
        for attempt in range(3):
            try:
                subprocess.run([sys.executable, str(Path(__file__)), str(src),
                                "--out", str(out), "--window", str(args.window),
                                "--one", f"{done:.3f}"], check=True)
                break
            except subprocess.CalledProcessError as exc:
                print(f"window at {done:.0f}s failed ({exc.returncode}), "
                      f"retry {attempt + 1}/3", flush=True)
                time.sleep(5.0 * (attempt + 1))
        else:
            print(f"STOPPED at {done:.0f}s - resume with the same command", flush=True)
            return 1
        data = _load(out)
        done = float(data.get("transcribed_to") or done + args.window)
    print(f"TRANSCRIBE_DONE words={len(data['words'])}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
