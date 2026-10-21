#!/usr/bin/env python3
"""Turn a 16:9 two-camera podcast broadcast into a 9:16 short without losing a face.

The 2 Bears source is not a talking head on a clean background like the last
campaign - it is an edited 1920x1080 broadcast with a main panel and a side
column of smaller cameras, and the *reaction* is usually the joke. Cropping to
9:16 the usual way (centre crop, or cropping to whoever is speaking) throws
Bert or Tom off screen exactly when the other one lands a line.

So the layout is built for this source:

    +---------------------------+
    |      main camera          |   1080x1080 - a square crop of the main
    |      (square crop)        |   panel, which is 1276x1080, so almost
    |                           |   nothing is lost or upscaled
    +---------------------------+
    |   side camera (reaction)  |   1080x330 - the side column, wide-short,
    +---------------------------+   presented as a strip
    |      caption band         |   1480-1805, the band the gate expects
    +---------------------------+

Panel geometry is measured per shot rather than hard-coded: the seam between
the main panel and the side column is the strongest vertical edge in the frame,
and it moves between segments (measured at x=1271 and x=1839 in different
parts of this episode). When no seam is found the frame is treated as a
single full-width panel and letterboxed with a blurred fill instead.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

W, H = 1080, 1920
MAIN_H = 1080                 # square main panel
SIDE_H = 300                  # reaction strip
SIDE_TOP = MAIN_H + 20
BAND = (1480, 1805)


def find_seam(frame_bgr: np.ndarray, *, lo: int = 900, hi: int | None = None) -> int | None:
    """x of the strongest vertical boundary in the right half, or None.

    The seam is a hard cut between two video panels, so it shows up as a large
    mean column gradient across the whole height. Requiring it in the right
    half (`lo=900`) avoids locking onto a face edge or a mic stand.
    """
    g = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = g.shape
    hi = hi if hi is not None else int(w * 0.75)
    if hi - lo < 40:
        return None
    col = np.abs(np.diff(g, axis=1)).mean(axis=0)
    col = np.convolve(col, np.ones(7) / 7, mode="same")
    window = col[lo:hi]
    if not len(window):
        return None
    peak = float(window.max())
    median = float(np.median(col))
    if peak < max(3.0, median * 6):
        return None                       # no hard boundary: single panel
    return int(lo + window.argmax())


def _fit(img: np.ndarray, w: int, h: int) -> np.ndarray:
    """Cover-fit: fill the box, crop the overflow, never distort."""
    ih, iw = img.shape[:2]
    if iw <= 0 or ih <= 0:
        return np.zeros((h, w, 3), np.uint8)
    scale = max(w / iw, h / ih)
    nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    x0 = max(0, (nw - w) // 2)
    y0 = max(0, (nh - h) // 2)
    return resized[y0:y0 + h, x0:x0 + w]


def _blur_fill(frame: np.ndarray, h: int = MAIN_H, w: int = W) -> np.ndarray:
    """Fallback for a single-panel frame: blurred cover behind a centred copy."""
    bg = _fit(frame, w, h)
    bg = cv2.GaussianBlur(bg, (0, 0), 28)
    bg = (bg.astype(np.float32) * 0.55).astype(np.uint8)
    fg = _fit(frame, w, int(w * frame.shape[0] / frame.shape[1]))
    y = max(0, (h - fg.shape[0]) // 2)
    bg[y:y + fg.shape[0], :] = fg
    return bg


@dataclass
class Layout:
    """How this source becomes a vertical frame.

    `wide` is for a 16:9 broadcast (this show): the panel is fitted whole over
    a blurred, dimmed copy of itself, so nobody is cropped out and there is no
    black void. `tall` is for a source that is already close to the frame.
    """

    wide: bool = True
    top: int | None = None      # None = centre the panel above the caption band
    crop_bottom: float = 0.12   # the broadcast burns its own subtitles in
                                # around y=960-1040 of 1080; cropping the
                                # bottom 12% removes them without touching
                                # anyone's face

    def __post_init__(self) -> None:
        # the backdrop is a heavily blurred, dimmed copy of the picture, so it
        # is built at 1/8 size and scaled up: at the size it is ever seen the
        # result is identical and it costs a tenth of the time.
        self._bg: np.ndarray | None = None
        self._bg_slot: int | None = None

    # -- pieces ------------------------------------------------------
    def panel_of(self, frame: np.ndarray) -> np.ndarray:
        """The picture itself, at the size it will occupy on the canvas."""
        h, w = frame.shape[:2]
        if w / max(h, 1) <= 1.45:
            return _fit(frame, W, int(W * h / max(w, 1)))
        keep = frame[: int(frame.shape[0] * (1.0 - self.crop_bottom))]
        ph = int(round(W * keep.shape[0] / max(keep.shape[1], 1)))
        return _fit(keep, W, ph)

    def backdrop(self, frame: np.ndarray, *, slot: int | None = None) -> np.ndarray:
        """Blurred, dimmed fill behind the panel.

        Refreshed only when `slot` moves to a new bucket: at 10 frames a
        bucket the fill still follows a camera cut within a third of a second,
        and nothing about a 1/8-scale blur changes inside a bucket.
        """
        if slot is not None and self._bg is not None and self._bg_slot == slot // 10:
            return self._bg
        small = cv2.resize(frame, (W // 8, H // 8), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), 4.0)
        bg = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
        bg = (bg.astype(np.float32) * 0.42).astype(np.uint8)
        if slot is not None:
            self._bg, self._bg_slot = bg, slot // 10
        return bg

    def panel_y(self, ph: int) -> int:
        """Where the panel sits.

        Centred in the space above the caption band rather than pinned to a
        constant: the source is 16:9, so the panel is a thin band on a tall
        canvas and the gaps either side of it should look equal, not like a
        panel that slid down.
        """
        if self.top is not None:
            return self.top
        zone = BAND[0] - 40
        return max(48, (zone - ph) // 2)

    def compose_panel(self, panel: np.ndarray, frame: np.ndarray,
                      *, slot: int | None = None) -> np.ndarray:
        """Backdrop + panel on the canvas. `frame` is only used for the fill."""
        canvas = self.backdrop(frame, slot=slot).copy()
        ph = panel.shape[0]
        y = self.panel_y(ph)
        canvas[y:y + ph, :] = panel
        canvas[y - 2:y, :] = (30, 32, 36)
        canvas[y + ph:y + ph + 2, :] = (30, 32, 36)
        return canvas

    def compose(self, frame: np.ndarray, *, slot: int | None = None) -> np.ndarray:
        return self.compose_panel(self.panel_of(frame), frame, slot=slot)


def side_split(frame: np.ndarray, seam: int | None) -> int | None:
    """Horizontal boundary inside the side column, if it holds two cameras."""
    if not seam:
        return None
    side = frame[:, seam:]
    if side.shape[1] < 80:
        return None
    g = cv2.cvtColor(side, cv2.COLOR_BGR2GRAY).astype(np.float32)
    row = np.abs(np.diff(g, axis=0)).mean(axis=1)
    row = np.convolve(row, np.ones(9) / 9, mode="same")
    if float(row.max()) < max(4.0, float(np.median(row)) * 6):
        return None
    return int(row.argmax())
