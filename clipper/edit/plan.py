"""Turn a chosen moment into an edit plan: where to cut, how to move the camera.

A plan is plain JSON - a list of shots with in/out points, a camera move each,
and the caption window that belongs to them. It is written before anything is
rendered, so the edit can be inspected, hand-edited and re-rendered without
touching the footage.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .. import config
from ..util import log

DEFAULT_SHOT_LEN = 2.0          # when the style profile does not say
MIN_SHOT_LEN = 0.7              # never create a shot shorter than this
JITTER = 0.15                   # ± of the target shot length, for rhythm
DEFAULT_TRANSITION_LEN = 0.25   # when the style profile does not say
MAX_TRANSITION_LEN = 0.8        # longer than this stops reading as a transition

# Every blend ffmpeg's xfade filter can do, so a profile can name one directly
# (wipeleft, circleopen, zoomin, squeezeh, pixelize ...). "cut" is not a blend:
# it is the plain concat path, and the default.
FFMPEG_TRANSITIONS = (
    "fade", "wipeleft", "wiperight", "wipeup", "wipedown", "slideleft", "slideright",
    "slideup", "slidedown", "circlecrop", "rectcrop", "distance", "fadeblack",
    "fadewhite", "radial", "smoothleft", "smoothright", "smoothup", "smoothdown",
    "circleopen", "circleclose", "vertopen", "vertclose", "horzopen", "horzclose",
    "dissolve", "pixelize", "diagtl", "diagtr", "diagbl", "diagbr", "hlslice",
    "hrslice", "vuslice", "vdslice", "hblur", "fadegrays", "wipetl", "wipetr",
    "wipebl", "wipebr", "squeezeh", "squeezev", "zoomin", "fadefast", "fadeslow",
    "hlwind", "hrwind", "vuwind", "vdwind", "coverleft", "coverright", "coverup",
    "coverdown", "revealleft", "revealright", "revealup", "revealdown",
)

# What people call these in an editor, mapped to what ffmpeg calls them. "fade"
# is a crossfade (overlap dissolve); "fade_black" dips through black, "fade_white"
# flashes through white.
TRANSITION_ALIASES = {
    "": "cut", "cut": "cut", "hard_cut": "cut", "hardcut": "cut", "none": "cut",
    "fade": "fade", "crossfade": "fade", "cross_fade": "fade", "mix": "fade",
    "dissolve": "fade",
    "fade_black": "fade_black", "fadeblack": "fade_black", "fade_to_black": "fade_black",
    "dip": "fade_black", "dip_to_black": "fade_black", "black": "fade_black",
    "fade_white": "fade_white", "fadewhite": "fade_white", "flash": "fade_white",
    # editors say "dissolve" for a crossfade, so ffmpeg's own noisy dissolve needs
    # its own way in
    "noisy_dissolve": "dissolve", "noise_dissolve": "dissolve",
    "fade_grays": "fadegrays", "fadegrays": "fadegrays",
}
SUPPORTED_TRANSITIONS = ("cut",) + FFMPEG_TRANSITIONS


def resolve_transition(value) -> str | None:
    """A profile's transition word -> a canonical name, or None if we cannot do it."""
    name = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if name in TRANSITION_ALIASES:
        return TRANSITION_ALIASES[name]
    return name if name in FFMPEG_TRANSITIONS else None


def _seeded_lengths(clip_key: str, total: float, target: float, *, jitter: bool = True) -> list[float]:
    """Split `total` seconds into shot lengths around `target`.

    Real edits are not metronomic, so the lengths wander a little - but
    deterministically, keyed on the clip, so a plan can be re-rendered and come
    out identical.
    """
    target = max(MIN_SHOT_LEN, float(target))
    if total <= target:
        return [round(total, 3)]
    rng = hashlib.sha256(clip_key.encode()).digest()
    lengths: list[float] = []
    remaining = total
    i = 0
    while remaining > target * 0.75:
        noise = 0.0
        if jitter:
            byte = rng[i % len(rng)]
            noise = (byte / 255.0 * 2.0 - 1.0) * JITTER * target
        length = min(max(MIN_SHOT_LEN, target + noise), remaining)
        lengths.append(round(length, 3))
        remaining = round(remaining - length, 3)
        i += 1
    if remaining > 0.05:
        if lengths and lengths[-1] + remaining >= MIN_SHOT_LEN:
            lengths[-1] = round(lengths[-1] + remaining, 3)
        elif lengths and lengths[-1] + remaining < MIN_SHOT_LEN and len(lengths) > 1:
            merged = round(lengths[-1] + remaining, 3)
            lengths.pop()
            lengths[-1] = round(lengths[-1] + merged, 3)
        else:
            lengths.append(round(remaining, 3))
    return lengths


