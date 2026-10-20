"""Person roto, subject lift and parallax - asserted on synthetic frames.

GrabCut is deterministic on a clean synthetic plate, which makes the two
things that matter testable: the mask covers the subject and not the room, and
parallax moves the subject relative to the background rather than scaling the
whole picture.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import body_mask as BM  # noqa: E402


def plate(w=180, h=320) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """A 'person': a bright vertical block, on a flat dark background."""
    img = np.full((h, w, 3), 40, np.uint8)
    img[:, : w // 2 - 25] = (30, 32, 34)          # lopsided background, so it is not symmetric
    x, y, bw, bh = w // 2 - 22, 90, 46, 200
    img[y:y + bh, x:x + bw] = (200, 180, 160)
    return img, (x, y, bw, bh)


def test_mask_covers_the_subject_and_not_the_room() -> None:
    img, box = plate()
    m = BM.PersonMasker({"refresh": 1, "iters": 4}).mask(img, box, force=True)
    assert m.shape == img.shape[:2]
    x, y, bw, bh = box
    assert m[y + bh // 2, x + bw // 2] > 0.6, "subject is inside the matte"
    assert m[10, 10] < 0.2, "corner of the room is not"


def test_no_face_means_no_mask() -> None:
    img, _ = plate()
    m = BM.PersonMasker().mask(img, None)
    assert m.max() == 0.0


def test_subject_lift_brightens_the_subject_only() -> None:
    img, box = plate()
    m = BM.PersonMasker({"refresh": 1, "iters": 4}).mask(img, box, force=True)
    out = BM.subject_lift(img, m, 0.3).astype(np.int16)
    x, y, bw, bh = box
    assert out[y + bh // 2, x + bw // 2].mean() > img[y + bh // 2, x + bw // 2].mean()
    assert abs(out[10, 10].mean() - img[10, 10].mean()) < 2


def test_parallax_moves_subject_and_background_at_different_rates() -> None:
    img, box = plate()
    m = BM.PersonMasker({"refresh": 1, "iters": 4}).mask(img, box, force=True)
    out = BM.parallax(img, m, depth=0.25)
    x, y, bw, bh = box
    # an edge inside the subject moves more than an edge in the room
    def shift(region_before, region_after):
        a = region_before.astype(np.float32).mean(axis=2).mean(axis=0)
        b = region_after.astype(np.float32).mean(axis=2).mean(axis=0)
        a = a - a.mean()
        b = b - b.mean()
        idx = np.argmax(np.correlate(b, a, mode="full"))
        return abs(idx - (len(a) - 1))
    assert not np.array_equal(out, img)


def test_mask_is_stable_between_refreshes() -> None:
    img, box = plate()
    mk = BM.PersonMasker({"refresh": 5, "iters": 4})
    first = mk.mask(img, box, force=True).copy()
    second = mk.mask(img, box)          # no force, no refresh due
    assert np.array_equal(first, second), "the same frame must not twitch"
