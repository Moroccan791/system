"""The energy plan — when to cut, how long to hold, what to cut to.

This is the module that encodes the one structural fact the reference edit is
built on:

    a fast edit that is fast from the first frame has nowhere to go.

The reference spends 42% of its runtime on two shots, then cuts 30 times in the
next 16 seconds. That is not "a fast edit" — it is a build, and the build is
what makes the drop read. So the planner works from an ACT TEMPLATE:

    build   0.00 - 0.42   long holds, few cuts, the quiet part
    drop    0.42 - 0.80   dense cuts on 8ths and 16ths
    out     0.80 - 1.00   release, slow motion, the exhale

Densities are expressed in CUTS PER BEAT, not cuts per second, so the same plan
retimed to a different track keeps its shape.

The template is aligned to the track: the drop boundary snaps to the nearest bar
line at or after a real energy rise, and every cut lands on the grid division
for its act (16ths in the drop, quarters in the build).
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .grid import Grid
from .ramp import Ramp, make as make_ramp, mean_speed_of
from .shots import Source

# fractions of the edit
ACTS = {
    "build": (0.00, 0.42),
    "drop": (0.42, 0.80),
    "out": (0.80, 1.00),
}

# cuts per beat, and the grid division cuts quantise to
DENSITY = {
    "build": 0.11,
    "drop": 1.15,
    "out": 0.42,
}
DIVISION = {"build": 1, "drop": 4, "out": 2}

# how much the last stretch of the build accelerates toward the drop
RAMP = (0.80, 2.4)   # density multiplier at ramp start / at the drop

# A hold may not exceed this many seconds: beyond it the planner splits the
# hold across shots. On a scenepack the only shots long enough for a 4.4s hold
# are the dark atmospheric ones, so an uncapped hold forces the edit onto the
# worst footage in the pack.
MAX_HOLD_S = {"build": 2.6, "drop": 99.0, "out": 2.6}

# playback speed per act. Slow motion in the out is the reference's exhale.
SPEED = {"build": 1.0, "drop": 1.0, "out": 0.55}

# Which cuts get a speed ramp. A ramp has to be a surprise, so it goes on a
# minority of cuts: every drop cut ramping would be a house style, not an edit.
RAMP_SHARE = {"build": 0.0, "drop": 0.35, "out": 0.0}

# per-act grade. The reference changes colour by act: cold grief -> hot drop ->
# monochrome memory -> warm resolution. One grade for a whole video is amateur.
GRADE = {
    "build": {"contrast": 1.10, "saturation": 0.88, "brightness": -0.02,
              "gamma": 0.96, "shadow_tint": (0.99, 0.995, 1.04)},
    "drop": {"contrast": 1.14, "saturation": 1.10, "brightness": 0.0,
             "gamma": 1.01, "shadow_tint": (1.03, 1.0, 0.985)},
    "out": {"contrast": 1.12, "saturation": 0.16, "brightness": 0.015,
            "gamma": 1.04, "shadow_tint": (1.01, 1.01, 1.02)},
}


@dataclass
class Cut:
    index: int
    act: str
    start_beat: float
    length_beats: float
    shot: int
    src_in: float
    src_out: float
    speed: float
    flash: bool = False
    ramp: str | None = None          # name in ramp.RAMPS, or None for constant
    transition: str = "cut"          # cut | whip

    # derived
    out_start: float = 0.0
    out_end: float = 0.0

    @property
    def dur(self) -> float:
        return self.out_end - self.out_start

    @property
    def src_dur(self) -> float:
        return self.src_out - self.src_in

    def as_dict(self):
        d = asdict(self)
        for k in ("start_beat", "length_beats", "src_in", "src_out", "speed",
                  "out_start", "out_end"):
            d[k] = round(float(d[k]), 4)
        return d


@dataclass
class Plan:
    grid: Grid
    source: Source
    cuts: list[Cut] = field(default_factory=list)
    start: float = 0.0
    end: float = 0.0
    bpm: float = 0.0
    seed: int = 0

    @property
    def duration(self) -> float:
        return self.end - self.start

    def grade_for(self, act: str) -> dict:
        return GRADE.get(act, GRADE["build"])

    def as_dict(self):
        return {
            "bpm": round(self.grid.bpm, 2),
            "seed": self.seed,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "acts": {k: list(v) for k, v in ACTS.items()},
            "cuts": [c.as_dict() for c in self.cuts],
        }


def _act_bounds(grid: Grid, start: float, end: float) -> dict[str, tuple[float, float]]:
    """Place the act template in beats, snapping boundaries to bar lines and
    nudging the drop to a real energy rise when the track has one."""
    bpb = grid.bpm / 60.0
    b0, b1 = grid.beats(start), grid.beats(end)
    span = b1 - b0

    def bar(v: float) -> float:
        return b0 + round((v - b0) / 4.0) * 4.0

    drop_start = bar(b0 + span * ACTS["drop"][0])
    out_start = bar(b0 + span * ACTS["out"][0])

    # align the drop to the strongest energy rise within +/- 1 bar, if the track
    # actually has one (a looped bed does not, and forcing it would be a lie)
    best, best_jump = None, 0.0
    secs = grid.sections
    for i in range(1, len(secs)):
        jump = secs[i].level - secs[i - 1].level
        if jump > best_jump:
            best, best_jump = secs[i].start, jump
    if best is not None and best_jump > 0:
        cand = bar(grid.beats(best))
        # a real drop is worth moving the build for; a bed with no dynamics is not
        if abs(cand - drop_start) <= max(4.0, span * 0.20):
            drop_start = cand

    if out_start <= drop_start + 4.0:
        out_start = drop_start + 4.0
    return {"build": (b0, drop_start), "drop": (drop_start, out_start),
            "out": (out_start, b1)}


def _density_at(act: str, progress: float) -> float:
    """Cuts per beat at a given position inside an act."""
    if act == "build":
        # accelerate over the last stretch into the drop
        if progress < 0.55:
            return DENSITY["build"]
        k = (progress - 0.55) / 0.45
        return DENSITY["build"] + (DENSITY["drop"] * 0.55 - DENSITY["build"]) * (k ** 2.2)
    if act == "drop":
        # front-load the drop slightly, then settle — constant density reads flat
        if progress < 0.65:
            return DENSITY["drop"]
        return DENSITY["drop"] * (1.0 - 0.25 * (progress - 0.65) / 0.35)
    return DENSITY["out"]


_MOTION_RANK: dict[int, dict[int, float]] = {}
_BRIGHT_RANK: dict[int, dict[int, float]] = {}


def _max_shot(source: Source) -> float:
    return max((s.dur for s in source.shots), default=0.0)


def _cut_speed(cut_ramp: str | None, act: str) -> float:
    """Mean source seconds per output second for a cut."""
    if cut_ramp:
        return mean_speed_of(cut_ramp)
    return SPEED[act]


def _motion_ranks(source: Source) -> dict[int, float]:
    """Percentile rank of each shot's motion within this source (0..1).

    Absolute motion does not transfer between sources: a slow-motion scenepack
    measures 0.002 on every shot and a handheld vlog 0.05, but both have a
    liveliest shot and a stillest one. Rank, not raw value.
    """
    vals = sorted((s.motion for s in source.shots))
    if len(vals) < 2:
        return {s.index: 0.5 for s in source.shots}
    lo, hi = vals[0], vals[-1]
    span = max(1e-9, hi - lo)
    return {s.index: (s.motion - lo) / span for s in source.shots}


def _in_point(shot, room: float, need: float, out_dur: float,
              rng: random.Random) -> float:
    """Where inside a shot to start.

    Three rules, in order:
      * long holds start mid-shot, because the head of a scene in a graded pack
        is usually a fade up from black and holding on a fade looks broken;
      * never start somewhere the shot's own brightness profile says is dark —
        a 6s shot can be bright in the middle and near-black at the head, and one
        mean would put the hold in the dark part of a good shot;
      * otherwise a small random offset, so repeated use of one shot differs.
    """
    if room <= 0.05:
        return shot.src_in
    usable = min(room, max(0.0, shot.dur - need))
    prof = shot.profile or []
    lo = 0.34 if out_dur >= 1.5 else 0.0
    cands = []
    steps = 7
    for i in range(steps):
        f = lo + (0.95 - lo) * (i / max(1, steps - 1))
        off = usable * f
        b = shot.bright
        if prof:
            slot = int(min(len(prof) - 1, (off + need / 2) / max(1e-6, shot.dur)
                           * len(prof)))
            b = prof[slot]
        cands.append((b + rng.random() * 0.15 * b, off))
    cands.sort(key=lambda c: -c[0])
    return shot.src_in + cands[0][1]


def _bright_ranks(source: Source) -> dict[int, float]:
    vals = sorted((s.bright for s in source.shots))
    lo, hi = vals[0], vals[-1]
    span = max(1e-9, hi - lo)
    return {s.index: (s.bright - lo) / span for s in source.shots}


def _pick_shot(source: Source, rng: random.Random, act: str, need: float,
               recent: list[int], used: set[int]) -> int:
    """Choose a shot for this cut.

    Rules, in priority order:
      1. it must be long enough to supply the cut (after speed),
      2. never the shot we just used,
      3. prefer a motion level that matches the act (drop = movement,
         out = stillness),
      4. prefer a shot not yet used, so the edit does not repeat itself,
      5. ties broken by a seeded draw, so a plan is reproducible.
    """
    want_motion = {"build": 0.5, "drop": 0.8, "out": 0.15}[act]
    if id(source) not in _MOTION_RANK:
        _MOTION_RANK[id(source)] = _motion_ranks(source)
    ranks = _MOTION_RANK[id(source)]
    if id(source) not in _BRIGHT_RANK:
        _BRIGHT_RANK[id(source)] = _bright_ranks(source)
    bright_rank = _BRIGHT_RANK[id(source)]
    scored = []
    for s in source.shots:
        if s.dur * 0.98 < need:
            continue
        if s.index in recent[-2:]:
            continue
        score = 0.0
        score -= abs(ranks.get(s.index, 0.5) - want_motion) * 3.0
        score -= 1.2 if s.index in used else 0.0
        # A long hold has to be a shot worth holding. Near-black frames and
        # soft focus look like a mistake for 5 seconds even when they are art.
        if s.dur >= 2.0:
            # A five-second hold on a near-black frame is not mood, it is a
            # dead screen. The reference's build was dark but always legible.
            if s.bright < 45:
                score -= 6.0 * (1.0 - s.bright / 45.0)
            if s.sharp < 350:
                score -= 2.5
            score += min(1.0, s.sharp / 2000.0)
            # a long hold also wants a frame with something in it: the brightest
            # shots in a graded scenepack are the ones you can actually read
            score += bright_rank.get(s.index, 0.5) * 1.5
        score += rng.random() * 1.0
        scored.append((score, s.index))
    if not scored:                      # everything too short: allow a repeat
        scored = [(-rng.random(), s.index) for s in source.shots]
    scored.sort(reverse=True)
    return scored[0][1]


def build_plan(grid: Grid, source: Source, start: float = 0.0,
               end: float | None = None, seed: int = 0) -> Plan:
    rng = random.Random(seed)
    end = grid.duration if end is None else end
    span = end - start
    bounds = _act_bounds(grid, start, end)
    plan = Plan(grid=grid, source=source, start=start, end=end,
                bpm=grid.bpm, seed=seed)

    recent: list[int] = []
    used: set[int] = set()
    idx = 0
    for act in ("build", "drop", "out"):
        b_start, b_end = bounds[act]
        beat = b_start
        width = b_end - b_start
        if width <= 0:
            continue
        while beat < b_end - 1e-6:
            progress = (beat - b_start) / max(width, 1e-6)
            density = max(_density_at(act, progress), 0.02)
            length = max(1.0 / DIVISION[act], 1.0 / density)
            # quantise the length to the act's grid division
            div = DIVISION[act]
            length = max(1.0 / div, round(length * div) / div)
            max_hold_beats = MAX_HOLD_S[act] * grid.bpm / 60.0
            if length > max_hold_beats:
                length = max(1.0 / div, round(max_hold_beats * div) / div)
            if beat + length > b_end:
                length = b_end - beat
                if length < 1.0 / div:
                    break
            out_dur = length * 60.0 / grid.bpm
            # A ramp changes how much source the cut consumes, so the choice of
            # ramp has to happen BEFORE the shot is picked: a ramped cut needs
            # more runway than a constant one (mean speed 0.87 vs 1.0 here).
            ramp_name = None
            if act in RAMP_SHARE and rng.random() < RAMP_SHARE[act]:
                ramp_name = "settle" if rng.random() < 0.75 else "launch"
            speed = _cut_speed(ramp_name, act)
            need = out_dur * speed

            # A cut can never be longer than the shot feeding it. If nothing in
            # the source is that long, split the hold into two or three cuts on
            # the grid — freezing is never the answer, a freeze reads as a bug.
            if need > _max_shot(source) * 0.98:
                pieces = int(math.ceil(need / max(0.35, _max_shot(source) * 0.85)))
                pieces = max(2, min(pieces, 6))
                sub = length / pieces
                div = DIVISION[act]
                sub = max(1.0 / div, round(sub * div) / div)
                for _ in range(pieces):
                    if beat >= b_end - 1e-6:
                        break
                    ln = min(sub, b_end - beat)
                    if ln < 1.0 / div:
                        break
                    od = ln * 60.0 / grid.bpm
                    nd = od * SPEED[act]
                    sh = _pick_shot(source, rng, act, nd, recent, used)
                    ss = source.shots[sh]
                    room2 = max(0.0, ss.dur - nd)
                    si = _in_point(ss, room2, nd, od, rng)
                    c2 = Cut(index=idx, act=act, start_beat=beat, length_beats=ln,
                             shot=sh, src_in=si, src_out=si + nd, speed=SPEED[act],
                             ramp=None)
                    c2.out_start = grid.t(beat) - grid.t(0)
                    c2.out_end = c2.out_start + od
                    plan.cuts.append(c2)
                    recent.append(sh)
                    used.add(sh)
                    idx += 1
                    beat += ln
                continue

            shot = _pick_shot(source, rng, act, need, recent, used)
            src_shot = source.shots[shot]
            # in-point: somewhere that leaves enough runway, biased to the head
            room = max(0.0, src_shot.dur - need)
            src_in = _in_point(src_shot, room, need, out_dur, rng)
            cut = Cut(index=idx, act=act, start_beat=beat, length_beats=length,
                      shot=shot, src_in=src_in, src_out=src_in + need,
                      speed=speed, ramp=ramp_name)
            cut.out_start = grid.t(beat) - grid.t(0)
            cut.out_end = cut.out_start + out_dur
            plan.cuts.append(cut)
            recent.append(shot)
            used.add(shot)
            idx += 1
            beat += length

    # Shift picture so the edit starts at zero. `plan.start` stays the position
    # in the TRACK that frame one comes from — subtracting the grid phase from it
    # reads the audio from before the file begins.
    t0 = plan.cuts[0].out_start if plan.cuts else 0.0
    for c in plan.cuts:
        c.out_start -= t0
        c.out_end -= t0
    picture_dur = plan.cuts[-1].out_end if plan.cuts else (end - start)
    plan.end = plan.start + picture_dur

    _mark_flashes(plan, source)
    _mark_transitions(plan, source)
    return plan


def build_directed_plan(grid: Grid, source: Source, segments: list[dict],
                        start: float = 0.0) -> Plan:
    """Turn directed segments into a Plan.

    Same Cut objects, same flash/whip marking, same renderer — only the choice of
    shot is removed from the scorer and given to the director. That is the whole
    difference between an edit with a subject and a montage.

    Sync is absolute: a segment's length is the lyric's length, never a number
    the footage can negotiate. If the chosen shot is shorter than the cut needs,
    the cut SLOWS DOWN to fill it. Shortening the picture instead would slide
    every word after it off the song.
    """
    plan = Plan(grid=grid, source=source, start=start, end=start,
                bpm=grid.bpm, seed=0)
    taken: dict[int, list[tuple[float, float]]] = {}

    def free_in(shot, need: float, want: float | None) -> float:
        """An in-point that is not already on screen.

        A shot used four times in sixteen seconds has to show four different
        moments of itself. Taking the head of the shot every time is how an
        overedit ends up stuttering on one frame.
        """
        lo, hi = shot.src_in, shot.src_in + max(0.0, shot.dur - need)
        spans = taken.setdefault(shot.index, [])
        first = min(max(want if want is not None else lo + 0.25, lo), hi)
        best, best_overlap = first, None
        t = first
        for _ in range(int(max(1, (hi - lo) / 0.12)) + 2):
            if t > hi:
                break
            ov = sum(max(0.0, min(t + need, b) - max(t, a)) for a, b in spans)
            if ov <= 1e-6:
                best = t
                break
            if best_overlap is None or ov < best_overlap:
                best, best_overlap = t, ov
            t += 0.18
        spans.append((best, best + need))
        return best

    for idx, seg in enumerate(segments):
        out_dur = seg["end"] - seg["start"]
        if out_dur <= 1e-4:
            continue
        act = seg.get("act", "drop")
        ramp_name = seg.get("ramp")
        speed = _cut_speed(ramp_name, act)
        need = out_dur * speed

        pool = [i for i in seg["pool"] if i < len(source.shots)]
        if not pool:
            pool = [max(range(len(source.shots)),
                        key=lambda i: source.shots[i].dur)]
        fits = [i for i in pool if source.shots[i].dur * 0.97 >= need]
        chosen = fits[0] if fits else max(pool, key=lambda i: source.shots[i].dur)
        shot = source.shots[chosen]
        if need > shot.dur:
            # not enough footage at this speed: slow it down to fill the line
            need = shot.dur * 0.99
            speed = need / out_dur

        want = seg.get("src")
        if want is None:
            want = _in_point(shot, max(0.0, shot.dur - need), need, out_dur,
                             random.Random(int(seg["start"] * 1000)))
        src_in = free_in(shot, need, float(want))
        cut = Cut(index=idx, act=act, start_beat=grid.beats(seg["start"]),
                  length_beats=out_dur * grid.bpm / 60.0, shot=chosen,
                  src_in=src_in, src_out=src_in + need, speed=speed,
                  ramp=ramp_name)
        cut.out_start = seg["start"]
        cut.out_end = seg["end"]
        plan.cuts.append(cut)

    if not plan.cuts:
        return plan
    t0 = plan.cuts[0].out_start
    for c in plan.cuts:
        c.out_start -= t0
        c.out_end -= t0
    plan.end = plan.start + plan.cuts[-1].out_end
    _mark_flashes(plan, source)
    _mark_transitions(plan, source)
    return plan


def card_slots(plan: Plan, card: dict, max_hold: float = 2.4) -> dict:
    """How long a scripted card may stay on screen.

    A card that survives five shots has stopped being an instrument and become a
    lower third. Hold is capped by the act's own cut length: in the drop a card
    lives about one cut, in the build it may breathe for up to `max_hold`.
    """
    out = {}
    for i, c in enumerate(plan.cuts):
        cap = 0.75 if c.act == "drop" else max_hold
        out[i] = min(cap, max(c.dur * 1.5, 0.30))
    return out


def _mark_flashes(plan: Plan, source: Source) -> None:
    """A flash is earned when two consecutive shots differ hard in brightness or
    colour. Firing one on every cut is the tell of an amateur overedit; the
    reference only does it on the biggest jumps."""
    drop = [c for c in plan.cuts if c.act == "drop"]
    budget = max(1, int(len(drop) * 0.22))     # a flash on 1 cut in 5, no more
    scored = []
    for a, b in zip(plan.cuts, plan.cuts[1:]):
        if b.act != "drop":
            continue
        sa, sb = source.shots[a.shot], source.shots[b.shot]
        jump = abs(sa.bright - sb.bright) / 255.0
        colour_break = sa.colour != sb.colour and "mono" in (sa.colour, sb.colour)
        if jump > 0.14 or colour_break:
            scored.append((jump + (0.25 if colour_break else 0.0), b))
    scored.sort(key=lambda x: -x[0])
    for _score, cut in scored[:budget]:
        cut.flash = True


def _mark_transitions(plan: Plan, source: Source) -> None:
    """Choose the 1-2 frame double-sided transitions.

    A whip is not a cut with a blur on it: it is one or two frames that belong to
    BOTH shots — the outgoing frame pushed and the incoming frame pulled, blended.
    It earns its place where the cut would otherwise be a hard jump between two
    shots that do not share a direction. Never adjacent to a flash: two loud
    transitions in a row is noise.
    """
    drop = [c for c in plan.cuts if c.act == "drop"]
    budget = max(1, int(len(drop) * 0.15))
    scored = []
    for a, b in zip(plan.cuts, plan.cuts[1:]):
        if b.act != "drop" or b.flash:
            continue
        sa, sb = source.shots[a.shot], source.shots[b.shot]
        jump = abs(sa.bright - sb.bright) / 255.0
        # a whip reads best between two shots with real movement in them
        motion = max(sa.motion, sb.motion)
        scored.append((jump * 2.0 + min(1.0, motion * 20.0), b))
    scored.sort(key=lambda x: -x[0])
    chosen = 0
    for _score, cut in scored:
        if chosen >= budget:
            break
        prev = plan.cuts[cut.index - 1] if cut.index > 0 else None
        if prev is not None and (prev.flash or prev.transition != "cut"):
            continue
        cut.transition = "whip"
        chosen += 1


def summarise(plan: Plan) -> str:
    lines = [f"plan: {len(plan.cuts)} cuts over {plan.duration:.2f}s "
             f"({plan.bpm:.1f} BPM, seed {plan.seed})"]
    for act in ("build", "drop", "out"):
        cs = [c for c in plan.cuts if c.act == act]
        if not cs:
            continue
        d = [c.dur for c in cs]
        per_beat = len(cs) / max(sum(c.length_beats for c in cs), 1e-6)
        lines.append(f"  {act:6s} {len(cs):3d} cuts  {sum(d):6.2f}s  "
                     f"median {sorted(d)[len(d)//2]:.2f}s  "
                     f"{per_beat:.2f} cuts/beat  "
                     f"{sum(1 for c in cs if c.flash)} flash  "
                     f"{sum(1 for c in cs if c.transition == 'whip')} whip  "
                     f"{sum(1 for c in cs if c.ramp)} ramp")
    return "\n".join(lines)


def main(argv=None):
    import argparse

    from .grid import analyse as analyse_track
    from .shots import analyse as analyse_source

    ap = argparse.ArgumentParser(description="build an energy plan")
    ap.add_argument("--track", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)

    grid = analyse_track(a.track)
    src = analyse_source(a.source)
    plan = build_plan(grid, src, a.start, a.end, a.seed)
    print(summarise(plan))
    if a.out:
        Path(a.out).write_text(json.dumps(plan.as_dict(), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
