"""Cover selection and the results loop.

The cover test is about the ranking, not the absolute score: a sharp face must
beat a blurry frame and a frame with no face. The results loop test is about
honesty - with no data it must say so, and with backwards data it must say the
rubric is wrong rather than inventing a story.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import cover as CV        # noqa: E402
import results_tracker as RT  # noqa: E402


def face_plate(blur: bool = False) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    img = np.full((480, 270, 3), 70, np.uint8)
    cv2.rectangle(img, (60, 90), (210, 330), (190, 175, 160), -1)
    for y in range(110, 320, 18):                 # texture, so sharpness means something
        cv2.line(img, (70, y), (200, y), (120, 110, 100), 2)
    if blur:
        img = cv2.GaussianBlur(img, (31, 31), 0)
    return img, (60.0, 90.0, 150.0, 240.0)


def test_sharp_beats_blurry() -> None:
    sharp, face = face_plate(False)
    soft, _ = face_plate(True)
    a = CV.score_frame(sharp, face)
    b = CV.score_frame(soft, face)
    assert a["score"] > b["score"]
    assert a["sharpness"] > b["sharpness"]


def test_face_beats_no_face() -> None:
    img, face = face_plate()
    assert CV.score_frame(img, face)["score"] > CV.score_frame(img, None)["score"]


def test_score_prefers_a_usable_exposure() -> None:
    img, face = face_plate()
    dark = (img * 0.15).astype(np.uint8)
    assert CV.score_frame(img, face)["score"] > CV.score_frame(dark, face)["score"]


# ------------------------------------------------------------------- results
def _rows(hooks, watched):
    return [{"post": f"p{i}", "hook": h, "watched_3s": w, "views": 1000,
             "duration": 22.0} for i, (h, w) in enumerate(zip(hooks, watched))]


def test_not_enough_data_says_so() -> None:
    out = RT.analyse(_rows([5.0, 6.0], [0.5, 0.6]))
    assert out["correlation"] is None
    assert "not enough" in out["verdict"]


def test_aligned_data_endorses_the_floor() -> None:
    out = RT.analyse(_rows([3.0, 4.0, 6.0, 8.0], [0.35, 0.45, 0.6, 0.75]))
    assert out["correlation"] > 0.5
    assert "keep" in out["verdict"]


def test_backwards_data_blames_the_rubric() -> None:
    out = RT.analyse(_rows([8.0, 6.0, 4.0, 3.0], [0.30, 0.42, 0.60, 0.72]))
    assert out["correlation"] < 0
    assert "backwards" in out["verdict"]


def test_percentage_is_accepted_as_a_fraction(tmp_path: Path) -> None:
    p = tmp_path / "r.csv"
    p.write_text("post,hook_score,views,watched_3s\np1,5,1000,71%\np2,6,900,64\n")
    rows = RT.parse_table(p)
    assert rows[0]["watched_3s"] == 0.71
    assert rows[1]["watched_3s"] == 0.64


def test_markdown_table_is_accepted(tmp_path: Path) -> None:
    p = tmp_path / "RESULTS.md"
    p.write_text("| post | hook_score | views | watched_3s |\n"
                 "|---|---|---|---|\n| post7 | 5.0 | 120k | 0.61 |\n")
    rows = RT.parse_table(p)
    assert rows and rows[0]["hook"] == 5.0 and rows[0]["watched_3s"] == 0.61
