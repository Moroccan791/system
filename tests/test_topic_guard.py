"""The DO NOT CLIP guard: block the moment before the clip is cut.

Every test here maps to a line in the 2 Bears brief. The important one is
`test_banned_moment_invalidates_the_window` - a clip that needs the taboo line
for its punchline cannot be saved by trimming around it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import topic_guard as TG  # noqa: E402

LEX = TG.load_lexicon(ROOT / "campaigns" / "two_bears_ep344")


def words(*spans):
    """spans: (text, start) - 0.4s per word."""
    out = []
    for text, start in spans:
        out.append({"text": text, "start": start, "end": start + 0.35})
    return out


def test_hitler_and_nazi_are_blocked_and_never_allowed_in_text() -> None:
    w = words(("so", 0.0), ("Hitler", 0.4), ("again", 0.8))
    hits = TG.scan_words(w, lexicon=LEX)
    assert any(h["category"] == "nazi" and h["severity"] == "block" for h in hits)
    text = TG.scan_text("Tom does his Hitler bit", lexicon=LEX)
    assert any(h["category"] == "nazi" for h in text)


def test_multi_word_self_harm_phrase_is_caught() -> None:
    w = words(("I", 0.0), ("will", 0.3), ("kill", 0.6), ("myself", 0.9))
    hits = TG.scan_words(w, lexicon=LEX)
    assert any(h["category"] == "self_harm" for h in hits)
    hit = next(h for h in hits if h["category"] == "self_harm")
    assert abs(hit["start"] - 0.6) < 0.01


def test_token_start_matching_is_not_a_substring_match() -> None:
    assert TG.scan_words(words(("nazis", 0.0)), lexicon=LEX)
    assert not TG.scan_words(words(("snazzy", 0.0)), lexicon=LEX)


def test_slur_blocks_and_is_banned_in_copy() -> None:
    hits = TG.scan_words(words(("that", 0.0), ("word", 0.3)), lexicon=LEX)
    assert hits == []
    sung = TG.scan_words(words(("what", 0.0), ("a", 0.3), ("retard", 0.6)), lexicon=LEX)
    assert any(h["category"] == "slur" and h["severity"] == "block" for h in sung)
    assert TG.scan_text("the retard bit", lexicon=LEX)


def test_banned_moment_invalidates_the_window() -> None:
    w = words(("funny", 0.0), ("setup", 0.4), ("kill", 1.0), ("myself", 1.3),
              ("punchline", 2.0), ("more", 2.4))
    hits = TG.scan_words(w, lexicon=LEX)
    ok, inside = TG.window_ok(0.0, 3.0, hits)
    assert ok is False, "a window containing the moment must be unusable"
    assert inside, "and it must say which hit it overlapped"


def test_window_just_before_a_banned_line_is_still_caught_by_padding() -> None:
    w = words(("funny", 0.0), ("bit", 0.5), ("hitler", 2.0))
    hits = TG.scan_words(w, lexicon=LEX)
    # clip ends at 1.6s, the banned word starts at 2.0s: pad 0.6 catches it
    ok, _ = TG.window_ok(0.0, 1.6, hits, pad=0.6)
    assert ok is False


def test_clean_window_is_usable() -> None:
    w = words(("bert", 0.0), ("told", 0.4), ("a", 0.8), ("story", 1.0),
              ("hitler", 9.0))
    hits = TG.scan_words(w, lexicon=LEX)
    ok, inside = TG.window_ok(0.0, 2.0, hits)
    assert ok is True and inside == []


def test_warning_categories_do_not_block() -> None:
    w = words(("my", 0.0), ("divorce", 0.4), ("was", 0.8))
    hits = TG.scan_words(w, lexicon=LEX)
    assert hits and all(h["severity"] == "warn" for h in hits)
    ok, inside = TG.window_ok(0.0, 1.4, hits)
    assert ok is True and inside, "usable, but flagged for a human read"


def test_strict_text_ignores_non_text_categories() -> None:
    relaxed = TG.scan_text("we talk politics and divorce", lexicon=LEX, strict=False)
    strict = TG.scan_text("we talk politics and divorce", lexicon=LEX, strict=True)
    assert relaxed and not strict


def test_lexicon_merges_campaign_terms_with_defaults() -> None:
    assert "slur" in LEX["categories"]
    assert len(LEX["categories"]["slur"]["terms"]) > 5, "campaign list must load"
    assert "sexual" in LEX["categories"], "defaults must survive the merge"
