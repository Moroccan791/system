"""`barrage` — the v26 style: half-second cutting, a breakdown, no words.

Read the reference first: `studio/reference/barrage_v26.md`. The rules taken
from it, in the order they matter:

  1. median shot half a second; nothing holds except in the breakdown
  2. flashes of exactly three frames as punctuation, on the beat
  3. whips used as texture as much as joins
  4. one quiet window about two-thirds in, where a single shot is allowed to sit
     for three seconds and the grade lifts
  5. **no type at all** — the only text is the signature, and that is the
     watermark, which the renderer already stamps

This module builds the PLAN only. It does not touch the house director, the
house planner, or any of the delivered edits: a barrage edit is a plan with its
own grade attached, rendered by the same compositor as everything else.
"""

from __future__ import annotations

import random

from .plan import Cut, Plan, _in_point
from .repertoire import pick

# The reference's numbers, from the frame-by-frame pass.
OPEN_S = 2.8          # the cold open, before the first real section
MEDIAN_S = 0.50       # body shot length
BREAKDOWN_AT = 0.66   # where the quiet window starts (fraction of runtime)
BREAKDOWN_LEN = 0.09  # how much of the runtime the window takes
HOLD_S = 3.10         # the longest shot in the reference, 18.93 s -> 22.03 s
FLASH_SHARE = 0.12    # 6 of 52 cuts were three-frame flashes
WHIP_SHARE = 0.27     # 14 of 52 transitions were whips

# Bright and flat: the reference's median luma is 85 against a saturation of
# 0.33, because a flash has to read as white rather than as a grey cut.
GRADE = {
    "contrast": 1.00,
    "brightness": 0.030,
    "gamma": 0.92,
    "saturation": 1.25,
    "shadow_tint": (1.00, 1.00, 1.02),
}


def _length(rng: random.Random, length_s: float) -> float:
    """A shot length around the reference's median, with a little spread.

    Deliberately NOT snapped to the beat grid: the reference only lands 16 of
    its 52 cuts on a kick, and rounding every length to a quarter note pushed
    the median from 0.53 to 0.67 — a whole subdivision slower than the style.
    """
    return max(0.10, length_s * rng.uniform(0.72, 1.40))


