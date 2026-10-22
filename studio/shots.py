"""Source analysis — what the footage actually gives you.

An overedit is only as good as the cut you choose, and you cannot choose a cut
from a shot you have not classified. This module turns a source file into a
shot list with enough per-shot description for the planner to make decisions:

  motion   how much the frame moves inside the shot (0-1). Pans and action
           shots score high, locked-off dialogue scores near zero.
  sharp    laplacian variance — tells you whether a shot can carry a hard cut
           or needs to be softened / speed-ramped.
  bright   mean luma. Needed for flash transitions: a flash out of a dark shot
           has to land on a bright one, or it reads as a glitch.
  sat/colour  mean saturation and warm/cool balance. Grouping shots by colour
           is what stops a fast cut sequence looking like a ransom note.

Pure numpy on frames decoded by ffmpeg. No cv2, so a broken OpenCV install
cannot take the studio down with it.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, asdict, field
from pathlib import Path

import numpy as np

_DIMS = re.compile(r"[,\s](\d{2,5})x(\d{2,5})(?=[\s,\[]|$)")
_FPS = re.compile(r"(\d+(?:\.\d+)?)\s+fps")

PROBE_W = 192
PROBE_H = 108


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def probe(path: str | Path) -> dict:
    """Width, height, fps, duration. Parsed from ffmpeg's banner."""
    out = subprocess.run([ffmpeg(), "-nostdin", "-i", str(path)],
                         capture_output=True, text=True).stderr
    meta = {"width": 0, "height": 0, "fps": 30.0, "duration": 0.0}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            h, m, s = line.split()[1].rstrip(",").split(":")
            meta["duration"] = int(h) * 3600 + int(m) * 60 + float(s)
        elif "Video:" in line:
            m = _DIMS.search(line)
            if m:
                meta["width"], meta["height"] = int(m.group(1)), int(m.group(2))
            f = _FPS.search(line)
            if f:
                meta["fps"] = float(f.group(1))
    return meta


def _stream_stats(path: str | Path, max_seconds: float | None):
    """Decode the probe stream in batches and return per-frame statistics.

    A 10-minute source is 17k frames; holding them as float32 is 4 GB. Nothing
    here needs the pixels after it has measured them, so this streams.
    """
    cmd = [ffmpeg(), "-nostdin", "-v", "error"]
    if max_seconds:
        cmd += ["-t", f"{max_seconds:.3f}"]
    cmd += ["-i", str(path),
            "-vf", f"scale={PROBE_W}:{PROBE_H}:flags=area",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    frame_bytes = PROBE_W * PROBE_H * 3
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    bright, sat, sharp, diff, hdiff = [], [], [], [], []
    prev_grey = None
    prev_hist = None
    while True:
        buf = proc.stdout.read(frame_bytes * 64)
        if not buf:
            break
        n = len(buf) // frame_bytes
        batch = np.frombuffer(buf[: n * frame_bytes], dtype=np.uint8)
        batch = batch.reshape(n, PROBE_H, PROBE_W, 3).astype(np.float32)
        grey = batch.mean(axis=3)
        for i in range(n):
            g = grey[i]
            bright.append(float(g.mean()))
            mx, mn = batch[i].max(axis=2), batch[i].min(axis=2)
            sat.append(float(((mx - mn) / np.maximum(mx, 1e-3)).mean()))
            lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1]
                   + g[1:-1, :-2] + g[1:-1, 2:])
            sharp.append(float(lap.var()))
            h = np.histogram(g, bins=24, range=(0, 255))[0].astype(np.float32)
            h /= max(h.sum(), 1.0)
            if prev_grey is None:
                diff.append(0.0)
                hdiff.append(0.0)
            else:
                diff.append(float(np.abs(g - prev_grey).mean()))
                hdiff.append(float(np.abs(h - prev_hist).sum()))
            prev_grey, prev_hist = g.copy(), h
    proc.stdout.close()
    proc.wait()
    return (np.array(bright, dtype=np.float32), np.array(sat, dtype=np.float32),
            np.array(sharp, dtype=np.float32), np.array(diff, dtype=np.float32),
            np.array(hdiff, dtype=np.float32))


@dataclass
class Shot:
    index: int
    src_in: float
    src_out: float
    motion: float = 0.0
    sharp: float = 0.0
    bright: float = 0.0
    sat: float = 0.0
    colour: str = "neutral"
    # coarse brightness across the shot (N buckets). A 6s shot can be bright in
    # the middle and near-black at the head; one mean would put a hold in the
    # dark part of a good shot and call it a bad shot.
    profile: list[float] = field(default_factory=list)

    @property
    def dur(self) -> float:
        return self.src_out - self.src_in

    def as_dict(self):
        d = asdict(self)
        d["dur"] = round(self.dur, 3)
        d["src_in"] = round(self.src_in, 3)
        d["src_out"] = round(self.src_out, 3)
        for k in ("motion", "sharp", "bright", "sat"):
            d[k] = round(float(d[k]), 3)
        d["profile"] = [round(float(v), 1) for v in self.profile]
        return d


