"""`cold_read` — the v5 style: a subtitle that dies on the cut.

Read `studio/stylepacks/cold_read_v1.json` for the numbers. The rules:

  1. slow cutting — median 1.03 s, and the file ENDS on a long hold with
     nothing on it (6.5 s in the reference, 21% of its runtime)
  2. the words are fragments in the lower-left: small caps, fixed size, never
     centred, never a paragraph
  3. **a fragment dies with the shot it sits on.** It is not a caption that
     waits for the next line; it arrives and goes with the cut, which is why
     the words read as speech rather than as titles
  4. almost no movement: one whip in 32 s, no flashes
  5. very dark and quite saturated — median luma 19 with saturation 0.59, so
     faces read warm against a blue-black field
"""

from __future__ import annotations

import random

from .plan import Cut, Plan, _in_point
from .repertoire import pick

MEDIAN_S = 1.03
END_HOLD_S = 6.5          # the reference's closing hold
FLASH = None              # this style never punctuates
WHIPS = 1                 # one in the whole file

GRADE = {
    "contrast": 1.10,
    "brightness": -0.028,
    "gamma": 1.16,
    "saturation": 1.45,
    "shadow_tint": (0.97, 1.00, 1.10),
}


def build(grid, source, start: float = 0.0, end: float | None = None,
          seed: int = 0) -> Plan:
    rng = random.Random(seed)
    end = grid.duration if end is None else end
    plan = Plan(grid=grid, source=source, start=start, end=end,
                bpm=grid.bpm, seed=seed, grade_override=GRADE)

    total = end - start
    longest = max((s.dur for s in source.shots), default=0.0)
    hold = min(END_HOLD_S, longest * 0.92, total * 0.30)
    body_end = total - hold

    recent: list[int] = []
    used: set[int] = set()
    idx = 0
    t = 0.0
    while t < body_end - 1e-6:
        span = body_end - t
        want = min(_length(rng), span)
        if want < 0.30:
            break
        act = "build" if t < body_end * 0.16 else "drop"
        shot = pick(source, rng, act, want, recent, used)
        ss = source.shots[shot]
        room = max(0.0, ss.dur - want)
        src_in = _in_point(ss, room, want, want, rng)
        cut = Cut(index=idx, act=act, start_beat=t * grid.bpm / 60.0,
                  length_beats=want * grid.bpm / 60.0, shot=shot,
                  src_in=src_in, src_out=src_in + want, speed=1.0)
        cut.out_start, cut.out_end = t, t + want
        if idx == 3:                       # the one whip, early, as in the reel
            cut.transition = "whip"
        plan.cuts.append(cut)
        recent.append(shot)
        used.add(shot)
        idx += 1
        t = cut.out_end

    # the closing hold: one frame of film, no type, allowed to sit
    if hold >= 0.5:
        shot = pick(source, rng, "out", hold, recent, used)
        ss = source.shots[shot]
        src_in = _in_point(ss, max(0.0, ss.dur - hold), hold, hold, rng)
        cut = Cut(index=idx, act="out", start_beat=t * grid.bpm / 60.0,
                  length_beats=hold * grid.bpm / 60.0, shot=shot,
                  src_in=src_in, src_out=src_in + hold, speed=1.0)
        cut.out_start, cut.out_end = t, t + hold
        plan.cuts.append(cut)

    plan.end = plan.start + plan.cuts[-1].out_end
    return plan


def _length(rng: random.Random) -> float:
    return max(0.28, MEDIAN_S * rng.uniform(0.70, 1.55))


def shape_cards(cards: list[dict], plan: Plan) -> list[dict]:
    """Kill every fragment on the cut it sits on.

    This is the rule that makes the style. A card keeps the words it has; its
    end moves to the end of the shot it started in. Cards in the closing hold
    are dropped entirely — the reference's last 6.5 s carry no type.
    """
    out = []
    hold_start = next((c.out_start for c in plan.cuts if c.act == "out"),
                      plan.duration)
    for c in cards:
        start = c["start"]
        if start >= hold_start:
            continue
        cut = next((k for k in plan.cuts
                    if k.out_start - 1e-6 <= start < k.out_end), None)
        if cut is None:
            continue
        end = min(cut.out_end - 0.04, start + 2.2)
        if end - start < 0.18:
            continue
        d = dict(c)
        d["end"] = round(end, 3)
        out.append(d)
    return out


def summarise(plan: Plan) -> str:
    from .plan import summarise as _s

    lines = _s(plan).splitlines()
    d = [c.dur for c in plan.cuts]
    lines.append(f"  cold_read  {len(d)} cuts  median {sorted(d)[len(d)//2]:.2f}s  "
                 f"closing hold {plan.cuts[-1].dur:.2f}s  "
                 f"whips {sum(1 for c in plan.cuts if c.transition == 'whip')}  "
                 f"flashes 0")
    return "\n".join(lines)
