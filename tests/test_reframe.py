"""The vertical crop: inside the picture, off the watermark, on the face."""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import reframe as RF       # noqa: E402


def framed(w=1920, h=1080) -> np.ndarray:
    """A frame like the show's: cream border, picture inside, bug top-right."""
    img = np.full((h, w, 3), 244, np.uint8)
    img[71:1009, 123:1797] = (70, 80, 90)
    cv2.rectangle(img, (123, 71), (1797, 1009), (255, 255, 255), 6)
    cv2.putText(img, "2 BEARS", (1520, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.4,
                (255, 255, 255), 4)
    return img


def test_the_border_is_found() -> None:
    x0, y0, x1, y1 = RF.picture_rect(framed())
    assert abs(x0 - 123) <= 6 and abs(y0 - 71) <= 6
    assert abs(x1 - 1797) <= 3 and abs(y1 - 1009) <= 3


def test_the_window_never_leaves_the_picture() -> None:
    f = framed()
    r = RF.Reframe()
    for _ in range(6):
        x, _cut = r.crop_x(f, 0.0)
        w = r.window(f)
        assert x >= w[0] and x + w[2] <= RF.picture_rect(f)[2]


def test_the_window_keeps_off_the_watermark() -> None:
    f = framed()
    r = RF.Reframe()
    x, _ = r.crop_x(f, 0.0)
    _px0, _py0, win_w, _ = r.window(f)
    right = RF.picture_rect(f)[2]
    assert x + win_w <= right - int(r.watermark_margin * (right - RF.picture_rect(f)[0]))


def test_the_crop_is_full_bleed_vertical() -> None:
    out = RF.Reframe().apply(framed())
    assert out.shape == (RF.H, RF.W, 3)
    # no cream border smuggled into the vertical frame
    assert out[:, :12].mean() < 235 and out[:, -12:].mean() < 235


def test_an_unframed_source_still_renders() -> None:
    plain = np.full((1080, 1920, 3), 90, np.uint8)
    r = RF.Reframe()
    assert r.apply(plain).shape == (RF.H, RF.W, 3)
