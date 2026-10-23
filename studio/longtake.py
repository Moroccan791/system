"""`longtake` — the v12 style (the square interview reel), minus the square.

The reference is 1:1 because it is a phone interview. **The square is not the
style** — cropping a 16:9 pack to 1:1 to imitate a camera throws away the sides
of every frame, and the decision on 2026-10-23 was landscape only. What is left
when the aspect goes is the thing that actually shapes the edit:

  1. it does not perform — 14 cuts in 30 s, and nearly half the runtime sits in
     shots of four seconds or more
  2. the cutting follows the sentence, not the beat: in the reference the median
     distance from a cut to the nearest kick is 0.75 s, five times looser than
     the barrage reel
  3. the type is plain, centred, and stops: it appears early and is gone long
     before the end
  4. the picture is left alone — no flashes, and only a handful of whips
  5. the grade is close to neutral; the footage supplies the colour

Read the numbers: `studio/stylepacks/longtake_v1.json`.
"""

from __future__ import annotations

import random

from .plan import Cut, Plan, _in_point
from .repertoire import pick

MEDIAN_S = 1.33          # reference median shot
HOLD_S = (4.0, 4.6)      # the 4s+ shots: 44% of the reference's runtime
HOLD_SHARE = 0.44
WHIP_EVERY = 5           # 3 whips in 14 cuts
TYPE_UNTIL = 0.70        # the reference's type stops 22 s before the end

GRADE = {
    "contrast": 1.02,
    "brightness": 0.008,
    "gamma": 0.99,
    "saturation": 1.10,
    "shadow_tint": (1.01, 1.00, 1.00),
}


def build(grid, source, start: float = 0.0, end: float | None = None,
          seed: int = 0) -> Plan:
    """Long takes, loose cutting, plain type, no flashes."""
    rng = random.Random(seed)
    end = grid.duration if end is None else end
    plan = Plan(grid=grid, source=source, start=start, end=end,
                bpm=grid.bpm, seed=seed, grade_override=GRADE)

    total = end - start
    longest = max((s.dur for s in source.shots), default=0.0)

    # The rhythm is a repeating block, because that is what the reference does:
    # one long look, then three or four short ones. Solving for the ratio:
    #   hold + n*short = block, and hold/block = HOLD_SHARE
    hold = rng.uniform(*HOLD_S)
    short = MEDIAN_S
    block = hold / HOLD_SHARE
    n_short = max(1, int(round((block - hold) / short)))

    recent: list[int] = []
    used: set[int] = set()
    short_i = 0          # only the short shots carry whips; a whip on a 4s hold
                         # would be the one performative gesture in the style
    idx = 0
    t = 0.0
    while t < total - 1e-6:
        in_hold = idx % (n_short + 1) == 0
        want = hold if in_hold else short
        want = min(want, total - t)

        # A hold can only be as long as the shot under it. If this pack has no
        # take that long, the hold becomes the longest one available and the
        # block absorbs the difference — the alternative is freezing, which
        # reads as a bug.
        if want > longest * 0.95:
            want = longest * 0.92
        if want < 0.35:
            break

        act = "build" if t < total * 0.18 else "drop"
        shot = pick(source, rng, act, want, recent, used)
        ss = source.shots[shot]
        room = max(0.0, ss.dur - want)
        src_in = _in_point(ss, room, want, want, rng)

        cut = Cut(index=idx, act=act,
                  start_beat=t * grid.bpm / 60.0,
                  length_beats=want * grid.bpm / 60.0,
                  shot=shot, src_in=src_in, src_out=src_in + want, speed=1.0)
        cut.out_start = t
        cut.out_end = t + want
        # No flashes at all: this style never punctuates. A few whips, because
        # the reference's three whips are the only movement in it.
        if not in_hold:
            if short_i % WHIP_EVERY == 2:
                cut.transition = "whip"
            short_i += 1
        plan.cuts.append(cut)
        recent.append(shot)
        used.add(shot)
        idx += 1
        t = cut.out_end

    plan.end = plan.start + (plan.cuts[-1].out_end if plan.cuts else total)
    return plan


def type_until(plan: Plan) -> float:
    """Where type stops. The reference's words are gone for the last fifth."""
    return plan.duration * TYPE_UNTIL


def summarise(plan: Plan) -> str:
    from .plan import summarise as _s

    lines = _s(plan).splitlines()
    d = [c.dur for c in plan.cuts]
    holds = [c for c in plan.cuts if c.dur >= 4.0]
    share = sum(c.dur for c in holds) / max(1e-9, plan.duration)
    median = sorted(d)[len(d) // 2]
    lines.append(f"  longtake  {len(d)} cuts  median {median:.2f}s  "
                 f"holds 4s+ {len(holds)} ({share * 100:.0f}% of runtime)  "
                 f"whips {sum(1 for c in plan.cuts if c.transition == 'whip')}  "
                 f"flashes 0")
    return "\n".join(lines)
