"""Hook strength, pinned to the campaign's own reference clips.

The rubric is calibrated on three measured examples (defiance 8.0, number
6.0, setup-first 0.6). These tests keep that ordering - if someone "improves"
the weights and the setup-first clip starts beating the defiance one, that is
a regression, not a refinement.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import hook_lab as HL  # noqa: E402


def words(text: str, rate: float = 0.22) -> list[dict]:
    return [{"text": w, "start": round(i * rate, 3),
             "end": round(i * rate + rate * 0.8, 3)}
            for i, w in enumerate(text.split())]


def score(text: str) -> float:
    return HL.classify(text, words(text))[0]


def test_reference_ordering_holds() -> None:
    defiance = score("Coming off as a player isn't a bad thing i'm sorry i don't care")
    number = score("$6.6 billion going to fans men")
    setup = score("When you use regular cold approach like on the street")
    assert defiance > number > setup
    assert defiance >= 7.0 and setup < 2.0


def test_filler_opening_is_penalised() -> None:
    assert score("um so basically what happened was") < score("Nobody tells you this")


def test_a_number_is_concrete() -> None:
    assert score("80% of men aren't going to succeed") >= 6.0


def test_shipped_post6_opening_is_weak() -> None:
    """The clip we shipped opens on setup; the lab must say so."""
    assert score("I'm trying to build a beautiful") < 4.0


def test_shipped_post7_opening_clears_the_floor() -> None:
    assert score("I will never be angry for a struggle") >= 4.0


def test_candidates_include_card_boundaries() -> None:
    ws = words("one two three four five six seven eight")
    cards = [{"lines": [[{"w": "five", "at": ws[4]["start"]}]]}]
    starts = {c["start"] for c in HL.candidates(ws, cards=cards)}
    assert ws[4]["start"] in starts


def test_candidates_start_at_the_head() -> None:
    ws = words("a b c d", rate=0.1)          # no pauses anywhere
    assert HL.candidates(ws)[0]["start"] == ws[0]["start"]