@dataclass
class Source:
    path: str
    width: int
    height: int
    fps: float
    duration: float
    shots: list[Shot]

    def as_dict(self):
        return {"path": self.path, "width": self.width, "height": self.height,
                "fps": round(self.fps, 3), "duration": round(self.duration, 3),
                "shots": [s.as_dict() for s in self.shots]}


def _cuts(diff: np.ndarray, hdiff: np.ndarray, fps: float,
          min_shot: float = 0.33) -> list[int]:
    """Boundary frame indices. Needs BOTH a big frame difference and a big
    histogram change: a whip-pan moves a lot of pixels but keeps the palette,
    and that is not a cut."""
    n = len(diff)
    if n < 3:
        return [0]
    d_thr = max(float(np.percentile(diff, 95)), 6.0)
    h_thr = max(float(np.percentile(hdiff, 95)), 0.20)
    cand = [i for i in range(1, n - 1) if diff[i] > d_thr and hdiff[i] > h_thr]
    cuts = [0]
    min_frames = max(1, int(min_shot * fps))
    for c in cand:
        if c - cuts[-1] >= min_frames:
            cuts.append(c)
    if n - 1 - cuts[-1] >= max(2, min_frames // 2):
        cuts.append(n - 1)
    return cuts


PROFILE_N = 12

# A pack is cut from a longer film, so some shots open or close on the black
# frame the edit before them faded through. Cutting into one of those puts a
# single dead frame on a beat — half a frame of nothing, then a slam, which reads
# as a glitch rather than a cut. A shot is trimmed past them when it is measured.
DEAD_LUMA = 20.0      # a frame this dark has no picture in it
DEAD_FLAT = 12.0      # ...and if it is flat too, it is a fade, not a dark shot
DEAD_MAX = 0.6        # do not eat more than this much of a shot's head or tail


def _trim_dead(a: int, b: int, bright: np.ndarray, sharp: np.ndarray,
               fps: float) -> tuple[int, int]:
    """Advance a shot past leading/trailing black frames.

    Only trims: indices stay put, so a direction sheet that names shot 63 keeps
    meaning the same shot after the fix. If the whole shot is black the trim is
    abandoned rather than leaving a zero-length shot behind.
    """
    cap = max(1, int(DEAD_MAX * fps))

    def dead(i: int) -> bool:
        return bool(bright[i] < DEAD_LUMA and sharp[i] < DEAD_FLAT)

    a0, b0 = a, b
    moved = 0
    while a < b - 1 and moved < cap and dead(a):
        a += 1
        moved += 1
    moved = 0
    while b - 1 > a and moved < cap and dead(b - 1):
        b -= 1
        moved += 1
    if b - a < max(1, int(0.12 * fps)):      # the shot was black, not head-black
        return a0, b0
    return a, b


def _profile(bright: np.ndarray) -> list[float]:
    """Mean luma in N equal slices of a shot."""
    if len(bright) == 0:
        return []
    n = min(PROFILE_N, len(bright))
    edges = np.linspace(0, len(bright), n + 1).astype(int)
    return [float(bright[edges[i]:max(edges[i] + 1, edges[i + 1])].mean())
            for i in range(n)]


def analyse(path: str | Path, max_seconds: float | None = None) -> Source:
    meta = probe(path)
    bright, sat, sharp, diff, hdiff = _stream_stats(path, max_seconds)
    fps = meta["fps"] or 30.0
    n = len(bright)
    duration = n / fps if n else meta["duration"]
    bounds = _cuts(diff, hdiff, fps)

    def colour_of(a: int, b: int) -> str:
        s_ = float(np.clip(sat[a:b].mean(), 0, 1))
        if s_ < 0.12:
            return "mono"
        # warm/cool from the ratio of the R and B means over the shot
        return "warm" if s_ > 0.2 else "neutral"

    shots: list[Shot] = []
    for i, a in enumerate(bounds):
        b = bounds[i + 1] if i + 1 < len(bounds) else n
        if b <= a:
            continue
        a, b = _trim_dead(a, b, bright, sharp, fps)
        shots.append(Shot(
            index=len(shots), src_in=a / fps, src_out=b / fps,
            motion=float(diff[a + 1:b].mean() / 255.0) if b - a > 1 else 0.0,
            sharp=float(np.median(sharp[a:b])),
            bright=float(np.median(bright[a:b])),
            sat=float(np.clip(sat[a:b].mean(), 0, 1)),
            colour=colour_of(a, b),
            profile=_profile(bright[a:b])))
    return Source(path=str(path), width=meta["width"], height=meta["height"],
                  fps=fps, duration=duration, shots=shots)


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="shot list + per-shot stats")
    ap.add_argument("source")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-seconds", type=float, default=None)
    a = ap.parse_args(argv)
    src = analyse(a.source, a.max_seconds)
    if a.out:
        Path(a.out).write_text(json.dumps(src.as_dict(), indent=1) + "\n")
    print(f"{src.path}: {src.width}x{src.height} {src.fps:.2f}fps "
          f"{src.duration:.2f}s -> {len(src.shots)} shots")
    for s in src.shots[:40]:
        print(f"  {s.index:3d} {s.src_in:7.2f}-{s.src_out:7.2f} "
              f"({s.dur:5.2f}s) motion {s.motion:.3f} sharp {s.sharp:7.1f} "
              f"bright {s.bright:5.1f} {s.colour}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
