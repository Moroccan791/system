"""Word-level timings from the vocal, via faster-whisper.

The sherpa export has no cross-attention outputs, so it cannot say WHEN a word
was sung — only that it was. faster-whisper computes word timestamps from the
cross-attention maps directly, and its weights come from Hugging Face, which CI
can reach and the sandbox cannot.

Known lyric, unknown times: this is the piece that supplies the times.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

REQUEST = Path(".github/asr-request.json")
RATE = 16000
MODEL = sys.argv[1] if len(sys.argv) > 1 else "small"
ONLY = sys.argv[2:]


def crop(audio: str, start: float, end: float) -> np.ndarray:
    tmp = Path(tempfile.mkdtemp()) / "w.wav"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(start), "-to", str(end),
         "-i", audio, "-ac", "1", "-ar", str(RATE), "-f", "wav", str(tmp)],
        check=True,
    )
    with wave.open(str(tmp)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def main() -> int:
    from faster_whisper import WhisperModel

    model = WhisperModel(MODEL, device="cpu", compute_type="int8", cpu_threads=4)
    items = json.loads(REQUEST.read_text())["items"]
    for item in items:
        if ONLY and item["out"] not in ONLY:
            continue
        audio = crop(item["audio"], item["start"], item["end"])
        segs, info = model.transcribe(
            audio, language=item["language"], task="transcribe",
            word_timestamps=True, condition_on_previous_text=False,
            vad_filter=False, beam_size=5,
        )
        words, text = [], []
        for s in segs:
            text.append(s.text.strip())
            for w in (s.words or []):
                words.append({"w": w.word.strip(), "start": round(w.start, 2),
                              "end": round(w.end, 2), "p": round(float(w.probability), 3)})
        out = Path(item["out"]).with_name(Path(item["out"]).stem.replace("asr_", "fw_") + ".json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "audio": item["audio"], "language": item["language"],
            "start": item["start"], "end": item["end"],
            "duration": round(len(audio) / RATE, 2),
            "text": " ".join(text), "words": words,
        }, ensure_ascii=False, indent=1) + "\n")
        print(f"--- {item['audio']} -> {out}: {len(words)} words")
        print(" ".join(f"{w['w']}@{w['start']}" for w in words[:40]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
