"""Provider-agnostic ASR types and registry."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass
class Word:
    """One spoken word with a time span (seconds, absolute in the source)."""

    text: str
    start: float
    end: float
    prob: float | None = None
    kind: str = "word"          # word | punct | noise
    source: str | None = None   # which engine produced this timing

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Word":
        return cls(**{k: d.get(k) for k in ("text", "start", "end", "prob", "kind", "source")})


@dataclass
class Transcript:
    words: list[Word] = field(default_factory=list)
    text: str = ""
    language: str | None = None
    provider: str = "unknown"
    duration: float = 0.0
    meta: dict = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.words

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "language": self.language,
            "provider": self.provider,
            "duration": self.duration,
            "meta": self.meta,
            "words": [w.to_dict() for w in self.words],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Transcript":
        return cls(
            words=[Word.from_dict(w) for w in d.get("words", [])],
            text=d.get("text", ""),
            language=d.get("language"),
            provider=d.get("provider", "unknown"),
            duration=d.get("duration", 0.0),
            meta=d.get("meta", {}) or {},
        )


@runtime_checkable
class ASRProvider(Protocol):
    name: str

    def available(self) -> bool:
        """True when the backend can actually run here (deps + model present)."""

    def transcribe(self, audio: np.ndarray, rate: int) -> Transcript:
        """Transcribe mono float32 audio. `audio` length = duration * rate."""


_REGISTRY: dict[str, str] = {
    "moonshine": "clipper.asr.moonshine:MoonshineProvider",
    "faster_whisper": "clipper.asr.faster_whisper:FasterWhisperProvider",
    "fixture": "clipper.asr.fixture:FixtureProvider",
}


def list_providers() -> list[str]:
    return sorted(_REGISTRY)


def get_provider(name: str = "auto", **kwargs):
    """Resolve a provider by name.

    `auto` picks the best available engine: whisper (if installed) -> moonshine.
    A missing optional dependency raises with an install hint instead of an
    ImportError deep inside the pipeline.
    """
    import importlib

    if name == "auto":
        for candidate in ("faster_whisper", "moonshine"):
            try:
                prov = get_provider(candidate, **kwargs)
                if prov.available():
                    return prov
            except Exception:
                continue
        raise RuntimeError(
            "no ASR provider available - run `python -m clipper doctor` for details"
        )
    if name not in _REGISTRY:
        raise KeyError(f"unknown ASR provider '{name}' (have: {', '.join(list_providers())})")
    module_path, cls_name = _REGISTRY[name].split(":")
    module = importlib.import_module(module_path)
    return getattr(module, cls_name)(**kwargs)
