"""One command: track + footage + words -> an overedit.

    python -m studio.produce \
        --track work/studio/test_score.wav \
        --source clips/amazing_spiderman.mp4 \
        --script studio/scripts/example.json \
        --start 12.0 --end 34.0 \
        --out work/studio/edit.mp4

Writes the edit, plus `<out>.plan.json` and `<out>.report.json` next to it, so a
render can be explained after the fact: every cut, which shot fed it, where it
landed on the grid, and what the analysis found.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .compose import OUT_FPS, OUT_H, OUT_W, render
from .grid import analyse as analyse_track
from .plan import build_plan, summarise
from .shots import analyse as analyse_source


def report(plan, grid, src) -> dict:
    acts = {}
    for cut in plan.cuts:
        a = acts.setdefault(cut.act, {"cuts": 0, "seconds": 0.0, "shots": set(),
                                      "flash": 0})
        a["cuts"] += 1
        a["seconds"] += cut.dur
        a["shots"].add(cut.shot)
        a["flash"] += int(cut.flash)
    for a in acts.values():
        a["seconds"] = round(a["seconds"], 2)
        a["shots"] = len(a["shots"])

    # on-grid check: how far each cut lands from the nearest 16th
    import math

    grid_errors = []
    for cut in plan.cuts:
        beat = (cut.out_start) / (60.0 / grid.bpm)
        nearest = round(beat * 4) / 4
        grid_errors.append(abs(beat - nearest) * 60.0 / grid.bpm)
    return {
        "bpm": round(grid.bpm, 2),
        "duration": round(plan.duration, 3),
        "size": f"{OUT_W}x{OUT_H}@{OUT_FPS}",
        "cuts": len(plan.cuts),
        "acts": acts,
        "median_cut": round(sorted(c.dur for c in plan.cuts)[len(plan.cuts) // 2], 3)
        if plan.cuts else 0,
        "min_cut": round(min((c.dur for c in plan.cuts), default=0), 3),
        "max_cut": round(max((c.dur for c in plan.cuts), default=0), 3),
        "distinct_shots_used": len({c.shot for c in plan.cuts}),
        "shots_available": len(src.shots),
        "grid_error_ms_median": round(1000 * sorted(grid_errors)[len(grid_errors) // 2], 1)
        if grid_errors else 0,
        "grid_error_ms_max": round(1000 * max(grid_errors), 1) if grid_errors else 0,
        "sections": [s.as_dict() for s in grid.sections],
    }


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="render an overedit")
    ap.add_argument("--track", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--script", default=None, help="json list of {beat,text,accent}")
    ap.add_argument("--start", type=float, default=0.0, help="track start, seconds")
    ap.add_argument("--end", type=float, default=None, help="track end, seconds")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--crf", type=int, default=18)
    a = ap.parse_args(argv)

    t0 = time.time()
    grid = analyse_track(a.track, a.end)
    print(f"track: {grid.bpm:.1f} BPM, {len(grid.sections)} sections, "
          f"beat0 {grid.phase:.3f}s")
    for s in grid.sections:
        print(f"  {s.label:6s} {s.start:6.2f}-{s.end:6.2f}")
    src = analyse_source(a.source, a.end)
    print(f"source: {len(src.shots)} shots, {src.duration:.2f}s")

    plan = build_plan(grid, src, a.start, a.end, a.seed)
    print(summarise(plan))

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rep = report(plan, grid, src)
    out.with_suffix(".plan.json").write_text(json.dumps(plan.as_dict(), indent=1) + "\n")
    out.with_suffix(".report.json").write_text(json.dumps(rep, indent=1) + "\n")

    render(plan, a.source, a.track, out, a.script,
           progress=lambda m: None, preset=a.preset, crf=a.crf)
    print(f"wrote {out}  ({plan.duration:.2f}s, {time.time() - t0:.0f}s to build)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
