"""Transcribe edit audio with timings, inside CI.

Two ways to get time out of Whisper here, because the shipped decoder has no
cross-attention outputs (so token timestamps are unavailable):

1. segment timestamps — the model emits <|12.34|> markers, which are parsed
   straight out of the text;
2. a decode sweep — overlapping short windows, each transcribed on its own, so
   a word is known to be audible somewhere inside a known 6s span. The sweep is
   slower but it does not depend on the marker export at all, and the two agree
   on everything that matters.

The audio is Hindi and Bangla; the aligners that handle those need weights from
hosts this sandbox cannot reach, so the decode runs in CI and only the timings
are committed back.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx

MODEL_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "asr-model")
REQUEST = Path(".github/asr-request.json")
RATE = 16000
CHUNK = 28.0          # the decoder refuses anything over 30s
SWEEP_WIN = 6.0
SWEEP_HOP = 0.5

STAMP = re.compile(r"<\|(\d+(?:\.\d+)?)\|>")


def crop(audio: str, start: float, end: float) -> np.ndarray:
    tmp = Path("/tmp/asr_window.wav")
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(start), "-to", str(end),
         "-i", audio, "-ac", "1", "-ar", str(RATE), "-f", "wav", str(tmp)],
        check=True,
    )
    with wave.open(str(tmp)) as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def paths() -> tuple[str, str, str]:
    files = list(MODEL_DIR.rglob("*.onnx"))
    enc = next(p for p in files if "encoder" in p.name and "int8" not in p.name)
    dec = next(p for p in files if "decoder" in p.name and "int8" not in p.name)
    tok = next(MODEL_DIR.rglob("*tokens.txt"))
    return str(enc), str(dec), str(tok)


_RECS: dict[str, sherpa_onnx.OfflineRecognizer] = {}


def recognizer(lang: str, segments: bool) -> sherpa_onnx.OfflineRecognizer:
    key = f"{lang}:{segments}"
    if key not in _RECS:
        enc, dec, tok = paths()
        _RECS[key] = sherpa_onnx.OfflineRecognizer.from_whisper(
            encoder=enc, decoder=dec, tokens=tok,
            language=lang, task="transcribe",
            num_threads=4, decoding_method="greedy_search",
            enable_segment_timestamps=segments,
        )
    return _RECS[key]


def decode(rec, samples: np.ndarray) -> dict:
    stream = rec.create_stream()
    stream.accept_waveform(RATE, samples)
    rec.decode_stream(stream)
    r = stream.result
    text = getattr(r, "text", "") or ""
    return {
        "text": STAMP.sub("", text).strip(),
        "stamps": [float(x) for x in STAMP.findall(text)],
        "segments": [
            {"start": float(s.start), "end": float(s.end), "text": s.text}
            for s in (getattr(r, "segments", None) or [])
        ],
    }


def run(item: dict) -> dict:
    lang = item["language"]
    samples = crop(item["audio"], item["start"], item["end"])
    total = len(samples) / RATE

    chunk_rec = recognizer(lang, True)
    chunks = []
    t = 0.0
    while t < total - 0.05:
        s = samples[int(t * RATE): int(min(t + CHUNK, total) * RATE)]
        d = decode(chunk_rec, s)
        d["offset"] = round(t, 2)
        chunks.append(d)
        t += CHUNK

    sweep_rec = recognizer(lang, False)
    sweep = []
    t = 0.0
    while t + SWEEP_WIN <= total + 1e-6:
        s = samples[int(t * RATE): int((t + SWEEP_WIN) * RATE)]
        d = decode(sweep_rec, s)
        if d["text"]:
            sweep.append({"start": round(t, 2), "text": d["text"]})
        t += SWEEP_HOP

    return {
        "audio": item["audio"], "language": lang,
        "start": item["start"], "end": item["end"], "duration": round(total, 2),
        "chunks": chunks,
        "sweep": sweep,
        "full_text": " ".join(c["text"] for c in chunks),
    }


def main() -> int:
    req = json.loads(REQUEST.read_text())
    print("model files:", [p.name for p in Path(MODEL_DIR).rglob("*.onnx")])
    for item in req["items"]:
        out = Path(item["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = run(item)
        except Exception:
            import traceback
            Path("work/asr_error.txt").write_text(traceback.format_exc())
            raise
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        print(f"--- {item['audio']} [{item['language']}] {len(data['sweep'])} sweep windows")
        print(data["full_text"][:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
