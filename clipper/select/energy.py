"""Where is anything happening in the audio?

Everything here is deliberately cheap and explainable: an RMS envelope, a
baseline, and the stretches that stand out from it. That curve is what makes
"the loud bit" findable without a transcript, and it is also what tells the
selector where a clip can start or end without cutting a word in half.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..ffmpeg import decode_audio


def energy_curve(path: str | Path, *, rate: int = 16000, hop: float = 0.05,
                 window: float = 0.10, smooth: float = 0.4) -> dict:
    """RMS envelope in dBFS, sampled every `hop` seconds."""
    audio = decode_audio(path, rate=rate)
    audio = np.asarray(audio, dtype=np.float32)
    n = max(8, int(window * rate))
    step = max(1, int(hop * rate))
    if audio.size < n:
        audio = np.pad(audio, (0, n - audio.size))
    frames = np.lib.stride_tricks.sliding_window_view(audio, n)[::step]
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    db = 20.0 * np.log10(np.maximum(rms, 1e-7))
    if smooth > 0 and db.size > 3:
        k = max(1, int(round(smooth / hop)))
        kernel = np.hanning(2 * k + 1)
        kernel /= kernel.sum()
        db = np.convolve(db, kernel, mode="same")
    times = np.arange(db.size, dtype=np.float64) * hop
    return {
        "hop": hop,
        "times": times,
        "db": db.astype(np.float64),
        "duration": round(float(audio.size / rate), 3),
        "baseline_db": float(np.median(db)) if db.size else -100.0,
        "peak_db": float(db.max()) if db.size else -100.0,
    }


def hot_spots(curve: dict, *, margin_db: float = 6.0, floor_db: float = -45.0,
              min_len: float = 0.4, merge_gap: float = 1.0) -> list[dict]:
    """Stretches that stand above the clip's own baseline.

    Speech-only podcasts have a baseline near the speech level, so a fixed
    threshold would find nothing; the baseline is therefore relative, which is
    what makes this work on both quiet and loud recordings.

    `merge_gap` is generous on purpose: laughter, cheering and applause arrive in
    bursts with gaps inside them, and a reaction that is really one moment should
    not be reported as five separate ones.
    """
    db = np.asarray(curve["db"], dtype=np.float64)
    times = np.asarray(curve["times"], dtype=np.float64)
    if db.size == 0:
        return []
    threshold = max(curve["baseline_db"] + margin_db, floor_db)
    active = db >= threshold
    if not active.any():
        return []
    spots: list[dict] = []
    start = None
    for i, on in enumerate(active):
        if on and start is None:
            start = i
        elif not on and start is not None:
            spots.append((start, i))
            start = None
    if start is not None:
        spots.append((start, len(active)))
    # merge spots separated by a short dip: a laugh has gaps inside it
    merged: list[list[int]] = []
    for s, e in spots:
        if merged and times[s] - times[merged[-1][1] - 1] <= merge_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    out: list[dict] = []
    for s, e in merged:
        if times[e - 1] - times[s] < min_len:
            continue
        peak = int(s + int(np.argmax(db[s:e])))
        out.append({
            "start": round(float(times[s]), 3),
            "end": round(float(times[min(e, len(times) - 1)]), 3),
            "peak_time": round(float(times[peak]), 3),
            "peak_db": round(float(db[peak]), 2),
            # how far the loudest moment stands above the clip's own level. The
            # *mean* of the window would be misleading: reactions are bursts with
            # silence between them, which drags an average below the baseline.
            "peak_above_db": round(float(db[peak] - curve["baseline_db"]), 2),
            "mean_db": round(float(db[s:e].mean()), 2),
        })
    return out


def quiet_points(curve: dict, *, below_db: float | None = None,
                 min_len: float = 0.12) -> list[float]:
    """Times where the audio dips - the safe places to start or end a clip."""
    db = np.asarray(curve["db"], dtype=np.float64)
    times = np.asarray(curve["times"], dtype=np.float64)
    if db.size == 0:
        return []
    limit = curve["baseline_db"] - 3.0 if below_db is None else below_db
    quiet: list[float] = []
    run = 0
    for i, value in enumerate(db):
        if value <= limit:
            run += 1
        else:
            if run * curve["hop"] >= min_len:
                quiet.append(float(times[i - run // 2]))
            run = 0
    if run * curve["hop"] >= min_len:
        quiet.append(float(times[len(db) - run // 2 - 1]))
    return quiet


def snap_to_pause(t: float, curve: dict, *, window: float = 0.9, max_shift: float = 0.75) -> float:
    """Move a cut time to the nearest quiet moment, if there is one nearby."""
    candidates = [q for q in quiet_points(curve) if abs(q - t) <= window]
    if not candidates:
        return round(float(t), 3)
    best = min(candidates, key=lambda q: abs(q - t))
    if abs(best - t) > max_shift:
        return round(float(t), 3)
    return round(float(best), 3)


def activity(curve: dict) -> np.ndarray:
    """Envelope rescaled to 0..1 against the clip's own peak (for scoring)."""
    db = np.asarray(curve["db"], dtype=np.float64)
    if db.size == 0:
        return db
    lo = curve["baseline_db"] - 6.0
    # normalise against a high percentile rather than the absolute peak: a single
    # click or door slam at the top of a file would otherwise flatten everything
    hi = float(np.percentile(db, 97)) if db.size else curve["peak_db"]
    hi = max(hi, lo + 1.0)
    return np.clip((db - lo) / (hi - lo), 0.0, 1.0)


def mean_activity(curve: dict, start: float, end: float) -> float:
    act = activity(curve)
    times = np.asarray(curve["times"], dtype=np.float64)
    if act.size == 0 or end <= start:
        return 0.0
    mask = (times >= start) & (times < end)
    if not mask.any():
        i = int(np.clip(np.searchsorted(times, start), 0, act.size - 1))
        return float(act[i])
    return float(act[mask].mean())
