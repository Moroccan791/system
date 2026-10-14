"""Moonshine ASR provider - works out of the box, no model download.

`pip install moonshine-cpp` ships the real ONNX weights (base-en, ~64 MB) plus
onnxruntime inside the wheel, so this is the default engine in environments
where you cannot download models (containers, sandboxes, offline machines).

Trade-off vs whisper: text quality is close on clean speech, it is fast on CPU,
but it returns no per-word timestamps - the caption stage runs the energy
aligner to get them.

Two things about this model are measured, not assumed:

* **Memory grows with the chunk.** Peak RSS for one call: 3.3 GB at 22 s,
  1.5 GB at 12 s, 976 MB at 8 s, 698 MB at 5 s. The default chunk is therefore
  8 s, not 22 s.
* **Memory leaks across calls.** Twelve five-second chunks took RSS from 184 MB
  to 2705 MB; had they been longer the process would have been killed (which is
  exactly what happened here on a 4 GB box). So each chunk is transcribed in a
  subprocess that outlives nothing: the provider writes the chunk to a wav, runs
  `python -m clipper.asr.moonshine_worker` on it and lets the process exit.
  Small chunks are also *faster* per second of audio (2.3x realtime at 5 s vs
  1.9x at 22 s), so this costs nothing but ~0.7 s of startup per chunk.

Set `isolate_chunks=False` to call the model in-process (fine for a short clip
on a roomy machine, fatal for a long file on a small one).

    python -m clipper transcribe clip.mp4 --asr moonshine
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np

from ..align.energy_align import align_words
from ..align.vad import merge_to_chunks, speech_intervals
from ..util import log
from .base import Transcript


def split_interval_chunks(chunks: list[tuple[float, float]],
                          max_len: float) -> list[tuple[float, float]]:
    """No chunk longer than `max_len`, not even one long unbroken stretch of speech.

    `merge_to_chunks` only caps chunks it builds by merging; an interval that is
    already longer than the cap (a speaking voice with no pause to cut on) came
    through untouched, which is how a 22s+ piece of audio reached the model and
    pushed a 4 GB machine into an OOM kill. Splitting here keeps every call at
    the size whose memory cost was measured.
    """
    if max_len <= 0:
        return list(chunks)
    out: list[tuple[float, float]] = []
    for start, end in chunks:
        span = end - start
        if span <= max_len * 1.05:
            out.append((start, end))
            continue
        pieces = int(span // max_len) + (1 if span % max_len else 0)
        step = span / pieces
        for i in range(pieces):
            out.append((round(start + i * step, 3), round(start + (i + 1) * step, 3)))
    return out


class MoonshineProvider:
    name = "moonshine"

    def __init__(self, model_dir: str | Path | None = None, model_type: str = "base",
                 language: str = "en", chunk_seconds: float = 8.0,
                 force_align: bool = True, isolate_chunks: bool = True,
                 worker_timeout: float = 600.0, **_: object) -> None:
        self.model_type = model_type
        self.language = language
        self.chunk_seconds = chunk_seconds
        self.force_align = force_align
        self.isolate_chunks = isolate_chunks
        self.worker_timeout = worker_timeout
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

    def _chunk_text(self, wav: Path, model) -> str:
        """Transcribe one chunk - in a throwaway process when asked.

        A worker that dies (the model is a native library; it can take the whole
        process with it) is retried here, where the chunk still fits in memory.
        Speech is never dropped just because the isolated route failed.
        """
        if self.isolate_chunks:
            try:
                return self._worker_text(wav)
            except Exception as exc:
                log.warn("isolated chunk failed, retrying in this process",
                         err=f"{type(exc).__name__}: {exc}"[:120])
        return (model.transcribe_wav(str(wav)) or "").strip()

    def _worker_text(self, wav: Path) -> str:
        import subprocess
        import sys

        model_dir = self._resolve_model_dir()
        proc = subprocess.run(
            [sys.executable, "-m", "clipper.asr.moonshine_worker", str(wav),
             str(model_dir) if model_dir else ""],
            capture_output=True, text=True, timeout=self.worker_timeout,
        )
        line = (proc.stdout or "").strip().splitlines()
        if not line:
            raise RuntimeError(f"worker produced no output (rc={proc.returncode})")
        payload = json.loads(line[-1])
        if payload.get("error"):
            raise RuntimeError(payload["error"])
        return (payload.get("text") or "").strip()

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
        chunks = split_interval_chunks(merge_to_chunks(intervals, max_len=self.chunk_seconds),
                                       self.chunk_seconds)
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
                text = self._chunk_text(wav, model)
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
