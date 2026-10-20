#!/usr/bin/env python3
"""Roto without a segmentation model: GrabCut, seeded by the face.

The face tracker gives us a box we trust. A person in a vertical short is
essentially "that box, extended down to the bottom of the frame", so GrabCut
run inside that rectangle separates the subject from the room well enough for
a light wrap, a subject lift or a parallax push - none of which need a
pixel-perfect matte, only a soft one.

Why not a model: the segmentation models that do this properly are 100-200 MB
downloads with runtime model fetching. GrabCut is already in OpenCV, needs no
download, and on a locked-off talking head (which is what this campaign is)
it is accurate enough. LIMIT, stated plainly: it will fail on a busy
background or a fast-moving subject, and it is refreshed a few times a second
rather than every frame.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

DEFAULTS = {
    "scale": 0.25,        # grabcut runs on a quarter-size frame: ~40 ms
    "refresh": 5,         # every N frames; a static camera does not need more
    "iters": 3,
    "grow_w": 1.35,       # person rect, relative to the face box
    "grow_h_down": 4.5,
    "feather": 9,
}


@dataclass
class PersonMasker:
    cfg: dict = field(default_factory=dict)
    _mask: np.ndarray | None = None
    _box: tuple[int, int, int, int] | None = None
    _frame_no: int = 0

    def __post_init__(self) -> None:
        self.cfg = {**DEFAULTS, **self.cfg}

    def rect_for(self, face: tuple[float, float, float, float],
                 shape: tuple[int, int]) -> tuple[int, int, int, int]:
        h, w = shape
        x, y, fw, fh = face
        cx = x + fw / 2
        rw = fw * float(self.cfg["grow_w"])
        rh = fh * float(self.cfg["grow_h_down"])
        x0 = int(max(0, cx - rw / 2))
        y0 = int(max(0, y - fh * 0.25))
        x1 = int(min(w - 1, cx + rw / 2))
        y1 = int(min(h - 1, y0 + rh))
        return x0, y0, max(2, x1 - x0), max(2, y1 - y0)

    def mask(self, frame: np.ndarray,
             face: tuple[float, float, float, float] | None,
             *, force: bool = False) -> np.ndarray:
        """Soft 0..1 person mask at full resolution."""
        h, w = frame.shape[:2]
        if face is None:
            return np.zeros((h, w), np.float32)
        rect = self.rect_for(face, (h, w))
        stale = (self._mask is None or force
                 or self._frame_no % int(self.cfg["refresh"]) == 0
                 or self._box != rect)
        self._frame_no += 1
        if not stale and self._mask is not None:
            return self._mask

        s = float(self.cfg["scale"])
        small = cv2.resize(frame, (max(8, int(w * s)), max(8, int(h * s))),
                           interpolation=cv2.INTER_AREA)
        x, y, rw, rh = (int(v * s) for v in rect)
        x, y = max(1, x), max(1, y)
        rw = min(small.shape[1] - x - 1, max(4, rw))
        rh = min(small.shape[0] - y - 1, max(4, rh))
        if rw <= 2 or rh <= 2:
            return np.zeros((h, w), np.float32)

        bgm = np.zeros((1, 65), np.float64)
        fgm = np.zeros((1, 65), np.float64)
        gc = np.zeros(small.shape[:2], np.uint8)
        try:
            cv2.grabCut(small, gc, (x, y, rw, rh), bgm, fgm,
                        int(self.cfg["iters"]), cv2.GC_INIT_WITH_RECT)
        except cv2.error:
            return self._mask if self._mask is not None else np.zeros((h, w), np.float32)
        keep = ((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD)).astype(np.float32)

        # Fill holes: GrabCut leaves specks inside the jacket; a closing pass
        # makes the matte something we can composite with.
        keep = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        big = cv2.resize(keep, (w, h), interpolation=cv2.INTER_LINEAR)
        big = cv2.GaussianBlur(big, (0, 0), float(self.cfg["feather"]))
        self._mask = np.clip(big, 0, 1).astype(np.float32)
        self._box = rect
        return self._mask


def subject_lift(frame: np.ndarray, mask: np.ndarray, amount: float = 0.12) -> np.ndarray:
    """Lift the subject out of the background by a touch of exposure."""
    if mask.max() <= 0.01:
        return frame
    gain = 1.0 + amount * mask[:, :, None]
    return np.clip(frame.astype(np.float32) * gain, 0, 255).astype(np.uint8)


def parallax(frame: np.ndarray, mask: np.ndarray, *, depth: float = 0.035) -> np.ndarray:
    """Push the camera in: the subject grows faster than the room behind it.

    A single flat frame has no depth, so the depth is invented - subject scaled
    by (1 + depth), background left alone, composited through the matte. It
    only reads as parallax because the two layers move at different rates.
    """
    if mask.max() <= 0.01:
        return frame
    h, w = frame.shape[:2]
    ys, xs = np.where(mask > 0.5)
    if not len(xs):
        return frame
    cx, cy = float(xs.mean()), float(ys.mean())

    def scaled(img: np.ndarray, s: float) -> np.ndarray:
        m = cv2.getRotationMatrix2D((cx, cy), 0, s)
        return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE)

    fg = scaled(frame, 1.0 + depth)
    bg = scaled(frame, 1.0 + depth * 0.15)
    m = mask[:, :, None]
    return np.clip(bg.astype(np.float32) * (1 - m) + fg.astype(np.float32) * m,
                   0, 255).astype(np.uint8)
