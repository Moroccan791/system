"""Reframe map for a candidate window: where the 9:16 crop should sit,
segment by segment.

Multi-speaker sources cut between people sitting in different parts of
the landscape frame, and one global crop window cannot hold them all (it
will slice somebody's ear off mid-sentence). This scans the source's own
shot cuts and, for every segment, takes the median centre of the largest
face - which is who a viewer should be looking at - and converts it to
the `focus_x` the edit stage crops with (see edit.render.crop_offset).

The output is exactly the `segments` list a candidate can carry into
`edit.plan.build_plan`. Segments shorter than `min_seg` are merged into
the next one: reframing every half second looks like a seizure, not an
edit.

Detection is YuNet (assets/models/, see scripts/bootstrap.sh); when the
model or OpenCV is unavailable the cut boundaries are still returned,
just without focus values - the global focus then applies, as before.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .. import config
from ..ffmpeg import ffmpeg_exe, probe
from ..util import log

_MODEL = config.ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx"
_SCENE = 0.35


def crop_fraction(src_w: int, src_h: int, target=(9, 16)) -> float:
    """Width of the vertical crop as a fraction of the source width."""
    return (target[0] / target[1]) / (src_w / src_h)


def focus_for(centers: list[float], crop_frac: float) -> float | None:
    """Median face centre -> focus_x that centres it in the crop window.

    focus_x is the crop window's left edge as a fraction of the slack
    (1 - crop_frac): centre the face, clamp to what the frame allows.
    """
    if not centers:
        return None
    ordered = sorted(centers)
    cx = ordered[len(ordered) // 2]
    fx = (cx - crop_frac / 2) / (1 - crop_frac)
    return round(min(max(fx, 0.0), 1.0), 3)


def merge_bounds(bounds: list[float], min_seg: float) -> list[float]:
    """Drop internal boundaries that would leave a segment < min_seg."""
    merged = [bounds[0]]
    for t in bounds[1:-1]:
        if t - merged[-1] >= min_seg:
            merged.append(t)
    return merged + [bounds[-1]]


def scene_cuts(src: str | Path, start: float, end: float,
               threshold: float = _SCENE) -> list[float]:
    """The source's own shot boundaries inside [start, end] (ffmpeg scene
    detection; sub-second flashes at the window edges are ignored)."""
    p = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-ss", f"{start:.3f}", "-i", str(src),
         "-t", f"{end - start:.3f}", "-vf",
         f"select='gt(scene,{threshold})',showinfo",
         "-vsync", "vfr", "-f", "null", "-"],
        capture_output=True, text=True)
    times = [start + float(m) for m in re.findall(r"pts_time:([0-9.]+)", p.stderr)]
    return sorted({round(t, 2) for t in times if start + 0.3 < t < end - 0.2})


def _face_centers(src: str | Path, start: float, end: float, det) -> list[float]:
    """Largest-face centre (x fraction) sampled at 3 fps over the span."""
    import cv2
    import numpy as np

    p = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-ss", f"{start:.3f}",
         "-i", str(src), "-t", f"{end - start:.3f}", "-vf", "fps=3,scale=960:540",
         "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
    buf, centers, i = p.stdout, [], 0
    while True:
        j = buf.find(b"\x89PNG", i)
        if j < 0:
            break
        k = buf.find(b"IEND", j)
        if k < 0:
            break
        img = cv2.imdecode(np.frombuffer(buf[j:k + 8], np.uint8), cv2.IMREAD_COLOR)
        i = k + 8
        if img is None:
            continue
        det.setInputSize((img.shape[1], img.shape[0]))
        _, faces = det.detect(img)
        if faces is not None and len(faces):
            f = max(faces, key=lambda f: f[2] * f[3])
            centers.append(float((f[0] + f[2] / 2) / img.shape[1]))
    return centers


def _detector():
    try:
        import cv2
    except ImportError:
        return None
    if not _MODEL.exists():
        log.warn("yunet model missing - reframe returns cuts without focus",
                 model=str(_MODEL))
        return None
    return cv2.FaceDetectorYN.create(str(_MODEL), "", (960, 540), 0.6, 0.3, 50)


def reframe_map(src: str | Path, start: float, end: float, *,
                min_seg: float = 1.1, threshold: float = _SCENE) -> list[dict]:
    """Segments tiling [start, end], each with its own crop focus_x."""
    info = probe(src)
    frac = crop_fraction(info.width, info.height)
    bounds = merge_bounds([start] + scene_cuts(src, start, end, threshold) + [end],
                          min_seg)
    det = _detector()
    segments = []
    for s0, s1 in zip(bounds, bounds[1:]):
        seg = {"start": round(s0, 3), "end": round(s1, 3)}
        if det is not None:
            fx = focus_for(_face_centers(src, s0, s1, det), frac)
            if fx is not None:
                seg["focus_x"] = fx
        segments.append(seg)
    log.info("reframe map", segments=len(segments),
             focused=sum(1 for s in segments if "focus_x" in s))
    return segments
