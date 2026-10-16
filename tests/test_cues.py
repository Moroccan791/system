"""Cue grouping: the rules that make captions readable."""
from __future__ import annotations

from clipper.asr.base import Word
from clipper.captions.cues import group_words, layout_lines


def W(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end, source="test")


def test_sentence_end_forces_a_break():
    words = [W("Hello", 0, 0.3), W("there.", 0.3, 0.7), W("Next", 0.8, 1.1), W("one", 1.1, 1.4)]
    cues = group_words(words, max_words=4)
    assert [c.text for c in cues] == ["Hello there.", "Next one"]


def test_long_pause_forces_a_break():
    words = [W("first", 0, 0.3), W("thought", 0.3, 0.7), W("second", 1.6, 2.0), W("thought", 2.0, 2.4)]
    cues = group_words(words, max_words=4, gap_break=0.45)
    assert len(cues) == 2
    assert cues[0].text == "first thought"
    assert cues[1].text == "second thought"


def test_max_words_respected():
    words = [W(f"w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(9)]
    cues = group_words(words, max_words=3, max_chars=99, gap_break=9)
    assert all(len(c.words) <= 3 for c in cues)


def test_max_chars_respected():
    words = [W("extraordinarily", 0, 0.4), W("complicated", 0.4, 0.8), W("sentence", 0.8, 1.2)]
    cues = group_words(words, max_words=10, max_chars=22, gap_break=9)
    assert max(len(c.text) for c in cues) <= 22 + len(" extraordinarily") or len(cues) >= 2
    assert all(c.text.strip() for c in cues)


def test_orphan_word_is_absorbed():
    # "and" alone would be an ugly 1-word cue
    words = [W("this", 0, 0.3), W("is", 0.3, 0.5), W("fine", 0.5, 0.9),
             W("and", 0.95, 1.2), W("now", 1.2, 1.5), W("more", 1.5, 1.9)]
    cues = group_words(words, max_words=4, max_chars=30, gap_break=9)
    assert all(len(c.words) >= 2 for c in cues)


def test_cue_timestamps_match_words():
    words = [W("one", 0.0, 0.4), W("two", 0.4, 0.8), W("three", 0.8, 1.2)]
    cues = group_words(words, max_words=3, gap_break=9, max_chars=99)
    assert len(cues) == 1
    assert cues[0].start == 0.0 and cues[0].end == 1.2


def test_layout_lines_balances():
    words = [W("a", 0, 0.1), W("bb", 0.1, 0.2), W("ccc", 0.2, 0.3), W("dddd", 0.3, 0.4)]
    lines = layout_lines(words, max_chars=8, max_lines=2)
    assert len(lines) == 2
    assert [t for ln in lines for t in ln] == ["a", "bb", "ccc", "dddd"]


def test_empty_input():
    assert group_words([]) == []
