"""Story-arc shaping: where a clip is allowed to start, and where it must end.

The first real reviewer said it plainly: "it doesn't know when to cut the
videos - it literally stopped at a middle point." Energy windows pick loud
moments; a professional reel is a shape:

    setup/question -> build -> payoff -> reaction -> END

and the END is a sentence that lands, followed by a real breath of silence,
not a hard stop 13 seconds into the next topic or in the middle of nowhere.

This module answers three questions for a window:
  - how late may it END?   (the first real silence after a finished sentence,
                            with a capped reaction tail)
  - how early could it START?  (never more than `lead_in` before the first word)
  - does anything inside it PAY OFF?  (a number, a conclusion, an absolute)

An arc that fails its floor is rejected, not padded: reporting "this beat is
14 s and the campaign wants >=20" is a real answer; growing a 20 s shell
around a 10 s moment is exactly the "random part of the clip" feeling.
"""

from __future__ import annotations

import re

from ..asr.base import Word

SILENCE_AFTER = 0.9           # a pause this long means the beat has landed
REACTION_TAIL = 2.6           # max seconds of reaction/laughter kept after the last word
LEAD_IN = 0.3                 # max dead air before the first word
HOLD_AFTER_WORD = 0.55        # the payoff word needs at least this long to breathe
QUESTION = re.compile(r"^(who|what|why|how|when|where|which|have you|do you|did you|"
                      r"is it|would you|can you|are you|ever|guess)\b|\?$", re.I)
NUMBERISH = re.compile(r"\b\d+\b|\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|"
                       r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
                       r"nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|"
                       r"thousand|million|billion|percent|percentage|half|quarter)\b", re.I)
CONCLUSION = re.compile(r"\b(never|nothing|everything|always|worst|best|secret|truth|"
                        r"reason|real|actually|nobody|everybody|no one)\b", re.I)


def breath_groups(words: list[Word], *, gap: float = SILENCE_AFTER) -> list[list[Word]]:
    """Words cut at every real pause - the shape of speech before sentences."""
    groups: list[list[Word]] = []
    current: list[Word] = []
    # ASR output is not guaranteed monotonic (overlapping speakers interleave);
    # grouping unsorted words welds a whole minute into one "breath"
    for w in sorted(words, key=lambda w: float(w.start)):
        if current and float(w.start) - float(current[-1].end) >= gap:
            groups.append(current)
            current = []
        current.append(w)
    if current:
        groups.append(current)
    return groups


def _is_hook(text: str) -> bool:
    return bool(QUESTION.search(text.strip()))


def _is_payoff(text: str) -> bool:
    return bool(NUMBERISH.search(text) or CONCLUSION.search(text))


