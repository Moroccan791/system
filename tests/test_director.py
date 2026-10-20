"""When to use which move - and when using it would be wrong.

The user's correction: "all of these is important at times and i need u to
figure out when is which one thing needed." So these tests are about the
rules, not the effects: a single continuous shot must never get a whip, a
moving camera must never get a dolly, a dark room must never get a light wrap,
and continuous speech must never get a framing jump.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import director as D  # noqa: E402


def cards(*spans: tuple[float, float]) -> list[dict]:
    return [{"show_from": a, "show_until": b, "lines": [["word"]]} for a, b in spans]


def meas(**kw) -> dict:
    base = {"cuts": [], "motion": 5.0,
            "face": {"found": 1.0, "area": 0.25, "steadiness": 0.9, "bg_vs_face": 0.0}}
    base.update(kw)
    return base


def plan(m, **kw) -> dict:
    kw.setdefault("cards", cards((0.0, 20.0)))
    kw.setdefault("words", [{"at": i * 0.4, "end": i * 0.4 + 0.3} for i in range(50)])
    kw.setdefault("key_words", 3)
    kw.setdefault("duration", 20.0)
    return D.decide(m, **kw)


# ------------------------------------------------------------------ transitions
def test_one_continuous_shot_gets_no_transition() -> None:
    p = plan(meas(cuts=[]))
    assert p["transition"]["use"] is False
    assert "continuous shot" in p["transition"]["why"]


def test_two_shots_earn_a_transition() -> None:
    p = plan(meas(cuts=[7.5]))
    assert p["transition"]["use"] is True
    assert p["transition"]["where"] == [7.5]


# ------------------------------------------------------------------ light wrap
def test_bright_background_earns_the_light_wrap() -> None:
    p = plan(meas(face={"found": 1.0, "area": 0.25, "steadiness": 0.9, "bg_vs_face": 0.30}))
    assert p["light_wrap"]["use"] is True


def test_dark_room_gets_no_light_wrap() -> None:
    # post 7: background sits 61% *below* skin, so there is no spill to wrap
    p = plan(meas(face={"found": 1.0, "area": 0.28, "steadiness": 0.9, "bg_vs_face": -0.61}))
    assert p["light_wrap"]["use"] is False


def test_no_face_gets_no_light_wrap() -> None:
    p = plan(meas(face={"found": 0.0, "area": 0.0, "steadiness": 0.0, "bg_vs_face": 0.4}))
    assert p["light_wrap"]["use"] is False


# --------------------------------------------------------------------- dolly
def test_static_single_take_earns_the_dolly() -> None:
    p = plan(meas(cuts=[], motion=4.0))
    assert p["dolly"]["use"] is True


def test_moving_camera_gets_no_dolly() -> None:
    p = plan(meas(cuts=[], motion=80.0))
    assert p["dolly"]["use"] is False
    assert "seasick" in p["dolly"]["why"]


def test_a_clip_with_cuts_gets_no_dolly() -> None:
    p = plan(meas(cuts=[4.0], motion=3.0))
    assert p["dolly"]["use"] is False
    assert "belongs on the cut" in p["dolly"]["why"]


# ------------------------------------------------------------------ A/B framing
def test_continuous_speech_gets_no_framing_jump() -> None:
    p = plan(meas(), cards=cards((0.0, 1.0), (1.0, 2.0), (2.0, 3.0)))
    assert p["ab_framing"]["use"] is False


def test_a_real_silence_earns_the_framing_change() -> None:
    p = plan(meas(), cards=cards((0.0, 1.0), (1.6, 3.0), (3.0, 5.0)))
    assert p["ab_framing"]["use"] is True
    assert p["ab_framing"]["where"] == [1.0]


# ---------------------------------------------------------------------- punches
def test_no_emphasis_words_means_no_punches() -> None:
    p = plan(meas(), key_words=0)
    assert p["punches"]["use"] is False


def test_slow_speech_gets_no_punches() -> None:
    p = plan(meas(), key_words=4, words=[{"at": i * 2.0, "end": i * 2.0 + 0.4} for i in range(8)],
             duration=16.0)
    assert p["punches"]["use"] is False


def test_normal_speech_with_emphasis_gets_punches() -> None:
    p = plan(meas(), key_words=5)
    assert p["punches"]["use"] is True


# ------------------------------------------------------------------ the opener
def test_opening_line_always_gets_the_title() -> None:
    p = plan(meas())
    assert p["kinetic_type"]["use"] is True


# --------------------------------------------------------------- shot detection
def test_shot_detection_separates_a_hard_cut_from_a_head_turn() -> None:
    rng = np.random.default_rng(0)
    a = (rng.random((60, 40, 3)) * 255).astype(np.uint8)
    b = (rng.random((60, 40, 3)) * 60 + 180).astype(np.uint8)   # totally different shot
    turn = np.roll(a, 4, axis=1)                                # same shot, moved
    frames = [(0.0, a), (0.25, turn), (0.5, b)]
    cuts = D.shot_cuts(frames, threshold=0.5)
    assert cuts == [0.5], cuts


def test_transitions_never_touch_the_opening_or_the_card() -> None:
    cuts = [0.53, 5.33, 6.67, 16.8, 20.72, 21.0]
    kept = D.filter_transitions(cuts, duration=21.6, endcard=20.38)
    assert 0.53 not in kept, "the hook must not be smeared"
    assert all(c < 20.38 for c in kept), "no whip into the end card"


def test_transitions_are_thinned_out() -> None:
    cuts = [4.0, 4.2, 4.4, 8.0]
    kept = D.filter_transitions(cuts, duration=12.0, endcard=11.0)
    assert len(kept) == 2 and kept[0] == 4.0 and kept[1] == 8.0
