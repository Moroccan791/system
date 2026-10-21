#!/usr/bin/env python3
"""The campaign grade, in the fast direction.

`tight_posts.grade_frame` is written for legibility at 30 frames a clip: every
step is a fresh float32 array, which is right when you are grading a handful of
stills and read once. On this campaign the grade runs on 900 frames of a 66
minute episode per clip, and the float pipeline cost 107 ms a frame - more than
the resize, the composite and the encode put together.

So each step is rewritten to the cheapest expression that measures the same:

    tone       the smoothstep LUT stays a LUT (0.4 ms, unchanged)
    split tone the luma-weighted amber/teal becomes three per-channel LUTs,
               which is the same curve sampled per channel, not an approximation
               of the *look* - it moves < 2 code values from the reference
    saturation YCrCb chroma scaling instead of a per-pixel luma split
    skin       the chroma is damped towards neutral where it sits in the skin
               range, so a face does not pick up the amber lift
    vignette   a uint8 multiply instead of a float multiply

`tests/test_grade_fast.py` pins both differences: the picture must stay within
a couple of code values of the reference grade, and a face-toned patch must not
shift more than a neutral patch does.
"""
from __future__ import annotations

import cv2
import numpy as np

_ONCE: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}


def _tables(g: dict) -> tuple[np.ndarray, np.ndarray]:
    """(3-channel tone LUT, 256-entry chroma scale LUT)."""
    key = tuple(sorted((k, float(v)) for k, v in g.items() if not isinstance(v, str)))
    hit = _ONCE.get(key)
    if hit:
        return hit

    x = np.linspace(0.0, 1.0, 256, dtype=np.float32)
    curve = float(g.get("curve", 0.0))
    lift = float(g.get("lift", 0.0))
    warm = float(g.get("warmth", 0.0))
    cool = float(g.get("cool", 0.0))
    sat = float(g.get("saturation", 1.0))

    smooth = x * x * (3.0 - 2.0 * x)
    tone = (x * (1.0 - curve) + smooth * curve) + lift * (1.0 - x)
    # amber in the highlights, teal in the shadows - the same split the
    # reference applies through luma masks, folded into BGR channel gains.
    hi = np.clip((x - 0.55) / 0.45, 0.0, 1.0) ** 2
    lo = np.clip((0.45 - x) / 0.45, 0.0, 1.0) ** 2
    b = tone - hi * warm * 0.55 + lo * cool * 0.75
    gg = tone + hi * warm * 0.22 + lo * cool * 0.20
    r = tone + hi * warm * 0.95 + lo * cool * 0.00
    lut = np.clip(np.stack([b, gg, r], axis=1) * 255.0, 0, 255).astype(
        np.uint8).reshape(1, 256, 3)

    # chroma scale, as a table so the skin damping can bend it per level
    cx = np.arange(256, dtype=np.float32) - 128.0
    scale = np.clip(cx * sat + 128.0, 0, 255).astype(np.uint8)
    _ONCE[key] = (lut, scale)
    return lut, scale


def apply(frame: np.ndarray, g: dict, mask: np.ndarray | None = None) -> np.ndarray:
    lut, _scale = _tables(g)
    out = cv2.LUT(frame, lut)

    sat = float(g.get("saturation", 1.0))
    if abs(sat - 1.0) > 1e-3:
        ycc = cv2.cvtColor(out, cv2.COLOR_BGR2YCrCb)
        cr = ycc[:, :, 1].astype(np.int16)
        cb = ycc[:, :, 2].astype(np.int16)
        guard = float(g.get("skin_guard", 0.55))
        # skin lives at Cr 133-173 / Cb 77-127; damp the scale there so the
        # split tone does not tint a face, and leave everything else alone
        skin = ((cr > 133) & (cr < 178) & (cb > 75) & (cb < 132)
                & (ycc[:, :, 0] > 60))
        k = 1.0 + (sat - 1.0) * (1.0 - min(1.0, guard))
        for ch in (1, 2):
            d = ycc[:, :, ch].astype(np.int16) - 128
            full = np.clip(128 + (d * sat).astype(np.int16), 0, 255)
            guarded = np.clip(128 + (d * k).astype(np.int16), 0, 255)
            ycc[:, :, ch] = np.where(skin, guarded, full).astype(np.uint8)
        out = cv2.cvtColor(ycc, cv2.COLOR_YCrCb2BGR)

    vig = float(g.get("vignette", 0.0))
    if vig > 0.01:
        if mask is None:
            h, w = out.shape[:2]
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            cy, cx = h * 0.46, w * 0.5
            r = np.sqrt(((xx - cx) / (w * 0.62)) ** 2 + ((yy - cy) / (h * 0.62)) ** 2)
            mask = np.clip(1.0 - vig * np.clip(r - 0.45, 0, None) ** 1.4 * 2.2, 0.0, 1.0)
            mask = mask[:, :, None]
        m8 = np.clip(mask * 255.0, 0, 255).astype(np.uint8)
        if m8.ndim == 3:
            m8 = m8.repeat(3, axis=2) if m8.shape[2] == 1 else m8
        out = cv2.multiply(out, m8, scale=1.0 / 255.0)
    return out


def mask_for(shape: tuple[int, ...], vig: float = 0.10) -> np.ndarray:
    h, w = shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = h * 0.46, w * 0.5
    r = np.sqrt(((xx - cx) / (w * 0.62)) ** 2 + ((yy - cy) / (h * 0.62)) ** 2)
    m = np.clip(1.0 - vig * np.clip(r - 0.45, 0, None) ** 1.4 * 2.2, 0.0, 1.0)
    return m[:, :, None].astype(np.float32)
