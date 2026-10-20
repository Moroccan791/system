"""Speed ramps, pre-flight, batch and the results loop.

These are the operational pieces: the ones that decide whether a raw is worth
editing, whether a ramp keeps sync, whether a drop can be rendered in one
command, and whether the numbers ever get written down.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import preflight as PF       # noqa: E402
import results_tracker as RT  # noqa: E402
import retime as RET          # noqa: E402
import sound_design as SD     # noqa: E402


# ------------------------------------------------------------------- retime
def test_ramp_duration_maths() -> None:
    clean, dur = RET.plan([(2.0, 4.0, 0.90)], 10.0)
    assert clean == [(2.0, 4.0, 0.9)]
    assert abs(dur - (10.0 + 2.0 * (1 / 0.9 - 1))) < 0.01


def test_ramp_factors_are_clamped() -> None:
    clean, _ = RET.plan([(1.0, 3.0, 0.10)], 5.0)          # absurd request
    assert clean[0][2] == 0.85
    clean, _ = RET.plan([(1.0, 3.0, 3.0)], 5.0)
    assert clean[0][2] == 1.15


def test_ramp_ignores_tiny_or_overlapping_windows() -> None:
    clean, _ = RET.plan([(1.0, 1.05, 0.9), (2.0, 4.0, 0.9), (3.0, 5.0, 1.1)], 6.0)
    assert len(clean) == 1 and clean[0][:2] == (2.0, 4.0)


def test_map_time_round_trips_the_ramp() -> None:
    clean, _ = RET.plan([(2.0, 4.0, 0.9)], 10.0)
    assert RET.map_time(1.0, clean) == 1.0
    assert abs(RET.map_time(4.0, clean) - (2.0 + 2.0 / 0.9)) < 1e-6
    assert abs(RET.map_time(6.0, clean) - (6.0 + 2.0 * (1 / 0.9 - 1))) < 1e-6


# ---------------------------------------------------------------- preflight
def _clip(path: Path, *, seconds: float = 2.0) -> None:
    ff = RET.ffmpeg()
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"testsrc=size=270x480:rate=30:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}",
                    "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", str(path)], check=True)


def test_preflight_flags_a_small_clip(tmp_path: Path) -> None:
    p = tmp_path / "small.mp4"
    _clip(p)
    rows, failed = PF.check(p)
    by = {r["check"]: r for r in rows}
    assert by["readable"]["state"] == "PASS"
    assert by["resolution"]["state"] == "FAIL", "270px short side must fail"
    assert by["face_time"]["state"] == "FAIL", "testsrc has no face"
    assert failed is True


def test_preflight_reports_audio(tmp_path: Path) -> None:
    p = tmp_path / "small.mp4"
    _clip(p)
    rows, _ = PF.check(p)
    audio = next(r for r in rows if r["check"] == "audio")
    assert "dBFS" in audio["detail"]


# ----------------------------------------------------------------- results
def test_append_row_then_refuse_a_duplicate(tmp_path: Path) -> None:
    p = tmp_path / "RESULTS.md"
    RT.append_row(p, post="post1", hook=5.0, views=1000, watched_3s=0.42, duration=21.0)
    RT.append_row(p, post="post2", hook=6.5, views=2000, watched_3s=0.55, duration=20.0)
    text = p.read_text()
    assert text.count("| post1 |") == 1 and text.count("| post2 |") == 1
    rows = RT.parse_table(p)
    assert [r["post"] for r in rows][-2:] == ["post1", "post2"]
    try:
        RT.append_row(p, post="post1", hook=5.0, views=1, watched_3s=0.1, duration=21.0)
    except SystemExit:
        pass
    else:
        raise AssertionError("a duplicate post must be refused")


# ------------------------------------------------------------------- audio
def test_emphasis_tick_is_quiet_and_short() -> None:
    tk = SD.tick()
    assert 0 < len(tk) < SD.RATE // 10
    assert 0.02 < float(np.abs(tk).max()) < 0.10, "a tick must sit under the voice"
