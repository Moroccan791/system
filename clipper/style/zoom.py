"""Zoom / punch-in detection.

Editors open a shot with a fast punch-in (1.08-1.20x in ~0.2-0.4 s) or a slow
push across the whole shot. We measure the *relative scale* between consecutive
sampled frames by matching a centre template from frame A inside frame B at
several candidate scales, then read the trajectory of the cumulative scale
inside each shot.

Template matching is used instead of log-polar phase correlation on purpose:
it needs no sign conventions, and NCC gives a response we can threshold for
honesty ("I cannot measure this frame" is a valid answer).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .frames import SampledFrame

DEFAULT_SCALES = np.arange(0.90, 1.36, 0.01)


@dataclass
class ZoomResult:
    pattern: str = "unknown"          # static | punch_in | slow_push | mixed
    scale: float | None = None        # punch-in magnitude, e.g. 1.14
    duration: float | None = None     # seconds to reach it
    median_shot_zoom: float | None = None
    confidence: float = 0.0
    per_shot: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dominant": self.pattern,
            "punch_in_scale": self.scale,
            "punch_in_duration": self.duration,
            "median_shot_zoom": self.median_shot_zoom,
            "confidence": round(self.confidence, 3),
            "per_shot": self.per_shot,
        }


def _square(gray: np.ndarray, size: int) -> np.ndarray:
    h, w = gray.shape
    s = min(h, w)
    y0, x0 = (h - s) // 2, (w - s) // 2
    crop = gray[y0:y0 + s, x0:x0 + s]
    return cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0


def estimate_scale(a_gray: np.ndarray, b_gray: np.ndarray, *,
                   scales: np.ndarray | None = None, size: int = 256,
                   tmpl_ratio: float = 0.5, search: int = 10) -> tuple[float, float]:
    """How much did the image zoom between a and b? Returns (scale, response).

    scale > 1 means content grew (punch-in), < 1 means it shrank (pull-out).
    response is NCC in [0, 1]; below ~0.35 the measurement is meaningless.

    Both frames are normalised to the same square canvas first, so the same
    scene content occupies `scale` times more pixels in b. To compare, the
    region of b that holds that content (t*scale px) is resized back down to the
    template size (t px): the two patches are then at the same pixel scale and
    NCC is meaningful.
    """
    scales = DEFAULT_SCALES if scales is None else scales
    A = _square(a_gray, size)
    B = _square(b_gray, size)
    t = int(size * tmpl_ratio)
    y0 = (size - t) // 2
    tmpl = A[y0:y0 + t, y0:y0 + t]
    if float(tmpl.std()) < 1e-3:     # flat frame, nothing to track
        return 1.0, 0.0

    target = t + 2 * search          # resized search region (same px scale as A)
    if target > size:
        return 1.0, 0.0
    best_s, best_r = 1.0, -1.0
    for s in scales:
        w = int(round(t * float(s))) + 2 * search
        if w < 24 or w > size:
            continue
        x0 = (size - w) // 2
        window = B[x0:x0 + w, x0:x0 + w]
        region = cv2.resize(window, (target, target), interpolation=cv2.INTER_LINEAR)
        if region.shape[0] < t or region.shape[1] < t:
            continue
        res = cv2.matchTemplate(region, tmpl, cv2.TM_CCOEFF_NORMED)
        _, maxv, _, _ = cv2.minMaxLoc(res)
        if maxv > best_r:
            best_s, best_r = float(s), float(maxv)
    return best_s, max(0.0, min(1.0, best_r))


def _classify(trajectory: list[tuple[float, float]]) -> dict:
    """trajectory: (t_relative, scale_relative_to_shot_start) inside one shot."""
    if len(trajectory) < 3:
        return {"pattern": "unknown", "scale": None, "duration": None, "confidence": 0.0}
    times = np.array([t for t, _ in trajectory])
    scales = np.array([s for _, s in trajectory])
    total = float(scales[-1] - scales[0])
    span = float(times[-1] - times[0]) or 1e-3

    # gain inside the first 0.6 s vs the rest (a punch-in front-loads its zoom)
    early = scales[times <= 0.6]
    early_gain = float(early[-1] - scales[0]) if len(early) > 1 else 0.0
    late_gain = total - early_gain

    if abs(total) < 0.04 and abs(early_gain) < 0.04:
        return {"pattern": "static", "scale": 1.0, "duration": None, "confidence": 0.7}
    if abs(early_gain) >= 0.05 and abs(late_gain) <= max(0.04, abs(early_gain) * 0.5):
        target = scales[0] + early_gain * 0.95
        within = np.where(scales >= target)[0] if early_gain > 0 else np.where(scales <= target)[0]
        idx = int(within[0]) if len(within) else min(len(times) - 1, 1)
        return {"pattern": "punch_in" if early_gain > 0 else "pull_out",
                "scale": round(1.0 + early_gain, 3),
                "duration": round(float(times[idx]), 3),
                "confidence": min(1.0, 0.4 + abs(early_gain) * 4)}
    if abs(total) >= 0.05 and span >= 0.8 and abs(total / span) < 0.6:
        return {"pattern": "slow_push" if total > 0 else "slow_pull",
                "scale": round(1.0 + total, 3), "duration": round(span, 3),
                "confidence": min(1.0, 0.3 + abs(total) * 3)}
    return {"pattern": "mixed", "scale": round(1.0 + total, 3), "duration": round(span, 3),
            "confidence": 0.25}


def analyze_zoom(frames: list[SampledFrame], cuts: list[float], *,
                 response_min: float = 0.35, size: int = 200,
                 deadband: float = 0.004) -> ZoomResult:
    """Measure zoom inside every shot and summarise the dominant pattern.

    Every frame is compared against the *first frame of its shot* rather than
    against its predecessor: chaining consecutive ratios accumulates NCC noise
    into a fake slow zoom, which is exactly the failure mode that matters here.
    """
    if len(frames) < 3:
        return ZoomResult()
    cut_set = {round(c, 2) for c in cuts}
    shots: list[dict] = []
    current: list[tuple[float, float]] = []
    reference: SampledFrame | None = None

    for frame in frames:
        if reference is None or (frame.index and round(frame.t, 2) in cut_set):
            if len(current) >= 3:
                shots.append(_classify(current))
            current = []
            reference = frame
            t0 = frame.t
        scale, response = estimate_scale(reference.gray, frame.gray, size=size)
        ok = response >= response_min and abs(scale - 1.0) >= deadband
        current.append((round(frame.t - t0, 3), round(scale if ok else 1.0, 4)))
    if len(current) >= 3:
        shots.append(_classify(current))

    if not shots:
        return ZoomResult()
    counts: dict[str, int] = {}
    for s in shots:
        counts[s["pattern"]] = counts.get(s["pattern"], 0) + 1
    dominant = max(counts, key=lambda k: (counts[k], k != "static"))
    punches = [s for s in shots if s["pattern"] == "punch_in" and s["scale"]]
    scales = [s["scale"] for s in punches]
    durations = [s["duration"] for s in punches if s["duration"]]
    confidence = float(np.mean([s["confidence"] for s in shots]))
    return ZoomResult(
        pattern=dominant,
        scale=round(float(np.median(scales)), 3) if scales else None,
        duration=round(float(np.median(durations)), 3) if durations else None,
        median_shot_zoom=round(float(np.median([s["scale"] for s in shots if s["scale"]])), 3)
        if any(s["scale"] for s in shots) else None,
        confidence=round(confidence, 3),
        per_shot=[{**s, "n": counts.get(s["pattern"], 0)} for s in shots][:12],
    )
