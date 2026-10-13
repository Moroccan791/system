"""What in the transcript makes a moment worth clipping?

Short-form editors pick moments for recognisable reasons: a question that sets
up an answer, a number that surprises, a story with stakes, someone contradicting
what "everyone knows". Those are cheap to spot in text and much cheaper than
running a classifier - and because every rule carries its own label, the output
can explain itself: "starts on a question", "contains a statistic".
"""
from __future__ import annotations

import re

import numpy as np

# (pattern, weight, explanation) - weights are deliberately small and additive;
# several weak signals should beat one strong keyword.
PATTERNS: tuple[tuple[str, float, str], ...] = (
    # questions set something up
    (r"\?", 0.20, "a question"),
    (r"^\s*(who|what|why|how|when|where|which|do you|did you|have you|are you|"
     r"is it|can you|would you|should you)\b", 0.18, "opens with a question"),
    # specifics beat generalities
    (r"\b\d+(\.\d+)?\s*(%|percent|per cent|x|times)\b", 0.22, "a percentage or multiple"),
    (r"\$\s?\d|\b\d+\s*(dollars|bucks|grand|k)\b", 0.22, "a money figure"),
    (r"\b\d{2,}\b", 0.12, "a specific number"),
    (r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+"
     r"(things|reasons|ways|steps|rules|mistakes|lessons)\b", 0.24, "a list promise"),
    # curiosity and contradiction
    (r"\b(nobody|no one|nobody's|nobody is)\b", 0.22, "a contrarian claim"),
    (r"\b(the truth|secret|nobody tells you|they don't want|what they don't)\b", 0.22,
     "a curiosity hook"),
    (r"\b(actually|in fact|turns out|here's why|the reason is)\b", 0.14, "a reveal"),
    (r"\b(never|always|every single time|the only way)\b", 0.14, "an absolute claim"),
    # stakes
    (r"\b(i lost|i made|i spent|we lost|we made|almost|went wrong|failed|"
     r"the mistake|my biggest)\b", 0.20, "a story with stakes"),
    # emotion
    (r"\b(crazy|insane|wild|shocking|unbelievable|hilarious|terrifying|brutal)\b", 0.18,
     "strong emotion"),
    (r"\b(best|worst|biggest|huge|massive|tiny)\b", 0.10, "a superlative"),
    # talking to the viewer
    (r"\b(you|your|you're|you've)\b", 0.08, "speaks to the viewer"),
    (r"\b(laughs?|laughing|jokes?|kidding)\b", 0.10, "a laugh"),
)

# filler that marks a moment as padding rather than content
FILLER = re.compile(
    r"\b(um+|uh+|erm+|you know|kind of|sort of|i mean|anyway|so yeah|"
    r"like i said|as i was saying)\b", re.IGNORECASE)

_SENTENCE_END = re.compile(r"[.!?…]\s*$")


def score_text(text: str) -> tuple[float, list[str]]:
    """0..1 hook score for a stretch of speech, plus the reasons for it."""
    if not text or not text.strip():
        return 0.0, []
    lowered = text.lower()
    score = 0.0
    reasons: list[str] = []
    for pattern, weight, reason in PATTERNS:
        if re.search(pattern, lowered if not pattern.startswith("^") else text.lower()):
            score += weight
            if reason not in reasons:
                reasons.append(reason)
    fillers = len(FILLER.findall(lowered))
    if fillers:
        penalty = min(0.25, 0.05 * fillers)
        score -= penalty
        reasons.append(f"{fillers} filler phrase(s)")
    # a wall of words with no signal is not a hook
    if score <= 0.05:
        reasons.append("no obvious hook")
    return float(np.clip(score, 0.0, 1.0)), reasons


def sentence_units(words, *, max_gap: float = 0.75, max_words: int = 70,
                   max_len: float = 30.0, min_words: int = 3) -> list[dict]:
    """Group timed words into sentences / utterances.

    Splits on punctuation when the transcriber provides it, on pauses when it
    does not, and on length as a last resort so a monologue without punctuation
    still turns into sensible units.
    """
    units: list[dict] = []
    current: list = []
    for word in words:
        if current:
            gap = float(word.start) - float(current[-1].end)
            too_long = len(current) >= max_words or (float(word.end) - float(current[0].start)) > max_len
            if gap > max_gap or too_long:
                _flush(units, current, min_words)
                current = []
        current.append(word)
        if _SENTENCE_END.search(str(word.text).strip()):
            _flush(units, current, min_words)
            current = []
    _flush(units, current, min_words)
    return units


def _flush(units: list[dict], words: list, min_words: int) -> None:
    if len(words) < min_words:
        return
    text = " ".join(str(w.text).strip() for w in words).strip()
    if not text:
        return
    units.append({
        "start": round(float(words[0].start), 3),
        "end": round(float(words[-1].end), 3),
        "text": text,
        "words": words,
    })
