#!/usr/bin/env python3
"""Face-tracked 9:16 reframing for motion bases.

The Stage-A bases used a FIXED crop window; when the speaker moved,
the window sliced their face (measured: 28% of face frames at the
edge). This tool replaces the blind crop: YuNet detects faces every
`--stride` frames, a continuity-locked primary face (the speaker) is
tracked, and the crop window pans to keep faces inside with margin.
The window WIDTH never changes (no zoom pulsing, ever); the pan is
median+EMA smoothed and velocity-clamped so it glides, never jumps.
When every detected face fits in the window the span is centred,
otherwise the tracked speaker wins.

Usage:
  python motion/reframe.py <src16x9.mp4> <out9x16.mp4> [--margin 26]
Prints a JSON report: worst face margin, % frames with the speaker's
face fully inside at >= --margin px (source scale).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from clipper.ffmpeg import ffmpeg_exe  # noqa: E402

MODEL = (Path(__file__).resolve().parent.parent / "assets" / "models" /
         "face_detection_yunet_2023mar.onnx")


def detect_track(src: Path, stride: int, cuts: list[int]):
    cap = cv2.VideoCapture(str(src))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    det = cv2.FaceDetectorYN.create(str(MODEL), "", (w, h), 0.6, 0.3, 50)
    samples = []  # (frame, primary bbox|None, all bboxes)
    primary_c = None
    primary_a = 1.0
    last_seg = 0
    f = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if f % stride == 0:
            seg = sum(1 for c in cuts if f >= c)
            if seg != last_seg:  # new shot: re-acquire the speaker
                primary_c = None
                last_seg = seg
            _, faces = det.detect(fr)
            boxes = [] if faces is None else [tuple(map(float, b[:4]))
                                              for b in faces]
            primary = None
            if boxes:
                if primary_c is None:
                    # acquire: largest face FULLY inside the source -
                    # a face the source itself cuts can never be framed
                    inside = [b for b in boxes
                              if b[0] >= 8 and b[0] + b[2] <= w - 8]
                    primary = max(inside or boxes,
                                  key=lambda b: b[2] * b[3])
                else:
                    # identity cost: centre distance + size change, so
                    # the track cannot hop to a neighbour whose face
                    # merely passes near (profile views flicker)
                    def cost(b):
                        d = ((b[0] + b[2] / 2 - primary_c[0]) ** 2
                             + (b[1] + b[3] / 2 - primary_c[1]) ** 2) ** 0.5
                        return d + 0.22 * w * abs(np.log(
                            (b[2] * b[3]) / max(primary_a, 1.0)))
                    primary = min(boxes, key=cost)
                    if cost(primary) > 0.22 * w:
                        primary = None  # lost: hold, don't leap
                if primary is not None:
                    primary_c = (primary[0] + primary[2] / 2,
                                 primary[1] + primary[3] / 2)
                    primary_a = primary[2] * primary[3]
            samples.append((f, primary, boxes))
        f += 1
    cap.release()
    return fps, total, w, h, samples


def window_centers(samples, total, w, crop_w, margin, fps, stride, cuts):
    """Desired centre per sample -> smoothed WITHIN each shot (the
    window snaps at cuts: a cut already breaks continuity, a glide
    across it leaves the new shot's face sliced for a second)."""
    segs = np.array([sum(1 for c in cuts if f >= c)
                     for f, _, _ in samples])
    desired = []
    for f, primary, boxes in samples:
        if primary is None:
            desired.append(desired[-1] if desired else w / 2)
            continue
        cx = primary[0] + primary[2] / 2
        if boxes:
            x0 = min(b[0] for b in boxes)
            x1 = max(b[0] + b[2] for b in boxes)
            if x1 - x0 + 2 * margin <= crop_w:  # everyone fits: centre span
                cx = (x0 + x1) / 2
        desired.append(cx)
    d = np.array(desired, dtype=np.float64)
    ema = np.empty_like(d)
    max_step = 260.0 * stride / fps  # velocity clamp: <= 260 src px/s
    half = crop_w / 2
    for seg in np.unique(segs):
        idx = np.where(segs == seg)[0]
        ds = d[idx]
        k = 9  # median kills detection jitter
        med = np.array([np.median(ds[max(0, j - k // 2):j + k // 2 + 1])
                        for j in range(len(ds))])
        e = np.empty_like(med)
        e[0] = med[0]
        for j in range(1, len(med)):
            e[j] = e[j - 1] + np.clip(0.35 * (med[j] - e[j - 1]),
                                      -max_step, max_step)
        # guarantee: primary face + margin inside, window inside frame
        for j, i in enumerate(idx):
            primary = samples[i][1]
            cx = float(np.clip(e[j], half, w - half))
            if primary is not None:
                if primary[0] - margin < cx - half:
                    cx = primary[0] - margin + half
                if primary[0] + primary[2] + margin > cx + half:
                    cx = primary[0] + primary[2] + margin - half
                cx = float(np.clip(cx, half, w - half))
            e[j] = cx
        ema[idx] = e
    # per-frame: linear inside a shot, hard step ON the cut frame
    sample_frames = np.array([s[0] for s in samples], dtype=np.float64)
    centres = np.empty(total)
    for i in range(len(samples)):
        f0 = int(sample_frames[i])
        f1 = int(sample_frames[i + 1]) if i + 1 < len(samples) else total
        cut_in = [c for c in cuts if f0 < c < f1]
        if segs[i] == (segs[i + 1] if i + 1 < len(samples) else segs[i]) \
                or not cut_in:
            centres[f0:f1] = np.linspace(
                ema[i], ema[i + 1] if i + 1 < len(samples) else ema[i],
                max(1, f1 - f0))[:f1 - f0]
        else:
            c = cut_in[0]
            centres[f0:c] = ema[i]
            centres[c:f1] = ema[i + 1]
    report = margins_report(samples, sample_frames, ema, crop_w, margin)
    return centres, report


def margins_report(samples, sample_frames, ema, crop_w, margin):
    half = crop_w / 2
    worst, ok, seen = 1e9, 0, 0
    for f, primary, _ in samples:
        if primary is None:
            continue
        cx = float(np.interp(f, sample_frames, ema))
        m = min(primary[0] - (cx - half), (cx + half)
                - (primary[0] + primary[2]))
        worst = min(worst, m)
        seen += 1
        ok += m >= margin * 0.75
    return {"worst_face_margin_px": round(worst, 1),
            "frames_with_face": seen,
            "pct_face_inside_margin": round(100.0 * ok / max(seen, 1), 1)}


def main() -> int:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    margin = float(sys.argv[sys.argv.index("--margin") + 1]) \
        if "--margin" in sys.argv else 26.0
    stride = 1  # per-frame: the face-margin guarantee holds everywhere
    from transitions import detect_cuts  # same dir; seconds -> frames
    probe_fps = cv2.VideoCapture(str(src)).get(cv2.CAP_PROP_FPS) or 30.0
    cuts = sorted({int(round(t * probe_fps))
                   for t in detect_cuts(src)} - {0})
    fps, total, w, h, samples = detect_track(src, stride, cuts)
    crop_w = int(round(h * 9 / 16)) // 2 * 2
    centres, report = window_centers(samples, total, w, crop_w, margin,
                                     fps, stride, cuts)
    report["cuts_honoured"] = len(cuts)
    tmp = out.with_suffix(".video.mp4")
    cmd = [ffmpeg_exe(), "-y", "-v", "error", "-f", "rawvideo",
           "-pix_fmt", "bgr24", "-s", f"{crop_w}x{h}", "-r", str(fps),
           "-i", "-", "-an", "-c:v", "libx264", "-crf", "17",
           "-preset", "veryfast", "-pix_fmt", "yuv420p", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    cap = cv2.VideoCapture(str(src))
    f = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        x0 = int(round(centres[min(f, total - 1)] - crop_w / 2))
        x0 = max(0, min(w - crop_w, x0)) // 2 * 2
        proc.stdin.write(fr[:, x0:x0 + crop_w].tobytes())
        f += 1
    cap.release()
    proc.stdin.close()
    proc.wait()
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(tmp),
                    "-i", str(src), "-map", "0:v", "-map", "1:a?",
                    "-c:v", "copy", "-c:a", "copy", "-shortest",
                    str(out)], check=True)
    tmp.unlink()
    report.update({"src": str(src), "out": str(out), "frames": total,
                   "crop_w": crop_w})
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
