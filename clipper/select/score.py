"""Turning scored sentences and loud stretches into candidate clip windows.

Two paths, one output shape:

* with a transcript - sentences are scored on their text and on the audio under
  them, then grown into windows that respect the target length
* without one - loud stretches are the seeds, padded out to the target length

Both end by snapping the edges to a quiet moment so a clip does not start or end
mid-word, which is the difference between a clip and a chop.
"""
from __future__ import annotations

import numpy as np

from . import energy as energy_mod

# what "one clip" means per platform (seconds) - short-form platforms reward
# complete thoughts, so this is a range, not a fixed number
TARGET_LENGTHS: dict[str, tuple[float, float]] = {
    "tiktok": (15.0, 45.0),
    "reels": (15.0, 60.0),
    "shorts": (15.0, 60.0),
}
TEXT_WEIGHT = 0.62          # text vs audio when a transcript exists
MIN_UNIT_QUALITY = 0.30     # a neighbouring sentence this weak is not absorbed
# A clip may end up shorter than the target when that is what it takes to keep a
# good moment separate from its neighbour - but never shorter than this.
MIN_FLOOR_RATIO = 0.7
HARD_FLOOR_SECONDS = 6.0


def length_floor(min_seconds: float) -> float:
    return max(HARD_FLOOR_SECONDS, min_seconds * MIN_FLOOR_RATIO)


def score_units(units: list[dict], curve: dict, hot_spots: list[dict] | None = None) -> list[dict]:
    """Attach text, audio and combined scores to each sentence unit."""
    from .hooks import score_text

    spots = hot_spots if hot_spots is not None else energy_mod.hot_spots(curve)
    scored: list[dict] = []
    for unit in units:
        text_score, reasons = score_text(unit["text"])
        audio_score = energy_mod.mean_activity(curve, unit["start"], unit["end"])
        covers = [(i, s) for i, s in enumerate(spots)
                  if s["start"] < unit["end"] and s["end"] > unit["start"]]
        burst = bool(covers)
        burst_id = covers[0][0] if covers else None
        combined = TEXT_WEIGHT * text_score + (1 - TEXT_WEIGHT) * audio_score
        if burst:
            combined = min(1.0, combined + 0.08)
            reasons = reasons + ["a loud reaction inside it"]
        scored.append({**unit, "burst_id": burst_id, "text_score": round(text_score, 3),
                       "audio_score": round(float(audio_score), 3),
                       "score": round(float(combined), 3),
                       "reasons": reasons, "has_burst": burst})
    return scored


def _absorbable(unit: dict) -> bool:
    return unit["score"] >= MIN_UNIT_QUALITY


def build_candidates(scored: list[dict], curve: dict, *, min_seconds: float, max_seconds: float,
                     top: int = 5, spots: list[dict] | None = None) -> list[dict]:
    """Grow the best sentences into clip-sized windows, then pick non-overlapping."""
    if not scored:
        return []
    if spots is None:
        spots = energy_mod.hot_spots(curve)

    seeds = sorted(scored, key=lambda u: -u["score"])[: max(top * 4, 12)]
    windows: list[dict] = []
    for seed in seeds:
        first_i = last_i = scored.index(seed)
        duration = seed["end"] - seed["start"]

        # Grow outwards until the window is long enough to be a clip. Weak
        # neighbouring sentences are allowed in as context - that is what the
        # seed's own words need around them - but a sentence carrying its *own*
        # loud moment is never absorbed: two moments must not become one clip.
        while duration < min_seconds:
            options = []
            if first_i > 0:
                options.append(("prev", first_i - 1))
            if last_i + 1 < len(scored):
                options.append(("next", last_i + 1))
            options = [(side, i) for side, i in options
                       if scored[i]["burst_id"] in (None, seed["burst_id"])]
            options = [(side, i) for side, i in options
                       if _fits(scored, side, i, first_i, last_i, max_seconds)]
            if not options:
                break
            # on a tie keep going forwards: a clip usually continues a thought
            side, index = max(options, key=lambda si: (scored[si[1]]["score"], si[0] == "next"))
            if side == "prev":
                first_i = index
            else:
                last_i = index
            duration = scored[last_i]["end"] - scored[first_i]["start"]

        first, last = scored[first_i], scored[last_i]
        if duration > max_seconds:
            # trim the weaker end rather than drop the moment
            if first["score"] < last["score"]:
                first, first_i = last, last_i
            else:
                last, last_i = first, first_i
            duration = last["end"] - first["start"]

        start = energy_mod.snap_to_pause(first["start"], curve)
        end = energy_mod.snap_to_pause(last["end"], curve)
        if end - start < length_floor(min_seconds):
            start, end = first["start"], last["end"]
        trimmed = _trim_foreign_moments(start, end, spots, seed["burst_id"],
                                        length_floor(min_seconds), (seed["start"], seed["end"]))
        if trimmed is None:
            continue
        start, end = trimmed
        windows.append({
            "start": round(float(start), 3),
            "end": round(float(end), 3),
            "duration": round(float(end - start), 3),
            "score": round(float(seed["score"]), 3),
            "seed_start": seed["start"],
            "seed_end": seed["end"],
            "burst_id": seed["burst_id"],
            "burst_span": _burst_span(spots, seed["burst_id"]),
            "text": _window_text(scored, first, last),
            "reasons": list(seed["reasons"]),
            "signals": {"text": seed["text_score"], "audio": seed["audio_score"],
                        "burst": seed["has_burst"]},
        })

    return _select_non_overlapping(windows, top=top, min_seconds=min_seconds)


