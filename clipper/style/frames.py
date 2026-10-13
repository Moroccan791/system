"""One streaming pass over a reference clip.

Sampling reduces a 60 s 1080x1920 clip to a few hundred small frames, which is
fast enough on a laptop and never holds the whole video in memory.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np

from ..ffmpeg import iter_frames, probe


@dataclass
class SampledFrame:
    index: int
    t: float
    bgr: np.ndarray
    gray: np.ndarray
    width: int   # size of the *source* frame
    height: int

    @property
    def scale_to_source(self) -> float:
        return self.height / self.gray.shape[0]


def sample_video(path: str, *, fps: float = 6.0, width: int = 320,
                 max_seconds: float | None = None) -> Iterator[SampledFrame]:
    """Yield (t, frame) pairs at `fps`, scaled to `width` px."""
    info = probe(path)
    if not info.width or not info.height:
        raise ValueError(f"cannot probe video: {path}")
    height = max(2, int(round(info.height * (width / info.width) / 2)) * 2)
    duration = info.duration if max_seconds is None else min(info.duration or 0, max_seconds)
    for i, frame in enumerate(iter_frames(path, size=(width, height), fps=fps, duration=duration)):
        gray = np.ascontiguousarray(
            frame[:, :, 0] * 0.114 + frame[:, :, 1] * 0.587 + frame[:, :, 2] * 0.299
        ).astype(np.uint8)
        yield SampledFrame(index=i, t=i / fps, bgr=frame, gray=gray,
                           width=info.width, height=info.height)
