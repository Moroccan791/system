"""The fast grade must be the same grade, not a cheaper look.

Two things are pinned: the picture stays within a couple of code values of the
reference implementation in `tight_posts`, and a face-toned patch is not pushed
around more than a neutral one - the brief asks for a grade that leaves skin
looking like skin.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import grade_fast as GF       # noqa: E402
import layout as L            # noqa: E402
import tight_posts as TP      # noqa: E402

GRADE = {"curve": 0.26, "saturation": 1.05, "warmth": 0.010, "cool": 0.008,
         "vignette": 0.10, "lift": 0.008, "skin_guard": 0.55}


def picture(seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = np.dstack([np.full((300, 400), v, np.uint8)
                      for v in (70, 95, 110)])
    noise = rng.integers(-18, 19, (300, 400, 3), dtype=np.int16)
    return np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def test_fast_grade_matches_the_reference() -> None:
    src = picture()
    mask = GF.mask_for(src.shape)
    ref = TP.grade_frame(src, GRADE, mask)
    fast = GF.apply(src, GRADE, mask)
    assert np.abs(ref.astype(int) - fast.astype(int)).mean() < 2.0


def _moved(colour: tuple[int, int, int], sat: float) -> float:
    patch = np.zeros((60, 60, 3), np.uint8)
    patch[:, :] = colour
    out = GF.apply(patch, {**GRADE, "saturation": sat}, np.ones((60, 60, 1), np.float32))
    return float(np.abs(out.astype(int) - patch.astype(int)).mean())


def test_skin_is_damped_against_an_equally_saturated_colour() -> None:
    """Raising saturation must not push a face as hard as it pushes a colour.

    A lit face (120,150,190 BGR) sits inside the skin chroma window; a teal of
    about the same distance from neutral sits outside it. If the guard works,
    the face moves less.
    """
    skin, teal = (120, 150, 190), (190, 150, 120)
    assert _moved(skin, 1.30) < _moved(teal, 1.30)


def test_panel_keeps_the_campaign_shape() -> None:
    src = np.full((1080, 1920, 3), 96, np.uint8)
    panel = L.Layout().panel_of(src)
    assert panel.shape[0] == 534 and panel.shape[1] == L.W
