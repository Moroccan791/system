#!/usr/bin/env python3
"""Speed ramps, applied to the finished clip so nothing drifts.

A ramp inside the frame loop would need the audio resampled in lockstep and
every caption re-timed. Applying it to the *finished* file avoids all of that:
the picture and its burned-in captions slow together, and `atempo` slows the
mix by the same factor, so sync is preserved by construction.

    retime.ramp(video, out, [(t0, t1, 0.92)])   # 8% slower between t0 and t1

Only small factors are allowed on purpose. Past ~15% a voice stops sounding
slowed and starts sounding wrong, and a viewer notices that far sooner than
they notice the ramp.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TOLERANCE = 0.15          # refuse anything outside 0.85 - 1.15


def ffmpeg() -> str:
    return subprocess.run(
        [sys.executable, "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
        capture_output=True, text=True).stdout.strip()


def plan(segments: list[tuple[float, float, float]], duration: float
         ) -> tuple[list[tuple[float, float, float]], float]:
    """Clamp and order the ramps, and report the new total duration.

    segments: [(start, end, factor)]. Returns the cleaned list and the duration
    after ramping, which is what the caller needs to re-time the manifest.
    """
    clean: list[tuple[float, float, float]] = []
    for a, b, f in sorted(segments):
        f = min(1 + TOLERANCE, max(1 - TOLERANCE, float(f)))
        a, b = max(0.0, float(a)), min(float(duration), float(b))
        if b - a < 0.2:
            continue
        # Overlapping ramps are dropped rather than trimmed: two different
        # speeds meeting at an arbitrary point is a visible jolt.
        if clean and a < clean[-1][1]:
            continue
        if b <= a:
            continue
        clean.append((round(a, 3), round(b, 3), round(f, 4)))
    out_dur = float(duration)
    for a, b, f in clean:
        out_dur += (b - a) * (1.0 / f - 1.0)
    return clean, round(out_dur, 3)


def _graph(clean: list[tuple[float, float, float]], duration: float) -> str:
    """trim + setpts + atempo per piece, then concat."""
    pieces: list[tuple[float, float, float]] = []
    cursor = 0.0
    for a, b, f in clean:
        if a > cursor:
            pieces.append((cursor, a, 1.0))
        pieces.append((a, b, f))
        cursor = b
    if cursor < duration:
        pieces.append((cursor, duration, 1.0))

    parts, labels = [], []
    for i, (a, b, f) in enumerate(pieces):
        parts.append(
            f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=(PTS-STARTPTS)/{f:.4f}[v{i}]")
        parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
                     f"atempo={f:.4f}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    parts.append("".join(labels) + f"concat=n={len(pieces)}:v=1:a=1[v][a]")
    return ";".join(parts)


def ramp(video: Path, out: Path, segments: list[tuple[float, float, float]],
         duration: float | None = None) -> tuple[Path, float]:
    """Write `out` with the ramps applied. Returns (path, new duration)."""
    if duration is None:
        duration = _duration(video)
    clean, new_duration = plan(segments, duration)
    if not clean:
        if out != video:
            subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                            "-i", str(video), "-c", "copy", str(out)], check=True)
        return out, duration
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(video), "-filter_complex", _graph(clean, duration),
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "17",
                    "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    str(out)], check=True)
    return out, new_duration


def _duration(path: Path) -> float:
    ff = ffmpeg()
    res = subprocess.run([ff, "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True)
    for line in res.stderr.splitlines():
        if "Duration:" in line:
            hms = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = hms.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def map_time(t: float, clean: list[tuple[float, float, float]]) -> float:
    """Original time -> post-ramp time, for the manifest the gate reads."""
    shift = 0.0
    for a, b, f in clean:
        if t < a:
            return t + shift
        if t < b:
            return a + shift + (t - a) / f
        shift += (b - a) * (1.0 / f - 1.0)
    return t + shift
