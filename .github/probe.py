"""Ask about one phrase at a time.

A long decode drifts on a repeated hook: it starts guessing which line comes
next instead of listening. Cropping to a single phrase and giving the model the
lyric as a prompt makes it commit to what is actually there — which is the only
way to tell "line 1 again" from "line 2".
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

REQUEST = Path(".github/probe-request.json")
RATE = 16000


def crop(audio: str, start: float, dur: float) -> np.ndarray:
    tmp = Path(tempfile.mkdtemp()) / "w.wav"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(start),
                    "-t", str(dur), "-i", audio, "-ac", "1", "-ar", str(RATE),
                    "-f", "wav", str(tmp)], check=True)
    with wave.open(str(tmp)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def main() -> int:
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
    req = json.loads(REQUEST.read_text())
    results = []
    for item in req["items"]:
        for at in item["at"]:
            audio = crop(item["audio"], at, item["dur"])
            segs, _ = model.transcribe(
                audio, language=item["language"], task="transcribe",
                initial_prompt=item.get("prompt", ""),
                word_timestamps=True, condition_on_previous_text=False,
                vad_filter=False, beam_size=5, temperature=0.0,
            )
            words, text = [], []
            for s in segs:
                text.append(s.text.strip())
                for w in (s.words or []):
                    words.append({"w": w.word.strip(),
                                  "start": round(at + w.start, 2),
                                  "end": round(at + w.end, 2),
                                  "p": round(float(w.probability), 2)})
            results.append({"at": at, "text": " ".join(text), "words": words})
            print(f"== {at:.2f}s  {' '.join(text)}")
            print("   " + " ".join(f"{w['w']}@{w['start']}" for w in words))
    Path("work/probe.json").write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
