#!/usr/bin/env python3
"""Track the speaker and write each post's crop/split plan.

    .venv/bin/python scripts/whop/crop_track.py \
        --source work/two_bears/full.mp4 \
        --picks campaigns/two_bears_ep344/picks.json \
        --out-dir scripts/whop/plans --prefix _

The vertical window is cut from inside the show's own picture frame (so the
broadcaster's burned-in bug in the top-right corner never enters the crop) and
follows whoever is speaking. Picking the highest-confidence face per frame is
not tracking: it flips between the two hosts every sample and produces a cut
every half second. This tracks continuity instead - each sample takes the face
nearest the previous centre, a hard cut is only declared when the picture
changes (histogram distance) AND the tracked centre jumps, and short or
near-identical segments are collapsed into their neighbour.

Output is the crop block of a plan base:

    {"span": [a, b], "splits": [...], "crops": [{until, crop, push, anchor}, ...]}
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx"

PICT = (123, 71, 1674, 938)     # the show's picture area inside the 1920x1080 frame
STEP = 0.4                      # seconds between samples
CUT_HIST = 0.30                 # Bhattacharyya distance that means "new shot"
MIN_FACE_W = 60
MIN_CONF = 0.6
JUMP_PX = 330                   # a centre jump this large is a cut, not a move
MIN_SEG = 1.6                   # seconds; shorter segments are merged away
COLLAPSE_MOVE = 70              # px; a segment that barely moves is redundant
COLLAPSE_SEG = 1.5
PUSH = 0.05
#: the broadcaster's burned-in "2 BEARS, / 1 CAVE" bug lives here in the source
#: frame. A crop whose right edge passes this x drags it back on screen, so the
#: window is clamped left of it even when that puts the speaker off-centre.
BUG_X0 = 1610


def crop_w() -> int:
    _, _, _, h = PICT
    return int(round(h * 9 / 16))


def clamp_x(cx: float, w: int) -> int:
    x0, _, pw, _ = PICT
    return int(round(min(max(cx - w / 2, x0), min(x0 + pw - w, BUG_X0 - w))))


def sample(source: Path, span: tuple[float, float]):
    cap = cv2.VideoCapture(str(source))
    det = cv2.FaceDetectorYN.create(str(MODEL), "", (1920, 1080), 0.5, 0.3, 50)
    out = []
    t = span[0]
    prev_cx, prev_hist = None, None
    while t < span[1]:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        x, y, w, h = PICT
        pic = frame[y:y + h, x:x + w]
        small = cv2.resize(pic, (0, 0), fx=0.25, fy=0.25)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        dist = 1.0 if prev_hist is None else cv2.compareHist(
            prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA)
        det.setInputSize((w, h))
        _, faces = det.detect(pic)
        faces = [] if faces is None else [
            f for f in faces if f[2] >= MIN_FACE_W and f[-1] >= MIN_CONF]
        cx = None
        if faces:
            if prev_cx is None:
                f = max(faces, key=lambda f: f[2] * f[-1])
            else:
                f = min(faces, key=lambda f: abs((f[0] + f[2] / 2) - prev_cx))
            cx = float(f[0] + f[2] / 2) + PICT[0]
        out.append({"t": t, "cx": cx, "hist": dist})
        prev_hist = hist
        if cx is not None:
            prev_cx = cx
        t += STEP
    cap.release()
    return out


def segments(samples, span) -> list[dict]:
    cw = crop_w()
    # fill gaps in the track with the last / next known centre
    known = [s for s in samples if s["cx"] is not None]
    if not known:
        return [{"start": span[0], "end": span[1], "cx": None}]
    last = known[0]["cx"]
    for s in samples:
        if s["cx"] is None:
            s["cx"] = last
        else:
            last = s["cx"]

    segs = [{"start": samples[0]["t"], "end": samples[-1]["t"],
             "cx": [s["cx"] for s in samples[:1]][0], "vals": []}]
    segs[0]["vals"] = []
    for prev, s in zip(samples, samples[1:]):
        moved = abs(s["cx"] - prev["cx"])
        cut = s["hist"] > CUT_HIST and moved > JUMP_PX
        if cut:
            segs[-1]["end"] = prev["t"]
            segs.append({"start": s["t"], "end": s["t"], "cx": s["cx"], "vals": []})
        segs[-1]["end"] = s["t"]
        segs[-1]["vals"].append(s["cx"])

    for s in segs:
        s["med"] = float(np.median(s["vals"])) if s["vals"] else s["cx"]

    # merge segments too short to be a shot of their own
    merged: list[dict] = []
    for s in segs:
        if merged and (s["end"] - s["start"] < MIN_SEG):
            merged[-1]["end"] = s["end"]
            merged[-1]["vals"] += s["vals"]
            merged[-1]["med"] = float(np.median(merged[-1]["vals"]))
        else:
            merged.append(s)
    # collapse a segment that stays on the same framing as its neighbour
    out: list[dict] = []
    for s in merged:
        if out and (s["end"] - s["start"] < COLLAPSE_SEG
                    or abs(s["med"] - out[-1]["med"]) < COLLAPSE_MOVE):
            out[-1]["end"] = s["end"]
        else:
            out.append(s)
    out[0]["start"] = span[0]
    out[-1]["end"] = span[1]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="work/two_bears/full.mp4")
    ap.add_argument("--picks", default="campaigns/two_bears_ep344/picks.json")
    ap.add_argument("--out-dir", default="scripts/whop/plans")
    ap.add_argument("--prefix", default="_")
    args = ap.parse_args()

    src = ROOT / args.source
    picks = json.loads((ROOT / args.picks).read_text())
    cw = crop_w()
    for pick in picks:
        span = (float(pick["start"]), float(pick["end"]))
        samples = sample(src, span)
        segs = segments(samples, span)
        crops, splits = [], []
        for i, s in enumerate(segs):
            x = clamp_x(s["med"], cw)
            crops.append({"until": round(s["end"] + (0.01 if i == len(segs) - 1 else 0), 2),
                          "crop": [x, PICT[1], cw, PICT[3]],
                          "push": PUSH, "anchor": 0.5})
            if i:
                splits.append(round(s["start"], 1))
        # a split is only a cut if the framing actually changed
        crops = [c for c in crops]
        base = {"slug": pick["slug"], "span": [round(span[0], 2), round(span[1], 2)],
                "splits": splits, "crops": crops}
        out = ROOT / args.out_dir / f"{args.prefix}{pick['slug']}_base.json"
        out.write_text(json.dumps(base, indent=1) + "\n")
        print(f"{pick['slug']}: {len(segs)} segments, "
              f"x={[c['crop'][0] for c in crops]}, splits={splits} -> {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
