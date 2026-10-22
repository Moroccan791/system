"""Where the edit is allowed to stop.

The complaint this answers: the video ended while the vocal was still singing
"baby do it like you do". The cause was a hardcoded `--end 62.0` typed by hand,
which is a number chosen before anyone listened to the end of the track.

So the out-point is now measured:

    last vocal word ends at T   ->  the edit may not stop before T + tail
    snap that up to the next bar ->  the picture ends on a musical boundary

`out_point()` is pure and takes the measured last-vocal time, so the rule is
testable without a 4-minute ASR run. `vocals_end()` does the measuring.

An edit is allowed to end BEFORE the last word: that is a decision, and it is
made by passing an explicit out-point. It is never allowed to end in the MIDDLE
of the last word, which is what a hardcoded window does by accident.
"""

from __future__ import annotations

import math


def out_point(last_vocal: float | None, grid, tail: float = 1.2,
              ceiling: float | None = None) -> float:
    """The earliest bar line at or after the vocal finishes, plus a tail."""
    if last_vocal is None:
        return ceiling if ceiling is not None else 0.0
    want = last_vocal + tail
    bar = 4.0
    beats = grid.beats(want) if hasattr(grid, "beats") else want
    out = grid.t(math.ceil(beats / bar) * bar) if hasattr(grid, "t") else want
    if ceiling is not None:
        out = min(out, ceiling)
    return float(out)


def check_window(end: float, last_vocal: float | None, tail: float = 0.25) -> str | None:
    """Return a refusal message when the window cuts a word in half."""
    if last_vocal is None:
        return None
    if end < last_vocal + tail:
        return (f"the window ends at {end:.2f}s but the last vocal word runs to "
                f"{last_vocal:.2f}s — the edit would stop mid-word. Use "
                f"--end {last_vocal + tail:.2f} or later (the bar after it is "
                f"better), or cut the phrase out of the song first.")
    return None


def vocals_end(track: str, duration: float, search_from: float | None = None,
               cache: str | None = None) -> float | None:
    """When does the last sung word end? Absolute seconds in the track.

    Only the tail of the track is transcribed — the question is about the end,
    and ASR over 20 s costs a fraction of ASR over the whole file. Words with no
    duration (an ASR artefact on a cymbal) are ignored: a hallucinated word at
    67.9 s would push the picture past the end of the song.
    """
    from pathlib import Path

    from .lyrics import transcribe

    if cache and Path(cache).exists():
        import json

        return json.loads(Path(cache).read_text()).get("last_vocal")
    lo = max(0.0, (search_from if search_from is not None else duration) - 25.0)
    words = transcribe(track, lo, max(0.2, duration - lo),
                       tmp="/tmp/ends_asr.wav")
    # A word's `start` is as important as its `end`: ASR clips the final word of
    # a phrase ("do" at 64.73 came back with an end barely past its start), and
    # taking only `end` puts the out-point BEFORE the last word has been sung —
    # the exact bug this module exists to prevent.
    real = [w for w in words
            if w["end"] - w["start"] >= 0.06 and w["text"].strip()]
    last = (lo + max(max(w["end"], w["start"] + 0.30) for w in real)
            if real else None)
    if cache:
        import json

        Path(cache).write_text(json.dumps({"last_vocal": last, "from": lo},
                                          indent=1) + "\n")
    return last
