"""Energy-based forced alignment: give words timings when the ASR engine
returns plain text.

How it works
------------
1. VAD gives the speech intervals -> everything else is silence.
2. Inside an interval we detect *syllable nuclei*: the amplitude peaks of the
   250-3500 Hz band. Speech rhythm lives there - one peak per syllable.
3. Words are distributed over the interval proportionally to their length
   (weight = letters + space), then each boundary is snapped to the nearest
   nucleus if one is within `snap` seconds.

Accuracy is roughly +/- 100 ms on clean speech, which is well inside what
captions need (karaoke word windows are ~300 ms). With whisper
`word_timestamps=True` this module is never used.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..asr.base import Word
from .vad import speech_intervals


def _bandpass(x: np.ndarray, rate: int, fmin: float = 250.0, fmax: float = 3500.0) -> np.ndarray:
    """Zero-phase-ish bandpass by masking the rFFT (fast, no scipy)."""
    n = len(x)
    if n == 0:
        return x
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, d=1.0 / rate)
    mask = (freqs >= fmin) & (freqs <= fmax)
    return np.fft.irfft(spec * mask, n=n).astype(np.float32)


def _moving_average(x: np.ndarray, win: int) -> np.ndarray:
    if win <= 1:
        return x
    kernel = np.ones(win, dtype=np.float32) / win
    return np.convolve(x, kernel, mode="same").astype(np.float32)


def nuclei_times(audio: np.ndarray, rate: int, *, min_dist: float = 0.09,
                 smooth: float = 0.03, floor_ratio: float = 0.12) -> np.ndarray:
    """Times (seconds, relative to `audio`) of syllable-nuclei energy peaks."""
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    if len(x) < int(0.05 * rate):
        return np.zeros(0, dtype=np.float32)
    env = np.abs(_bandpass(x, rate))
    env = _moving_average(env, max(1, int(smooth * rate)))
    if env.size == 0 or float(env.max()) <= 1e-6:
        return np.zeros(0, dtype=np.float32)
    thr = float(env.max()) * floor_ratio
    min_gap = max(1, int(min_dist * rate))
    peaks: list[int] = []
    last = -min_gap
    order = np.argsort(env)[::-1]  # strongest first, then enforce spacing
    for i in order:
        if env[i] < thr:
            break
        if i - last >= min_gap and (not peaks or all(abs(i - p) >= min_gap for p in peaks)):
            peaks.append(int(i))
            last = i
    peaks.sort()
    return (np.asarray(peaks, dtype=np.float32) / rate).astype(np.float32)


def _weights(tokens: list[str]) -> np.ndarray:
    w = np.array([max(1, len("".join(ch for ch in t if ch.isalnum()))) + 0.6 for t in tokens],
                 dtype=np.float64)
    return w / w.sum()


def assign_words_to_intervals(tokens: list[str],
                              intervals: list[tuple[float, float]]) -> list[list[str]]:
    """Split `tokens` across speech intervals, proportional to speech time."""
    if not intervals:
        return [list(tokens)]
    if len(intervals) == 1:
        return [list(tokens)]
    weights = _weights(tokens)
    cum = np.concatenate([[0.0], np.cumsum(weights)])
    total_words = cum[-1]
    lengths = np.array([e - s for s, e in intervals], dtype=np.float64)
    speech_total = float(lengths.sum()) or 1.0
    # cumulative word-mass at each interval boundary (by speech-time share)
    bounds: list[int] = []
    running = 0.0
    for length in lengths[:-1]:
        running += float(length) / speech_total
        # index of the first word whose midpoint passes the boundary
        mids = (cum[:-1] + cum[1:]) / 2.0 / total_words
        idx = int(np.searchsorted(mids, running, side="left"))
        bounds.append(max(1, min(idx, len(tokens) - 1)))
    out: list[list[str]] = []
    prev = 0
    for b in bounds:
        b = max(b, prev)
        out.append(tokens[prev:b])
        prev = b
    out.append(tokens[prev:])
    return out


def _align_interval(tokens: list[str], start: float, end: float,
                    nuclei: np.ndarray, snap: float = 0.12,
                    min_word: float = 0.07) -> list[Word]:
    """Distribute tokens inside one speech interval."""
    span = end - start
    if not tokens or span <= 0:
        return []
    weights = _weights(tokens)
    edges = start + np.concatenate([[0.0], np.cumsum(weights)]) * span
    if len(nuclei) >= len(tokens):
        local = np.sort(nuclei[(nuclei >= start - snap) & (nuclei <= end + snap)])
        anchors = local[np.linspace(0, len(local) - 1, len(tokens)).round().astype(int)]
        # blend proportional edges with nucleus anchors
        mids = (edges[:-1] + edges[1:]) / 2.0
        blended = 0.5 * mids + 0.5 * np.clip(anchors, start, end)
        edges = np.concatenate([[start], (blended[:-1] + blended[1:]) / 2.0, [end]])
    else:
        for i in range(1, len(edges) - 1):
            if len(nuclei):
                near = nuclei[np.argmin(np.abs(nuclei - edges[i]))]
                if abs(float(near) - float(edges[i])) <= snap:
                    edges[i] = float(near)
    words: list[Word] = []
    for i, tok in enumerate(tokens):
        s, e = float(edges[i]), float(edges[i + 1])
        if e - s < min_word:
            e = s + min_word
        words.append(Word(text=tok, start=round(s, 3), end=round(e, 3), source="energy-align"))
    return words


def align_words(text: str, audio: np.ndarray, rate: int, *, t0: float = 0.0,
                intervals: list[tuple[float, float]] | None = None,
                min_speech: float = 0.15, **vad_kwargs: object) -> list[Word]:
    """Timing for every token of `text` inside `audio`.

    `intervals` are seconds relative to `audio`; pass them when the caller
    already knows the speech regions (chunked transcription does).
    Returns absolute times with `t0` added.
    """
    tokens = [t for t in text.split() if t]
    if not tokens:
        return []
    if intervals is None:
        intervals = speech_intervals(audio, rate, min_speech=min_speech, **vad_kwargs)
    if not intervals:
        duration = len(audio) / rate
        intervals = [(0.0, duration)] if duration > 0 else []
    groups = assign_words_to_intervals(tokens, intervals)
    nuc = nuclei_times(audio, rate)
    out: list[Word] = []
    for (start, end), group in zip(intervals, groups):
        if not group:
            continue
        local_nuclei = nuc[(nuc >= start - 0.05) & (nuc <= end + 0.05)]
        for w in _align_interval(group, float(start), float(end), local_nuclei):
            w.start = round(w.start + t0, 3)
            w.end = round(w.end + t0, 3)
            out.append(w)
    out.sort(key=lambda w: w.start)
    return out
