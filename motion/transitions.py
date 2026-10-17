#!/usr/bin/env python3
"""Cut detection + transition injection (permanent rules 1.11/1.12).

    python motion/transitions.py <base.mp4> <timeline.json> <out.json>

Every hard cut in the base footage gets a 6-10 frame transition whose
peak lands on the cut frame. Authored fx (flash/flare/leak/bwflash)
already sitting on a cut are respected; the rest get an injected fx
item, kinds rotating flare -> flash -> leak -> bwflash and durations
varying 6/8/9/10 frames so consecutive cuts never feel stamped-on.

Writes the augmented timeline plus a sidecar `<out>.transitions.json`
listing every cut and its transition - QC checks against it that all
text is fully out 3 frames before each cut and that no cut is bare.
Deterministic: same base + same timeline -> same output.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from clipper.ffmpeg import ffmpeg_exe  # noqa: E402

FPS = 30
KINDS = ["flare", "flash", "leak", "bwflash"]
DURS = [8, 10, 9, 8]                     # frames, cycled - never two alike;
# >= the 8-frame exit so an exit caught mid-flight at a cut always
# completes inside its transition (see qc.py `cuts` for the rule)
TRANSITION_KINDS = ("flash", "flare", "leak", "bwflash")


def detect_cuts(base: Path, threshold: float = 0.25) -> list[float]:
    # 0.25 verified frame-by-frame on the MILK episode: every event
    # >=0.25 there is a real camera cut (0.28-0.59), and punch-ins on
    # calmer footage score lower. False positives fail safe: an extra
    # transition is a beat accent; a missed cut is a bare cut.
    proc = subprocess.run(
        [ffmpeg_exe(), "-v", "info", "-i", str(base),
         "-vf", f"select='gt(scene,{threshold})',metadata=print",
         "-an", "-f", "null", "-"],
        capture_output=True, text=True)
    cuts = [float(m) for m in
            re.findall(r"pts_time:([0-9.]+)", proc.stderr or "")]
    # the opening owns the first ~10 frames (its blur-zoom IS the entry
    # transition); a "cut" there is the base starting mid-shot-change
    return [c for c in cuts if c > 0.35]


def main() -> int:
    base, tl_path, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    tl = json.loads(tl_path.read_text())
    cuts = detect_cuts(base)
    if "--hard" in sys.argv:
        # theme-scoped doctrine (whop): the reference editors cut
        # hard - no injected flash/flare/leak. The sidecar still
        # lists every cut so QC can enforce that no text exit is
        # in progress across one.
        out.write_text(json.dumps(tl, indent=2))
        sidecar = {"base": str(base), "cuts": [
            {"t": round(c, 3), "kind": "hard", "dur": 0.0,
             "source": "theme"} for c in cuts]}
        Path(str(out) + ".transitions.json").write_text(
            json.dumps(sidecar, indent=2))
        print(f"transitions: {len(cuts)} cut(s), hard (theme) -> {out}")
        return 0
    items = tl.setdefault("items", [])
    authored = [i for i in items
                if i.get("type") == "fx" and i.get("kind") in TRANSITION_KINDS]
    log = []
    n = 0
    for cut in cuts:
        hit = next((i for i in authored
                    if abs(float(i["at"]) + float(i.get("dur") or 0.27) / 2 - cut)
                    <= 0.25), None)
        if hit is not None:
            log.append({"t": round(cut, 3), "kind": hit["kind"],
                        "dur": float(hit.get("dur") or 0.27),
                        "source": "authored"})
            continue
        dur = DURS[n % len(DURS)] / FPS
        kind = KINDS[n % len(KINDS)]
        items.append({"type": "fx", "kind": kind,
                      "at": round(cut - dur / 2, 3), "dur": round(dur, 3),
                      "strength": 0.6})
        log.append({"t": round(cut, 3), "kind": kind, "dur": round(dur, 3),
                    "source": "injected"})
        n += 1
    items.sort(key=lambda i: float(i["at"]))
    out.write_text(json.dumps(tl, indent=2))
    sidecar = {"base": str(base), "cuts": log}
    Path(str(out) + ".transitions.json").write_text(json.dumps(sidecar, indent=2))
    print(f"transitions: {len(cuts)} cut(s), {n} injected -> {out}")
    for c in log:
        print(f"  cut @{c['t']:6.2f}  {c['kind']:<8} {c['dur'] * FPS:.0f}f  {c['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
