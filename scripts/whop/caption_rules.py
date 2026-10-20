#!/usr/bin/env python3
"""Caption rules from the clipping course, as code instead of vibes.

    from caption_rules import wrap_cells, check_cards, filler_words

The course is explicit about captions ("1-2 lines max, ~14 characters per
line (most cases)") and about cuts ("remove dead air, filler words and
silences ... trim uh, um, you know, like"). Both were aspirations in this
repo: the number 14 appeared in a comment while shipped lines ran to 24
characters, and the filler list was applied by hand per post. Here they are
constants with one implementation each, so a render can be failed against
them.

Nothing here touches timing. Cells keep their own `at`/`end`; wrapping only
decides which words share a card.
"""
from __future__ import annotations

#: The course's number is ~14 characters a line "in most cases". Wrapping at
#: 15 absorbs the one-character overrun that otherwise strands a word on its
#: own line ("That will" / "come from / that soil,"); the gate still judges the
#: result against 14 as the typical line and 17 as the absolute ceiling.
TARGET_LINE_CHARS = 14
MAX_LINE_CHARS = 15
MAX_LINES = 2                # course rule: 1-2 lines max
HARD_LINE_CHARS = 17

#: Spoken filler, per the course's explicit list. "like" and "you know" are
#: only filler in their discourse-marker role, which the caller decides by
#: passing the tokens it has already flagged - `filler_words` reports both the
#: bare list and the pairs so a gate can show what it found.
FILLERS = {"uh", "uhh", "um", "uhm", "erm", "er", "hmm", "mm", "mhm"}
DISCOURSE = {"like", "basically", "literally", "right", "okay"}
PAIRS = {("you", "know"), ("i", "mean"), ("kind", "of"), ("sort", "of")}


def bare(word: str) -> str:
    return "".join(ch for ch in word.lower() if ch.isalnum() or ch == "'").strip("'")


def filler_words(words: list[str]) -> list[str]:
    """Fillers present in a spoken word list, in order, verbatim as found."""
    out: list[str] = []
    bare_words = [bare(w) for w in words]
    i = 0
    while i < len(bare_words):
        w = bare_words[i]
        pair = (w, bare_words[i + 1]) if i + 1 < len(bare_words) else None
        if pair in PAIRS and pair == ("you", "know"):
            out.append("you know")
            i += 2
            continue
        if w in FILLERS or w in DISCOURSE:
            out.append(words[i])
        i += 1
    return out


def _join_len(line: list[dict]) -> int:
    return len(" ".join(c["w"] for c in line))


def _layout(cells: list[dict], max_chars: int,
            max_lines: int) -> tuple[int, list[list[dict]]] | None:
    """Best way to set `cells` on at most `max_lines` lines, or None.

    Cost is the squared empty space per line, so a layout that fills the
    budget evenly beats one that crams the first line and orphans a word on
    the second ("I will never / be" loses to "I will / never be").
    """
    n = len(cells)
    best: tuple[int, list[list[dict]]] | None = None
    if max_lines >= 1:
        text = _join_len(cells)
        if text <= max_chars:
            best = ((max_chars - text) ** 2, [cells])
        elif n == 1 and len(cells) == 1:   # one word longer than the budget
            best = (0, [cells])
    if max_lines >= 2:
        for k in range(1, n):
            a, b = cells[:k], cells[k:]
            la, lb = _join_len(a), _join_len(b)
            if la > max_chars or lb > max_chars:
                continue
            cost = (max_chars - la) ** 2 + (max_chars - lb) ** 2
            if best is None or cost < best[0]:
                best = (cost, [a, b])
    return best


#: What one more card costs, in the same units as `_layout`'s raggedness.
#: Large enough that words prefer to share a two-line card, small enough that
#: a genuinely short line does not get stretched onto a card of its own.
_CARD_COST = 70
#: What a one-line card costs on top. The course allows 1-2 lines, but at a
#: 14-character budget a one-liner is usually the residue of a bad split
#: ("That will" / "come from that soil,"), so two lines are the default and a
#: one-liner has to earn its place.
_ONE_LINE_COST = 45


