"""Cutting dead air without breaking everything timed against the old clock."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import timeline as TL  # noqa: E402


def words(spans):
    return [{"at": a, "end": b} for a, b in spans]


def test_no_long_gaps_is_the_identity() -> None:
    segs = TL.keep_segments(words([(0.0, 1.0), (1.2, 2.0), (2.1, 3.0)]), duration=3.0)
    assert segs == [(0.0, 3.0)]
    assert TL.Timeline(segs).is_identity


def test_one_long_pause_is_removed() -> None:
    segs = TL.keep_segments(words([(0.0, 1.0), (3.0, 4.0)]), duration=4.0)
    tl = TL.Timeline(segs)
    assert not tl.is_identity
    trimmed = tl.preview()["removed"]
    assert 1.3 < trimmed < 1.9, trimmed       # 1.0..3.0 minus the padding, kept air


def test_mapping_shifts_everything_after_the_cut() -> None:
    tl = TL.Timeline([(0.0, 1.0), (3.0, 4.0)])
    assert tl.map(0.5) == 0.5
    assert abs(tl.map(3.0) - 1.0) < 1e-6      # the cut stitches 1.0 straight to 3.0
    assert abs(tl.map(3.5) - 1.5) < 1e-6
    assert abs(tl.duration - 2.0) < 1e-6


def test_mapping_inside_a_removed_gap_pins_to_the_cut() -> None:
    tl = TL.Timeline([(0.0, 1.0), (3.0, 4.0)])
    assert abs(tl.map(2.0) - 1.0) < 1e-6


def test_short_gaps_are_left_alone() -> None:
    segs = TL.keep_segments(words([(0.0, 1.0), (1.4, 2.0)]), duration=2.0)
    assert segs == [(0.0, 2.0)]


def test_cuts_never_leave_less_air_than_asked() -> None:
    # three pauses, each just over the threshold: they must not stutter
    segs = TL.keep_segments(words([(0.0, 0.6), (1.3, 1.9), (2.6, 3.2)]),
                            duration=3.2, keep_air=0.8)
    gaps = [b[0] - a[1] for a, b in zip(segs, segs[1:])]
    assert all(g >= 0.8 for g in gaps), segs


def test_first_and_last_are_trimmed_to_the_clip_edges() -> None:
    segs = TL.keep_segments(words([(0.0, 1.0), (3.0, 4.0)]), duration=10.0)
    assert segs[0][0] == 0.0
    assert segs[-1][1] == 10.0
