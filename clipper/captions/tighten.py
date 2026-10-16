"""Tighten a clip by cutting dead air, and carry every timestamp through.

Talking-head podcasts breathe between sentences; in a 40-second short a
0.7-second pause is a viewer reaching for the next video. The tighten pass
finds the pauses the word timings already know about, removes most of each
one from the picture and the sound together, and remaps the words (via the
shot-plan remapper - kept segments are just "shots") so captions, camera
punches, whooshes and inserts all stay in sync without a second ASR pass.

What it never does: cut inside a word, cut the first or last word away, or
remove a pause shorter than the threshold - tightening is pacing, not
butchery. Defaults: gaps >= 0.60s shrink to ~0.22s of kept breath.
"""
from __future__ import annotations

from pathlib import Path

from ..ffmpeg import ffmpeg_exe, run

DEFAULT_MIN_GAP = 0.60
TAIL = 0.14            # breath kept after a word before the cut
HEAD = 0.08            # breath kept before the next word after the cut


def _times(word) -> tuple[float, float]:
    if isinstance(word, dict):
        return float(word.get("start") or 0.0), float(word.get("end") or 0.0)
    return float(word.start or 0.0), float(word.end or 0.0)


def dead_air_cuts(words, *, min_gap: float = DEFAULT_MIN_GAP,
                  tail: float = TAIL, head: float = HEAD) -> list[tuple[float, float]]:
    """[(cut_start, cut_end), ...] - the spans to REMOVE, in clip time."""
    timed = sorted((_times(w) for w in words))
    cuts: list[tuple[float, float]] = []
    for (_, a_end), (b_start, _) in zip(timed, timed[1:]):
        if b_start - a_end >= float(min_gap):
            cs, ce = a_end + tail, b_start - head
            if ce - cs >= 0.10:                      # worth removing at all
                cuts.append((round(cs, 3), round(ce, 3)))
    return cuts


def kept_segments(cuts: list[tuple[float, float]],
                  total: float) -> list[tuple[float, float]]:
    """The complement of `cuts` over [0, total] - what stays in the clip."""
    segs: list[tuple[float, float]] = []
    cursor = 0.0
    for cs, ce in cuts:
        if cs > cursor:
            segs.append((round(cursor, 3), round(cs, 3)))
        cursor = max(cursor, ce)
    if total > cursor:
        segs.append((round(cursor, 3), round(float(total), 3)))
    return [(s, e) for s, e in segs if e - s >= 0.05]


def kept_duration(segments: list[tuple[float, float]]) -> float:
    return round(sum(e - s for s, e in segments), 3)


def map_time(t: float, cuts: list[tuple[float, float]]) -> float:
    """Carry one timestamp (whoosh, insert start) through the cuts."""
    t = float(t)
    removed = 0.0
    for cs, ce in cuts:
        if t >= ce:
            removed += ce - cs
        elif t > cs:                                 # inside the cut: land on its start
            return round(cs - removed, 3)
        else:
            break
    return round(t - removed, 3)


def assemble(src: str | Path, segments: list[tuple[float, float]],
             out: str | Path, *, offset: float = 0.0) -> Path:
    """Concatenate the kept segments of `src` into `out` (picture + sound)."""
    if not segments:
        raise ValueError("tighten: no segments to keep")
    off = float(offset or 0.0)
    parts: list[str] = []
    labels: list[str] = []
    for i, (s, e) in enumerate(segments):
        parts.append(f"[0:v]trim=start={s + off:.3f}:end={e + off:.3f},"
                     f"setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim=start={s + off:.3f}:end={e + off:.3f},"
                     f"asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(segments)}:v=1:a=1[outv][outa]")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    args = [ffmpeg_exe(), "-y", "-nostdin", "-v", "error", "-i", str(src),
            "-filter_complex", ";".join(parts),
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-ar", "48000", str(out)]
    proc = run(args, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"tighten assemble failed: {proc.stderr[-400:]}")
    return out
