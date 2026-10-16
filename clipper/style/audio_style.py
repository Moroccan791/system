"""Audio treatment: loudness, how much of the clip is speech, music bed, ducking.

Kept deliberately simple and labelled: music detection is a spectral heuristic,
not a classifier, so it reports a confidence and can be `None` when unsure.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..align.vad import speech_intervals
from ..util import log
from ..ffmpeg import decode_audio, loudness


def _spectral_flatness(x: np.ndarray, rate: int, frame: float = 0.05, hop: float = 0.025) -> np.ndarray:
    n = int(frame * rate)
    step = max(1, int(hop * rate))
    if len(x) < n:
        return np.zeros(0, dtype=np.float32)
    win = np.hanning(n).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::step]
    spec = np.abs(np.fft.rfft(frames * win, axis=1)) + 1e-10
    geo = np.exp(np.mean(np.log(spec), axis=1))
    arith = np.mean(spec, axis=1)
    return (geo / arith).astype(np.float32)


def _rms_db(x: np.ndarray) -> float:
    if len(x) == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))
    return 20.0 * np.log10(max(rms, 1e-8))


def analyze_audio_style(path: str, *, rate: int = 16000) -> dict:
    """Loudness + speech ratio + music/ducking heuristics for one reference."""
    try:
        audio = decode_audio(path, rate=rate)
    except Exception as exc:            # no audio track at all
        log.debug("no audio to analyse", file=Path(path).name, err=type(exc).__name__)
        return {"music_bed": None, "ducking": None, "target_lufs": None, "speech_ratio": None,
                "confidence": 0.0, "note": "no audio track"}
    if len(audio) == 0:
        return {"music_bed": None, "ducking": None, "target_lufs": None,
                "speech_ratio": None, "confidence": 0.0}

    measured = loudness(path)
    intervals = speech_intervals(audio, rate)
    duration = len(audio) / rate
    speech = sum(e - s for s, e in intervals)
    speech_ratio = float(np.clip(speech / duration, 0.0, 1.0)) if duration else 0.0

    # music bed: tonal (low spectral flatness) energy that keeps going while
    # nobody is talking. Speech-only clips are near silent in those gaps.
    flat = _spectral_flatness(audio, rate)
    hop = 0.025
    gap_db = speech_db = None
    if len(flat) and intervals:
        speech_mask = np.zeros(len(flat), dtype=bool)
        for s, e in intervals:
            speech_mask[int(s / hop):int(e / hop)] = True
        gaps = flat[~speech_mask]
        gap_audio = _slice(audio, rate, _gaps(intervals, duration))
        speech_audio = _slice(audio, rate, intervals)
        gap_db, speech_db = _rms_db(gap_audio), _rms_db(speech_audio)
        tonal = float(np.mean(gaps < 0.25)) if gaps.size else 0.0
        music_bed = bool(gap_db > -45.0 and tonal > 0.5)
        ducking = bool(music_bed and (gap_db - speech_db) > -6.0)
        music_conf = float(np.clip(0.35 + 0.4 * tonal + 0.25 * (1.0 if gap_db > -45.0 else 0.0),
                                   0.0, 0.85))
    else:
        music_bed = ducking = None
        music_conf = 0.1

    return {
        "music_bed": music_bed,
        "ducking": ducking,
        "target_lufs": measured.get("integrated_lufs"),
        "true_peak_dbfs": measured.get("true_peak_dbfs"),
        "lra": measured.get("lra"),
        "speech_ratio": round(speech_ratio, 3),
        "gap_loudness_dbfs": round(gap_db, 1) if gap_db is not None else None,
        "speech_loudness_dbfs": round(speech_db, 1) if speech_db is not None else None,
        "confidence": round(music_conf, 3),
    }


def _slice(audio: np.ndarray, rate: int, spans: list[tuple[float, float]]) -> np.ndarray:
    if not spans:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate([audio[int(s * rate):int(e * rate)] for s, e in spans])


def _gaps(intervals: list[tuple[float, float]], duration: float,
          min_len: float = 0.4) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    prev = 0.0
    for s, e in intervals:
        if s - prev >= min_len:
            out.append((prev, s))
        prev = max(prev, e)
    if duration - prev >= min_len:
        out.append((prev, duration))
    return out
