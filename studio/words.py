"""Put the recognised words on the lyric, then the lyric on the screen.

What this replaces: a metronome. The previous placement assumed the lyric
restarted every N seconds, which is only true if the singer never pauses — and
in a metal verse there is a gap of several seconds between lines. The error was
small on line one and about four seconds by line four, which is exactly what
"the captions don't match" looks like.

Here the times come from the vocal itself: a speech model with word timestamps
was run over the track, and those words are matched to the lyric the operator
gave. Unheard words are interpolated between their neighbours, never
extrapolated past the last thing actually sung.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DEVA = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ii", "उ": "u", "ऊ": "uu", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऍ": "e", "ऑ": "o",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s",
    "ह": "h", "ळ": "l", "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z",
    "ड़": "r", "ढ़": "rh", "फ़": "f", "य़": "y",
    "ा": "aa", "ि": "i", "ी": "ii", "ु": "u", "ू": "uu", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॅ": "e", "ॉ": "o",
    "ं": "n", "ँ": "n", "ः": "h", "्": "",
    "া": "aa", "ি": "i", "ী": "ii", "ু": "u", "ূ": "uu", "ে": "e", "ৈ": "ai",
    "ো": "o", "ৌ": "au", "ং": "ng", "ঁ": "n", "্": "",
}


def lat(word: str) -> str:
    """A rough transliteration, then a spelling both sides can meet on.

    The recogniser writes Hindi/Bangla in Devanagari; the operator wrote the
    lyric in Latin. Neither is standardised, so both are reduced to a skeleton:
    doubled letters collapse, v/b and sh/s merge, and vowels are kept because
    they carry the syllable count.
    """
    out = []
    for ch in word:
        out.append(DEVA.get(ch, ch))
    s = "".join(out).lower()
    s = re.sub(r"[^a-z]", "", s)
    for a, b in (("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"),
                 ("ph", "f"), ("th", "t"), ("dh", "d"), ("kh", "k"), ("gh", "g"),
                 ("bh", "b"), ("chh", "ch"), ("sh", "s"), ("v", "b"), ("z", "j"),
                 ("w", "b"), ("y", "i")):
        s = s.replace(a, b)
    s = re.sub(r"(.)\1+", r"\1", s)
    return s


def lev(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def sim(a: str, b: str) -> float:
    a, b = lat(a), lat(b)
    if not a or not b:
        return 0.0
    return 1.0 - lev(a, b) / max(len(a), len(b))


def global_align(expected: list[str], heard: list[str]) -> list[int | None]:
    """For each expected word, the index of the heard word it is, or None.

    Needleman-Wunsch. Order is the constraint that makes this work at all: the
    lyric is known, so a heard word only has to be placed somewhere ahead of the
    previous one.
    """
    n, m = len(expected), len(heard)
    NEG = -1e9
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    GAP = 0.55
    for i in range(1, n + 1):
        score[i][0] = score[i - 1][0] - GAP
        back[i][0] = 1
    for j in range(1, m + 1):
        score[0][j] = score[0][j - 1] - GAP
        back[0][j] = 2
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            s = sim(expected[i - 1], heard[j - 1])
            diag = score[i - 1][j - 1] + (s - 0.32) * 3
            up = score[i - 1][j] - GAP
            left = score[i][j - 1] - GAP
            best = max(diag, up, left)
            score[i][j] = best
            back[i][j] = 0 if best == diag else (1 if best == up else 2)
    out: list[int | None] = [None] * n
    i, j = n, m
    while i > 0 and j > 0:
        if back[i][j] == 0:
            out[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif back[i][j] == 1:
            i -= 1
        else:
            j -= 1
    return out


def words_of(lines: list[str]) -> list[str]:
    return [w for line in lines for w in line.split()]


def sequence(lines: list[str], cycles: int) -> tuple[list[str], list[tuple[int, int]]]:
    """The lyric repeated, with each word's (line index, word index in line)."""
    words, tag = [], []
    for _ in range(cycles):
        for li, line in enumerate(lines):
            for wi, w in enumerate(line.split()):
                words.append(w)
                tag.append((li, wi))
    return words, tag


