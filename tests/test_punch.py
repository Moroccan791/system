"""Camera that reacts to the words.

The authored zoom keys are a slow push across a whole clip. These pin the
faster layer that sits on top: a punch that lands on an emphasised word and
is gone before the next, and the A/B framing that stops a 20-second take from
reading as a static zoom.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import tight_posts as TP  # noqa: E402


def test_punch_peaks_at_the_word_and_returns_to_one() -> None:
    ev = TP.punch_events([2.0])
    assert TP.punch_at(1.0, ev) == 1.0, "nothing before the word"
    assert TP.punch_at(2.0, ev) == 1.0, "envelope starts at zero, not at full"
    peak = max(TP.punch_at(2.0 + i / 120, ev) for i in range(60))
    assert 1.02 < peak <= 1.036
    assert abs(TP.punch_at(2.0 + 0.07 + 0.20 + 0.38 + 0.05, ev) - 1.0) < 1e-6


def test_punch_never_exceeds_its_amount() -> None:
    ev = TP.punch_events([1.0, 3.0, 5.0])
    for i in range(0, 800):
        assert TP.punch_at(i / 100, ev) <= 1.0 + TP.PUNCH["amount"] + 1e-9


def test_punches_are_spaced_so_the_camera_never_fidgets() -> None:
    times = [0.5, 0.7, 0.9, 1.1, 2.4, 3.0, 9.0]
    ev = TP.punch_events(times)
    starts = [t for t, _ in ev]
    assert starts[0] == 0.5
    for a, b in zip(starts, starts[1:]):
        assert b - a >= TP.PUNCH["min_gap"]


def test_punch_count_is_capped() -> None:
    ev = TP.punch_events([i * 1.5 for i in range(40)])
    assert len(ev) <= TP.PUNCH["max"]


def test_ab_framing_alternates_only_after_a_cut() -> None:
    cuts = [3.0, 7.0, 12.0]
    assert TP.segment_scale(0.0, cuts) == 1.0
    assert TP.segment_scale(3.0, cuts) == 1.016
    assert TP.segment_scale(7.0, cuts) == 1.0
    assert TP.segment_scale(12.0, cuts) == 1.016


def test_combined_camera_stays_inside_the_crop_limit() -> None:
    """Natural push (1.10) plus a punch must not exceed what the crop can fill."""
    keys = [(0.0, 1.10)]
    ev = TP.punch_events([1.0])
    worst = max(TP.zoom_at(1.0 + i / 60, keys) * TP.punch_at(1.0 + i / 60, ev)
                for i in range(90))
    assert min(1.10, worst) <= 1.10


def test_framing_cuts_need_a_silence_not_a_card_boundary() -> None:
    # tiled cards: no silence anywhere -> no framing change at all
    tiled = [{"show_from": 0.0, "show_until": 1.0}, {"show_from": 1.0, "show_until": 2.0},
             {"show_from": 2.0, "show_until": 3.0}, {"show_from": 3.0, "show_until": 4.0}]
    assert TP.framing_cuts(tiled) == []

    # one real pause -> exactly one change, at the pause
    paused = [{"show_from": 0.0, "show_until": 1.0}, {"show_from": 1.0, "show_until": 2.0},
              {"show_from": 2.4, "show_until": 3.6}, {"show_from": 3.6, "show_until": 5.0}]
    assert TP.framing_cuts(paused) == [2.4]


def test_framing_cuts_are_spaced_and_capped() -> None:
    caps, t = [], 0.0
    for _ in range(12):
        caps.append({"show_from": t, "show_until": t + 1.0})
        t += 1.4          # every card is preceded by a 0.4 s silence
    cuts = TP.framing_cuts(caps, min_gap=3.5, max_cuts=4)
    assert len(cuts) <= 4
    assert all(b - a >= 3.5 for a, b in zip(cuts, cuts[1:])), cuts
