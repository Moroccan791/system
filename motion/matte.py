#!/usr/bin/env python3
"""Person matte for behind-the-person graphics.

    python motion/matte.py <base.mp4> <mask.mp4>

Runs MediaPipe selfie segmentation (model bundled in the pip wheel,
CPU) over the base and writes the matte as a grayscale video (luma =
alpha: 255 on the speaker). composite.py merges it with the graded
base in-graph ([fg][mask]alphamerge), so the speaker's own pixels are
re-laid over behind-graphics with zero grade mismatch at the edge.

The matte is firmed (clean floor/ceiling), feathered ~1.5px and
temporally smoothed (EMA) so the silhouette cannot boil. It is a pure
function of the base frames: same base, same mask, every run.

Setup (sandbox): pip install mediapipe==0.10.21
                 opencv-contrib-python-headless (GUI builds need libGL)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from clipper.ffmpeg import ffmpeg_exe  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: matte.py <base.mp4> <mask.mp4>", file=sys.stderr)
        return 2
    base, out = Path(sys.argv[1]), Path(sys.argv[2])

    import mediapipe as mp
    seg = mp.solutions.selfie_segmentation.SelfieSegmentation(
        model_selection=1)

    cap = cv2.VideoCapture(str(base))
    if not cap.isOpened():
        print(f"matte: cannot open {base}", file=sys.stderr)
        return 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    masks: list[np.ndarray] = []
    prev: np.ndarray | None = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        m = seg.process(rgb).segmentation_mask.astype(np.float32)
        m = np.clip((m - 0.30) / 0.40, 0.0, 1.0)
        m = cv2.GaussianBlur(m, (0, 0), 1.4)
        if prev is not None and prev.shape == m.shape:
            m = 0.55 * m + 0.45 * prev
        prev = m
        masks.append((m * 255).astype(np.uint8))
        if len(masks) % 300 == 0:
            print(f"matte: {len(masks)}/{n_frames or '?'} frames")
    cap.release()
    if not masks:
        print("matte: no frames read", file=sys.stderr)
        return 1
    h, w = masks[0].shape
    stack = np.stack(masks)
    cov = float((stack > 127).mean() * 100)
    print(f"matte: {len(masks)} frames {w}x{h}@{fps:.2f}, "
          f"person coverage {cov:.0f}%")
    if stack.min() == stack.max() or not 3.0 < cov < 97.0:
        print("matte: implausible matte (constant or full-frame) - "
              "refusing to write a mask that would corrupt the stack",
              file=sys.stderr)
        return 1
    enc = subprocess.Popen(
        [ffmpeg_exe(), "-y", "-v", "error", "-f", "rawvideo",
         "-pix_fmt", "gray", "-s", f"{w}x{h}", "-r", f"{fps:.3f}",
         "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "5",
         "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    try:
        for m in masks:
            enc.stdin.write(m.tobytes())
        enc.stdin.close()
    except BrokenPipeError:
        print("matte: mask encoder died", file=sys.stderr)
        return 1
    if enc.wait() != 0:
        print("matte: mask encode failed", file=sys.stderr)
        return 1
    print(f"matte: wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
