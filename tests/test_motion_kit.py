"""The six "After Effects" moves, asserted without watching a video.

Each test pins the property that makes the effect an effect rather than a
filter that happens to run: a spring overshoots, a mask is soft at its edge,
a neutral camera leaves the frame alone, a transition smears in one direction.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import font_refresh as FR     # noqa: E402
import motion_kit as MK       # noqa: E402


def frame(w=270, h=480) -> np.ndarray:
    rng = np.random.default_rng(3)
    base = np.zeros((h, w, 3), np.uint8)
    base[:] = (60, 70, 80)
    base[::17, ::13] = (200, 190, 180)          # texture, so warps are visible
    return np.clip(base.astype(np.int16) + rng.integers(-8, 8, base.shape), 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ easings
def test_spring_overshoots_then_settles() -> None:
    assert MK.spring(0.0) == 0.0
    assert MK.spring(-1.0) == 0.0
    peak = max(MK.spring(i / 200) for i in range(1, 400))
    assert peak > 1.02, "a spring that never overshoots is just an ease"
    assert abs(MK.spring(3.0) - 1.0) < 0.02, "and it has to settle"


# --------------------------------------------------------------- kinetic type
def test_kinetic_type_lands_words_over_time() -> None:
    words = [("I", False), ("will", False), ("never", True)]
    f0 = frame()
    before = MK.kinetic_type(f0.copy(), words, -1.0, font_path=FR.SHAWKIND,
                             size=40, y=240)
    assert np.array_equal(before, f0), "nothing drawn before the first word is due"
    after = MK.kinetic_type(f0.copy(), words, 1.5, font_path=FR.SHAWKIND,
                            size=40, y=240)
    assert not np.array_equal(after, f0), "words must be on screen"


def test_kinetic_words_in_a_row_do_not_stack() -> None:
    """Three words on one line have to occupy three places, not one."""
    words = [("aaa", False), ("bbb", False), ("ccc", False)]
    out = MK.kinetic_type(frame().copy(), words, 2.0, font_path=FR.SHAWKIND,
                          size=40, per_line=3, y=240)
    band = out[190:300]
    cols = np.where((band.max(axis=2) > 200).any(axis=0))[0]
    assert len(cols) and cols.max() - cols.min() > 80, "words are stacked on one spot"


# ---------------------------------------------------------------- face track
def test_mask_is_soft_and_local() -> None:
    tr = MK.FaceTracker.__new__(MK.FaceTracker)
    tr.box = (100.0, 100.0, 80.0, 100.0)
    m = tr.mask((480, 270), grow=0.3, feather=20)
    assert m.shape == (480, 270)
    assert 0.0 <= m.min() and m.max() <= 1.0
    assert m[150, 140] > 0.8, "face centre is inside"
    assert m[440, 20] < 0.05, "corner is not"
    assert 0.2 < m[150, 100] < 0.98, "edge is feathered, not a hard cut"


def test_light_wrap_leaves_a_no_mask_frame_alone() -> None:
    f = frame()
    out = MK.light_wrap(f, np.zeros(f.shape[:2], np.float32))
    assert np.array_equal(out, f)


def test_light_wrap_brightens_the_ring_not_the_inside() -> None:
    f = frame()
    tr = MK.FaceTracker.__new__(MK.FaceTracker)
    tr.box = (60.0, 120.0, 140.0, 170.0)
    m = tr.mask(f.shape[:2], grow=0.2, feather=12)
    out = MK.light_wrap(f, m, strength=0.9, radius=25).astype(np.int16)
    ring = (m > 0.05) & (m < 0.6)
    inner = m > 0.95
    assert out[ring].mean() > f[ring].mean(), "the edge picks up the background light"
    assert abs(out[inner].mean() - f[inner].mean()) < 6, "the face itself is untouched"


# ----------------------------------------------------------------- 3D camera
def test_neutral_camera_is_a_no_op() -> None:
    f = frame()
    out = MK.perspective_cam(f, zoom=1.0, yaw=0.0, pitch=0.0)
    assert np.abs(out.astype(int) - f.astype(int)).mean() < 2.0


def test_camera_yaw_moves_the_frame_and_keeps_it_full() -> None:
    f = frame()
    out = MK.perspective_cam(f, zoom=1.10, yaw=1.0)
    assert out.shape == f.shape
    assert np.abs(out.astype(int) - f.astype(int)).mean() > 5
    assert out[0, 0].any(), "no black corner: the plate must still fill the frame"


# --------------------------------------------------------------- transitions
def test_zero_transition_is_identity() -> None:
    f = frame()
    assert np.array_equal(MK.whip_pan(f, 0.0), f)
    assert np.array_equal(MK.zoom_blur(f, 0.0), f)


def test_whip_pan_smears_horizontally() -> None:
    f = frame()
    out = MK.whip_pan(f, 1.0)
    assert out.shape == f.shape
    # a horizontal smear lowers horizontal high-frequency energy far more
    # than vertical, which is what makes it read as a pan and not a defocus
    def hf(a, axis):
        g = a.astype(np.float32).mean(axis=2)
        return float(np.abs(np.diff(g, axis=axis)).mean())
    assert hf(out, 1) < hf(f, 1) * 0.8


def test_zoom_blur_lowers_detail_without_changing_size() -> None:
    f = frame()
    out = MK.zoom_blur(f, 1.0)
    assert out.shape == f.shape
    assert out.astype(np.float32).std() < f.astype(np.float32).std()
