"""The bed keeps its weight and its air, and gives up the speech band.

Post 4 measured the voice 11.3 dB over the bed after the limiter, under the
campaign's 12: the limiter squeezes the speech peaks harder than anything else
in the mix, so the bed has to leave the 250-3500 Hz band alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import render_clip  # noqa: E402

SR = 48000


def _level(freq: float) -> tuple[float, float]:
    t = np.arange(SR, dtype=np.float32) / SR
    x = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    y = render_clip._carve_voice_band(x, SR)
    return float(np.sqrt((x ** 2).mean())), float(np.sqrt((y ** 2).mean()))


def test_the_speech_band_comes_down_eighteen_db() -> None:
    a, b = _level(1000.0)
    assert 20 * np.log10(b / a) == pytest.approx(-18.0, abs=1.0)


def test_the_bass_and_the_air_are_untouched() -> None:
    for f in (100.0, 6000.0):
        a, b = _level(f)
        assert abs(20 * np.log10(b / a)) < 0.5, f"{f} Hz lost level"


def test_a_stereo_bed_keeps_its_channels() -> None:
    x = np.random.default_rng(0).normal(0, 0.1, (SR, 2)).astype(np.float32)
    y = render_clip._carve_voice_band(x, SR)
    assert y.shape == x.shape and y.dtype == np.float32
