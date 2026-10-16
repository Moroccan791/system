"""faster-whisper provider - the recommended engine on a real machine.

It gives true word-level timestamps (`word_timestamps=True`), so the caption
stage skips the energy aligner entirely and captions land exactly on the voice.

    pip install faster-whisper
    python -m clipper captions raw.mp4 --asr faster_whisper --model small

Model files are downloaded by the library on first use (they are cached in
~/.cache/huggingface). Use `--model small` / `medium` / `distil-small.en`.
"""
from __future__ import annotations

import numpy as np

from .base import Transcript, Word


class FasterWhisperProvider:
    name = "faster_whisper"
    _MODEL_CACHE: dict[str, object] = {}

    def __init__(self, model: str = "small", device: str = "cpu", compute_type: str = "int8",
                 language: str | None = "en", vad_filter: bool = True, beam_size: int = 5,
                 cpu_threads: int = 0, **_: object) -> None:
        import os

        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.vad_filter = vad_filter
        self.beam_size = beam_size
        self.cpu_threads = cpu_threads or max(1, (os.cpu_count() or 4) - 1)

    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
        except Exception:
            return False
        return True

    def _model(self):
        if self.model_name not in self._MODEL_CACHE:
            from faster_whisper import WhisperModel

            self._MODEL_CACHE[self.model_name] = WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
            )
        return self._MODEL_CACHE[self.model_name]

    def transcribe(self, audio: np.ndarray, rate: int) -> Transcript:
        if not self.available():
            raise RuntimeError("faster-whisper is not installed: pip install faster-whisper")
        model = self._model()
        segments, info = model.transcribe(
            np.asarray(audio, dtype=np.float32),
            language=self.language,
            word_timestamps=True,
            vad_filter=self.vad_filter,
            beam_size=self.beam_size,
            condition_on_previous_text=False,
        )
        words: list[Word] = []
        chunks: list[str] = []
        for seg in segments:
            chunks.append(seg.text.strip())
            for w in seg.words or []:
                token = w.word.strip()
                if not token:
                    continue
                words.append(Word(text=token, start=float(w.start), end=float(w.end),
                                  prob=float(getattr(w, "probability", 0.0) or 0.0),
                                  source=self.name))
        return Transcript(
            words=words, text=" ".join(c for c in chunks if c),
            language=getattr(info, "language", self.language), provider=self.name,
            duration=len(audio) / rate,
            meta={"model": self.model_name, "compute_type": self.compute_type,
                  "device": self.device},
        )
