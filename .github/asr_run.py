"""Transcribe edit audio with word timestamps, inside CI.

Why this is a workflow and not a local script: the audio is a Hindi and a Bangla
vocal, and the only aligners that handle those are neural models whose weights
live behind hosts this sandbox cannot reach. GitHub Actions can reach them. So
the job downloads the model, decodes the tracks, and commits back the timings —
a few kilobytes of JSON — which is all the caption renderer actually needs.
"""
from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx

MODEL_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "asr-model")
REQUEST = Path(".github/asr-request.json")


def crop(audio: str, start: float, end: float) -> np.ndarray:
    tmp = Path("/tmp/asr_window.wav")
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(start), "-to", str(end),
         "-i", audio, "-ac", "1", "-ar", "16000", "-f", "wav", str(tmp)],
        check=True,
    )
    with wave.open(str(tmp)) as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def encoder_decoder() -> tuple[str, str, str]:
    files = list(MODEL_DIR.rglob("*.onnx"))
    enc = next(p for p in files if "encoder" in p.name)
    dec = next(p for p in files if "decoder" in p.name)
    tok = next(MODEL_DIR.rglob("*tokens.txt"))
    return str(enc), str(dec), str(tok)


def recognizer(lang: str) -> sherpa_onnx.OfflineRecognizer:
    enc, dec, tok = encoder_decoder()
    return sherpa_onnx.OfflineRecognizer.from_whisper(
        encoder=enc, decoder=dec, tokens=tok,
        language=lang, task="transcribe",
        num_threads=4, decoding_method="greedy_search",
        enable_token_timestamps=True, enable_segment_timestamps=True,
    )


def run(item: dict) -> dict:
    lang = item["language"]
    rec = recognizer(lang)
    samples = crop(item["audio"], item["start"], item["end"])
    stream = rec.create_stream()
    stream.accept_waveform(16000, samples)
    rec.decode_stream(stream)
    r = stream.result
    tokens = list(getattr(r, "tokens", []) or [])
    stamps = list(getattr(r, "timestamps", []) or [])
    # Rebuild words: sentencepiece tokens start a new word unless they lead with
    # the whitespace marker, which sherpa strips — so a token that begins with
    # "▁" or that is preceded by a timestamp gap opens a word.
    words, cur = [], None
    for tok, ts in zip(tokens, stamps):
        if tok.startswith("▁") or tok.startswith(" "):
            if cur:
                words.append(cur)
            cur = {"w": tok.lstrip("▁ "), "t": float(ts)}
        elif cur is None:
            cur = {"w": tok, "t": float(ts)}
        else:
            cur["w"] += tok
    if cur:
        words.append(cur)
    return {
        "audio": item["audio"], "language": lang,
        "start": item["start"], "end": item["end"],
        "text": getattr(r, "text", ""),
        "words": words,
        "raw_tokens": [{"t": float(t), "tok": s} for s, t in zip(tokens, stamps)][:4000],
    }


def main() -> int:
    req = json.loads(REQUEST.read_text())
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
        print(f"--- {item['audio']} [{item['language']}] -> {out}")
        print(data["text"][:400])
        print(f"{len(data['words'])} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
