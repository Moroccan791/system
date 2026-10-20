"""Caption rules and the campaign gate, pinned.

These are the rules the clipping course states as numbers ("1-2 lines max,
~14 characters per line", "trim uh, um, you know, like"). They were applied
by hand before, which is how shipped files ended up with 24-character lines
and a visible "um". A test is what stops that from being a matter of memory.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import caption_rules as CR  # noqa: E402


def cells(*words: str) -> list[dict]:
    return [{"w": w, "kind": "conn", "at": i * 0.4, "end": i * 0.4 + 0.35}
            for i, w in enumerate(words)]


def test_lines_respect_the_character_budget() -> None:
    text = ("I will never be angry for a struggle that you know that we share "
            "we share").split()
    cards = CR.wrap_cells(cells(*text))
    for card in cards:
        assert len(card["lines"]) <= CR.MAX_LINES
        for line in card["lines"]:
            # one-word lines may exceed the budget; nothing else may
            if len(line) > 1:
                assert len(" ".join(c["w"] for c in line)) <= CR.MAX_LINE_CHARS


def test_no_orphan_words_when_a_merge_fits() -> None:
    """A one-word card inside a sentence means the wrapper gave up early."""
    cards = CR.wrap_cells(cells("she", "went", "into", "treatment,", "a",
                                "few", "months", "later,"))
    for card in cards[:-1]:
        assert sum(len(line) for line in card["lines"]) >= 2


def test_words_are_never_reordered_or_dropped() -> None:
    words = "That will come from that soil, and outside, um".split()
    cards = CR.wrap_cells(cells(*words))
    flat = [c["w"] for card in cards for line in card["lines"] for c in line]
    assert flat == words


def test_rewrap_keeps_sentences_apart() -> None:
    caps = [
        {"lines": [cells("that", "we", "share.")], "zone": "low"},
        {"lines": [cells("We", "share.")], "zone": "low"},
    ]
    cards = CR.rewrap(caps)
    assert len(cards) == 2
    assert cards[0]["lines"][0][-1]["w"] == "share."
    assert cards[1]["lines"][0][0]["w"] == "We"


def test_fillers_are_found_and_named() -> None:
    found = CR.filler_words("Um, and she's in recovery now, you know, like that".split())
    assert found == ["Um,", "you know", "like"]


def test_filler_gate_reads_a_clean_sentence() -> None:
    assert CR.filler_words("she went into treatment a few months later".split()) == []


def test_card_report_flags_long_lines() -> None:
    cards = [{"lines": [cells("she went into treatment.")]}]
    report = CR.card_report(cards)
    assert report["over_hard"], "a 24-character line must be reported"
    assert report["max_chars"] == len("she went into treatment.")


def test_card_report_accepts_manifest_words() -> None:
    """The gate reads a manifest of plain strings, not live cells."""
    report = CR.card_report([{"lines": [["I", "will"], ["never", "be"]]}])
    assert report["lines"] == 2
    assert report["max_chars"] == len("never be")
