"""Stage B image pipeline: gates, grade match, prompt discipline."""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "motion"))
import images  # noqa: E402

PROFILE = {"lab": [128.0, 134.0, 140.0],
           "lab_std": [42.0, 11.0, 13.0], "luma": 137.0, "sat": 75.0,
           "grain_sigma": 2.5, "lighting": "warm indoor light",
           "palette_words": "muted earthy tones"}
SLOT = {"id": "x", "type": "pip", "sentence": "We need a hoop",
        "subject": "a basketball hoop in a lounge"}


def _img(tmp: Path, name: str, arr: np.ndarray) -> Path:
    p = tmp / name
    cv2.imwrite(str(p), arr)
    return p


def test_blur_fails_sharpness(tmp_path):
    soft = np.full((900, 700, 3), 128, np.uint8)
    s = images.score_candidate(_img(tmp_path, "a.jpg", soft), SLOT, PROFILE)
    assert not s["pass"] and any("laplacian" in f for f in s["failures"])


def test_textured_passes_and_upscale_flagged(tmp_path):
    rng = np.random.default_rng(3)
    tex = rng.integers(60, 200, (900, 700, 3), dtype=np.uint8)
    s = images.score_candidate(_img(tmp_path, "a.jpg", tex), SLOT, PROFILE)
    assert s["pass"], s["failures"]
    assert s["needs_upscale"]  # 700px wide < 1252 pip target


def test_blown_exposure_fails(tmp_path):
    rng = np.random.default_rng(3)
    tex = rng.integers(60, 200, (900, 700, 3), dtype=np.uint8)
    tex[:450] = 255  # half the frame blown out
    s = images.score_candidate(_img(tmp_path, "a.jpg", tex), SLOT, PROFILE)
    assert not s["pass"] and any("exposure" in f for f in s["failures"])


def test_prompts_rotate_framings_and_carry_measured_look():
    ps = images.build_prompts(SLOT, PROFILE)
    assert len(ps) == len(images.FRAMINGS) and len(set(ps)) == len(ps)
    assert all(SLOT["subject"] in p and "warm indoor light" in p
               and "photorealistic photograph" in p for p in ps)
    assert "watermark" in images.NEGATIVE_PROMPT


def test_grade_match_moves_toward_video_without_colour_explosion():
    rng = np.random.default_rng(3)
    img = rng.integers(40, 160, (300, 400, 3), dtype=np.uint8)
    out = images.grade_match(img, PROFILE)
    before = images._delta_e(images._lab_mean(img), PROFILE["lab"])
    after = images._delta_e(images._lab_mean(out), PROFILE["lab"])
    assert after < before
    assert out.shape == img.shape and out.dtype == np.uint8


def test_subject_crop_hits_target(tmp_path):
    rng = np.random.default_rng(3)
    img = rng.integers(0, 255, (1376, 768, 3), dtype=np.uint8)
    out = images.subject_crop(img, 1080, 1920)
    assert out.shape[:2] == (1920, 1080)