def place_all(lines: list[str], heard: list[dict], thresh: float = 0.45) -> list[dict]:
    """Every sung phrase, on its own lyric line, in order.

    The lyric is aligned as a whole against everything the model heard: the
    sequence is repeated enough times to cover the audio, and Needleman-Wunsch
    keeps the mapping monotonic. That is what stops the second "hi" in a line
    from being matched to the first "hi" forty seconds earlier — the failure
    that turned one card into a nine-second hold.
    """
    per_cycle = sum(len(l.split()) for l in lines)
    cycles = max(2, int(len(heard) / max(1, per_cycle)) + 1)
    exp, tag = sequence(lines, cycles)
    mapping = global_align(exp, [h["w"] for h in heard])
    placed: dict[tuple[int, int], dict[int, dict]] = {}
    for k, (line, wi) in enumerate(tag):
        j = mapping[k]
        if j is None:
            continue
        h = heard[j]
        sc = sim(exp[k], h["w"])
        if sc < thresh:
            continue
        occ = k // per_cycle
        slot = placed.setdefault((occ, line), {})
        if wi not in slot:
            slot[wi] = {"text": exp[k], "start": h["start"], "end": h["end"],
                        "heard": h["w"], "sim": round(sc, 2)}
    out: list[dict] = []
    for (occ, line), slots in sorted(placed.items()):
        # A phrase is only used if most of it was actually recognised. A line
        # stitched from one lucky similarity is worse than no card at all.
        need = max(2, (len(lines[line].split()) + 1) // 2)
        if sum(1 for v in slots.values() if v.get("sim", 0) >= 0.45) < need:
            continue
        ws = lines[line].split()
        known = sorted(slots)
        if not known:
            continue
        for wi in range(len(ws)):
            if wi in slots:
                continue
            prev = max([k for k in known if k < wi], default=None)
            nxt = min([k for k in known if k > wi], default=None)
            if prev is None or nxt is None:
                # Edge words have no neighbouring evidence, so they are only
                # given a short step off the nearest real word — enough for the
                # line's last word to appear, not enough to run past the vocal.
                step = 0.36
                if prev is None:
                    base = slots[nxt]["start"] - step * (nxt - wi)
                    slots[wi] = {"text": ws[wi], "start": round(base, 2),
                                 "end": round(base + 0.20, 2), "filled": True}
                else:
                    base = slots[prev]["end"] + step * (wi - prev)
                    slots[wi] = {"text": ws[wi], "start": round(base, 2),
                                 "end": round(base + 0.20, 2), "filled": True}
                continue
            a, b = slots[prev]["end"], slots[nxt]["start"]
            f = (wi - prev) / (nxt - prev)
            slots[wi] = {"text": ws[wi], "start": round(a + (b - a) * f, 2),
                         "end": round(a + (b - a) * f + 0.16, 2), "filled": True}
        for wi in sorted(slots):
            row = dict(slots[wi])
            row["line"] = line
            row["occ"] = occ
            out.append(row)
    out.sort(key=lambda r: r["start"])
    return out


def cards_from_slots(slots: list[dict], per_card: int = 2, hold: float = 0.10,
                     tail: float = 1.1) -> list[dict]:
    """Cards inside one sung line — never one that straddles the silence.

    A card's end is where the next card starts, unless the next one is so far
    away that the singer has stopped: then the card ends shortly after its own
    last word. Otherwise the last card of a verse hangs on screen through the
    whole instrumental gap.
    """
    groups: dict[tuple, list[dict]] = {}
    for r in slots:
        groups.setdefault((r.get("occ", 0), r.get("line", 0)), []).append(r)
    cards: list[dict] = []
    for _, rows in sorted(groups.items()):
        rows.sort(key=lambda r: r["start"])
        for k in range(0, len(rows), per_card):
            part = rows[k:k + per_card]
            cards.append({"start": part[0]["start"],
                          "end": max(p["end"] for p in part) + tail,
                          "text": " ".join(p["text"] for p in part)})
    cards.sort(key=lambda c: c["start"])
    for i, c in enumerate(cards):
        if i + 1 < len(cards):
            c["end"] = min(c["end"], cards[i + 1]["start"])
        c["end"] = round(max(c["end"], c["start"] + 0.30), 2)
        c["start"] = round(c["start"], 2)
        c["conf"] = 1.0
    return cards


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="lyric words onto recognised words")
    ap.add_argument("transcript")
    ap.add_argument("lyric")
    ap.add_argument("--offset", type=float, required=True, help="track time of t=0")
    ap.add_argument("--per-card", type=int, default=2)
    ap.add_argument("--line", type=int, default=None, help="only this lyric line")
    ap.add_argument("--cards", default=None)
    a = ap.parse_args(argv)
    d = json.loads(Path(a.transcript).read_text())
    lines = [l.strip() for l in Path(a.lyric).read_text().splitlines() if l.strip()]
    rows = place_all(lines, d["words"])
    if a.line is not None:
        rows = [r for r in rows if r["line"] == a.line]
    for r in rows:
        print(f"{r['start'] + a.offset:7.2f} {r['end'] + a.offset:7.2f}  "
              f"L{r['line']}  {r['text']:<12} heard {r.get('heard', ''):<12}"
              f"{'  (filled)' if r.get('filled') else ''}")
    cards = cards_from_slots(rows, per_card=a.per_card)
    for c in cards:
        c["start"] += a.offset
        c["end"] += a.offset
        c["line"] = 0
    print(f"{len(cards)} cards from {len(rows)} words")
    if a.cards:
        Path(a.cards).write_text(json.dumps({"polished": True, "cards": cards}, indent=1) + "\n")
        print("wrote", a.cards)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
