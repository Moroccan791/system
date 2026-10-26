"""Grading: one look across the whole edit, and one look that feels expensive.

Two separate jobs, and they were being confused:

  * **matching** — a scenepack is not one film. It is 37 shots grabbed from a
    movie, so the daylight hallway is warm, the rooftop is cyan, and the interior
    is green. Cutting between them ungraded reads as *assembled*, not *made*.
    Every cut is pulled toward the pack's own median, with a hard cap, so the
    edit has one colour temperature without flattening a shot that was lit
    differently on purpose.

  * **the look** — a filmic curve (slightly lifted blacks, rolled highlights),
    a split tone (cool shadows, warm highlights), a touch of saturation and a
    soft vignette. This is what "premium" means in practice: no crushed blacks,
    no clipped highlights, and the eye pulled to the centre of the frame.

Everything is a 256-entry lookup table plus one multiply, so a 1080p frame costs
a couple of milliseconds. A per-pixel float pipeline here would double the
render time for output nobody can tell apart.

The numbers are deliberately conservative. An edit that is obviously graded is
dated in eighteen months; one that is quietly graded still looks right.
"""
from __future__ import annotations

import subprocess

import numpy as np

LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

# act -> (curve strength, shadow tint, highlight tint, saturation, vignette)
LOOK = {
    "build": (0.30, (0.975, 0.995, 1.035), (1.045, 1.010, 0.965), 0.94, 0.10),
    "drop":  (0.38, (0.965, 0.990, 1.050), (1.060, 1.015, 0.950), 1.08, 0.14),
    "out":   (0.26, (0.985, 0.995, 1.020), (1.030, 1.010, 0.985), 0.18, 0.12),
}

MAX_GAIN = 0.16      # a shot may move at most 16% in mean, per channel
MAX_LIFT = 12.0      # ...and 12/255 in offset


