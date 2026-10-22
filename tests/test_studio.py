"""Invariants for studio/. No rendering — every test here is fast."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from studio.grid import analyse as analyse_track
from studio.plan import DENSITY, build_plan, summarise
from studio.shots import Shot, Source
from studio.typecards import render_card


@pytest.fixture(scope="module")
def score(tmp_path_factory) -> Path:
    from studio.synth_score import build

    return build(tmp_path_factory.mktemp("score") / "score.wav")


@pytest.fixture(scope="module")
def grid(score):
    return analyse_track(score)


def test_grid_finds_tempo_and_phase(grid):
    """96 BPM, first beat at 0.625 s. Two-stage search must land within a frame."""
    assert grid.bpm == pytest.approx(96.0, abs=0.15)
    assert grid.phase == pytest.approx(0.625, abs=0.034)   # < 1 frame at 30fps


def test_grid_finds_the_drop(grid):
    """The synthetic score drops at 12.5 s and the drop is the loud run."""
    drop = [s for s in grid.sections if s.label == "drop"]
    assert drop, "no drop section found"
    assert 12.0 <= drop[0].start <= 13.5


def test_onsets_are_on_the_beat(grid):
    """Most onsets should sit near a 16th of the grid."""
    period = 60.0 / grid.bpm
    errs = []
    for t in grid.onsets:
        b = (t - grid.phase) / period
        errs.append(abs(b - round(b * 4) / 4) * period)
    near = sum(1 for e in errs if e < 0.04)
    assert near / len(errs) > 0.6


def _fake_source(n=40, dur=6.0, fps=30.0) -> Source:
    rng = np.random.default_rng(0)
    shots = [Shot(index=i, src_in=i * dur, src_out=(i + 1) * dur,
                  motion=float(rng.random()), sharp=float(rng.uniform(300, 3000)),
                  bright=float(rng.uniform(25, 180)), sat=float(rng.random()),
                  colour="warm") for i in range(n)]
    return Source(path="fake.mp4", width=1920, height=1080, fps=fps,
                  duration=n * dur, shots=shots)


def test_plan_never_freezes_a_frame(grid):
    """A cut must not outlast its source shot. No frame is ever held."""
    src = _fake_source(dur=2.0)          # every shot is 2s
    plan = build_plan(grid, src, 0.0, 30.0)
    for c in plan.cuts:
        assert c.src_dur <= 2.0 + 1e-6
        assert c.dur <= 2.0 / c.speed + 1e-6
    assert max(c.dur for c in plan.cuts) < 2.0


def test_plan_is_a_build_then_a_drop(grid):
    src = _fake_source()
    plan = build_plan(grid, src, 0.0, 30.0)
    by_act = {a: [c for c in plan.cuts if c.act == a] for a in DENSITY}
    build, drop = by_act["build"], by_act["drop"]
    assert build and drop
    # the whole point: the build is sparse and the drop is dense
    assert len(drop) > 4 * len(build)
    median = lambda cs: sorted(c.dur for c in cs)[len(cs) // 2]
    assert median(drop) < 0.75 < median(build)


def test_plan_reuses_shots_but_never_adjacent(grid):
    src = _fake_source()
    plan = build_plan(grid, src, 0.0, 30.0)
    for a, b in zip(plan.cuts, plan.cuts[1:]):
        assert a.shot != b.shot


def test_plan_flashes_are_budgeted(grid):
    src = _fake_source()
    plan = build_plan(grid, src, 0.0, 30.0)
    drop = [c for c in plan.cuts if c.act == "drop"]
    flashes = [c for c in drop if c.flash]
    assert flashes, "the reference earns at least one flash"
    assert len(flashes) <= max(1, int(len(drop) * 0.25))


def test_plan_is_reproducible(grid):
    src = _fake_source()
    a = build_plan(grid, src, 0.0, 30.0, seed=3).as_dict()
    b = build_plan(grid, src, 0.0, 30.0, seed=3).as_dict()
    c = build_plan(grid, src, 0.0, 30.0, seed=4).as_dict()
    assert a == b
    assert a != c


def test_cuts_land_on_the_grid(grid):
    src = _fake_source()
    plan = build_plan(grid, src, 0.0, 30.0)
    period = 60.0 / grid.bpm
    for cut in plan.cuts:
        b = cut.out_start / period
        assert abs(b - round(b * 4) / 4) * period < 0.002


def test_card_beats_are_relative_to_frame_one():
    """A script says "beat 28"; that must mean 28 beats after frame one."""
    from studio.compose import card_time

    assert card_time(0.0, 122.75) == 0.0
    assert card_time(28.0, 122.75) == pytest.approx(28 * 60 / 122.75, abs=1e-9)
    # four beats is one bar, whatever the tempo
    for bpm in (96.0, 122.75, 174.0):
        assert card_time(4.0, bpm) == pytest.approx(4 * 60 / bpm)


def test_cards_are_sized_to_the_frame():
    for text in ("WAIT", "MOMENT", "STILL HERE", "THEY SAID"):
        c = render_card(text, 1920, 1080)
        assert c.rgba.shape[1] <= 1920
        assert c.rgba.shape[0] <= int(1080 * 0.42)
        assert 0 <= c.x and c.x + c.rgba.shape[1] <= 1920
        assert 0 <= c.y and c.y + c.rgba.shape[0] <= 1080


def test_three_words_max_on_a_card():
    c = render_card("this is far too many words for one beat", 1920, 1080)
    assert len(c.text.split()) <= 3