def wrap_cells(cells: list[dict], max_chars: int = MAX_LINE_CHARS,
               max_lines: int = MAX_LINES) -> list[dict]:
    """Regroup a flat list of caption cells into cards of short lines.

    A small dynamic programme over the sentence: every card costs its
    raggedness plus `_CARD_COST`, and the cheapest total wins. That is what
    stops the "orphan word on its own card" ("...that soil," / "soil,") and
    the lopsided two-liner that greedy wrapping produces at a 14-character
    budget. Cells keep their own times; only grouping changes.
    """
    n = len(cells)
    if n == 0:
        return []
    INF = float("inf")
    best = [INF] * (n + 1)
    pick: list[int] = [0] * (n + 1)
    best[n] = 0.0
    for i in range(n - 1, -1, -1):
        for j in range(i + 1, min(n, i + 9) + 1):
            # a card needs two words unless the sentence itself is one word:
            # "That will" alone reads as a stumble, "That will come" does not
            if j - i < 2 and not (n == 1 and j - i == 1):
                continue
            lay = _layout(cells[i:j], max_chars, max_lines)
            if lay is None:
                continue
            total = lay[0] + _CARD_COST + best[j]
            if len(lay[1]) == 1:
                total += _ONE_LINE_COST
            if total < best[i]:
                best[i], pick[i] = total, j
    cards: list[dict] = []
    i = 0
    while i < n and pick[i] > i:
        j = pick[i]
        lay = _layout(cells[i:j], max_chars, max_lines)
        if lay is None:                    # pragma: no cover - defensive
            lay = (0, [cells[i:j]])
        cards.append({"lines": lay[1], "zone": "low"})
        i = j
    return cards


def rewrap(caps: list[dict], max_chars: int = MAX_LINE_CHARS,
           max_lines: int = MAX_LINES) -> list[dict]:
    """Re-wrap existing caption blocks, one block (sentence) at a time.

    Blocks are kept as the outer unit on purpose: re-wrapping the whole clip
    flat would let the end of one sentence share a card with the start of the
    next, which reads as a misquote. Inside a block, every word is re-grouped
    to the short-line rule and the caller re-times the cards.
    """
    out: list[dict] = []
    for cap in caps:
        cells = [c for line in cap["lines"] for c in line]
        if not cells:
            continue
        for card in wrap_cells(cells, max_chars, max_lines):
            card["zone"] = cap.get("zone", "low")
            out.append(card)
    return out


def time_cards(cards: list[dict], endcard: float) -> list[dict]:
    """Show/hide windows from the cells' own word times (same rule as shipped)."""
    for i, card in enumerate(cards):
        cells = [c for line in card["lines"] for c in line]
        nxt = (cards[i + 1]["lines"][0][0]["at"] if i + 1 < len(cards) else endcard)
        card["show_from"] = max(0.0, float(cells[0]["at"]) - 0.03)
        last = float(cells[-1]["end"])
        card["show_until"] = min(max(last + 0.45, nxt - 0.02), nxt - 0.02, endcard)
    for i in range(len(cards) - 1):
        gap = cards[i + 1]["show_from"] - cards[i]["show_until"]
        if 0 < gap < 0.7:
            cards[i]["show_until"] = cards[i + 1]["show_from"]
    return cards


def _word(cell) -> str:
    """A caption item, whether it is a cell dict or a bare word from a manifest."""
    return cell if isinstance(cell, str) else str(cell.get("w", ""))


def card_report(cards: list[dict]) -> dict:
    """What a gate needs to judge the captions (cells or plain manifest words)."""
    lines = [" ".join(_word(c) for c in line) for card in cards for line in card["lines"]]
    lengths = [len(t) for t in lines]
    over = [(t, n) for t, n in zip(lines, lengths) if n > TARGET_LINE_CHARS]
    hard = [(t, n) for t, n in zip(lines, lengths) if n > HARD_LINE_CHARS]
    return {
        "cards": len(cards),
        "lines": len(lines),
        "max_chars": max(lengths) if lengths else 0,
        "median_chars": sorted(lengths)[len(lengths) // 2] if lengths else 0,
        "over_target": over,
        "over_hard": hard,
        "max_lines_per_card": max((len(c["lines"]) for c in cards), default=0),
    }