def build(grid, source, start: float = 0.0, end: float | None = None,
          seed: int = 0) -> Plan:
    """A barrage plan: fast body, one quiet window, three-frame flashes."""
    rng = random.Random(seed)
    end = grid.duration if end is None else end
    plan = Plan(grid=grid, source=source, start=start, end=end,
                bpm=grid.bpm, seed=seed, grade_override=GRADE)

    total = end - start
    bd_in = total * BREAKDOWN_AT
    bd_out = bd_in + total * BREAKDOWN_LEN

    # Where the quiet window goes is the SONG's business, not the style's. The
    # reference has a real breakdown at two-thirds (it drops 22 dB); if this
    # track has one near the same place, the window moves onto it. If it does
    # not, the cutting still slows at two-thirds but the music is left alone —
    # ducking a track that never steps back is inventing a moment the song does
    # not have, and it is audible as a mistake.
    bd_span = bd_out - bd_in
    quiet_sec = _quietest_section(grid, start, end)
    if quiet_sec is not None and not (quiet_sec[2] < quiet_sec[3] - 1.5):
        # Louder than the track average is not a breakdown. Keep the window
        # where the style puts it and leave the music alone.
        quiet_sec = None
    if quiet_sec is not None:
        s0, s1 = quiet_sec
        bd_in = max(0.0, s0)
        bd_out = min(total, s1)
        if bd_out - bd_in < 1.6:                     # too short to hold a shot
            mid = (bd_in + bd_out) / 2
            bd_in, bd_out = max(0.0, mid - bd_span / 2), min(total, mid + bd_span / 2)

    recent: list[int] = []
    used: set[int] = set()
    idx = 0
    t = 0.0                     # seconds into the edit
    # The hold belongs to the first cut that BEGINS inside the window. Testing
    # `t == bd_in` missed it whenever the preceding cut straddled the boundary,
    # which is most of the time — the window then had no long shot in it at all.
    placed_hold = False
    while t < total - 1e-6:
        quiet = bd_in <= t < bd_out
        if quiet:
            # one long shot at the top of the window, then two shorter ones;
            # the reference's window is 3.10 s + a 1.60 s + a 1.77 s.
            span = min(bd_out - t, total - t)
            if not placed_hold:
                want = min(HOLD_S, max(span, HOLD_S))
                placed_hold = True
            else:
                want = min(1.70, span)
        else:
            want = _length(rng, MEDIAN_S)
        want = max(3.0 / grid.fps if hasattr(grid, "fps") else 0.10, want)
        want = min(want, total - t)

        act = "build" if t < OPEN_S else "drop"
        need = want
        # A cut can never be longer than the shot feeding it; ask for a shorter
        # one rather than freezing the last frame.
        longest = max((s.dur for s in source.shots), default=0.0)
        if need > longest * 0.95:
            need = longest * 0.90
            want = need
        shot = pick(source, rng, act, need, recent, used)
        ss = source.shots[shot]
        room = max(0.0, ss.dur - need)
        src_in = _in_point(ss, room, need, want, rng)

        cut = Cut(index=idx, act=act, start_beat=t * grid.bpm / 60.0,
                  length_beats=want * grid.bpm / 60.0, shot=shot,
                  src_in=src_in, src_out=src_in + need, speed=1.0)
        cut.out_start = t
        cut.out_end = t + want

        # Flashes and whips are placed on a COUNT, not on a dice roll. The
        # reference has 6 three-frame flashes in 52 cuts (one in 8.7) and 14
        # whips in 52 (one in 3.7); drawing them at random gave 2 and 7 on a
        # 56-cut plan and the texture disappeared. A style has to be reliable
        # across footage, so the rhythm is a function of the cut index.
        if t > OPEN_S and t + want < total - 0.2:
            if idx % 9 == 5:
                cut.flash = True
                cut.flash_frames = 3
            elif idx % 4 == 2:
                cut.transition = "whip"
        plan.cuts.append(cut)
        recent.append(shot)
        used.add(shot)
        idx += 1
        t = cut.out_end

    plan.end = plan.start + (plan.cuts[-1].out_end if plan.cuts else total)
    # Only claim a breakdown in the AUDIO if a genuinely quieter section is
    # sitting under the window; the visual slowdown happens either way.
    if quiet_sec is not None and quiet_sec[2] < quiet_sec[3] - 1.5:
        plan.breakdown = (bd_in, min(bd_out, plan.duration - 0.5))
    return plan


def _quietest_section(grid, start: float, end: float):
    """The quietest section between 50% and 85% of the window, as edit seconds.

    Returns (in, out, level_db, loudest_db) or None when the track has no
    sections or nothing quiet enough to be called a breakdown.
    """
    secs = getattr(grid, "sections", None) or []
    rms = getattr(grid, "rms_db", None) or []
    if not secs:
        return None
    total = end - start
    best = None
    for i, sec in enumerate(secs):
        a, b = max(0.0, sec.start - start), min(total, sec.end - start)
        if b - a < 1.6:
            continue
        mid = (a + b) / 2
        if not (0.50 * total <= mid <= 0.85 * total):
            continue
        # rms_db is sampled every 0.25 s, not once per section: indexing it by
        # the section number read the first few frames of the track and called
        # the loudest part of the song "quiet".
        db = _mean_db(rms, sec.start, sec.end)
        if best is None or db < best[2]:
            best = (a, b, db, _mean_db(rms, 0.0, grid.duration))
    return best


def _mean_db(rms: list[float], a: float, b: float) -> float:
    if not rms:
        return 0.0
    i0 = max(0, int(round(a / 0.25)))
    i1 = min(len(rms), max(i0 + 1, int(round(b / 0.25))))
    vals = rms[i0:i1]
    return float(sum(vals) / len(vals)) if vals else float(rms[0])


def summarise(plan: Plan) -> str:
    from .plan import summarise as _s

    lines = _s(plan).splitlines()
    d = [c.dur for c in plan.cuts]
    quiet = [c for c in plan.cuts if c.dur >= 1.5]
    flashes = sum(1 for c in plan.cuts if c.flash)
    whips = sum(1 for c in plan.cuts if c.transition == "whip")
    lines.append(f"  barrage   {len(d)} cuts  median {sorted(d)[len(d)//2]:.2f}s  "
                 f"flashes {flashes} (3 frames)  whips {whips}  "
                 f"holds 1.5s+ {len(quiet)}")
    return "\n".join(lines)
