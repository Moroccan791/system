"""Choosing shots without repeating yourself.

`plan._pick_shot` scores every usable shot and takes the best, with a fixed
-1.2 penalty for a shot already used. On a real pack that penalty is smaller
than the spread created by the motion and brightness preferences, so the same
three or four shots win every time — measured on the Peter & Gwen pack, 14 cuts
drew on 4 shots out of 87 that were long enough.

That is a defect, not a style. Fixing it inside `plan._pick_shot` would change
what the house plan does, and the house plan is frozen and hash-checked, so the
fix lives here instead: the built styles use this picker, the house system keeps
the one it shipped with.

The rule is the same one a person uses cutting to music: **use up the pack
before you go back to it**, and only repeat when the material genuinely runs
out.
"""

from __future__ import annotations

import random


def pick(source, rng: random.Random, act: str, need: float,
         recent: list[int], used: set[int]) -> int:
    from .plan import _bright_ranks, _motion_ranks

    want_motion = {"build": 0.5, "drop": 0.8, "out": 0.15}[act]
    ranks = _MOTION_RANK.setdefault(id(source), _motion_ranks(source))
    bright = _BRIGHT_RANK.setdefault(id(source), _bright_ranks(source))

    def ok(shot) -> bool:
        return shot.dur * 0.98 >= need and shot.index not in recent[-2:]

    fresh = [s for s in source.shots if ok(s) and s.index not in used]
    stale = [s for s in source.shots if ok(s) and s.index in used]
    pool = fresh or stale
    if not pool:                                    # nothing long enough
        pool = [s for s in source.shots if s.index not in recent[-2:]] or list(source.shots)

    scored = []
    for s in pool:
        score = -abs(ranks.get(s.index, 0.5) - want_motion) * 3.0
        # A long hold wants a frame you can actually read; the same rule the
        # house planner applies, repeated here so a style gets it too.
        if need >= 2.0:
            if s.bright < 45:
                score -= 6.0 * (1.0 - s.bright / 45.0)
            if s.sharp < 350:
                score -= 2.5
            score += min(1.0, s.sharp / 2000.0)
            score += bright.get(s.index, 0.5) * 1.5
        score += rng.random() * 1.0
        scored.append((score, s.index))
    scored.sort(reverse=True)
    return scored[0][1]


# keyed by object identity, exactly as plan.py does, so a Source is analysed once
_MOTION_RANK: dict[int, dict[int, float]] = {}
_BRIGHT_RANK: dict[int, dict[int, float]] = {}
