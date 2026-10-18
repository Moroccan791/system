#!/usr/bin/env python3
"""Compute the crop for every shot in a window, keeping the speaker's
face fully in frame (YuNet, the same detector the reframe tool uses).

    python scripts/whop/face_crops.py --start 1827.1 --end 1860.8 \
        --cuts 1843.88,1845.47 --post post2

Prints a crops[] list for the base spec:
  {"until": ..., "crop": [x, y, w, h], "push": 0.05, "anchor": 0.3}

Rules
  * a big face (taller than 26% of the frame) -> tight MCU 480x854
    (9:16 vertical, eyes in the upper third)
  * a small face -> full height 608x1080 (still 9:16) so nothing of
    the shot is lost
  * the face box is always fully inside the crop, with margin
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

ROOT = Path("/home/user/system")
SRC = ROOT / "work" / "street" / "raw" / "street_full.mp4"
MODEL = ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx"


def ffmpeg() -> str:
    return subprocess.run([str(ROOT / ".venv/bin/python"), "-c",
                           "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
                          capture_output=True, text=True).stdout.strip()


def faces_in(ff, t, tmp="/tmp/facec.jpg"):
    subprocess.run([ff, "-y", "-v", "error", "-ss", str(t), "-i", str(SRC),
                    "-frames:v", "1", tmp], check=False)
    img = cv2.imread(tmp)
    if img is None:
        return []
    h, w = img.shape[:2]
    det = cv2.FaceDetectorYN.create(str(MODEL), "", (w, h), 0.5, 0.3, 50)
    _, faces = det.detect(img)
    if faces is None:
        return []
    return [tuple(map(float, f[:4])) for f in faces]


def crop_for(box, W=1920, H=1080, margin=36):
    x, y, fw, fh = box
    # The detector's box runs past the jaw into the neck, and the hair
    # sits above the forehead: the visible chin is ~0.80 of the box
    # height and the hair's top ~0.25 above it.
    chin = y + 0.80 * fh
    head_top = y - 0.25 * fh
    # The crop is as WIDE as the frame allows while the chin stays at
    # ~0.57 (the caption then sits just under it) and the head stays
    # in frame. A wide crop also keeps the face at the reference size
    # (~45-60% of the frame width) instead of a tight close-up.
    lo = (chin - head_top) / 0.57          # the head must fit
    hi = min(H, chin / 0.57, (H - chin) / 0.43)
    ch = int(round(max(lo, min(hi, H))))
    ch = max(240, min(ch, H))
    cw = int(round(ch * 9 / 16 / 2) * 2)
    top = int(max(0, min(chin - 0.57 * ch, H - ch)))
    cx = x + fw / 2
    centred = int(round(cx - cw / 2))
    # the face must sit fully inside with margin on BOTH sides:
    #   left <= x - margin      and      left >= x + fw + margin - cw
    lo = x + fw + margin - cw
    hi = x - margin
    left = int(min(max(centred, lo), hi)) if lo <= hi else int(centred)
    left = int(max(0, min(left, W - cw)))
    if x - left < margin or (left + cw) - (x + fw) < margin:
        # too tight for this face: widen to the full-height window
        cw, ch, top = 608, 1080, 0
        left = int(max(0, min(cx - cw / 2, W - cw)))
    return [left, top, cw, ch]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--cuts", default="")
    ap.add_argument("--post", default="post2")
    a = ap.parse_args()
    ff = ffmpeg()
    cuts = [float(c) for c in a.cuts.split(",") if c.strip()]
    bounds = [a.start] + cuts + [a.end]

    crops = []
    for i in range(len(bounds) - 1):
        lo, hi = bounds[i], bounds[i + 1]
        boxes = []
        t = lo + 0.3
        while t < hi - 0.1:
            fs = faces_in(ff, t)
            if fs:
                boxes.append(max(fs, key=lambda b: b[2] * b[3]))
            t += 0.6
        if not boxes:
            print(f"!! no face found in {lo:.1f}-{hi:.1f} - keeping the previous crop")
            if crops:
                c = dict(crops[-1])
                c["until"] = round(hi, 2)
                crops.append(c)
            continue
        arr = np.array(boxes)
        box = (float(np.median(arr[:, 0])), float(np.median(arr[:, 1])),
               float(np.median(arr[:, 2])), float(np.median(arr[:, 3])))
        c = crop_for(box)
        crops.append({"until": round(hi, 2), "crop": c, "push": 0.05, "anchor": 0.3})
        print(f"{lo:8.2f}-{hi:8.2f}  face {tuple(int(v) for v in box)}  crop {c}")
    print(json.dumps(crops, indent=1))
    out = ROOT / "work" / "street" / a.post / "crops.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(crops, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