def _word_gaps(words: list, start: float, end: float, *, min_gap: float = 0.16) -> list[float]:
    """Times inside the window where nobody is talking."""
    inside = [w for w in words if start <= float(w.start) and float(w.end) <= end]
    gaps: list[float] = []
    for a, b in zip(inside, inside[1:]):
        gap = float(b.start) - float(a.end)
        if gap >= min_gap:
            gaps.append((float(a.end) + float(b.start)) / 2.0)
    return gaps


def _snap(t: float, gaps: list[float], curve: dict | None, *, window: float = 0.5) -> float:
    """Move a cut to the nearest place a person would cut."""
    best, best_gap = None, None
    for gap in gaps:
        distance = abs(gap - t)
        if distance <= window and (best_gap is None or distance < best_gap):
            best, best_gap = gap, distance
    if best is not None:
        return round(best, 3)
    if curve is not None:
        from ..select.energy import snap_to_pause

        return snap_to_pause(t, curve, window=window)
    return round(t, 3)


def camera_moves(style: dict, shot_durations: list[float]) -> list[dict]:
    """One camera move per shot, following the profile's zoom section."""
    zoom = (style or {}).get("zoom") or {}
    dominant = (zoom.get("dominant") or "static").lower()
    scale = float(zoom.get("punch_in_scale") or 1.0)
    over = float(zoom.get("punch_in_duration") or 0.25)
    moves: list[dict] = []
    for duration in shot_durations:
        if dominant in ("static", "none") or scale <= 1.001:
            moves.append({"type": "static"})
        elif dominant == "punch_in":
            moves.append({"type": "punch_in", "from": 1.0, "to": round(scale, 4),
                          "over": round(min(over, duration), 3)})
        elif dominant == "pull_out":
            moves.append({"type": "pull_out", "from": round(scale, 4), "to": 1.0,
                          "over": round(min(max(over, duration), duration), 3)})
        elif dominant == "slow_push":
            moves.append({"type": "slow_push", "from": 1.0, "to": round(scale, 4),
                          "over": round(duration, 3)})
        else:                       # "mixed" and anything unknown: play it safe
            moves.append({"type": "static"})
    return moves


def _timeline(shots: list[dict]) -> float:
    """Stamp each shot with where it lands in the rendered clip, and return its length.

    A blend has to show two moments at once, so it costs one blend's worth of
    time: with a 0.3 s dissolve every 2 s, a 16.35 s moment renders as 14.25 s.
    Each shot keeps its own material; only the *output* timeline is shorter, and
    `out_start`/`out_end` say exactly where every shot lands, so captions and
    anything else downstream can map source time -> clip time without guessing.
    """
    cursor = 0.0
    for i, shot in enumerate(shots):
        if i:
            blend = float(shot.get("transition_duration") or 0.0) \
                if str(shot.get("transition") or "cut") != "cut" else 0.0
            cursor = round(cursor - blend, 3)
        shot["out_start"] = round(cursor, 3)
        cursor = round(cursor + float(shot["duration"]), 3)
        shot["out_end"] = cursor
    return round(cursor, 3)


def _transition_length(value) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = DEFAULT_TRANSITION_LEN
    return round(min(max(seconds, 0.08), MAX_TRANSITION_LEN), 3)


