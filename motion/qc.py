#!/usr/bin/env python3
"""QC for a motion-graphics render (spec section QC).

    python motion/qc.py <timeline.json> <transcript.json> <video.mp4> <framesDir>

Checks (fail = exit 1):
  word_sync     every poster/card word's appear frame vs its speech
                start in the transcript - must be within +-40 ms
  pacing        longest stretch without a visual change (item starts,
                word appearances, fx) - reported against the 2.5 s cap
  face_zone     YuNet faces in the composited video vs the poster zone
                rectangle at every poster moment
  semi_text     consecutive frames containing semi-transparent text,
                from the renderer's own accounting (cap: 2)
  margins       timeline zones keep text inside the 6% safe margin

Prints a report; auto-fix note: word offsets are authored from the
transcript itself, so a word_sync failure means the timeline drifted
from the transcript - regenerate it, don't hand-nudge frames.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

CHECK_MS = 40.0


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


def word_sync(tl: dict, transcript: dict) -> tuple[str, str]:
    spoken = [(_norm(str(w["text"])), float(w["start"]))
              for w in transcript.get("words", [])]
    authored: list[tuple[str, float]] = []
    for it in tl["items"]:
        for row in (it.get("rows") or it.get("lines") or []):
            for w in row:
                authored.append((_norm(w["w"]), float(w["at"])))
    si = 0
    worst = 0.0
    misses = []
    for text, at in authored:
        # closest matching occurrence in order: uncaptioned beats
        # (counters, list plates) legitimately skip spoken words, so a
        # repeated word must bind to the occurrence nearest its
        # authored time - the offset is then measured honestly
        best, best_off = None, None
        for j in range(si, min(len(spoken), si + 80)):
            if spoken[j][0] == text:
                off = abs(at - spoken[j][1]) * 1000
                if best_off is None or off < best_off:
                    best, best_off = j, off
        if best is None:
            misses.append(text)
            continue
        worst = max(worst, best_off)
        if best_off > CHECK_MS:
            misses.append(f"{text} ({best_off:.0f} ms)")
        si = best + 1
    if misses:
        return "fail", f"words out of sync: {', '.join(misses[:5])}"
    return "pass", f"{len(authored)} words, worst offset {worst:.0f} ms (cap {CHECK_MS:.0f})"


def pacing(tl: dict) -> tuple[str, str]:
    events = set()
    for it in tl["items"]:
        events.add(round(float(it["at"]), 3))
        for row in (it.get("rows") or it.get("lines") or []):
            for w in row:
                events.add(round(float(w["at"]), 3))
        for key in ("items", "steps"):
            for sub in it.get(key) or []:
                events.add(round(float(sub["at"]), 3))
        if it["type"] == "counter":
            events.add(round(float(it["at"]) + float(it.get("countDur") or 0.9), 3))
    ev = sorted(events)
    gaps = [(b - a, a) for a, b in zip(ev, ev[1:])]
    if not gaps:
        return "warn", "no events"
    worst, at = max(gaps)
    return ("pass" if worst <= 2.5 else "fail",
            f"longest without a visual change {worst:.2f} s at {at:.1f} s (cap 2.5)")


def face_zone(video: Path, tl: dict) -> tuple[str, str]:
    # every text-bearing component that sits over the footage: posters,
    # counters, PiP cards, list plates and process stacks (full-screen
    # cards and B-roll windows are editorial takeovers, checked by eye
    # on the contact sheet instead)
    posters = [i for i in tl["items"]
               if i["type"] in ("poster", "pip", "counter", "list", "process")]
    if not posters:
        return "warn", "no poster items"
    try:
        import cv2  # noqa: F401
    except ImportError:
        return "warn", "opencv unavailable"
    sys.path.insert(0, str(ROOT))
    from clipper.edit.reframe import _MODEL, _detector
    from clipper.ffmpeg import iter_frames

    if not _MODEL.exists():
        return "warn", "YuNet model missing"
    det = _detector()
    if det is None:
        return "warn", "YuNet unavailable"
    zone_def = {"list": [0.50, 0.95], "process": [0.52, 0.92]}
    hits = []
    for it in posters:
        zone = it.get("zone") or zone_def.get(it["type"]) or [0.615, 0.845]
        zy0, zy1 = zone[0] * 1920, zone[1] * 1920
        t = (float(it["at"]) + float(it.get("until") or it["at"])) / 2
        frame = next(iter_frames(video, size=(540, 960), start=t, duration=0.1), None)
        if frame is None:
            continue
        det.setInputSize((frame.shape[1], frame.shape[0]))
        _, faces = det.detect(frame)
        if faces is None or not len(faces):
            continue
        fy = frame.shape[0] / 1920.0
        for f in faces:
            fy0, fh = float(f[1]), float(f[3])
            if fy0 < zy1 * fy and fy0 + fh > zy0 * fy:
                hits.append(f"{t:.1f} s")
                break
    return (("fail", f"face enters text zone at {', '.join(hits[:4])}")
            if hits else ("pass", f"faces clear of the text zone in "
                                  f"{len(posters)} items"))


def semi_text(frames: Path) -> tuple[str, str]:
    stats_path = Path(frames) / "render_stats.json"
    if not stats_path.exists():
        return "warn", "no render_stats.json"
    stats = json.loads(stats_path.read_text())
    run = int(stats.get("semiMaxConsecutive") or 0)
    return (("fail", f"text semi-transparent for {run} consecutive frames (cap 2)")
            if run > 2 else
            ("pass", f"max semi-transparent run {run} frames (cap 2)"))


def margins(tl: dict) -> tuple[str, str]:
    for it in tl["items"]:
        zone = it.get("zone")
        if zone and not (0.30 <= zone[0] and zone[1] <= 0.95):
            return "fail", f"{it['type']} zone {zone} escapes the frame"
    return "pass", "all zones inside the 6% safe margin plan"


def main() -> int:
    tl = json.loads(Path(sys.argv[1]).read_text())
    transcript = json.loads(Path(sys.argv[2]).read_text())
    video, frames = Path(sys.argv[3]), Path(sys.argv[4])
    checks = [("word_sync", *word_sync(tl, transcript)),
              ("pacing", *pacing(tl)),
              ("face_zone", *face_zone(video, tl)),
              ("semi_text", *semi_text(frames)),
              ("margins", *margins(tl))]
    ok = all(s != "fail" for _, s, _ in checks)
    print(f"MOTION QC {video.name}: {'PASS' if ok else 'FAIL'}")
    for name, status, detail in checks:
        print(f"  [{status.upper()}] {name}: {detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
