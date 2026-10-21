#!/usr/bin/env python3
"""Fill a 9:16 frame with a 16:9 broadcast, by following the face.

The first version of this campaign's renderer letterboxed the whole panel onto
a blurred backdrop. It was safe - nobody is cropped out - and it looked like a
horizontal video dropped into a vertical frame, because that is what it was:
the picture occupied 28% of the canvas and the rest was a blur.

This does the other thing. A 9:16 window is cut out of the picture and scaled to
fill 1080x1920, so the face is the frame.

Two things about this source have to be handled before any of that:

* **it is framed** - the broadcast sits inside a cream border, so the crop is
  taken from inside the frame, not from the edge of the file. Cropping the file
  edge puts the show's own white border down one side of the vertical frame,
  which is instantly readable as a bad crop.
* **it has a watermark** - "2 BEARS, 1 CAVE" is burned into the top right of the
  picture. The window is clamped so it can never reach it; that is cheaper and
  cleaner than inpainting a logo on 900 frames.

One target, smoothed, with hysteresis: a detector that jitters by a few pixels
does not make the picture swim, and a real change of subject cuts once instead
of sliding across the frame like a pan nobody asked for.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx"

W, H = 1080, 1920
ASPECT = W / H                      # 0.5625

Rect = tuple[int, int, int, int]    # x0, y0, x1, y1


def picture_rect(frame: np.ndarray) -> Rect:
    """The picture inside the broadcast's own border.

    The border is near-white and the picture behind it is not, so both edges are
    found from the brightest runs of rows and columns through the middle of the
    frame. Falls back to the whole frame when nothing that looks like a border
    is found - a source that is not framed still has to render.
    """
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    rows = g[:, int(w * 0.3):int(w * 0.7)].mean(axis=1)
    cols = g[int(h * 0.3):int(h * 0.7), :].mean(axis=0)
    bright_r = np.flatnonzero(rows > 235)
    bright_c = np.flatnonzero(cols > 235)
    if not len(bright_r) or not len(bright_c):
        return 0, 0, w, h
    # the inner edge of the top/bottom/left/right border: the last bright run
    # before the picture starts
    top = int(bright_r[bright_r < h * 0.25].max()) + 1 if np.any(bright_r < h * 0.25) else 0
    bot = int(bright_r[bright_r > h * 0.75].min()) if np.any(bright_r > h * 0.75) else h
    left = int(bright_c[bright_c < w * 0.25].max()) + 1 if np.any(bright_c < w * 0.25) else 0
    right = int(bright_c[bright_c > w * 0.75].min()) if np.any(bright_c > w * 0.75) else w
    if right - left < w * 0.5 or bot - top < h * 0.5:
        return 0, 0, w, h
    return left, top, right, bot


@dataclass
class Reframe:
    """Cuts a 9:16 window out of a frame and follows the subject in it."""

    model: Path = MODEL
    smooth: float = 0.22            # EMA per frame on the crop centre
    dead_band: float = 5.0          # px the target must move before we follow
    switch: float = 260.0           # px of jump that counts as a new subject
    sharpen: float = 0.45
    watermark_margin: float = 0.16  # keep this much of the picture's right edge
                                    # out of play: the show's bug lives there

    _det: object = None
    _rect: Rect | None = None
    _cx: float | None = None
    _bounds: tuple[float, float] | None = None
    _box: tuple[float, float, float, float] | None = None
    _misses: int = 0
    cuts: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._det = cv2.FaceDetectorYN.create(str(self.model), "", (1920, 1080),
                                              0.5, 0.3, 50)

    # -- geometry ----------------------------------------------------
    def rect(self, frame: np.ndarray) -> Rect:
        if self._rect is None:
            self._rect = picture_rect(frame)
        return self._rect

    def window(self, frame: np.ndarray) -> tuple[int, int, int, int]:
        """(x0, y0, win_w, win_h) of the 9:16 window inside the picture."""
        x0, y0, x1, y1 = self.rect(frame)
        pw, ph = x1 - x0, y1 - y0
        win_h = ph
        win_w = int(round(win_h * ASPECT))
        if win_w > pw:                       # a picture narrower than 9:16
            win_w = pw
            win_h = int(round(pw / ASPECT))
        return x0, y0, win_w, win_h

    def _travel(self, frame: np.ndarray) -> tuple[float, float]:
        """Where the window's left edge may go: face-following stays inside."""
        x0, _y0, win_w, _win_h = self.window(frame)
        x1 = self.rect(frame)[2]
        lo = float(x0)
        hi = float(max(x0, x1 - win_w - int(self.watermark_margin * (x1 - x0))))
        if self._bounds != (lo, hi):
            self._bounds = (lo, hi)
            self._cx = None
        return lo, hi

    def _target(self, frame: np.ndarray) -> float | None:
        h, w = frame.shape[:2]
        self._det.setInputSize((w, h))
        _, faces = self._det.detect(frame)
        if faces is None or not len(faces):
            self._misses += 1
            return None
        best = max(faces, key=lambda f: float(f[14]))
        x, y, fw, fh = (float(v) for v in best[:4])
        self._box = (x, y, fw, fh)
        self._misses = 0
        return x + fw / 2.0

    def crop_x(self, frame: np.ndarray, t: float) -> tuple[int, bool]:
        """Left edge of the window, and whether this frame starts a new shot."""
        _x0, _y0, win_w, _win_h = self.window(frame)
        lo, hi = self._travel(frame)
        centre = self._target(frame)
        target = centre if centre is not None else self._cx
        if target is None:
            return int(lo), False
        target = float(np.clip(target - win_w / 2.0, lo, hi))

        cut = False
        if self._cx is None:
            self._cx = target
            cut = True
        elif abs(target - self._cx) > self.switch:
            self._cx = target            # new subject: cut, do not pan
            cut = True
        elif abs(target - self._cx) > self.dead_band:
            self._cx += (target - self._cx) * self.smooth
        if cut:
            self.cuts.append(round(t, 3))
        return int(round(np.clip(self._cx, lo, hi))), cut

    # -- picture -----------------------------------------------------
    def apply(self, frame: np.ndarray, *, x0: int | None = None) -> np.ndarray:
        px0, py0, win_w, win_h = self.window(frame)
        x0 = px0 if x0 is None else int(np.clip(x0, px0, frame.shape[1] - win_w))
        window = frame[py0:py0 + win_h, x0:x0 + win_w]
        out = cv2.resize(window, (W, H), interpolation=cv2.INTER_CUBIC)
        if self.sharpen > 0:
            blur = cv2.GaussianBlur(out, (0, 0), 1.5)
            out = cv2.addWeighted(out, 1.0 + self.sharpen, blur, -self.sharpen, 0)
        return out
