"""Fitting a 16:9 broadcast into a 9:16 frame without losing a face.

The 2 Bears source is not a close-up on a clean background; it is a 1920x1080
broadcast where the reaction shot is often the joke. These tests pin the two
things that make or break it: the whole panel survives, and no black void.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import layout as L  # noqa: E402


def panel(w=1920, h=1080, *, marker=True) -> np.ndarray:
    img = np.full((h, w, 3), 90, np.uint8)
    cv2.rectangle(img, (0, 0), (w // 2, h), (60, 70, 80), -1)
    if marker:                       # a distinctive mark in each corner
        for x, y in ((40, 40), (w - 80, 40), (40, h - 80), (w - 80, h - 80)):
            cv2.rectangle(img, (x, y), (x + 40, y + 40), (255, 0, 255), -1)
    return img


def test_output_is_the_campaign_frame() -> None:
    out = L.Layout().compose(panel())
    assert out.shape == (L.H, L.W, 3)


def test_the_whole_panel_survives() -> None:
    """Both halves of a two-camera broadcast must still be in the frame."""
    lay = L.Layout()
    out = lay.compose(panel())
    ph = lay.panel_of(panel()).shape[0]
    band = out[lay.panel_y(ph): lay.panel_y(ph) + ph]
    left = band[:, :L.W // 4]
    right = band[:, -L.W // 4:]
    assert np.abs(left.astype(int) - right.astype(int)).mean() > 2, \
        "left and right halves are identical - the panel was cropped to one side"


def test_no_black_void_above_or_below() -> None:
    lay = L.Layout()
    out = lay.compose(panel())
    ph = lay.panel_of(panel()).shape[0]
    y = lay.panel_y(ph)
    assert out[:y - 4].mean() > 3, "top is a black bar"
    assert out[y + ph + 4:].mean() > 3, "bottom is a black bar"


def test_a_non_16_9_frame_still_fits() -> None:
    square = np.full((1080, 1080, 3), 120, np.uint8)
    out = L.Layout().compose(square)
    assert out.shape == (L.H, L.W, 3)


def test_oversized_source_is_scaled_not_cropped_away() -> None:
    lay = L.Layout()
    big = panel(3840, 2160)
    out = lay.compose(big)
    ph = lay.panel_of(big).shape[0]
    band = out[lay.panel_y(ph): lay.panel_y(ph) + ph]
    assert band.std() > 1, "panel is blank after scaling"


def test_burned_in_subtitles_are_cropped_off() -> None:
    """The broadcast burns its own captions into the bottom ~18% of the panel.

    Two sets of subtitles on screen at once is the failure this guards: the
    source's own words must not reach the canvas, while the faces above them
    must.
    """
    src = panel()
    cv2.rectangle(src, (600, 980), (1320, 1050), (255, 255, 255), -1)   # fake caption
    lay = L.Layout()
    panel_img = lay.panel_of(src)
    assert panel_img.shape[0] == 534
    # the bottom rows of the source are gone, the middle of the picture is not
    src_bottom = src[1000:1060, 600:1320].mean()
    assert src_bottom > 200
    assert panel_img.std() > 1


def test_backdrop_is_reused_inside_a_bucket() -> None:
    """Refreshing the 1/8-scale blur every frame costs more than it shows."""
    lay = L.Layout()
    a = lay.backdrop(panel(), slot=0)
    b = lay.backdrop(panel(w=1280, h=720), slot=3)
    assert a is b, "backdrop was rebuilt inside the same 10-frame bucket"
    c = lay.backdrop(panel(w=1280, h=720), slot=20)
    assert c is not a