# ---------------------------------------------------------------------------
# measurement
# ---------------------------------------------------------------------------
def thumbnails(src: str, fps: float = 3.0, width: int = 160):
    """Cheap pass over the source: small frames + their timestamps.

    One ffmpeg call, no seeking. At 3 fps and 160px wide a two-minute pack reads
    in about a second, which is why matching can afford to look at every shot
    instead of trusting a single sampled frame.
    """
    import imageio_ffmpeg

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.run(
        [ff, "-nostdin", "-v", "error", "-i", str(src),
         "-vf", f"fps={fps},scale={width}:-2", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-"], capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        return np.zeros(0, dtype=np.float32), np.zeros((0, 1, 1, 3), dtype=np.uint8)
    probe = subprocess.run(
        [ff, "-hide_banner", "-i", str(src)], capture_output=True, text=True).stderr
    h = None
    for line in probe.splitlines():
        if "Video:" in line and "x" in line:
            for tok in line.split():
                if "x" in tok and tok.replace("x", "").isdigit():
                    w_, h_ = tok.split("x")
                    h = max(2, int(round(width * int(h_) / int(w_)) // 2 * 2))
                    break
            break
    if h is None:
        return np.zeros(0, dtype=np.float32), np.zeros((0, 1, 1, 3), dtype=np.uint8)
    buf = np.frombuffer(proc.stdout, dtype=np.uint8)
    n = buf.size // (width * h * 3)
    frames = buf[: n * width * h * 3].reshape(n, h, width, 3)
    times = np.arange(n, dtype=np.float32) / fps
    return times, frames


def stats(times, frames, src) -> dict[int, dict]:
    """Per-shot colour statistics, from the thumbnails only."""
    out: dict[int, dict] = {}
    if frames.size == 0:
        return out
    f = frames.astype(np.float32)
    mean = f.reshape(len(f), -1, 3).mean(axis=1)          # (n, 3)
    luma = (f * LUMA).sum(axis=3).reshape(len(f), -1)
    for shot in getattr(src, "shots", []):
        sel = (times >= shot.src_in) & (times < shot.src_out)
        if not sel.any():
            continue
        out[shot.index] = {
            "mean": mean[sel].mean(axis=0),
            "p10": float(np.percentile(luma[sel], 10)),
            "p50": float(np.percentile(luma[sel], 50)),
            "p90": float(np.percentile(luma[sel], 90)),
        }
    return out


def target_for(per_shot: dict[int, dict], used: list[int]) -> dict | None:
    """The pack's own median, weighted by how much of it the edit actually uses."""
    rows = [per_shot[i] for i in used if i in per_shot]
    if not rows:
        return None
    means = np.stack([r["mean"] for r in rows])
    return {
        "mean": np.median(means, axis=0),
        "p50": float(np.median([r["p50"] for r in rows])),
    }


def correction(stat: dict | None, target: dict | None):
    """Gain and offset that pull one shot toward the pack, capped."""
    if not stat or not target:
        return None
    tgt = target["mean"]
    cur = np.maximum(stat["mean"], 1.0)
    gain = np.clip(tgt / cur, 1.0 - MAX_GAIN, 1.0 + MAX_GAIN)
    # A dark shot stays a dark shot: half the luma difference is corrected as an
    # offset, and only up to MAX_LIFT, so night does not become day.
    d_luma = (target["p50"] - stat["p50"]) * 0.35
    off = np.clip(d_luma, -MAX_LIFT, MAX_LIFT)
    return gain.astype(np.float32), np.float32(off)


def apply_correction(frame: np.ndarray, corr) -> np.ndarray:
    if corr is None:
        return frame
    gain, off = corr
    f = frame.astype(np.float32) * gain + off
    return np.clip(f, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# the look
# ---------------------------------------------------------------------------
_LUT: dict[str, np.ndarray] = {}
_VIG: dict[tuple, np.ndarray] = {}


def _curve(strength: float, lift: float = 0.012) -> np.ndarray:
    """Smoothstep contrast with lifted blacks and rolled highlights.

    `lift` is the toe of the curve. The default 0.012 is right for a pack that
    is already correctly exposed. On a very dark pack it is wrong: the curve
    holds the shadows where they are and the edit reads as mush, so the caller
    can raise the toe instead of pretending the footage is brighter than it is.
    """
    x = np.linspace(0.0, 1.0, 256, dtype=np.float32)
    s = x * x * (3.0 - 2.0 * x)                 # contrast, no clipping
    y = x * (1.0 - strength) + s * strength
    lift = min(max(lift, 0.0), 0.20)
    y = lift + y * (0.985 - lift)               # lift the toe, cap the shoulder
    return np.clip(y, 0.0, 1.0)


def lut(act: str, lift: float = 0.012) -> np.ndarray:
    key = act if abs(lift - 0.012) < 1e-6 else f"{act}@{lift:.3f}"
    if key in _LUT:
        return _LUT[key]
    strength, shadow, high, sat, _vig = LOOK.get(act, LOOK["drop"])
    base = _curve(strength, lift)               # (256,) 0..1
    xs = (base * 255.0)[:, None]                # (256, 1)
    # split tone: weights by how dark the value is
    dark = np.clip(1.0 - (xs / 120.0), 0.0, 1.0)
    light = np.clip((xs - 120.0) / 135.0, 0.0, 1.0)
    sh = np.array(shadow, dtype=np.float32)[None, :]
    hi = np.array(high, dtype=np.float32)[None, :]
    rgb = xs * (1.0 + (sh - 1.0) * dark + (hi - 1.0) * light)
    # saturation around the curve's own luma
    lum = (rgb * LUMA[None, :]).sum(axis=1, keepdims=True)
    rgb = lum + (rgb - lum) * sat
    _LUT[key] = np.clip(rgb, 0, 255).astype(np.uint8)      # (256, 3)
    return _LUT[key]


def vignette(h: int, w: int, strength: float) -> np.ndarray:
    key = (h, w, round(strength, 3))
    if key in _VIG:
        return _VIG[key]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    r = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2) / np.sqrt(2.0)
    v = 1.0 - strength * np.clip(r, 0.0, 1.0) ** 2.2
    _VIG[key] = np.clip(v * 256.0, 0, 256).astype(np.uint16)[..., None]
    return _VIG[key]


def premium(frame: np.ndarray, act: str, lift: float = 0.012) -> np.ndarray:
    """The look, one LUT and one multiply."""
    table = lut(act, lift)                # (256, 3)
    out = np.empty(frame.shape, dtype=np.uint8)
    for c in range(3):
        out[..., c] = table[:, c][frame[..., c]]
    vig = vignette(frame.shape[0], frame.shape[1], LOOK.get(act, LOOK["drop"])[4])
    # fixed-point multiply: uint16 is ~3x faster than float32 on this buffer and
    # the error is under one code value, which is below the grain anyway.
    out = ((out.astype(np.uint16) * vig) >> 8).astype(np.uint8)
    return out


# ---------------------------------------------------------------------------
# how much a pack needs lifting
# ---------------------------------------------------------------------------
def lift_for(median_luma: float) -> float:
    """The curve toe a pack needs, from its own median luma.

    A correctly exposed pack sits around 90-110 of 255 and needs the default
    toe. The Ghost montage has a median of **16-20**, which is not a look, it is
    an underexposure: the standard grade was taking it DOWN to 14 and the
    shadow detail went with it. The lift is deliberately capped — this opens
    the shadows and keeps the blacks black, it does not pretend the scene was
    lit.

    Calibrated so that a median of 20 lands near a toe of 0.06, which is the
    most that can be lifted before night starts reading as grey.
    """
    m = max(1.0, float(median_luma))
    # 0 below ~75, rising to the cap as the pack gets darker
    need = max(0.0, (75.0 - m) / 75.0)
    return round(min(0.065, 0.065 * need), 4)
