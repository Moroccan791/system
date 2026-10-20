#!/usr/bin/env python3
"""Cut the dead air, keep everything else where it was.

A raw podcast clip is full of air: a breath before a point, half a second
after a sentence, a pause while someone thinks. On a 40-second short that is
often four or five seconds of nothing - the exact seconds where a viewer's
thumb decides. Removing them is the cheapest retention there is, and it is
mechanical enough to trust a program with.

The hard part is not the cut, it is that *everything else* is timed against
the original: captions, punches, the bed, the manifest the gate reads. So this
module is one mapping - original time in, new time out - and every consumer
goes through it.

    keep_segments(words)  -> [(start, end), ...]   what survives
    Timeline(segments)    -> .map(t), .duration, .boundaries

Rules that keep it from sounding chopped:
    * keep a little air around each word (`pad`), or the cut clips consonants;
    * only remove gaps longer than `gap`, and never leave less than `keep`;
    * merge cuts that are close together instead of stuttering.
"""
from __future__ import annotations

import subprocess
from bisect import bisect_right
from pathlib import Path

DEFAULTS = {"gap": 0.55, "pad": 0.12, "keep": 0.28}


def keep_segments(words: list[dict], *, gap: float = DEFAULTS["gap"],
                  pad: float = DEFAULTS["pad"], keep_air: float = DEFAULTS["keep"],
                  duration: float | None = None) -> list[tuple[float, float]]:
    """Turn word timings into the stretches worth keeping.

    `words` is [{"at": start, "end": end}, ...] in source time. Returns
    ordered, non-overlapping (start, end) pairs. With no long gaps this
    returns the whole clip as one segment, which is the identity case and
    costs nothing downstream.
    """
    spans = sorted((float(w["at"]), float(w["end"])) for w in words
                   if float(w.get("end", 0)) > float(w.get("at", 0)))
    if not spans:
        return [(0.0, float(duration or 0.0))]
    if duration is None:
        duration = spans[-1][1]

    merged: list[list[float]] = []
    for s, e in spans:
        s, e = max(0.0, s - pad), min(duration, e + pad)
        if merged and s - merged[-1][1] <= gap:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    out: list[tuple[float, float]] = []
    for i, (s, e) in enumerate(merged):
        start = 0.0 if i == 0 else s
        end = duration if i == len(merged) - 1 else e
        if out and start - out[-1][1] < keep_air:
            out[-1] = (out[-1][0], end)          # too close: don't stutter
            continue
        out.append((round(start, 3), round(end, 3)))
    return out


class Timeline:
    """Maps source time to programme time."""

    def __init__(self, segments: list[tuple[float, float]]):
        self.segments = [(float(a), float(b)) for a, b in segments if b > a]
        if not self.segments:
            self.segments = [(0.0, 0.0)]
        self.starts = [a for a, _ in self.segments]
        self.news: list[float] = []
        acc = 0.0
        for a, b in self.segments:
            self.news.append(acc)
            acc += b - a
        self.duration = acc

    @property
    def is_identity(self) -> bool:
        return len(self.segments) == 1

    def map(self, t: float) -> float:
        """Source time -> programme time (clamped into the nearest kept part)."""
        if self.is_identity:
            a, b = self.segments[0]
            return max(0.0, min(t, b) - a)
        i = bisect_right(self.starts, t) - 1
        if i < 0:
            return 0.0
        a, b = self.segments[i]
        if t >= b:                                    # in a removed gap
            return self.news[i] + (b - a)
        return self.news[i] + (t - a)

    def kept(self, t: float) -> bool:
        return any(a <= t < b for a, b in self.segments)

    def preview(self) -> dict:
        removed = 0.0
        for (a, b), (c, d) in zip(self.segments, self.segments[1:]):
            removed += max(0.0, c - b)
        return {"segments": len(self.segments),
                "source": round(self.segments[-1][1] - self.segments[0][0], 2),
                "programme": round(self.duration, 2),
                "removed": round(removed, 2)}


def cut_audio(src: Path, segments: list[tuple[float, float]], out: Path,
              ffmpeg_bin: str = "ffmpeg", rate: int = 48000) -> Path:
    """Cut the source audio on exactly the same boundaries as the picture.

    atrim + concat rather than a stream copy: every join has to be sample
    accurate or the audio drifts against the tight picture by a frame per cut,
    which is audible on plosives long before it is visible.
    """
    parts, labels = [], []
    fade = 0.04          # equal-power 40 ms: a join at a silence should be
    for i, (a, b) in enumerate(segments):   # inaudible, not a click
        chain = f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS"
        if i:
            chain += f",afade=t=in:d={fade}"
        if i < len(segments) - 1:
            chain += f",afade=t=out:st={max(0.0, b - a - fade):.3f}:d={fade}"
        parts.append(chain + f"[a{i}]")
        labels.append(f"[a{i}]")
    graph = ";".join(parts) + ";" + "".join(labels) + \
        f"concat=n={len(segments)}:v=0:a=1[out]"
    subprocess.run([ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(src), "-filter_complex", graph,
                    "-map", "[out]", "-ar", str(rate), "-ac", "2",
                    "-c:a", "aac", "-b:a", "192k", str(out)], check=True)
    return out
