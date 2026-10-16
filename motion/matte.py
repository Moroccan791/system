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
    # stream masks straight into the encoder: buffering a whole
    # video of 1080x1920 mattes OOM-kills on anything past ~20 s
    # (measured: 60 s -> rc=137). Coverage is tracked incrementally.
    prev: np.ndarray | None = None
    enc = None
    w = h = 0
    count = 0
    above = 0
    total_px = 0
    gmin, gmax = 255, 0
    try:
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
            mu = (m * 255).astype(np.uint8)
            if enc is None:
                h, w = mu.shape
                # temp name, renamed on success: a killed run must
                # never leave a partial mask for produce.py to reuse
                tmp_out = out.with_name(out.stem + ".tmp.mp4")
                enc = subprocess.Popen(
                    [ffmpeg_exe(), "-y", "-v", "error", "-f", "rawvideo",
                     "-pix_fmt", "gray", "-s", f"{w}x{h}",
                     "-r", f"{fps:.3f}", "-i", "-", "-c:v", "libx264",
                     "-preset", "veryfast", "-crf", "5",
                     "-pix_fmt", "yuv420p", str(tmp_out)],
                    stdin=subprocess.PIPE)
            enc.stdin.write(mu.tobytes())
            count += 1
            above += int((mu > 127).sum())
            total_px += mu.size
            gmin = min(gmin, int(mu.min()))
            gmax = max(gmax, int(mu.max()))
            if count % 300 == 0:
                print(f"matte: {count}/{n_frames or '?'} frames")
    except BrokenPipeError:
        print("matte: mask encoder died", file=sys.stderr)
        return 1
    finally:
        cap.release()
        if enc is not None:
            try:
                enc.stdin.close()
            except BrokenPipeError:
                pass
    if not count:
        print("matte: no frames read", file=sys.stderr)
        return 1
    cov = 100.0 * above / max(total_px, 1)
    print(f"matte: {count} frames {w}x{h}@{fps:.2f}, "
          f"person coverage {cov:.0f}%")
    if enc.wait() != 0:
        tmp_out.unlink(missing_ok=True)
        print("matte: mask encode failed", file=sys.stderr)
        return 1
    if gmin == gmax or not 3.0 < cov < 97.0:
        tmp_out.unlink(missing_ok=True)
        print("matte: implausible matte (constant or full-frame) - "
              "refusing to keep a mask that would corrupt the stack",
              file=sys.stderr)
        return 1
    tmp_out.replace(out)
    print(f"matte: wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
