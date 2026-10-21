"""The peak ceiling has to hold between the samples, not on them.

A file limited to -1.3 dBFS at 48 kHz measured +0.0 dBTP: alimiter saw the
samples, the meter saw the waveform they describe. The campaign gate reads the
meter, so the limiter has to run where the inter-sample peak is a sample.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source() -> str:
    return (ROOT / "scripts" / "whop" / "tight_posts.py").read_text()


def test_limiter_oversamples_before_it_limits() -> None:
    src = _source()
    body = src.split("def apply_limiter", 1)[1].split("\ndef ", 1)[0]
    body = body.split("linear = 10 **", 1)[1]      # past the docstring
    assert "aresample=192000" in body, "the limiter must see inter-sample peaks"
    assert body.index("aresample=192000") < body.index("alimiter"), (
        "the upsample has to come before the limiter, not after it")
    assert "aresample=48000" in body, "and the program goes back to 48 kHz"


def test_the_settle_loop_checks_both_loudness_and_peak() -> None:
    body = _source().split("def settle_audio", 1)[1].split("\ndef ", 1)[0]
    assert "LOUD_TARGET" in body and "PEAK_TARGET" in body
    assert re.search(r"tp\s*<=\s*PEAK_TARGET", body), (
        "settle_audio must not report success while the peak is over")
