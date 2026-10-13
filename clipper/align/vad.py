"""Voice activity detection.

`SileroVAD` runs the bundled silero-vad onnx model on CPU through onnxruntime
(no torch required). `energy_probs` is a dependency-free fallback so the
pipeline still works if onnx is unavailable.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..util import log

SILERO_WINDOW = 512   # new samples per call @ 16 kHz
CONTEXT_SAMPLES = 64  # silero keeps 64 samples of context between calls


def _silero_model_path() -> Path | None:
    env = os.environ.get("CLIPPER_SILERO_MODEL")
    if env and Path(env).exists():
        return Path(env)
    from .. import config

    for cand in (config.MODELS / "silero_vad.onnx",):
        if cand.exists():
            return cand
    try:  # the silero-vad wheel ships the model inside the package
        import silero_vad

        p = Path(silero_vad.__file__).parent / "data" / "silero_vad.onnx"
        return p if p.exists() else None
    except Exception:
        return None


class SileroVAD:
    """Speech probability per 512-sample window (32 ms @ 16 kHz)."""

    def __init__(self, model_path: str | Path | None = None, threshold: float = 0.5) -> None:
        self.threshold = threshold
        self.model_path = Path(model_path) if model_path else _silero_model_path()
        self._session = None

    def available(self) -> bool:
        if self.model_path is None or not self.model_path.exists():
            return False
        try:
            import onnxruntime  # noqa: F401
        except Exception:
            return False
        return True

    def _get_session(self):
        if self._session is None:
            import onnxruntime as ort

            so = ort.SessionOptions()
            so.intra_op_num_threads = max(1, (os.cpu_count() or 2))
            so.inter_op_num_threads = 1
            so.log_severity_level = 3
            self._session = ort.InferenceSession(
                str(self.model_path), sess_options=so, providers=["CPUExecutionProvider"]
            )
        return self._session

    def probs(self, audio: np.ndarray, rate: int = 16000, window: int = SILERO_WINDOW) -> np.ndarray:
        """Window-wise speech probabilities in [0, 1].

        silero v5/v6 keeps 64 samples of context: each call feeds
        `[prev_64_samples, new_512_samples]` and returns one probability for the
        new window. Skipping the context makes every probability ~0.
        """
        session = self._get_session()
        if rate != 16000:
            raise ValueError("silero expects 16 kHz audio; decode with rate=16000")
        x = np.asarray(audio, dtype=np.float32).reshape(-1)
        if len(x) < window:
            x = np.pad(x, (0, window - len(x)))
        state = np.zeros((2, 1, 128), dtype=np.float32)
        ctx = np.zeros((1, CONTEXT_SAMPLES), dtype=np.float32)
        sr = np.array(16000, dtype=np.int64)
        out: list[float] = []
        for i in range(0, len(x) - window + 1, window):
            chunk = x[i:i + window].reshape(1, -1)
            feed = np.concatenate([ctx, chunk], axis=1) if CONTEXT_SAMPLES else chunk
            res = session.run(None, {"input": feed, "state": state, "sr": sr})
            out.append(float(res[0].reshape(-1)[-1]))
            state = res[1].astype(np.float32)
            if CONTEXT_SAMPLES:
                ctx = feed[:, -CONTEXT_SAMPLES:]
        return np.asarray(out, dtype=np.float32) if out else np.zeros(0, dtype=np.float32)

    def intervals(self, audio: np.ndarray, rate: int = 16000, *,
                  min_speech: float = 0.20, min_silence: float = 0.18,
                  pad: float = 0.05) -> list[tuple[float, float]]:
        probs = self.probs(audio, rate)
        win = SILERO_WINDOW / rate
        return probs_to_intervals(probs, win, threshold=self.threshold,
                                  min_speech=min_speech, min_silence=min_silence, pad=pad)


def energy_probs(audio: np.ndarray, rate: int, *, frame: float = 0.032,
                 hop: float = 0.016) -> tuple[np.ndarray, float]:
    """Dependency-free VAD: adaptive RMS threshold. Returns (probs, window_sec)."""
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    n = int(frame * rate)
    step = max(1, int(hop * rate))
    if len(x) < n:
        return np.zeros(0, dtype=np.float32), frame
    idx = np.arange(0, len(x) - n + 1, step)
    rms = np.sqrt(np.mean(np.lib.stride_tricks.sliding_window_view(x, n)[::step] ** 2, axis=1))
    db = 20.0 * np.log10(np.maximum(rms, 1e-8))
    floor = float(np.percentile(db, 20))
    top = float(np.percentile(db, 95))
    span = max(6.0, top - floor)
    probs = np.clip((db - (floor + 0.35 * span)) / (0.65 * span), 0.0, 1.0).astype(np.float32)
    return probs, hop


def probs_to_intervals(probs: np.ndarray, window: float, *, threshold: float = 0.5,
                       min_speech: float = 0.20, min_silence: float = 0.18,
                       pad: float = 0.05) -> list[tuple[float, float]]:
    """Turn per-window probabilities into merged (start, end) speech intervals."""
    if len(probs) == 0:
        return []
    active = probs >= threshold
    spans: list[list[float]] = []
    start: int | None = None
    for i, on in enumerate(active):
        if on and start is None:
            start = i
        elif not on and start is not None:
            spans.append([start * window, i * window])
            start = None
    if start is not None:
        spans.append([start * window, len(active) * window])
    if not spans:
        return []
    merged: list[list[float]] = [spans[0]]
    for s, e in spans[1:]:
        if s - merged[-1][1] < min_silence:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    out = []
    for s, e in merged:
        s2, e2 = max(0.0, s - pad), e + pad
        if e2 - s2 >= min_speech:
            out.append((round(s2, 3), round(e2, 3)))
    return out


def speech_intervals(audio: np.ndarray, rate: int = 16000, *, engine: str = "auto",
                     threshold: float = 0.5, min_speech: float = 0.20,
                     min_silence: float = 0.18, pad: float = 0.05,
                     ) -> list[tuple[float, float]]:
    """Speech intervals using silero when possible, else the energy fallback."""
    if engine in ("auto", "silero"):
        try:
            vad = SileroVAD(threshold=threshold)
            if vad.available():
                return vad.intervals(audio, rate, min_speech=min_speech,
                                     min_silence=min_silence, pad=pad)
            if engine == "silero":
                raise RuntimeError("silero VAD requested but the onnx model is missing")
        except Exception as exc:
            log.warn("silero VAD unavailable, falling back to energy VAD", err=type(exc).__name__)
    probs, win = energy_probs(audio, rate)
    return probs_to_intervals(probs, win, threshold=threshold, min_speech=min_speech,
                              min_silence=min_silence, pad=pad)


def merge_to_chunks(intervals: list[tuple[float, float]], *, max_len: float = 22.0,
                    pad: float = 0.12) -> list[tuple[float, float]]:
    """Merge speech intervals into ASR-sized chunks (engines like moonshine want
    short inputs) while keeping natural boundaries."""
    chunks: list[tuple[float, float]] = []
    for s, e in intervals:
        if chunks and (e - chunks[-1][0]) <= max_len and (s - chunks[-1][1]) <= 0.6:
            chunks[-1] = (chunks[-1][0], e)
        else:
            chunks.append((s, e))
    return [(max(0.0, s - pad), e + pad) for s, e in chunks]
