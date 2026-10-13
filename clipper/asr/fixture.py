"""Deterministic provider for tests and for checking the caption pipeline
without spending minutes on real speech recognition.

Two ways to use it:

    FixtureProvider(script=["hello", "world"])         # evenly spaced words
    FixtureProvider(words=[Word("hi", 0.0, 0.4)])      # exact timings
    FixtureProvider.from_json("work/x/transcript.json")
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import Transcript, Word


class FixtureProvider:
    name = "fixture"

    def __init__(self, words: list[Word] | None = None, script: list[str] | None = None,
                 word_duration: float = 0.32, gap: float = 0.06, start: float = 0.0,
                 language: str = "en", **_: object) -> None:
        self._words = words
        self._script = script
        self.word_duration = word_duration
        self.gap = gap
        self.start = start
        self.language = language

    @classmethod
    def from_json(cls, path: str | Path, **kwargs: object) -> "FixtureProvider":
        data = Transcript.from_dict(__import__("json").loads(Path(path).read_text("utf-8")))
        return cls(words=data.words, language=data.language or "en", **kwargs)

    def available(self) -> bool:
        return True

    def transcribe(self, audio: np.ndarray, rate: int) -> Transcript:
        words = list(self._words) if self._words else self._from_script()
        text = " ".join(w.text for w in words)
        return Transcript(words=words, text=text, language=self.language,
                          provider=self.name, duration=len(audio) / rate)

    def _from_script(self) -> list[Word]:
        out: list[Word] = []
        t = self.start
        for token in self._script or []:
            out.append(Word(text=token, start=round(t, 3), end=round(t + self.word_duration, 3),
                            prob=1.0, source=self.name))
            t += self.word_duration + self.gap
        return out
