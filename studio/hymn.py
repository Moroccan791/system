"""`hymn` — the v13 style: near-black, two type voices, slow.

The reference is the darkest of the five (median luma 11, half the next
darkest) and the one where type is on screen longest (69% of the runtime). What
is taken from it:

  1. slow cutting — median 1.79 s, 15 cuts in 31.6 s, no whips at all
  2. **two type voices, always paired**: a white serif states the line, a yellow
     script signs it underneath. One card object, drawn by `typefaces.hymn`
  3. type arrives early and stays — this is closer to a lyric video than to a
     montage, so a card holds about two seconds rather than dying on the cut
  4. the grade crushes to near-black with one warm source, so the type is the
     brightest thing on screen
  5. no flashes, and cuts that are only loosely tied to the beat (2 of 15 land
     on a kick in the reference; the first 15 s has no kicks at all)
"""

from __future__ import annotations

import random

from .plan import Cut, Plan, _in_point
from .repertoire import pick

MEDIAN_S = 1.79
CARD_HOLD = 1.8           # a line holds across cuts, unlike cold_read
FIRST_CARD = 0.7          # the reference's first word is at 0.7 s

GRADE = {
    "contrast": 1.22,
    "brightness": -0.055,
    "gamma": 1.42,        # a gamma above 1 pushes everything down to black
    "saturation": 0.90,
    "shadow_tint": (1.04, 1.00, 0.97),
}


def build(grid, source, start: float = 0.0, end: float | None = None,
          seed: int = 0) -> Plan:
    rng = random.Random(seed)
    end = grid.duration if end is None else end
    plan = Plan(grid=grid, source=source, start=start, end=end,
                bpm=grid.bpm, seed=seed, grade_override=GRADE)

    total = end - start
    recent: list[int] = []
    used: set[int] = set()
    idx = 0
    t = 0.0
    while t < total - 1e-6:
        want = min(max(0.5, MEDIAN_S * rng.uniform(0.80, 1.30)), total - t)
        if want < 0.32:
            break
        act = "build" if t < total * 0.22 else "drop"
        shot = pick(source, rng, act, want, recent, used)
        ss = source.shots[shot]
        room = max(0.0, ss.dur - want)
        src_in = _in_point(ss, room, want, want, rng)
        cut = Cut(index=idx, act=act, start_beat=t * grid.bpm / 60.0,
                  length_beats=want * grid.bpm / 60.0, shot=shot,
                  src_in=src_in, src_out=src_in + want, speed=1.0)
        cut.out_start, cut.out_end = t, t + want
        plan.cuts.append(cut)
        recent.append(shot)
        used.add(shot)
        idx += 1
        t = cut.out_end

    plan.end = plan.start + plan.cuts[-1].out_end
    return plan


def shape_cards(cards: list[dict], plan: Plan) -> list[dict]:
    """Each line holds for about two seconds and is allowed to span cuts.

    The reference keeps its words up for most of the film, which is the
    opposite of cold_read. A card is capped at CARD_HOLD and never runs past the
    next card's start, so two lines can never be on screen together.
    """
    out = []
    for i, c in enumerate(cards):
        d = dict(c)
        start = max(FIRST_CARD, d["start"])
        if start >= plan.duration:
            continue
        nxt = cards[i + 1]["start"] if i + 1 < len(cards) else plan.duration
        end = min(start + CARD_HOLD, max(start + 0.3, nxt - 0.02),
                  plan.duration - 0.1)
        if end - start < 0.2:
            continue
        d["start"] = round(start, 3)
        d["end"] = round(end, 3)
        out.append(d)
    return out


def summarise(plan: Plan) -> str:
    from .plan import summarise as _s

    lines = _s(plan).splitlines()
    d = [c.dur for c in plan.cuts]
    lines.append(f"  hymn      {len(d)} cuts  median {sorted(d)[len(d)//2]:.2f}s  "
                 f"whips 0  flashes 0  grade luma target ~11")
    return "\n".join(lines)
