"""Shot detection and pacing.

Short-form edits cut hard, so we look for abrupt frame-to-frame change with a
robust threshold (median + k*MAD over the clip) instead of a fixed one: that
keeps working on both a static podcast frame and handheld footage.

Two independent signals, because either one alone has blind spots:
  * pixel difference  - catches cuts between visually similar scenes
  * HSV histogram distance - catches cuts when the camera moved a lot

Gradual fades are reported separately (they matter for transitions) but do not
count as cuts.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .frames import SampledFrame


@dataclass
class ShotResult:
    cuts: list[float] = field(default_factory=list)          # seconds
    cut_scores: list[float] = field(default_factory=list)
    shots: list[tuple[float, float]] = field(default_factory=list)
    fades: list[float] = field(default_factory=list)
    duration: float = 0.0
    frame_times: list[float] = field(default_factory=list)
    change_scores: list[float] = field(default_factory=list)

    @property
    def n_cuts(self) -> int:
        return len(self.cuts)

    def stats(self) -> dict:
        lengths = [e - s for s, e in self.shots]
        if not lengths:
            return {"avg_shot_len": None, "median_shot_len": None, "min_shot_len": None,
                    "max_shot_len": None, "cuts_per_minute": None, "shot_count": 0}
        return {
            "avg_shot_len": round(float(np.mean(lengths)), 3),
            "median_shot_len": round(float(np.median(lengths)), 3),
            "min_shot_len": round(float(np.min(lengths)), 3),
            "max_shot_len": round(float(np.max(lengths)), 3),
            "shot_count": len(lengths),
            "cuts_per_minute": round(self.n_cuts / self.duration * 60.0, 2) if self.duration else None,
        }


def _hist(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    return cv2.normalize(h, h).flatten()


def change_scores(frames: list[SampledFrame]) -> list[float]:
    """Per consecutive pair: 0..1-ish score of how much the image changed."""
    scores = [0.0]
    for prev, cur in zip(frames, frames[1:]):
        pix = float(np.mean(cv2.absdiff(prev.gray, cur.gray))) / 255.0
        hist = 1.0 - float(cv2.compareHist(_hist(prev.bgr.astype(np.uint8)),
                                           _hist(cur.bgr.astype(np.uint8)),
                                           cv2.HISTCMP_CORREL))
        scores.append(round(0.5 * min(1.0, pix * 4.0) + 0.5 * min(1.0, hist), 4))
    return scores


def detect_cuts(frames: list[SampledFrame], *, k: float = 5.0, abs_min: float = 0.22,
                min_shot: float = 0.30) -> ShotResult:
    """Find hard cuts. `frames` must be evenly spaced."""
    if not frames:
        return ShotResult()
    if len(frames) < 3:
        return ShotResult(shots=[(frames[0].t, frames[-1].t)],
                          duration=frames[-1].t, frame_times=[f.t for f in frames])

    scores = change_scores(frames)
    body = np.asarray(scores[1:], dtype=np.float64)
    median = float(np.median(body))
    mad = float(np.median(np.abs(body - median))) or 1e-4
    threshold = max(abs_min, median + k * 1.4826 * mad)

    cuts: list[float] = []
    cut_scores: list[float] = []
    for i in range(1, len(frames)):
        if scores[i] < threshold:
            continue
        t = frames[i].t
        if cuts and (t - cuts[-1]) < min_shot:
            if scores[i] > cut_scores[-1]:      # keep the stronger of the pair
                cuts[-1], cut_scores[-1] = t, scores[i]
            continue
        cuts.append(t)
        cut_scores.append(scores[i])

    fades: list[float] = []
    for i in range(1, len(frames)):
        # a fade is *not* a spike: several consecutive mid-level changes
        if threshold * 1.4 > scores[i] > abs_min * 0.55:
            fades.append(frames[i].t)

    times = [f.t for f in frames]
    duration = (times[-1] + (times[1] - times[0] if len(times) > 1 else 1.0))
    shots: list[tuple[float, float]] = []
    prev = 0.0
    for c in cuts:
        shots.append((round(prev, 3), round(c, 3)))
        prev = c
    shots.append((round(prev, 3), round(duration, 3)))

    return ShotResult(cuts=[round(c, 3) for c in cuts], cut_scores=cut_scores, shots=shots,
                      fades=[round(f, 3) for f in fades], duration=round(duration, 3),
                      frame_times=times, change_scores=scores)


def detect_from_video(path: str, *, fps: float = 6.0, width: int = 320,
                      max_seconds: float | None = None) -> ShotResult:
    from .frames import sample_video

    return detect_cuts(list(sample_video(path, fps=fps, width=width, max_seconds=max_seconds)))
