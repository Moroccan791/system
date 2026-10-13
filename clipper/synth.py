"""Synthetic footage generators with *exact* ground truth.

Tests need references whose cut points, zoom trajectory and caption style are
known by construction. FFmpeg's scale/crop filters evaluate their size
expressions once, so an ffmpeg-authored "zoom" is not reliable - these helpers
render frames in numpy/cv2 and pipe them to the encoder instead.

Used by tests and by `python -m clipper samples`.
"""
from __future__ import annotations

import subprocess
from typing import Sequence

import cv2
import numpy as np

from .ffmpeg import ffmpeg_exe


def textured_scene(width: int = 1080, height: int = 1920, seed: int = 7,
                   palette: Sequence[tuple[int, int, int]] = (
                       (30, 40, 60), (70, 90, 130), (200, 200, 210), (90, 140, 90))) -> np.ndarray:
    """A deterministic, feature-rich frame: grid, blobs, edges, mild noise.

    Zoom/cut detectors need spatial structure to lock onto; a flat colour would
    make their measurements meaningless (and they say so, by returning a low
    response).
    """
    rng = np.random.default_rng(seed)
    img = np.zeros((height, width, 3), dtype=np.uint8)
    # vertical gradient background
    for c in range(3):
        img[:, :, c] = np.linspace(palette[0][c], palette[1][c], height, dtype=np.uint8)[:, None]
    # grid
    step = max(24, width // 16)
    for x in range(0, width, step):
        img[:, x:x + 2] = palette[2]
    for y in range(0, height, step):
        img[y:y + 2, :] = palette[2]
    # blobs and rectangles
    for _ in range(28):
        x, y = int(rng.integers(0, width)), int(rng.integers(0, height))
        r = int(rng.integers(step // 2, step * 2))
        color = tuple(int(v) for v in palette[rng.integers(0, len(palette))])
        cv2.circle(img, (x, y), r, color, -1)
        cv2.rectangle(img, (x + r, y - r // 2), (x + r + step, y + r // 2),
                      tuple(int(v) for v in palette[rng.integers(0, len(palette))]), -1)
    # high-frequency detail so NCC has something to lock onto
    noise = rng.normal(0, 14, (height, width, 1)).astype(np.float32)
    img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return img


def zoom_frame(base: np.ndarray, scale: float) -> np.ndarray:
    """Centre crop-and-magnify: content grows by `scale`, output size unchanged."""
    h, w = base.shape[:2]
    if abs(scale - 1.0) < 1e-6:
        return base
    sw, sh = int(round(w * scale)), int(round(h * scale))
    big = cv2.resize(base, (sw, sh), interpolation=cv2.INTER_LINEAR)
    x0, y0 = (sw - w) // 2, (sh - h) // 2
    return big[y0:y0 + h, x0:x0 + w]


def write_video(path: str, frames, *, fps: int = 30,
                audio_source: str | None = None, crf: int = 20,
                preset: str = "veryfast") -> str:
    """Encode BGR frames (list or generator, all the same size) into an mp4.

    Accepts a generator so long clips never have to be held in memory.
    """
    it = iter(frames)
    try:
        first = next(it)
    except StopIteration:
        raise ValueError("no frames")
    h, w = first.shape[:2]
    args = [ffmpeg_exe(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
    if audio_source:
        args += ["-f", "lavfi", "-i", audio_source, "-shortest"]
    args += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"]
    args += ["-c:a", "aac", "-b:a", "128k"] if audio_source else ["-an"]
    args += ["-movflags", "+faststart", path]
    proc = subprocess.Popen(args, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for frame in (first, *it):
        proc.stdin.write(np.ascontiguousarray(frame).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"encoding failed for {path}")
    return path


def render_zoom_clip(path: str, *, duration: float = 3.0, fps: int = 30,
                     punch_scale: float = 1.15, punch_over: float = 0.3,
                     cut_at: Sequence[float] = (), size: tuple[int, int] = (1080, 1920),
                     seed: int = 7, audio_source: str | None = None) -> dict:
    """A clip whose zoom trajectory is known exactly.

    `punch_scale` is reached over `punch_over` seconds, then held for the rest
    of each shot; `cut_at` starts a new shot (and a new punch-in) at those times.
    """
    w, h = size
    base = textured_scene(w, h, seed=seed)
    cuts = sorted(cut_at)
    n = int(duration * fps)

    def frames():
        for i in range(n):
            t = i / fps
            shot_start = max([0.0] + [c for c in cuts if c <= t])
            elapsed = t - shot_start
            scale = (1.0 + (punch_scale - 1.0) * min(1.0, elapsed / punch_over)
                     if punch_over > 0 else punch_scale)
            yield zoom_frame(base, scale)

    write_video(path, frames(), fps=fps, audio_source=audio_source)
    return {"path": path, "punch_scale": punch_scale, "punch_over": punch_over,
            "cuts": cuts, "duration": duration, "fps": fps}


def render_cut_clip(path: str, *, shots: Sequence[float] = (2.0, 2.0, 2.0), fps: int = 30,
                    size: tuple[int, int] = (1080, 1920), seed: int = 11,
                    audio_source: str | None = None) -> dict:
    """Hard cuts between visually distinct static scenes; cut times known exactly."""
    w, h = size
    cut_times: list[float] = []
    t = 0.0
    for i, length in enumerate(shots):
        if i < len(shots) - 1:
            t += length
            cut_times.append(round(t, 4))

    def frames():
        for i, length in enumerate(shots):
            base = textured_scene(w, h, seed=seed + i * 13)
            for _ in range(int(length * fps)):
                yield base

    write_video(path, frames(), fps=fps, audio_source=audio_source)
    return {"path": path, "cuts": cut_times, "duration": t, "fps": fps,
            "shots": list(shots)}
