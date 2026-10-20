#!/usr/bin/env python3
"""The "After Effects" moves, as code.

The user asked whether the six things they associate with AE - kinetic type,
bespoke motion, face-tracked masks/roto, light wraps, 3D camera moves, custom
transitions - can be done without AE. They can. Every one of them is a
per-frame image operation, and this module is that operation, one function
each, in the same style as the rest of the pipeline (numpy in, numpy out, no
GUI, deterministic, testable).

What is genuinely lost without AE: a timeline you can drag, real-time
scrubbing, and third-party plugins. What is gained: these run in a batch,
reproducibly, from JSON, and they can be asserted in tests.

Honest limits are marked LIMIT in the docstrings - a face ellipse is not a
full-body roto, and a trapezoid warp is not a 3D scene.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920


# --------------------------------------------------------------- easings
def spring(t: float, *, freq: float = 13.0, damp: float = 7.0) -> float:
    """A damped-oscillator step: 0 -> ~1.1 -> 1.0.

    This is the whole difference between "the word appeared" and "the word
    landed". Linear or ease-out has no weight; a spring overshoots and settles,
    which is what motion-graphics people mean by polish.
    """
    if t <= 0:
        return 0.0
    return 1.0 - math.exp(-damp * t) * math.cos(freq * t)


def ease_out_cubic(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1.0 - (1.0 - t) ** 3


# --------------------------------------------------------------- sprites
@lru_cache(maxsize=256)
def word_sprite(word: str, font_path: str, size: int, rgb: tuple[int, int, int],
                stroke: int = 6) -> tuple[np.ndarray, np.ndarray]:
    """Render one word once, then scale it per frame.

    Rasterising text through PIL every frame at 60 different sizes is the slow
    way; caching the glyphs and resampling the sprite is ~30x faster and, at
    these sizes, indistinguishable.
    """
    font = ImageFont.truetype(font_path, size)
    pad = stroke * 2 + 12
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    tw = int(probe.textlength(word, font=font))
    th = int(size * 1.25)
    img = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((pad, pad), word, font=font, fill=rgb + (255,),
           stroke_width=stroke, stroke_fill=(0, 0, 0, 170))
    arr = np.asarray(img)
    return arr[:, :, :3][:, :, ::-1].copy(), arr[:, :, 3].copy()   # BGR, alpha


def blit(frame: np.ndarray, rgb_bgr: np.ndarray, alpha: np.ndarray,
         center: tuple[float, float], scale: float = 1.0,
         rotation: float = 0.0, opacity: float = 1.0) -> np.ndarray:
    """Composite a sprite with scale, rotation and opacity."""
    if scale <= 0.01 or opacity <= 0.01:
        return frame
    sprite = rgb_bgr
    a = alpha
    if abs(scale - 1.0) > 0.005:
        nw = max(1, int(sprite.shape[1] * scale))
        nh = max(1, int(sprite.shape[0] * scale))
        sprite = cv2.resize(sprite, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        a = cv2.resize(a, (nw, nh), interpolation=cv2.INTER_LINEAR)
    if abs(rotation) > 0.05:
        hh, ww = sprite.shape[:2]
        diag = int(math.hypot(hh, ww)) + 4
        canvas = np.zeros((diag, diag, 3), np.uint8)
        acan = np.zeros((diag, diag), np.uint8)
        y0, x0 = (diag - hh) // 2, (diag - ww) // 2
        canvas[y0:y0 + hh, x0:x0 + ww] = sprite
        acan[y0:y0 + hh, x0:x0 + ww] = a
        m = cv2.getRotationMatrix2D((diag / 2, diag / 2), rotation, 1.0)
        sprite = cv2.warpAffine(canvas, m, (diag, diag), flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        acan = cv2.warpAffine(acan, m, (diag, diag), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        a = acan

    hh, ww = sprite.shape[:2]
    cx, cy = int(center[0]), int(center[1])
    x0, y0 = cx - ww // 2, cy - hh // 2
    fx0, fy0 = max(0, x0), max(0, y0)
    fx1, fy1 = min(frame.shape[1], x0 + ww), min(frame.shape[0], y0 + hh)
    if fx1 <= fx0 or fy1 <= fy0:
        return frame
    sx0, sy0 = fx0 - x0, fy0 - y0
    part = sprite[sy0:sy0 + (fy1 - fy0), sx0:sx0 + (fx1 - fx0)].astype(np.float32)
    pa = (a[sy0:sy0 + (fy1 - fy0), sx0:sx0 + (fx1 - fx0)].astype(np.float32) / 255.0)[:, :, None]
    pa = pa * opacity
    dst = frame[fy0:fy1, fx0:fx1].astype(np.float32)
    frame[fy0:fy1, fx0:fx1] = (dst * (1 - pa) + part * pa).astype(np.uint8)
    return frame


def kinetic_type(frame: np.ndarray, words: list[tuple[str, bool]], t: float, *,
                 t0: float = 0.0, font_path: str, ink=(240, 235, 226),
                 key_ink=(47, 59, 226), size: int = 150, gap: float = 0.11,
                 y: int = 1180, line_h: int = 170, per_line: int = 3,
                 settle_rot: float = -3.0) -> np.ndarray:
    """Words land one at a time on a spring, overshoot, and settle.

    `words` is [(text, is_key)]. Each word springs from 0.55x with a small
    rotation that unwinds to a settled tilt - the "bespoke motion" look that a
    fade-in never gets. Words are laid out across their row, not stacked on
    the centre point: three words on one line have to occupy three places.
    """
    rows: list[list[int]] = [list(range(i, min(i + per_line, len(words))))
                             for i in range(0, len(words), per_line)]
    for row_i, idxs in enumerate(rows):
        ready: list[tuple[int, np.ndarray, np.ndarray, float, float]] = []
        for i in idxs:
            word, is_key = words[i]
            local = t - (t0 + i * gap)
            if local < 0:
                continue
            rgb, a = word_sprite(word.upper(), font_path, size,
                                 key_ink if is_key else ink)
            ready.append((i, rgb, a, spring(local), local))
        if not ready:
            continue
        spacing = size * 0.26
        widths = [rgb.shape[1] * (0.55 + 0.45 * sp) for _, rgb, _, sp, _ in ready]
        total = sum(widths) + spacing * (len(ready) - 1)
        x = (frame.shape[1] - total) / 2
        row_y = y + row_i * line_h - (len(rows) - 1) * line_h / 2
        for (i, rgb, a, sp, local), wpt in zip(ready, widths):
            cx = x + wpt / 2
            frame = blit(frame, rgb, a, (cx, row_y), scale=0.55 + 0.45 * sp,
                         rotation=settle_rot * (1.0 - min(1.0, sp)) * 2.0,
                         opacity=min(1.0, local / 0.09))
            x += wpt + spacing
    return frame


# --------------------------------------------------------------- face track
class FaceTracker:
    """YuNet per frame, smoothed. LIMIT: this tracks the face, not the body,
    so masks and wraps are local to the head. A full-body roto needs a
    segmentation model; a face ellipse is what the footage supports today.
    """

    def __init__(self, model: Path, size: tuple[int, int] = (W, H),
                 smooth: float = 0.35):
        self.det = cv2.FaceDetectorYN.create(str(model), "", size, 0.5, 0.3, 50)
        self.box: tuple[float, float, float, float] | None = None
        self.smooth = smooth
        self.misses = 0

    def update(self, frame: np.ndarray) -> tuple[float, float, float, float] | None:
        h, w = frame.shape[:2]
        self.det.setInputSize((w, h))
        _, faces = self.det.detect(frame)
        if faces is not None and len(faces):
            best = max(faces, key=lambda f: float(f[14]))
            x, y, fw, fh = (float(v) for v in best[:4])
            cur = (x, y, fw, fh)
            if self.box is None:
                self.box = cur
            else:
                k = self.smooth
                self.box = tuple(a * (1 - k) + b * k for a, b in zip(self.box, cur))
            self.misses = 0
        else:
            self.misses += 1
            if self.misses > 12:                 # lost it: hold nothing
                self.box = None
        return self.box

    def mask(self, shape: tuple[int, int], *, grow: float = 0.35,
             feather: float = 45.0) -> np.ndarray:
        """Soft ellipse over the face, 0..1 float. The roto stand-in."""
        h, w = shape
        m = np.zeros((h, w), np.float32)
        if self.box is None:
            return m
        x, y, fw, fh = self.box
        cx, cy = x + fw / 2, y + fh / 2
        ax, ay = fw * (0.5 + grow), fh * (0.5 + grow)
        cv2.ellipse(m, (int(cx), int(cy)), (int(ax), int(ay)), 0, 0, 360, 1.0, -1)
        m = cv2.GaussianBlur(m, (0, 0), feather)
        return np.clip(m, 0, 1)


def light_wrap(frame: np.ndarray, mask: np.ndarray, *, strength: float = 0.55,
               radius: int = 41) -> np.ndarray:
    """Spill the background's light onto the subject's edge.

    Separates a cut-out from its background: a composited subject looks pasted
    on until the light behind it wraps the edge. LIMIT: with only a face
    ellipse the wrap hugs the head, not a full silhouette.
    """
    if mask.max() <= 0.01:
        return frame
    k = radius * 2 + 1
    blurred = cv2.GaussianBlur(frame, (k, k), 0).astype(np.float32)
    bg = cv2.GaussianBlur((frame * (1 - mask[:, :, None])).astype(np.float32), (k, k), 0)
    ring = cv2.GaussianBlur(np.clip(mask - cv2.erode(mask, np.ones((9, 9), np.uint8)), 0, 1),
                            (0, 0), radius * 0.55)
    ring = (ring / (ring.max() + 1e-6))[:, :, None] * strength
    screened = 255 - (255 - blurred) * (255 - bg) / 255.0
    out = frame.astype(np.float32) * (1 - ring) + screened * ring
    return np.clip(out, 0, 255).astype(np.uint8)


# --------------------------------------------------------------- 3D camera
def perspective_cam(frame: np.ndarray, *, zoom: float = 1.0, yaw: float = 0.0,
                    pitch: float = 0.0) -> np.ndarray:
    """A trapezoid warp that reads as a camera yawing/pitching in 3D.

    LIMIT: this is a single-plane perspective, not a scene with depth, so
    everything moves together. It is convincing on a locked-off talking head
    and would fall apart on a parallax-heavy shot.
    """
    h, w = frame.shape[:2]
    m = 1.0 / max(zoom, 1.0)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    # corners pulled in by the zoom, then pushed by yaw/pitch
    x0, x1 = w * (1 - m) / 2, w - w * (1 - m) / 2
    y0, y1 = h * (1 - m) / 2, h - h * (1 - m) / 2
    dx = yaw * w * 0.12
    dy = pitch * h * 0.06
    dst = np.float32([
        [x0 + dx, y0 + dy],
        [x1 - dx, y0 - dy],
        [x1 - dx, y1 + dy],
        [x0 + dx, y1 - dy],
    ])
    mat = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(frame, mat, (w, h), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REPLICATE)


# --------------------------------------------------------------- transitions
def whip_pan(frame: np.ndarray, amount: float, *, direction: int = 1) -> np.ndarray:
    """Directional smear + shift: the classic whip between two shots."""
    if amount <= 0.01:
        return frame
    k = max(3, int(amount * 70) | 1)
    kernel = np.zeros((1, k), np.float32)
    kernel[0, :] = np.linspace(0.2, 1.0, k)
    kernel /= kernel.sum()
    smeared = cv2.filter2D(frame, -1, kernel)
    shift = int(direction * amount * frame.shape[1] * 0.35)
    out = np.roll(smeared, shift, axis=1)
    if shift > 0:
        out[:, :shift] = out[:, shift:shift + 1]
    elif shift < 0:
        out[:, shift:] = out[:, shift - 1:shift]
    return out


def zoom_blur(frame: np.ndarray, amount: float, steps: int = 7) -> np.ndarray:
    """Radial blur by averaging scaled copies: a zoom transition's core."""
    if amount <= 0.01:
        return frame
    h, w = frame.shape[:2]
    acc = frame.astype(np.float32)
    for i in range(1, steps):
        s = 1.0 + amount * 0.22 * (i / steps)
        m = cv2.getRotationMatrix2D((w / 2, h / 2), 0, s)
        acc += cv2.warpAffine(frame, m, (w, h), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    return np.clip(acc / steps, 0, 255).astype(np.uint8)
