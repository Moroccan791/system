"""Moonshine ASR provider - works out of the box, no model download.

`pip install moonshine-cpp` ships the real ONNX weights (base-en, ~64 MB) plus
onnxruntime inside the wheel, so this is the default engine in environments
where you cannot download models (containers, sandboxes, offline machines).

Trade-off vs whisper: text quality is close on clean speech, it is fast on CPU
(~5x realtime on 2 cores), but it returns no per-word timestamps - the caption
stage runs the energy aligner to get them.

    python -m clipper transcribe clip.mp4 --asr moonshine
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np

from ..align.energy_align import align_words
from ..align.vad import merge_to_chunks, speech_intervals
from ..util import log
from .base import Transcript


class MoonshineProvider:
    name = "moonshine"

    def __init__(self, model_dir: str | Path | None = None, model_type: str = "base",
                 language: str = "en", chunk_seconds: float = 22.0,
                 force_align: bool = True, **_: object) -> None:
        self.model_type = model_type
        self.language = language
        self.chunk_seconds = chunk_seconds
        self.force_align = force_align
        self._explicit_dir = Path(model_dir) if model_dir else None
        self._model = None

    # -- setup ------------------------------------------------------------
    def _resolve_model_dir(self) -> Path | None:
        if self._explicit_dir and self._explicit_dir.exists():
            return self._explicit_dir
        env = os.environ.get("CLIPPER_MOONSHINE_MODEL")
        if env and Path(env).exists():
            return Path(env)
        from .. import config

        for cand in (config.MODELS / f"moonshine-{self.model_type}-{self.language}",
                     config.MODELS / f"moonshine-{self.model_type}"):
            if cand.exists():
                return cand
        try:
            import moonshine_cpp

            pkg = Path(moonshine_cpp.__file__).parent / "models" / f"{self.model_type}-{self.language}"
            return pkg if pkg.exists() else None
        except Exception:
            return None

    def available(self) -> bool:
        try:
            import moonshine_cpp  # noqa: F401
        except Exception:
            return False
        return self._resolve_model_dir() is not None

    def _get_model(self):
        if self._model is None:
            import moonshine_cpp

            model_dir = self._resolve_model_dir()
            if model_dir is None:
                raise RuntimeError(
                    "moonshine model not found - pip install moonshine-cpp "
                    "(or set CLIPPER_MOONSHINE_MODEL to a model directory)"
                )
            log.info("loading moonshine", model_dir=str(model_dir))
            self._model = moonshine_cpp.MoonshineModel(model_dir_path=str(model_dir))
        return self._model

    # -- transcription ----------------------------------------------------
    def transcribe(self, audio: np.ndarray, rate: int) -> Transcript:
        if not self.available():
            raise RuntimeError("moonshine-cpp is not installed: pip install moonshine-cpp")
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        duration = len(audio) / rate
        model = self._get_model()

        with log.step("vad"):
            try:
                intervals = speech_intervals(audio, rate)
            except Exception as exc:
                log.warn("VAD failed, treating the whole file as speech", err=type(exc).__name__)
                intervals = [(0.0, duration)]
        if not intervals:
            log.warn("no speech detected in audio", duration=f"{duration:.1f}s")
            return Transcript(words=[], text="", language=self.language,
                              provider=self.name, duration=duration,
                              meta={"reason": "no speech detected"})
        chunks = merge_to_chunks(intervals, max_len=self.chunk_seconds)
        log.info("transcribing", chunks=len(chunks), speech=f"{sum(e - s for s, e in intervals):.1f}s",
                 audio=f"{duration:.1f}s")

        words = []
        texts: list[str] = []
        tmpdir = Path(tempfile.mkdtemp(prefix="clipper-moonshine-"))
        for i, (cs, ce) in enumerate(chunks):
            seg = audio[int(cs * rate):int(ce * rate)]
            if len(seg) < int(0.2 * rate):
                continue
            wav = tmpdir / f"chunk-{i:04d}.wav"
            from ..ffmpeg import write_wav

            write_wav(wav, seg, rate)
            try:
                text = model.transcribe_wav(str(wav)).strip()
            except Exception as exc:
                log.warn("chunk failed", chunk=i, err=type(exc).__name__)
                continue
            if not text:
                continue
            texts.append(text)
            if self.force_align:
                local = [(s - cs, e - cs) for s, e in intervals if e > cs and s < ce]
                words.extend(align_words(text, seg, rate, t0=cs, intervals=local))
            if wav.exists():
                wav.unlink()

        words.sort(key=lambda w: w.start)
        return Transcript(
            words=words, text=" ".join(texts), language=self.language, provider=self.name,
            duration=duration,
            meta={"chunks": len(chunks), "model": f"moonshine-{self.model_type}.{self.language}",
                  "aligned": self.force_align},
        )
