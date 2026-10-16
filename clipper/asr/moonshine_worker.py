"""One chunk, one process: the memory-safe half of the moonshine provider.

`moonshine_cpp`'s ONNX session grows by roughly 180 MB per `transcribe_wav`
call and never gives it back, so transcribing a 20 minute podcast in one
process runs a 4 GB machine out of memory about 20 chunks in (measured: 12
five-second chunks took RSS from 184 MB to 2705 MB).

This module is the entry point for the remedy: the provider writes a chunk to
a wav, runs this file as a subprocess, reads one line of JSON back and lets the
process exit - which hands every byte back to the system. Startup costs ~0.7 s
per chunk; a 6 minute file is 45 chunks, so about half a minute of overhead.

    python -m clipper.asr.moonshine_worker /tmp/chunk.wav [model_dir]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(json.dumps({"error": "usage: moonshine_worker CHUNK.wav [MODEL_DIR]"}))
        return 2
    wav = argv[0]
    model_dir = argv[1] if len(argv) > 1 and argv[1] not in ("", "None") else None
    try:
        import moonshine_cpp

        if model_dir is None:
            pkg = Path(moonshine_cpp.__file__).parent / "models" / "base-en"
            model_dir = str(pkg) if pkg.exists() else None
        if model_dir is None:
            print(json.dumps({"error": "model directory not found"}))
            return 3
        model = moonshine_cpp.MoonshineModel(model_dir_path=str(model_dir))
        text = (model.transcribe_wav(wav) or "").strip()
        print(json.dumps({"text": text}))
        return 0
    except Exception as exc:                      # the parent retries inline
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:300]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