def build_plan(candidate: dict, *, style: dict | None = None, words: list | None = None,
               curve: dict | None = None, platform: str = "tiktok",
               shot_len: float | None = None, fps: int = 30,
               campaign: str | None = None) -> dict:
    """A complete, renderable plan for one candidate moment."""
    style = style or {}
    preset = config.PLATFORMS.get(platform, config.PLATFORMS[config.DEFAULT_PLATFORM])
    width, height = preset.get("width", 1080), preset.get("height", 1920)

    start, end = float(candidate["start"]), float(candidate["end"])
    total = round(end - start, 3)
    pacing = style.get("pacing") or {}
    target = float(shot_len or pacing.get("avg_shot_len") or DEFAULT_SHOT_LEN)
    transitions = style.get("transitions") or {}
    requested = transitions.get("in") or "cut"
    notes: list[str] = []
    resolved = resolve_transition(requested)
    if resolved is None:
        notes.append(f"transition '{requested}' is not one ffmpeg can blend, using a hard cut")
    transition = resolved or "cut"
    transition_len = _transition_length(transitions.get("duration")) if transition != "cut" else 0.0
    if not pacing.get("avg_shot_len"):
        notes.append(f"the style profile has no pacing, cutting every {target:.1f}s")
    if (style.get("zoom") or {}).get("dominant") in (None, "mixed"):
        notes.append("the style profile does not have a clear camera move, holding still")

    clip_key = f"{candidate.get('source_name') or candidate.get('file', 'clip')}:{start:.2f}"
    lengths = _seeded_lengths(clip_key, total, target, jitter=shot_len is None)

    gaps = _word_gaps(words, start, end) if words else []
    if not gaps and words:
        notes.append("no pauses between words in this window, cuts land on word boundaries")
    if not words:
        notes.append("no transcript for this clip, cuts snap to audio silences only")

    # boundaries first, then snap each internal cut, then build the shots: doing
    # it in this order keeps the sequence ordered and non-overlapping no matter
    # where the snapping lands
    boundaries = [start]
    for length in lengths:
        boundaries.append(min(end, round(boundaries[-1] + length, 3)))
    boundaries[-1] = end
    moves = camera_moves(style, lengths)
    for i in range(1, len(boundaries) - 1):
        lower = boundaries[i - 1] + MIN_SHOT_LEN
        upper = boundaries[i + 1] - MIN_SHOT_LEN
        if lower >= upper:
            continue
        snapped = _snap(boundaries[i], gaps, curve)
        boundaries[i] = round(min(max(snapped, lower), upper), 3)

    if transition != "cut":
        # a blend eats into both sides of a cut, so it has to fit the shortest shot
        shortest = min(round(b - a, 3) for a, b in zip(boundaries, boundaries[1:]))
        if transition_len > shortest * 0.5:
            transition_len = round(max(0.08, shortest * 0.5), 3)
            notes.append(f"blend shortened to {transition_len:.2f}s to fit the shortest shot")

    shots: list[dict] = []
    for i, (shot_start, shot_end) in enumerate(zip(boundaries, boundaries[1:]), start=1):
        shots.append({
            "index": i,
            "start": round(float(shot_start), 3),
            "end": round(float(shot_end), 3),
            "duration": round(float(shot_end - shot_start), 3),
            "zoom": moves[i - 1] if i - 1 < len(moves) else {"type": "static"},
            "transition": transition if i > 1 else "cut",
            "transition_duration": transition_len if i > 1 else 0.0,
            "out_start": 0.0, "out_end": 0.0,       # filled in by _timeline below
        })
    out_duration = _timeline(shots)

    shortening = round(total - out_duration, 3)
    if shortening > 0.05:
        notes.append(f"{len(shots) - 1} blend(s) overlap the shots, so the clip comes out "
                     f"{shortening:.2f}s shorter than the {total:.2f}s moment")

    caption_words = [w for w in (words or [])
                     if float(w.start) >= start - 0.01 and float(w.end) <= end + 0.01]
    plan = {
        "version": 1,
        "campaign": campaign,
        "clip": {
            "id": candidate.get("id"),
            "source": str(candidate.get("file") or candidate.get("source") or ""),
            "start": round(start, 3), "end": round(end, 3),
            "window": [round(start, 3), round(end, 3)],
            "duration": out_duration,               # what the rendered clip will measure
            "source_duration": total,               # how much footage it draws on
            "blend_shortening": shortening,
            "score": candidate.get("score"),
            "reasons": list(candidate.get("reasons") or []),
        },
        "target": {"platform": platform, "width": width, "height": height, "fps": fps},
        "style": {
            "path": style.get("path"),
            "avg_shot_len": target,
            "zoom": (style.get("zoom") or {}).get("dominant"),
            "transition": transition,
            "transition_duration": transition_len if transition != "cut" else 0.0,
        },
        "shots": shots,
        "captions": {
            "words": len(caption_words),
            "window": [round(float(caption_words[0].start), 3),
                       round(float(caption_words[-1].end), 3)] if caption_words else None,
        },
        "notes": notes,
    }
    return plan


def load_words(path) -> list:
    if not path:
        return []
    from ..select.pipeline import load_transcript

    return load_transcript(path) or []


def summarise(plan: dict) -> str:
    clip = plan["clip"]
    blend = plan["style"]["transition"]
    if blend != "cut" and plan["style"].get("transition_duration"):
        blend = f"{blend} {plan['style']['transition_duration']:.2f}s"
    return (f"{clip['id']} · {len(plan['shots'])} shots · "
            f"{clip['start']:.2f}-{clip['end']:.2f}s ({clip['duration']:.1f}s) · "
            f"{plan['style']['zoom'] or 'static'} · {blend}")
