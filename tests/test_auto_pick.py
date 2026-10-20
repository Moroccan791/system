"""Automatic clip + hook selection: the decision, not a shortlist.

The user's correction was blunt and right - "why do u need me to pick the
hook". So the picker is what chooses, and these tests pin the behaviour that
matters: it starts on the strong line even when a setup line comes first, it
never ends a cut mid-sentence, it respects the window, and its picks do not
overlap.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import auto_pick as AP  # noqa: E402


def build(spec: list[tuple[str, float, float]]) -> list[dict]:
    return [{"text": t, "start": s, "end": e} for t, s, e in spec]


def talker(lines: list[tuple[str, float]], rate: float = 0.30,
           gap_after: float = 0.55) -> list[dict]:
    """Words at `rate` s each, `gap_after` s of air at the end of each line."""
    out, t = [], 0.0
    for text, _pause in lines:
        words = text.split()
        for i, w in enumerate(words):
            out.append({"text": w, "start": round(t, 3), "end": round(t + rate * 0.85, 3)})
            t += rate
        t += gap_after
    return out


def test_starts_on_the_strong_line_not_the_setup() -> None:
    words = talker([
        ("When you use regular cold approach", 1),
        ("80% of men are not going to succeed", 1),
        ("in an unfamiliar environment", 1),
        ("that is the whole point", 1),
    ])
    picks = AP.choose(AP.windows(words, 6, 14, 10), 1)
    assert picks, "a window must be proposed"
    assert picks[0]["start"] > 1.5, "must not open on the setup line at 0"


def test_never_ends_mid_sentence() -> None:
    words = talker([
        ("nobody tells you this about dating", 1),
        ("the truth is most men fail here", 1),
        ("because they never ask", 1),
    ])
    hard = [c for c in AP.windows(words, 4, 12, 8) if not c["soft_cut"]]
    assert hard, "at least one hard boundary exists in this fixture"
    for c in hard:
        assert AP.ends_sentence(words, next(
            i for i, w in enumerate(words) if abs(w["end"] - c["end"]) < 0.01) + 1)


def test_respects_the_duration_window() -> None:
    words = talker([("some line of speech here", 1)] * 12)
    for c in AP.windows(words, 5, 9, 7):
        assert 5 - 0.01 <= c["duration"] <= 9 + 0.01


def test_picks_do_not_overlap() -> None:
    words = talker([("line number one is here", 1), ("line number two is here", 1),
                    ("line number three is here", 1), ("line number four is here", 1)])
    picks = AP.choose(AP.windows(words, 3, 8, 5), 3)
    for a, b in zip(picks, picks[1:]):
        assert a["end"] <= b["start"] or b["end"] <= a["start"]


def test_filler_costs_score() -> None:
    clean = talker([("80% of men are not going to succeed", 1),
                    ("that is the whole point", 1)])
    dirty = talker([("um 80% of men are not going to succeed", 1),
                    ("you know that is the whole point", 1)])
    best_clean = AP.choose(AP.windows(clean, 3, 10, 6), 1)[0]["score"]
    best_dirty = AP.choose(AP.windows(dirty, 3, 10, 6), 1)[0]["score"]
    assert best_clean > best_dirty
