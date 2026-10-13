"""Group timed words into caption cues.

Short-form captions (TikTok / Reels / Shorts) show 2-4 words at a time, one or
two lines, and they never split a sentence in a way that reads wrong. The rules
here are the ones editors apply by hand:

  * break on sentence-ending punctuation
  * break when a cue is full (words, characters or seconds)
  * break on a real pause in speech (>= `gap_break`)
  * never leave a 1-word cue behind if it can be absorbed
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..asr.base import Word

SENTENCE_END = (".", "!", "?", "…", "...")
CLAUSE_END = (",", ";", ":")


@dataclass
class Cue:
    index: int
    start: float
    end: float
    words: list[Word] = field(default_factory=list)
    lines: list[list[str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def display_text(self) -> str:
        return " ".join(" ".join(line) for line in self.lines)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["text"] = self.text
        d["duration"] = round(self.duration, 3)
        return d


def _char_len(words: list[Word]) -> int:
    return len(" ".join(w.text for w in words))


def _max_chars(text: str, max_chars: int) -> int:
    """Budget for one cue: `max_lines` lines of `max_chars`."""
    return max_chars


def layout_lines(words: list[Word], max_chars: int, max_lines: int) -> list[list[str]]:
    """Break a cue into (at most `max_lines`) visually balanced lines."""
    texts = [w.text for w in words]
    if max_lines <= 1:
        return [texts]
    # greedy fill, then balance the last two lines if the split is lopsided
    lines: list[list[str]] = [[]]
    for t in texts:
        cand = lines[-1] + [t]
        if lines[-1] and len(" ".join(cand)) > max_chars:
            lines.append([t])
        else:
            lines[-1] = cand
    if len(lines) > max_lines:
        # too many lines: pack into max_lines by character budget
        budget = max(max_chars, int(len(" ".join(texts)) / max_lines) + 1)
        lines = [[]]
        for t in texts:
            cand = lines[-1] + [t]
            if lines[-1] and len(" ".join(cand)) > budget and len(lines) < max_lines:
                lines.append([t])
            else:
                lines[-1] = cand
    if len(lines) == 2 and len(lines[0]) > 1 and len(lines[1]) == 1:
        moved = lines[0].pop()
        lines[1].insert(0, moved)
    return [ln for ln in lines if ln]


def group_words(words: list[Word], *, max_words: int = 4, max_chars: int = 22,
                max_lines: int = 1, max_duration: float = 2.6,
                gap_break: float = 0.45, min_duration: float = 0.6,
                split_on_sentence: bool = True) -> list[Cue]:
    """Timed words -> caption cues."""
    clean = [w for w in words if w.text and w.text.strip()]
    if not clean:
        return []
    cues: list[Cue] = []
    current: list[Word] = []

    def flush() -> None:
        if current:
            cues.append(Cue(index=len(cues), start=current[0].start,
                            end=current[-1].end, words=list(current)))

    for word in clean:
        if current:
            prev = current[-1]
            gap = word.start - prev.end
            too_many = len(current) >= max_words
            too_long = _char_len(current) + 1 + len(word.text) > _max_chars("", max_chars) * max_lines
            too_slow = (word.end - current[0].start) > max_duration
            if gap > gap_break or too_many or too_long or too_slow:
                flush()
                current = []
        current.append(word)
        if split_on_sentence and word.text.rstrip().endswith(SENTENCE_END):
            flush()
            current = []
    flush()

    # absorb orphan single-word cues (unless they end a sentence or say a lot)
    merged: list[Cue] = []
    for cue in cues:
        orphan = (
            len(cue.words) == 1
            and merged
            and len(merged[-1].words) < max_words
            and not merged[-1].words[-1].text.rstrip().endswith(SENTENCE_END)
            and _char_len(merged[-1].words) + 1 + len(cue.words[0].text) <= max_chars * max_lines
            and (cue.end - merged[-1].start) <= max_duration * 1.25
            and cue.duration >= min_duration * 0.4
        )
        if orphan:
            merged[-1].words.extend(cue.words)
            merged[-1].end = cue.words[-1].end
        else:
            merged.append(cue)

    for i, cue in enumerate(merged):
        cue.index = i
        cue.lines = layout_lines(cue.words, max_chars, max_lines)
    return merged
