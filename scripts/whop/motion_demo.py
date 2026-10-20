#!/usr/bin/env python3
"""A proof reel: every "we'd need After Effects for that" move, in code.

    .venv/bin/python scripts/whop/motion_demo.py

Renders 8 seconds of the post 7 source with four segments, each one a
capability that usually gets attributed to AE:

    0.0-2.4  kinetic type       - words land on a spring, overshoot, settle
    2.4-4.6  face track + roto  - smoothed YuNet ellipse drives a soft mask,
                                  subject lift and edge light wrap; a label
                                  sticks to the face as it moves
    4.6-6.4  3D camera          - trapezoid yaw/pitch with zoom: a single-plane
                                  perspective dolly
    6.4-8.0  transitions        - whip pan into a radial zoom blur

It writes work/street/post7/motion_demo.mp4 and touches nothing that shipped.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import motion_kit as MK          # noqa: E402
import font_refresh as FR        # noqa: E402

W, H = MK.W, MK.H
SRC = ROOT / "campaigns" / "street_you_grew_up_on" / "post7" / "street_post7.mp4"
MODEL = ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx"
OUT = ROOT / "work" / "street" / "post7" / "motion_demo.mp4"
START, DUR, FPS = 9.0, 8.0, 30.0

SEGMENTS = [(0.0, "KINETIC TYPE"), (2.4, "FACE TRACK + LIGHT WRAP"),
            (4.6, "3D CAMERA"), (6.4, "WHIP -> ZOOM BLUR")]


def label(frame: np.ndarray, text: str) -> np.ndarray:
    rgb, a = MK.word_sprite(text, FR.SHAWKIND, 32, (255, 255, 255), stroke=4)
    return MK.blit(frame, rgb, a, (W / 2, 168), opacity=0.8)


def ffmpeg() -> str:
    return subprocess.run([sys.executable, "-c",
                           "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    cap = cv2.VideoCapture(str(SRC))
    cap.set(cv2.CAP_PROP_POS_MSEC, START * 1000)
    tracker = MK.FaceTracker(MODEL)
    n = int(DUR * FPS)
    tmp = OUT.with_name("motion_demo_silent.mp4")
    tmp.parent.mkdir(parents=True, exist_ok=True)

    enc = subprocess.Popen(
        [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
         "-r", f"{FPS:.3f}", "-i", "-", "-an",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)

    # red key ink (the sprite takes RGB and converts to BGR internally)
    words = [("i", False), ("will", False), ("never", True),
             ("be", False), ("angry", False), ("for", False),
             ("a", False), ("struggle", True)]
    tracked_rgb, tracked_a = MK.word_sprite("TRACKED TO THE FACE", FR.SHAWKIND, 46,
                                            (240, 235, 226), stroke=4)
    frames = 0
    for i in range(n):
        ok, frame = cap.read()
        if not ok:
            break
        t = i / FPS
        frame = cv2.resize(frame, (W, H)) if frame.shape[:2] != (H, W) else frame
        frame = FR.erase_captions(frame, *FR.BAND)   # the archive's own subtitles
        box = tracker.update(frame)          # track every frame: history matters

        cur = max([s for s in SEGMENTS if s[0] <= t], key=lambda s: s[0])

        if t < 2.4:                                       # kinetic type
            z = 1.0 + 0.05 * (t / 2.4)
            frame = MK.perspective_cam(frame, zoom=z)
            frame = MK.kinetic_type(frame, words, t, t0=0.15,
                                    font_path=FR.SHAWKIND, size=120, gap=0.13,
                                    key_ink=(226, 59, 47),
                                    y=1150, line_h=150, per_line=3)
        elif t < 4.6:                                     # tracked mask + wrap
            mask = tracker.mask(frame.shape[:2], grow=0.30, feather=38)
            lift = 1.0 + 0.16 * mask[:, :, None]
            frame = np.clip(frame.astype(np.float32) * lift, 0, 255).astype(np.uint8)
            frame = MK.light_wrap(frame, mask, strength=0.66, radius=45)
            frame = MK.perspective_cam(frame, zoom=1.03)
            if box is not None:
                x, y, fw, fh = box
                frame = MK.blit(frame, tracked_rgb, tracked_a,
                                (x + fw / 2, max(240, y + fh + 70)),
                                scale=0.9 + 0.1 * min(1.0, (t - 2.4) / 0.4))
        elif t < 6.4:                                     # 3D dolly
            u = (t - 4.6) / 1.8
            frame = MK.perspective_cam(frame, zoom=1.0 + 0.10 * u,
                                       yaw=0.55 * math.sin(math.pi * u),
                                       pitch=0.18 * math.sin(math.pi * u))
        else:                                             # transitions
            u = (t - 6.4) / 1.6
            frame = MK.perspective_cam(frame, zoom=1.04)
            if u < 0.45:
                frame = MK.whip_pan(frame, amount=MK.ease_out_cubic(min(1.0, u / 0.35)),
                                    direction=1)
            else:
                frame = MK.zoom_blur(frame, amount=0.5 + 2.4 * ((u - 0.45) / 0.55))

        frame = label(frame, cur[1])
        enc.stdin.write(frame.tobytes())
        frames += 1
    cap.release()
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit("encode failed")

    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(tmp), "-ss", f"{START:.2f}", "-t", f"{DUR:.2f}",
                    "-i", str(SRC), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-movflags", "+faststart", str(OUT)], check=True)
    tmp.unlink(missing_ok=True)
    info = json.dumps({"out": str(OUT), "frames": frames,
                       "seconds": round(frames / FPS, 2),
                       "bytes": OUT.stat().st_size}, indent=1)
    print(info)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