def build_from_energy(curve: dict, hot_spots: list[dict], *, min_seconds: float,
                      max_seconds: float, top: int = 5) -> list[dict]:
    """No transcript: the loud stretches are the moments."""
    windows: list[dict] = []
    order = sorted(range(len(hot_spots)), key=lambda i: -hot_spots[i]["peak_above_db"])
    for spot_id in order:
        spot = hot_spots[spot_id]
        length = min(max(spot["end"] - spot["start"], min_seconds), max_seconds)
        centre = (spot["start"] + spot["end"]) / 2.0
        start = max(0.0, centre - length / 2.0)
        end = min(curve["duration"], start + length)
        start = max(0.0, end - length)
        start = energy_mod.snap_to_pause(start, curve)
        end = energy_mod.snap_to_pause(end, curve)
        if end - start < length_floor(min_seconds):
            start, end = max(0.0, centre - length / 2.0), min(curve["duration"], centre + length / 2.0)
        trimmed = _trim_foreign_moments(start, end, hot_spots, spot_id,
                                        length_floor(min_seconds), (spot["start"], spot["end"]))
        if trimmed is None:
            continue
        start, end = trimmed
        strength = float(np.clip(spot["peak_above_db"] / 18.0, 0.0, 1.0))
        windows.append({
            "start": round(float(start), 3),
            "end": round(float(end), 3),
            "duration": round(float(end - start), 3),
            "score": round(strength, 3),
            "seed_start": spot["start"],
            "seed_end": spot["end"],
            "burst_id": spot_id,
            "burst_span": [float(spot["start"]), float(spot["end"])],
            "trimmed": False,
            "text": None,
            "reasons": [f"loud stretch at {spot['peak_time']:.1f}s "
                        f"({spot['peak_above_db']:+.1f} dB over the clip's own level)"],
            "signals": {"text": None, "audio": round(strength, 3), "burst": True},
        })
    return _select_non_overlapping(windows, top=top, min_seconds=min_seconds)


def _trim_foreign_moments(start: float, end: float, spots: list[dict], keep_id: int | None,
                          floor: float, keep_span: tuple[float, float]) -> tuple[float, float] | None:
    """Shrink a window so it holds exactly the one moment it was built for.

    Clips are built around a moment but grown for length, so they can swallow a
    neighbouring moment. Two moments deserve two clips - this pulls back to the
    edge of the intruding one, as long as the clip stays long enough and the
    moment it belongs to stays inside.
    """
    if keep_id is None:
        return start, end
    changed = True
    while changed:
        changed = False
        for index, spot in enumerate(spots):
            if index == keep_id or spot["end"] <= start or spot["start"] >= end:
                continue
            if spot["start"] - start >= floor:
                end = min(end, float(spot["start"]))
            elif end - spot["end"] >= floor:
                start = max(start, float(spot["end"]))
            else:
                return None
            changed = True
            if keep_span[0] < start - 1e-6 or keep_span[1] > end + 1e-6:
                return None
    return start, end


def _burst_span(spots: list[dict], burst_id: int | None) -> list[float] | None:
    if burst_id is None or burst_id >= len(spots):
        return None
    spot = spots[burst_id]
    return [float(spot["start"]), float(spot["end"])]


def _fits(scored: list[dict], side: str, index: int, first_i: int, last_i: int,
          max_seconds: float) -> bool:
    """Would absorbing this neighbour keep the window inside the target length?"""
    if side == "prev":
        return scored[last_i]["end"] - scored[index]["start"] <= max_seconds
    return scored[index]["end"] - scored[first_i]["start"] <= max_seconds


def _span(scored: list[dict], first: dict, last: dict) -> list[dict]:
    return scored[scored.index(first): scored.index(last) + 1]


def _window_text(scored: list[dict], first: dict, last: dict) -> str:
    span = _span(scored, first, last)
    return " ".join(u["text"] for u in span)


def _select_non_overlapping(windows: list[dict], *, top: int, min_seconds: float) -> list[dict]:
    """Greedy by score, keeping as many moments as fit.

    When two candidates overlap, the weaker one is *trimmed* out of the way
    rather than thrown away - as long as the moment itself (its loud stretch, or
    its seed sentence) stays inside the shortened window. Two good moments a few
    seconds apart should give two clips, not one clip and one casualty.
    """
    floor = length_floor(min_seconds)
    ordered = sorted(windows, key=lambda w: (-w["score"], w["start"]))
    kept: list[dict] = []
    for window in ordered:
        if window["duration"] < floor:
            continue
        start, end = float(window["start"]), float(window["end"])
        for k in kept:
            if end <= k["start"] or start >= k["end"]:
                continue
            trimmed_end = min(end, float(k["start"]))
            trimmed_start = max(start, float(k["end"]))
            if trimmed_end - start >= floor and trimmed_end < end:
                end = trimmed_end
            elif end - trimmed_start >= floor and trimmed_start > start:
                start = trimmed_start
            else:
                start = end = None  # type: ignore[assignment]
                break
        if start is None or end is None:
            continue
        span = window.get("burst_span") or [window["seed_start"], window["seed_end"]]
        if span[0] < start - 1e-6 or span[1] > end + 1e-6:
            continue                      # the moment itself fell outside
        kept.append({**window, "start": round(start, 3), "end": round(end, 3),
                     "duration": round(end - start, 3), "trimmed": start != window["start"]
                     or end != window["end"]})
        if len(kept) >= top:
            break
    kept.sort(key=lambda w: w["start"])
    for i, window in enumerate(kept, start=1):
        window["id"] = f"#{i:02d}"
    return kept
