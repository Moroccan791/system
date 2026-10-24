"""A hand-cut segment map — the editor's choice, not a scorer's.

Every style built so far picks shots by scoring: motion, brightness, how long
ago it was used. On a scenepack that works, because any shot of Peter is as good
as any other. On an actual SCENE it fails completely — the scorer has no idea
that 119 s is her face as she falls and 129 s is the web being thrown, so it
picked neither.

This module renders from a list an editor wrote:

    {"cuts": [
      {"at": 0.00, "in": 112.0, "len": 2.4, "speed": 1.0, "note": "the two of
       them falling together"},
      {"at": 41.0, "in": 129.0, "len": 2.0, "speed": 0.5, "note": "the web"}
    ]}

`at` is the position in the finished edit, `in` is the source second, `len` is
how long the cut lasts on screen, and `speed` is a time multiplier: **0.5 plays
at half speed** (slow motion), 1.0 is normal, 2.0 is double.

Nothing here scores anything. If a cut is dull, that is my fault for putting it
in the list, and it is visible in one glance at the file.
"""

from __future__ import annotations

import json
from pathlib import Path

from .plan import Cut, Plan


def load(path: str | Path) -> list[dict]:
    d = json.loads(Path(path).read_text())
    cuts = d.get("cuts", d) if isinstance(d, dict) else d
    out = []
    for c in cuts:
        out.append({
            "at": float(c["at"]),
            "in": float(c["in"]),
            "len": float(c.get("len", 1.0)),
            "speed": float(c.get("speed", 1.0)),
            "note": c.get("note", ""),
            "zoom": float(c.get("zoom", 1.0)),
            "act": c.get("act"),
        })
    out.sort(key=lambda c: c["at"])
    # A gap is not a pause, because the renderer concatenates cuts. It is time
    # that silently disappears, which shows up as every card landing late and
    # the whole edit running short of the song. A small overlap is fine — that
    # is a deliberate cross-cut — but a hole never is.
    for a, b in zip(out, out[1:]):
        end = a["at"] + a["len"]
        if b["at"] - end > 0.02:
            raise ValueError(
                f"cut map has a {b['at'] - end:.2f}s HOLE at {end:.2f}s "
                f"({a['note']!r} -> {b['note']!r}). The renderer concatenates "
                f"cuts, so a hole is dropped time, not silence. Extend the "
                f"previous cut instead.")
    return out


def build(grid, source, segments: list[dict], start: float = 0.0,
          end: float | None = None, seed: int = 0, grade: dict | None = None
          ) -> Plan:
    """Turn the map into a plan. Times are already edit seconds."""
    total = (end - start) if end else (segments[-1]["at"] + segments[-1]["len"])
    plan = Plan(grid=grid, source=source, start=start, end=start + total,
                bpm=grid.bpm, seed=seed, grade_override=grade)

    for i, s in enumerate(segments):
        src_span = s["len"] * s["speed"]
        cut = Cut(index=i,
                  act=s["act"] or ("build" if s["at"] < total * 0.2 else "drop"),
                  start_beat=s["at"] * grid.bpm / 60.0,
                  length_beats=s["len"] * grid.bpm / 60.0,
                  shot=_nearest_shot(source, s["in"]),
                  src_in=s["in"],
                  src_out=s["in"] + src_span,
                  speed=s["speed"], zoom=s["zoom"])
        cut.out_start = s["at"]
        cut.out_end = s["at"] + s["len"]
        if s.get("whip"):
            cut.transition = "whip"
        plan.cuts.append(cut)

    plan.end = plan.start + (plan.cuts[-1].out_end if plan.cuts else total)
    return plan


def _nearest_shot(source, t: float) -> int:
    """Which analysed shot contains this source time (for colour matching)."""
    best, best_d = 0, 1e9
    for sh in source.shots:
        # Shot carries src_in/src_out, not start/dur-as-offset
        if sh.src_in - 1e-6 <= t <= sh.src_out + 1e-6:
            return sh.index
        d = abs(sh.src_in - t)
        if d < best_d:
            best, best_d = sh.index, d
    return best


def summarise(segments: list[dict]) -> str:
    total = max(s["at"] + s["len"] for s in segments)
    slow = [s for s in segments if s["speed"] < 1.0]
    lines = [f"  cut map   {len(segments)} cuts over {total:.2f}s  "
             f"({len(slow)} in slow motion)"]
    for s in segments:
        tag = f"{s['speed']:g}x" if s["speed"] != 1.0 else "   "
        lines.append(f"    {s['at']:6.2f} -> {s['at'] + s['len']:6.2f}  "
                     f"src {s['in']:7.2f}  {tag}  {s['note']}")
    return "\n".join(lines)
