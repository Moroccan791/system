"""Map a source transcript onto an edited clip - captions without a second ASR pass.

Stage 3 normally transcribes whatever file it is given. When that file has just
been assembled by stage 4, transcribing it again is both slower and worse: an
energy aligner re-run on cut-up audio loses the thread, and the cues end up
drifting from the speech (measured on a real 20.5s clip: up to +0.9s by the end).

The plan already knows exactly which source seconds went where, so the honest
route is to take the timings the source transcript already has and carry them
through the cut:

    source word at 31.37s  ->  shot 7 covers source 30.72-31.92s
                           ->  shot 7 starts 7.35s into the clip
                           ->  cue at 8.00s

Words falling in a gap the edit dropped are skipped, words straddling a cut are
clamped to the shot, and the word's own duration is preserved.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..asr.base import Word
from ..util import jsonio


def load_plan(path: str | Path) -> dict:
    return jsonio.load(path, {}) or {}


def shot_offsets(plan: dict) -> list[tuple[dict, float]]:
    """[(shot, seconds_into_the_clip_where_it_starts), ...]"""
    out: list[tuple[dict, float]] = []
    offset = 0.0
    for shot in plan.get("shots", []):
        out.append((shot, round(offset, 4)))
        if shot.get("speed"):                       # a sped-up shot lasts less than it spans
            duration = (float(shot["end"]) - float(shot["start"])) / float(shot["speed"])
        else:
            duration = float(shot.get("duration") or (float(shot["end"]) - float(shot["start"])))
        offset += duration
    return out


def clip_duration(plan: dict) -> float:
    offsets = shot_offsets(plan)
    if not offsets:
        return 0.0
    shot, offset = offsets[-1]
    if shot.get("speed"):
        return round(offset + (float(shot["end"]) - float(shot["start"])) / float(shot["speed"]), 3)
    return round(offset + float(shot.get("duration") or (float(shot["end"]) - float(shot["start"]))), 3)


GRACE_SECONDS = 0.15          # how far past a shot's edge a word may still belong to it


def remap_words(plan: dict, words: list, *, keep_gaps: bool = False,
                grace: float = GRACE_SECONDS) -> list[Word]:
    """Source-timed words -> clip-timed words, following the plan's shots.

    A word belongs to the shot its middle falls in, give or take `grace`, which
    keeps a word sitting exactly on a cut from falling between two shots and
    disappearing. A word whose middle lands in source the edit threw away is
    dropped - it was never in the clip.
    """
    shots = shot_offsets(plan)
    if not shots:
        return list(words)

    def as_word(item) -> Word:
        return item if isinstance(item, Word) else Word.from_dict(item)

    timed = sorted((as_word(w) for w in words), key=lambda w: w.start)
    out: list[Word] = []
    index = 0
    for shot, offset in shots:
        s, e = float(shot["start"]), float(shot["end"])
        speed = float(shot.get("speed") or 1.0)
        while index < len(timed) and (timed[index].start + timed[index].end) / 2 < s - grace:
            index += 1
        cursor = index
        while cursor < len(timed):
            word = timed[cursor]
            if (word.start + word.end) / 2 >= e + grace:
                break
            local_start = max(word.start, s) - s
            local_end = min(word.end, e) - s
            if local_end <= local_start:            # spoken across the edge: clamp it inside
                local_end = local_start + min(max(word.duration, 0.06), max(e - s, 0.06))
            if speed != 1.0:
                local_start, local_end = local_start / speed, local_end / speed
            out.append(Word(
                text=word.text,
                start=round(offset + local_start, 3),
                end=round(offset + local_end, 3),
                prob=word.prob,
                kind=word.kind,
                source="remap",
            ))
            cursor += 1
        index = cursor                               # no word is claimed twice
    if keep_gaps:
        return out
    return [w for w in out if w.end > w.start]


def words_for_clip(plan_path: str | Path, transcript_path: str | Path) -> tuple[list[Word], dict]:
    """Convenience: two paths in, clip-timed words plus a small report out."""
    plan = load_plan(plan_path)
    data = jsonio.load(transcript_path, {}) or {}
    words = remap_words(plan, data.get("words") or [])
    return words, {
        "plan": str(plan_path),
        "transcript": str(transcript_path),
        "words_in": len(data.get("words") or []),
        "words_out": len(words),
        "shots": len(plan.get("shots", [])),
        "clip_duration": clip_duration(plan),
    }
