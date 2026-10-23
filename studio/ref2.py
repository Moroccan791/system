"""Reference 2 — the system behind "Gwen Stacy's death" (58.5 s, 3.7M likes).

Reference 1 (`studio/typecards.py` + `studio/director.py`) is the house edit: the
lyric as a centred card that changes with the vocal, cuts on the music grid.

Reference 2 is a different machine, and the difference is measurable. It was
decomposed frame by frame (scene-cut detection, 10 fps type masks, digital-
silence runs, 2 fps grade statistics). The numbers below are the spec.

WHAT IT IS
----------
It is not a beat montage. It is *a scene, kept*. Twenty-one shots in 58.5 s —
mean 2.78 s, median 1.47 s — with three shots doing 25 s of the work between
them. Cuts land on the picture's own action beats, not on the music: only 7 of
20 cut points sit within 60 ms of an audio onset.

What makes it feel premium is therefore not cutting. It is three things:

  1. THE TYPE DOES THE RHYTHM. While the picture holds, the words move.
     A right-aligned stack grows line by line until it is four deep, then goes.
     One word at a time appears low right. A crimson phrase sits *behind* the
     subject for seconds at a time. Three registers, each on screen for a
     different length of time.
  2. THE AUDIO DIES. Not "gets quiet" — goes to digital zero, for 0.70 s, 0.72 s,
     0.94 s in the first seven seconds and then a 2.78 s hole before the biggest
     move in the film. Measured at −120 dBFS, i.e. exact silence.
  3. THE GRADE IS ONE THING. Median luma 31/255, saturation 0.49, shadows tinted
     teal (shadow R:G:B ≈ 0.68 : 0.90 : 1.00), and not a single pixel above 235 —
     the picture is dark and nothing is allowed to blow out.

MEASURED — STRUCTURE
--------------------
    shot   in      out     len     shot   in      out     len
      1   0.00    1.67    1.67       12  27.80   28.27    0.47
      2   1.67    2.90    1.23       13  28.27   29.17    0.90
      3   2.90    5.57    2.67       14  29.17   30.17    1.00
      4   5.57    5.93    0.37       15  30.17   33.40    3.23
      5   5.93    6.63    0.70       16  33.40   36.83    3.43
      6   6.63   10.57    3.93       17  36.83   41.80    4.97
      7  10.57   19.73    9.17       18  41.80   52.87   11.07
      8  19.73   19.97    0.23       19  52.87   54.07    1.20
      9  19.97   24.90    4.93       20  54.07   54.53    0.47
     10  24.90   26.37    1.47       21  54.53   58.47    3.94
     11  26.37   27.80    1.43

    six shots under 1 s, six 1-2 s, five 2-4 s, four over 4 s.

MEASURED — TYPE
---------------
    stack      right 0.95 W, top 0.094 H, cap 0.110 H, pitch 0.240 H,
               max 4 lines, older lines at 0.34 / 0.58 / 0.78 alpha,
               silver vertical gradient, tracking 0.018 em, drop shadow
    single     right edge ~0.87 W, band 0.75-0.91 H, cap 0.13-0.16 H
    bed        one phrase repeated 4x, 1.6-2.2 s each, always across >=2 cuts
               ghost: cap 0.50 H, alpha 0.40, #7c1119
               solid: cap 0.15 H, alpha 1.00, #c2131d

MEASURED — SOUND
----------------
    digital silence runs   1.75-1.92, 3.52-4.22, 4.96-5.68, 6.10-7.04,
                           24.10-26.88 (2.78 s), 29.86-31.05
    bed level              -17 to -19 dBFS throughout; no drops, no impacts
    the return from the long hole measures the SAME level as the bed before it
    (-18.8 dBFS) and still reads as loud, because the hole was absolute zero.
    That is the point: the lift is in the contrast, not in the gain.

WHAT WE COPY, AND WHAT WE DO NOT
--------------------------------
Copy: the stack, the bed, the single word, one grade, the silence holes, and
long holds that are allowed to be boring.

Not copied: the film's dialogue (there is none in our edits by standing rule),
and the cut-on-action because we cannot see an actor's intent in a scenepack —
we hang the cuts on the words, which is the closest honest equivalent.

VERTICAL
--------
This reference survives a 9:16 crop because its type lives in the top-right and
bottom-right corners *inside* the width it needs, and its picture is cut wide.
Nothing in the system depends on the picture being cropped — so a vertical made
from wide footage should letterbox the full width and let the type own the frame,
not slice a 4:5 band out of the middle. (See `studio/frame.py`.)
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# the numbers, in one place, so the renderer and the docs cannot drift apart
# ---------------------------------------------------------------------------
STACK_MAX_LINES = 4
STACK_ALPHA = (0.34, 0.58, 0.78, 1.0)

# how long a shot may be held, by act. The reference's longest single shot is
# 11.07 s; ours will not go that far on a scenepack, but 4.5 s in the build is
# what stops an overedit from feeling like a metronome.
HOLD_CAP = {"build": 4.5, "drop": 2.6, "out": 4.5}

# silence holes, as (position in the edit, length). The reference puts a short
# hole every few seconds early and one long one before the biggest move.
# These are fractions of the runtime, so the shape survives a different song.
HOLES = [(0.245, 0.70), (0.425, 0.95), (0.615, 2.78), (0.86, 0.60)]

# the reference's picture-side thresholds
GRADE = {
    "median_luma": 31 / 255,
    "saturation": 0.49,
    "shadow_tint": (0.68, 0.90, 1.00),
    "blown": 0.0,
}


@dataclass
class Bed:
    t: float
    dur: float
    text: str


def _get(card, key: str, default=None):
    """Cards arrive as dicts from json and as dataclasses from the renderer."""
    if isinstance(card, dict):
        return card.get(key, default)
    return getattr(card, key, default)


def _text(card) -> str:
    return str(_get(card, "text", "") or "")


def _start(card) -> float:
    return float(_get(card, "start", _get(card, "_at", 0.0)) or 0.0)


def _end(card) -> float:
    return float(_get(card, "end", _start(card)) or 0.0)


def stacks(cards: list[dict]) -> list[list[str]]:
    """Group the cards into stanzas — the lines that stack together.

    A stanza ends at a pause long enough to be read as a full stop: 0.45 s of
    dead air, or the fourth line, whichever comes first. This is the only rule
    the reference appears to apply — its first stack is four lines over 1.7 s,
    its second is a single word.
    """
    out: list[list[str]] = []
    run: list[str] = []
    prev_end = None
    for c in cards:
        text = _text(c).strip()
        if not text:
            continue
        gap = _start(c) - prev_end if prev_end is not None else 0.0
        if run and (gap > 0.45 or len(run) >= STACK_MAX_LINES):
            out.append(run)
            run = []
        run.append(text)
        prev_end = _end(c)
    if run:
        out.append(run)
    return out


def stack_at(cards: list[dict], i: int) -> list[str]:
    """The visible stack when card `i` is the newest one on screen."""
    groups = stacks(cards)
    seen = 0
    for g in groups:
        if i < seen + len(g):
            n = i - seen
            return g[max(0, n - STACK_MAX_LINES + 1): n + 1]
        seen += len(g)
    return [_text(cards[i])] if 0 <= i < len(cards) else []


def _phrase_bank(cards: list[dict]) -> list[str]:
    """Short phrases, most repeated first. The bed is a refrain, not a caption."""
    counts: dict[str, int] = {}
    for c in cards:
        words = _text(c).strip().split()
        if not words:
            continue
        # One or two words is the reference's own bed ("LOVE ME"); three is the
        # ceiling. Longer than that and a phrase at half frame height stops
        # being a texture and becomes a subtitle in a colour nobody asked for.
        for n in (1, 2, 3):
            if len(words) >= n:
                for key in (" ".join(words[:n]).upper(), " ".join(words[-n:]).upper()):
                    counts[key] = counts.get(key, 0) + 1
    # most repeated first; among equals the SHORTER phrase — a texture with
    # eleven letters in it is a sentence
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], len(kv[0])))
    return [k for k, _ in ranked]


def beds(cards: list[dict], start: float, end: float,
         count: int = 4, text: str | None = None) -> list[Bed]:
    """Where the phrase bed goes.

    Four placements, evenly spaced, each held across at least one cut. The text
    is the most-repeated short phrase in the lyric; if nothing repeats, the
    longest two-word phrase is used, because a bed needs weight, not novelty.
    """
    if not cards:
        return []
    bank = _phrase_bank(cards)
    text = (text or "").strip().upper() or (bank[0] if bank else "")
    if not text:
        return []
    span = end - start
    out: list[Bed] = []
    for k in range(count):
        # the reference's four beds sit at roughly 0.14, 0.22, 0.36, 0.47 of the
        # runtime, each one landing a little after the previous cut
        frac = 0.14 + k * (0.33 / max(1, count - 1))
        t = start + span * frac
        # beds never overlap: two crimson phrases on screen at once is a smear,
        # and on a short edit the even spacing alone would put them there
        if out and t < out[-1].t + out[-1].dur + 0.6:
            t = out[-1].t + out[-1].dur + 0.6
        if t + 1.9 > end - 0.3:
            continue
        out.append(Bed(round(t, 3), 1.9, text))
    return out


def holes(start: float, end: float, cuts: list[float] | None = None,
          scale: float = 1.0, accent_at: float | None = None
          ) -> list[tuple[float, float]]:
    """The silence windows, in edit time.

    Every hole is snapped backwards onto the nearest cut so the music dies on a
    picture event rather than mid-shot: a silence that starts on a cut reads as
    a decision, one that starts two frames into a shot reads as a dropout.
    """
    span = end - start
    out: list[tuple[float, float]] = []
    windows = list(HOLES)
    if accent_at is not None:
        # The long hole belongs BEFORE the hit, not at a fraction of the
        # runtime: the reference's 2.78 s gap ends exactly where its biggest
        # move starts, and that is the whole reason it works.
        long_len = max(length for _f, length in HOLES) * scale
        windows = [(f, l) for f, l in HOLES if l * scale < long_len - 1e-6]
        windows.append((None, long_len))
        windows.sort(key=lambda w: (accent_at - long_len) if w[0] is None
                     else start + span * w[0])
    for frac, length in windows:
        if frac is None:
            t = max(start, accent_at - length)
            dur = accent_at - t
            if out and t < out[-1][1] + 0.05:
                continue
            out.append((round(t, 3), round(accent_at, 3)))
            continue
        t = start + span * frac
        dur = length * scale
        if cuts:
            before = [c for c in cuts if c <= t + 1e-6]
            if before:
                t = before[-1]
        # Two windows on the same cut, or one inside another, is not two
        # silences — it is one silence and a bug report. The later one wins only
        # if it clears the earlier one entirely.
        if any(t < b and t + dur > a for a, b in out):
            continue
        if out and t < out[-1][1] + 0.05:
            continue
        if t + dur > end - 0.2:
            continue
        out.append((round(t, 3), round(t + dur, 3)))
    return out


def describe() -> str:
    return (
        "reference2 — stack / single / bed type, one dark teal grade, "
        "silence holes, long holds"
    )
