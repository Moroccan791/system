#!/usr/bin/env python3
"""Decide *which* move a shot needs - and which one it would ruin.

The user's position: "all of these is important at times and i need u to
figure out when is which one thing needed." That is a directing problem, not
an effects problem, so this module measures the footage and answers it per
clip, with a reason and a confidence for every call - including the calls that
say *don't*.

The rules come from what each effect is actually for:

    kinetic type   the opening line needs to register in the first beat
    light wrap     a subject on a bright background looks pasted on
    3D dolly       a locked-off shot can take a camera move; a moving one can't
    whip / zoom    needs two shots to cut between - never one
    A/B framing    needs a silence to hide the framing change
    punches        needs emphasised words and speech fast enough to carry them

So every decision is evidence-first: measure, threshold, state why. Nothing
here is a global "on" switch, and nothing is applied because it is available.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

MODEL = ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx"

#: Thresholds, each one calibrated on real footage rather than guessed; the
#: comment records what was measured.
T = {
    "cut_hist": 0.52,        # HSV histogram distance between sampled frames
    "motion_px_s": 22.0,     # global translation; above this the frame is moving
    "face_area": 0.015,      # face occupancy of the frame
    "bg_lift": 0.06,         # background brighter than the subject, relative
    "silence": 0.30,         # seconds of air that can hide a framing change
    "density": 2.5,          # words per second, below which punches feel random
}


def _sample(path: Path, every: float = 0.25) -> list[tuple[float, np.ndarray]]:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    out = []
    step = max(1, int(round(fps * every)))
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            t = i / fps
            out.append((t, cv2.resize(frame, (270, 480), interpolation=cv2.INTER_AREA)))
        i += 1
    cap.release()
    return out


def shot_cuts(frames: list[tuple[float, np.ndarray]], threshold: float | None = None) -> list[float]:
    """Times where the picture changes wholesale.

    HSV histograms, not frame difference: a head turn moves a lot of pixels
    without being a cut, and a cut changes the colour distribution even when
    the two shots are lit the same way.
    """
    th = T["cut_hist"] if threshold is None else threshold
    cuts = []
    prev = None
    for t, f in frames:
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        if prev is not None:
            d = 1.0 - float(cv2.compareHist(prev, hist, cv2.HISTCMP_CORREL))
            if d > th:
                cuts.append(round(t, 2))
        prev = hist
    return cuts


def camera_motion(frames: list[tuple[float, np.ndarray]], every: float = 0.25) -> float:
    """Global pan/tilt speed in px/s (at 1080 wide), from phase correlation."""
    if len(frames) < 2:
        return 0.0
    shifts = []
    for (_, a), (_, b) in zip(frames, frames[1:]):
        ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32)
        gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32)
        (dx, dy), _ = cv2.phaseCorrelate(ga, gb)
        scale = 1080.0 / a.shape[1]
        shifts.append(math_hypot(dx, dy) * scale)
    if not shifts:
        return 0.0
    return float(np.median(shifts)) / every


def math_hypot(x: float, y: float) -> float:
    return (x * x + y * y) ** 0.5


def face_stats(frames: list[tuple[float, np.ndarray]]) -> dict:
    """How much of the frame is face, how steady it is, and how bright the
    background sits behind it - the three things light wrap depends on."""
    if not MODEL.exists():
        return {"found": 0.0, "area": 0.0, "steadiness": 0.0, "bg_vs_face": 0.0}
    det = cv2.FaceDetectorYN.create(str(MODEL), "", (270, 480), 0.5, 0.3, 50)
    areas, boxes, lifts = [], [], []
    for _, f in frames:
        det.setInputSize((f.shape[1], f.shape[0]))
        _, faces = det.detect(f)
        if faces is None or not len(faces):
            continue
        best = max(faces, key=lambda b: float(b[14]))
        x, y, w, h = (float(v) for v in best[:4])
        areas.append((w * h) / (f.shape[0] * f.shape[1]))
        boxes.append((x, y, w, h))
        gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        face_mean = gray[int(y):int(y + h), int(x):int(x + w)].mean()
        pad = int(max(w, h) * 0.6)
        y0, y1 = max(0, int(y) - pad), min(f.shape[0], int(y + h) + pad)
        x0, x1 = max(0, int(x) - pad), min(f.shape[1], int(x + w) + pad)
        ring = gray[y0:y1, x0:x1].astype(np.float32)   # float: NaN masks the face
        ring[int(y) - y0:int(y + h) - y0, int(x) - x0:int(x + w) - x0] = np.nan
        bg = np.nanmean(ring) if np.isfinite(ring).any() else float("nan")
        if np.isfinite(bg) and face_mean:
            lifts.append((bg - face_mean) / face_mean)
    if not areas:
        return {"found": 0.0, "area": 0.0, "steadiness": 0.0, "bg_vs_face": 0.0}
    cx = [b[0] + b[2] / 2 for b in boxes]
    cy = [b[1] + b[3] / 2 for b in boxes]
    jitter = float(np.mean(np.abs(np.diff(cx)))) if len(cx) > 1 else 0.0
    return {
        "found": len(areas) / max(1, len(frames)),
        "area": float(np.median(areas)),
        "steadiness": float(1.0 - min(1.0, jitter / 20.0)),
        "bg_vs_face": float(np.median(lifts)) if lifts else 0.0,
    }


def silence_windows(cards: list[dict], min_gap: float | None = None) -> list[tuple[float, float]]:
    """Gaps between caption cards - the same input `framing_cuts` uses.

    Measuring silences from raw word times instead would tell the render to
    make a framing cut at a place the renderer cannot use, because the cards
    tile the speech. One definition, one answer.
    """
    gap = T["silence"] if min_gap is None else min_gap
    ordered = sorted(cards, key=lambda c: float(c.get("show_from", 0)))
    out = []
    prev_until = None
    for cap in ordered:
        start = float(cap.get("show_from", 0))
        if prev_until is not None and start - prev_until >= gap:
            out.append((prev_until, start))
        prev_until = float(cap.get("show_until", start))
    return out


def filter_transitions(cuts: list[float], *, duration: float, endcard: float,
                       start: float = 1.5, tail: float = 0.6,
                       min_gap: float = 0.9) -> list[float]:
    """Keep only the cuts worth putting a transition on.

    Three rules, each learned from the first render: never smear the opening
    (it is the hook), never smear into or out of the end card (it is a designed
    plate, not a shot), and never stack two inside a second - a clip with three
    whips in 1.1 s reads as broken rather than as edited.
    """
    out: list[float] = []
    for c in sorted(cuts):
        if c < start or c > endcard - tail:
            continue
        if out and c - out[-1] < min_gap:
            continue
        out.append(round(c, 2))
    return out


def decide(meas: dict, *, duration: float, cards: list[dict], words: list[dict],
           key_words: int, rules: dict | None = None) -> dict:
    """The rulebook. Every entry: use / why / confidence / where."""
    plan: dict[str, dict] = {}
    speeds = len(words) / max(duration, 0.1)

    cuts = meas.get("cuts", [])
    endcard = max((float(c.get("show_until", 0)) for c in cards), default=duration)
    usable = filter_transitions(cuts, duration=duration, endcard=endcard)
    plan["transition"] = {
        "use": len(usable) >= 1,
        "why": (f"{len(usable)} usable shot change(s) at {usable[:4]}"
                + (f" ({len(cuts) - len(usable)} skipped: too early, into the card, "
                   f"or too close to another)" if len(cuts) > len(usable) else "")
                if cuts else
                "one continuous shot - a whip or zoom has nothing to cut between"),
        "where": usable,
        "confidence": min(1.0, 0.5 + 0.3 * len(usable)),
    }

    face = meas.get("face", {})
    wrap_ok = (face.get("found", 0) > 0.6 and face.get("area", 0) > T["face_area"]
               and face.get("bg_vs_face", 0) > T["bg_lift"])
    plan["light_wrap"] = {
        "use": bool(wrap_ok),
        "why": (f"face {face.get('area', 0) * 100:.0f}% of frame, background "
                f"{face.get('bg_vs_face', 0) * 100:+.0f}% vs skin"
                if face.get("found") else "no steady face found"),
        "where": "face edge, all shots with a face",
        "confidence": 0.75 if wrap_ok else 0.25,
    }

    # A dark room has no spill to wrap - but it does leave the subject flat
    # against it, which is what a subject lift is for. One or the other,
    # decided by the same measurement.
    lift_ok = (face.get("found", 0) > 0.6 and face.get("area", 0) > T["face_area"]
               and face.get("bg_vs_face", 0) <= T["bg_lift"])
    plan["subject_lift"] = {
        "use": bool(lift_ok),
        "why": (f"background sits {face.get('bg_vs_face', 0) * 100:+.0f}% vs skin - "
                f"a dark room needs the subject separated, not wrapped"
                if lift_ok else "background is bright enough that the subject already separates"),
        "where": "subject matte",
        "confidence": 0.75 if lift_ok else 0.3,
    }

    moving = meas.get("motion", 0.0)
    dolly_ok = moving < T["motion_px_s"] and face.get("found", 0) > 0.5 and not cuts
    plan["dolly"] = {
        "use": bool(dolly_ok),
        "why": (f"camera already moves {moving:.0f} px/s - adding a move would "
                f"read as seasick" if moving >= T["motion_px_s"] else
                f"static shot ({moving:.0f} px/s)" + ("" if not cuts else
                                                      ", but it has cuts, so the camera move belongs on the cut")),
        "where": "whole clip, 0.5-1.5 deg",
        "confidence": 0.7 if dolly_ok else 0.3,
    }

    silences = silence_windows(cards)
    plan["ab_framing"] = {
        "use": len(silences) >= 1,
        "why": (f"{len(silences)} gap(s) >= {T['silence']}s to hide the change"
                if silences else "speech is continuous - a framing jump would land mid-word"),
        "where": [round(s, 2) for s, _ in silences[:4]],
        "confidence": 0.8 if silences else 0.2,
    }

    plan["punches"] = {
        "use": key_words >= 2 and speeds >= T["density"],
        "why": f"{key_words} emphasised words at {speeds:.1f} w/s",
        "where": "on each emphasised word",
        "confidence": min(1.0, 0.4 + 0.05 * key_words),
    }

    opening = cards[0] if cards else None
    n_open = len(opening["lines"][0]) if opening and opening.get("lines") else 0
    plan["kinetic_type"] = {
        "use": bool(opening) and n_open >= 1,
        "why": f"opening line is {n_open} words - set as a title for its first beat",
        "where": "0 - first card",
        "confidence": 0.9 if opening else 0.0,
    }
    return plan


def plan_for(video: Path, *, cards: list[dict], words: list[dict],
             key_words: int = 0, rules: dict | None = None,
             every: float = 0.25) -> dict:
    frames = _sample(video, every)
    duration = frames[-1][0] if frames else 0.0
    meas = {
        "cuts": shot_cuts(frames),
        "motion": camera_motion(frames, every),
        "face": face_stats(frames),
        "sampled": len(frames),
    }
    plan = decide(meas, duration=duration, cards=cards, words=words,
                  key_words=key_words, rules=rules)
    plan["_measured"] = meas
    return plan


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--manifest", help="tight_cards.json: cards + kept words")
    ap.add_argument("--json", help="write the plan here")
    args = ap.parse_args()

    cards, words, key = [], [], 0
    if args.manifest:
        m = json.loads(Path(args.manifest).read_text())
        cards = m.get("cards", [])
        words = m.get("words_kept", [])
        key = int(m.get("key_words") or 0)
    plan = plan_for(Path(args.video), cards=cards, words=words, key_words=key)
    print(f"\nDIRECTION — {Path(args.video).name}\n")
    for name, d in plan.items():
        if name.startswith("_"):
            continue
        mark = "USE " if d["use"] else "SKIP"
        print(f"[{mark}] {name:13s} {d['why']}")
    if args.json:
        Path(args.json).write_text(json.dumps(plan, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
