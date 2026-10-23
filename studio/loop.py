"""The loop: an edit whose last frame is its first frame.

Why it is worth building: a loop plays forever without a seam, so the platform
sees a viewer who never leaves. That is the one metric that reliably moves reach,
and it is a property of the FOOTAGE, not of a filter — either the pack contains a
shot that ends where it began, or the edit cannot loop.

Finding one is mechanical. A moving shot has pixels that travel; a shot built for
a loop returns to them. So the test is: take the first and last usable frame of
a shot and ask how far the image moved between them, compared with how far it
moves between the first frame and a frame from the middle. A loop shot's
start-to-end distance is SMALLER than its start-to-middle distance — the eye
can tell, and so can a sum of absolute differences.

This is a detector, not a generator: it cannot make a shot loop that does not.
It reports what is there, with the score, so the choice stays a decision rather
than a guess.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class LoopCandidate:
    shot: int
    src_in: float          # where to start the cut
    src_out: float         # where to end it
    span: float
    score: float           # end-vs-start distance / mid-vs-start distance
    note: str = ""

    def as_dict(self) -> dict:
        return {"shot": self.shot, "src_in": round(self.src_in, 3),
                "src_out": round(self.src_out, 3), "span": round(self.span, 3),
                "score": round(self.score, 3), "note": self.note}


def _grey(src: str, t: float, w: int = 96, h: int = 54) -> np.ndarray | None:
    import imageio_ffmpeg

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    raw = subprocess.run([ff, "-nostdin", "-v", "error", "-ss", f"{max(0.0, t):.3f}",
                          "-i", src, "-frames:v", "1",
                          "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    if len(raw) < w * h:
        return None
    return np.frombuffer(raw[:w * h], dtype=np.uint8).reshape(h, w).astype(np.float32)


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean() / 255.0)


def find(src: str | Path, shots: list, min_span: float = 1.2,
         max_span: float = 6.0, keep: int = 6) -> list[LoopCandidate]:
    """Rank the shots by how well they close on themselves."""
    src = str(src)
    out: list[LoopCandidate] = []
    for s in shots:
        dur = min(max_span, s.dur)
        if dur < min_span:
            continue
        first = _grey(src, s.src_in + 0.08)
        mid = _grey(src, s.src_in + dur / 2.0)
        last = _grey(src, s.src_in + dur - 0.12)
        if first is None or mid is None or last is None:
            continue
        d_mid = _dist(first, mid)
        d_end = _dist(first, last)
        if d_mid <= 1e-4:
            # a static shot loops trivially and is worthless for a loop edit:
            # there is nothing to notice repeating
            continue
        score = d_end / d_mid
        note = ("closes on itself" if score < 0.55 else
                "drifts back" if score < 0.85 else "travels")
        out.append(LoopCandidate(s.index, s.src_in + 0.08, s.src_in + dur - 0.12,
                                 dur - 0.20, score, note))
    out.sort(key=lambda c: c.score)
    return out[:keep]


def report(cands: list[LoopCandidate]) -> str:
    if not cands:
        return "loop: no shot in this pack closes on itself — build this one as a cut edit"
    lines = ["loop candidates (lower score = better):"]
    for c in cands:
        lines.append(f"  shot {c.shot:3d}  {c.src_in:7.2f}-{c.src_out:7.2f}  "
                     f"{c.span:4.2f}s  score {c.score:.2f}  {c.note}")
    return "\n".join(lines)
