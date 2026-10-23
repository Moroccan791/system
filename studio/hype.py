"""`hype` — the v11 style: one word, far too large.

The reference puts its type BEHIND the subject at a scale bigger than the
frame — "I'M A TRAGE", "DEFE", "TAKE IT AS A", "PRIDE" — and that needs a matte
of the person, which we do not have. What is built here is the honest half:

  1. fast-ish cutting — median 0.71 s, and no shot longer than 2.4 s
  2. **beat-locked**: 14 of its 38 cuts land within 80 ms of a kick, the
     tightest of the five references. This style snaps its cuts to onsets
  3. six whips as joins
  4. **one word, set at about 1.15x the frame width**, cropped by the edges and
     drawn over the picture at low alpha
  5. mid-dark and desaturated (luma 35, saturation 0.37) so the type carries
     what colour there is

Stated plainly in the pack as well: the reference's type is *behind* the
subject and ours is *over* the picture. Same scale, same rhythm, not the same
composite. Anything closer needs tracking.
"""

from __future__ import annotations

import random

from .plan import Cut, Plan, _in_point
from .repertoire import pick

MEDIAN_S = 0.71
MAX_SHOT_S = 2.4
WHIP_EVERY = 6            # 6 whips in 38 cuts

GRADE = {
    "contrast": 1.08,
    "brightness": -0.012,
    "gamma": 1.06,
    "saturation": 0.72,
    "shadow_tint": (0.98, 1.00, 1.05),
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
        want = min(max(0.2, MEDIAN_S * rng.uniform(0.60, 1.45)),
                   MAX_SHOT_S, total - t)
        # snap to the nearest onset so the cut lands on the music — this style's
        # defining habit, and the one number it beats every other reference on
        want = _snap_to_onset(grid, t, want, total)
        if want < 0.20:
            break
        act = "build" if t < total * 0.12 else "drop"
        shot = pick(source, rng, act, want, recent, used)
        ss = source.shots[shot]
        room = max(0.0, ss.dur - want)
        src_in = _in_point(ss, room, want, want, rng)
        cut = Cut(index=idx, act=act, start_beat=t * grid.bpm / 60.0,
                  length_beats=want * grid.bpm / 60.0, shot=shot,
                  src_in=src_in, src_out=src_in + want, speed=1.0)
        cut.out_start, cut.out_end = t, t + want
        if idx % WHIP_EVERY == 3:
            cut.transition = "whip"
        plan.cuts.append(cut)
        recent.append(shot)
        used.add(shot)
        idx += 1
        t = cut.out_end

    plan.end = plan.start + plan.cuts[-1].out_end
    return plan


def _snap_to_onset(grid, t: float, want: float, total: float) -> float:
    """Move the cut's end onto the nearest onset within 90 ms, if there is one."""
    target = t + want
    best, best_d = None, 0.09
    for o in getattr(grid, "onsets", ()) or ():
        # onsets are in TRACK seconds; t is in EDIT seconds
        d = abs((o - grid.t(0)) - target)
        if d < best_d:
            best, best_d = o - grid.t(0), d
    if best is None:
        return want
    snapped = best - t
    return snapped if 0.18 <= snapped <= want * 1.25 and t + snapped <= total else want


def shape_cards(cards: list[dict], plan: Plan) -> list[dict]:
    """One word per card, short and hard.

    The reference's words arrive in pieces and are gone in about a second; a
    card longer than that stops reading as a shout and starts reading as a
    subtitle.
    """
    out = []
    for c in cards:
        start = c["start"]
        if start >= plan.duration:
            continue
        end = min(start + 1.1, plan.duration - 0.05)
        if end - start < 0.25:
            continue
        d = dict(c)
        d["end"] = round(end, 3)
        out.append(d)
    return out


def summarise(plan: Plan) -> str:
    from .plan import summarise as _s

    lines = _s(plan).splitlines()
    d = [c.dur for c in plan.cuts]
    longest = max(d)
    lines.append(f"  hype      {len(d)} cuts  median {sorted(d)[len(d)//2]:.2f}s  "
                 f"longest {longest:.2f}s  "
                 f"whips {sum(1 for c in plan.cuts if c.transition == 'whip')}  "
                 f"flashes 0")
    return "\n".join(lines)