def find_arc(words: list[Word], seed_start: float, seed_end: float, *,
             min_s: float, max_s: float, gap: float = SILENCE_AFTER,
             tail: float = REACTION_TAIL, lead_in: float = LEAD_IN) -> dict | None:
    """Find the story arc that contains (seed_start, seed_end), honestly.

    Returns {"start", "end", "hook", "payoff", "note"} or None when the moment
    has no compliant arc (too short, or no payoff inside) - silence is findings.
    """
    groups = breath_groups(words, gap=gap)
    inside = [g for g in groups if float(g[-1].end) > seed_start and float(g[0].start) < seed_end]
    if not inside:
        return None

    # the arc opens on the breath-group containing the seed start, unless the
    # group before it is a question that sets it up and the gap is small
    first = inside[0]
    idx0 = groups.index(first)
    hook_group = first
    if idx0 > 0:
        prev = groups[idx0 - 1]
        if float(first[0].start) - float(prev[-1].end) < 2.0 and _is_hook(
                " ".join(str(w.text) for w in prev)) and not _is_hook(
                " ".join(str(w.text) for w in first)):
            hook_group = prev

    # the arc closes after the first real silence once the payoff is on screen;
    # include at most `tail` seconds of reaction, never cut into the next group
    last = inside[-1]
    close = float(last[-1].end)
    idx = groups.index(last)
    note = []
    if idx + 1 < len(groups):
        after = groups[idx + 1]
        pause = float(after[0].start) - close
        if pause >= gap or float(after[0].start) - close > 0.3:
            end = close + min(tail, max(HOLD_AFTER_WORD, pause - 0.05))
            if pause < gap:
                note.append(f"kept {float(after[0].start) - close:.1f}s of reaction, "
                            f"cut before the next sentence")
        else:
            end = close + min(tail, HOLD_AFTER_WORD)
    else:
        end = close + min(tail, HOLD_AFTER_WORD)
    start = max(0.0, float(hook_group[0].start) - lead_in)

    span = end - start
    if span > max_s:
        # crosstalk that never breathes has no arc boundary; say so instead
        # of returning a two-minute "arc" with a straight face
        return {"start": round(start, 3), "end": round(end, 3),
                "duration": round(span, 3), "hook": None, "payoff": None,
                "too_short": False, "unbounded": True,
                "note": f"speech runs {span:.0f}s without a {gap:.1f}s breath - "
                        "no silence-bounded arc here; end it on a sentence manually"}
    payoff = None
    for g in inside:
        text = " ".join(str(w.text) for w in g)
        if _is_payoff(text) and float(g[0].start) >= start:
            payoff = text[:80]
    if payoff is None:
        note.append("no number/conclusion inside - reads as a meander")
    if span < min_s:
        return {"start": round(start, 3), "end": round(end, 3),
                "duration": round(span, 3), "hook": None, "payoff": payoff,
                "too_short": True,
                "note": f"arc is {span:.1f}s, campaign wants >= {min_s}"}
    return {"start": round(start, 3), "end": round(end, 3),
            "duration": round(span, 3), "hook": _is_hook(
                " ".join(str(w.text) for w in hook_group)), "payoff": payoff,
            "too_short": False, "note": "; ".join(note)}


def scan_arcs(words: list[Word], *, min_s: float, max_s: float,
              gap: float = SILENCE_AFTER) -> list[dict]:
    """Every hook->payoff->reaction arc in the transcript, scored by compactness.

    Adjacent breath-groups are merged while their combined span fits `max_s`;
    candidates require a question-like opening and a payoff group inside.
    """
    groups = breath_groups(words, gap=gap)
    texts = [" ".join(str(w.text) for w in g) for g in groups]
    arcs: list[dict] = []
    for i, g in enumerate(groups):
        if not _is_hook(texts[i]):
            continue
        for j in range(i, min(i + 40, len(groups))):
            span = float(groups[j][-1].end) - float(groups[i][0].start)
            if span > max_s:
                break
            if span < min_s:
                continue
            mid = texts[i:j + 1]
            payoff = next((t for t in mid if _is_payoff(t)), None)
            if not payoff:
                continue
            stop = j + 1 < len(groups) and float(groups[j + 1][0].start) - \
                float(groups[j][-1].end) >= gap
            if not stop:                        # runs straight into more speech
                continue
            end = float(groups[j][-1].end) + REACTION_TAIL + 0.0
            score = (1.0 if _is_hook(texts[i]) else 0.4) \
                + 0.6 if NUMBERISH.search(payoff) else 0.2
            score -= abs(span - max(min_s, 34.0)) * 0.004   # tight arcs beat roomy ones
            arcs.append({"start": round(float(groups[i][0].start) - LEAD_IN, 3),
                         "end": round(end, 3), "duration": round(end - float(groups[i][0].start), 3),
                         "hook": texts[i][:70], "payoff": payoff[:80],
                         "score": round(score, 3)})
            break                               # first compliant span from this hook
        # don't return overlapping arcs starting at later hooks inside this one
    return sorted(arcs, key=lambda a: -a["score"])
