"""Does the audio actually say these words at this moment?

Every caption bug in this project had the same shape: the timings were produced
by ONE estimator and never checked by a second one. The aligner said "I need" at
11.3s; nothing in the pipeline ever asked the audio whether it agreed.

This module is that second opinion, and it is deliberately a different method
from the one that places the cards:

  * placement uses syllable onsets inside a phrase (fast, precise, ±50ms);
  * verification transcribes sliding windows of the finished mix and asks
    whether the words on screen are audible where they are on screen (±1.5s,
    too coarse to place, far too coarse to be fooled by a drum hit).

A line passes only if a window that CONTAINS the card's time also contains the
card's words. Sliding-window transcription is the cheap reliable part: the ASR
is bad at singing but it is not bad at sitting in the right three seconds.

Run it on the rendered file, not on the track — that is the audio the viewer
actually hears, effects and all.

    python -m studio.sync --video work/studio/x.mp4 --script work/studio/x.script.json
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from .lyrics import _sim

WINDOW = 3.0
HOP = 1.5
PASS = 0.42          # mean word similarity for "the audio says this"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z' ]+", "", s.lower()).strip()


def window_texts(video: str | Path, duration: float,
                 window: float = WINDOW, hop: float = HOP) -> list[dict]:
    """Transcribe overlapping windows of the mix. No VAD, no chunk merging.

    The provider's VAD is what went deaf through the middle of this track; run
    the model directly on a fixed window and it hears what is there.
    """
    import imageio_ffmpeg

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    out: list[dict] = []
    t = 0.0
    while t < duration - 0.5:
        end = min(t + window, duration)
        wav = Path("/tmp") / f"sync_{t:.1f}.wav"
        subprocess.run([ff, "-nostdin", "-y", "-ss", f"{t:.2f}", "-t", f"{end - t:.2f}",
                        "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                       capture_output=True)
        res = subprocess.run([sys.executable, "-m", "clipper.asr.moonshine_worker",
                              str(wav)], capture_output=True, text=True)
        text = ""
        for line in reversed(res.stdout.strip().splitlines()):
            try:
                text = json.loads(line).get("text", "") or ""
                break
            except Exception:
                continue
        out.append({"start": t, "end": end, "text": _norm(text)})
        if end >= duration:
            break
        t += hop
    return out


def match(words: list[str], window_text: str) -> float:
    """How much of `words` is in this transcript, in any order.

    Order is deliberately not required. A sung "for ya" comes back as the single
    token "fire", and "we're young tonight" as "we're only young tonight" — an
    order-preserving span match then scores a perfectly placed card at zero. The
    question here is "is this word in the room", not "is it in this seat".
    """
    if not words or not window_text:
        return 0.0
    toks = window_text.split()
    if not toks:
        return 0.0
    sims = sorted((max(_sim(w, t) for t in toks) for w in words), reverse=True)
    # Sung ASR drops and merges words: "we're young tonight" comes back "we got
    # tonight", so scoring every word would fail a perfectly placed line on the
    # one the recogniser lost. Judge the line by its strongest words.
    keep = max(1, int(round(len(sims) * 0.6)))
    return sum(sims[:keep]) / keep


def group_lines(cards: list[dict]) -> list[dict]:
    """Cards -> the lyric lines they came from, with the line's own time span.

    Verification happens at LINE level on purpose. A two-word card like "for ya"
    is not a reliable fingerprint — the recogniser returns it as "fire" — but the
    whole line is: "It's all about you" cannot be confused with "when the music
    makes you move". Lines are also the unit a viewer hears, so a line that sits
    right cannot produce the complaint this module exists to catch.
    """
    out: list[dict] = []
    for c in cards:
        ln = c.get("line", -1)
        if out and out[-1]["line"] == ln:
            out[-1]["end"] = c["end"]
            out[-1]["text"] += " " + c["text"]
        else:
            out.append({"line": ln, "start": c["start"], "end": c["end"],
                        "text": c["text"]})
    return out


def check(cards: list[dict], windows: list[dict], *, tol: float = 0.6) -> list[dict]:
    """Per-card verdict, decided by the verdict of the line the card belongs to.

    Three outcomes, because two would lie:

      PASS  the audio AT this time says these words, and nothing else says them
            better;
      WEAK  the words are not clearly audible here (the recogniser smears this
            line) but nothing contradicts the placement;
      FAIL  some other moment of the song matches the line better than the
            card's own moment does. That is the exact failure this module
            exists for, and it must block a render.
    """
    verdict = {}
    for ln in group_lines(cards):
        words = [w for w in _norm(ln["text"]).split() if w]
        inside, outside = 0.0, 0.0
        for w in windows:
            sc = match(words, w["text"])
            centre = (w["start"] + w["end"]) / 2.0
            if ln["start"] - tol <= centre <= ln["end"] + tol:
                inside = max(inside, sc)
            elif centre < ln["start"] - 2.5 or centre > ln["end"] + 2.5:
                outside = max(outside, sc)
        if inside >= PASS and inside >= outside - 0.15:
            state = "PASS"
        elif inside >= PASS * 0.7 and inside >= outside - 0.15:
            state = "WEAK"
        else:
            state = "FAIL"
        heard = ""
        if inside > 0:
            best = max(((match(words, w["text"]), w) for w in windows
                        if ln["start"] - tol <= (w["start"] + w["end"]) / 2.0 <= ln["end"] + tol),
                       key=lambda p: p[0])
            heard = best[1]["text"]
        verdict[ln["line"]] = (state, round(inside, 2), round(outside, 2), ln["text"],
                               (round(ln["start"], 2), round(ln["end"], 2)), heard)

    rows = []
    for c in cards:
        state, ins, outs, line, span, heard = verdict.get(
            c.get("line", -1), ("FAIL", 0.0, 0.0, "", (0, 0), ""))
        rows.append({"start": round(c["start"], 2), "text": c["text"], "line": line,
                     "state": state, "inside": ins, "outside": outs, "span": span,
                     "heard": heard})
    return rows


def report(rows: list[dict]) -> str:
    bad = [r for r in rows if r["state"] == "FAIL"]
    weak = [r for r in rows if r["state"] == "WEAK"]
    lines = [f"sync: {len(rows) - len(bad) - len(weak)}/{len(rows)} cards verified "
             f"against the audio, {len(weak)} weak, {len(bad)} contradicted"]
    seen = set()
    for r in rows:
        if r["line"] in seen:
            continue
        seen.add(r["line"])
        tag = {"PASS": "ok  ", "WEAK": "weak", "FAIL": "FAIL"}[r["state"]]
        span = f"{r['span'][0]:5.2f}-{r['span'][1]:5.2f}"
        lines.append(f"  {tag} {span}s  {r['line'][:38]}")
        lines.append(f"        heard there: \"{r['heard'][:64]}\"" if r["heard"] else "        heard there: (nothing)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="verify caption timing against the mix")
    ap.add_argument("--video", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--timeline", action="store_true",
                    help="print the card times in seconds instead of a report")
    a = ap.parse_args(argv)

    data = json.loads(Path(a.script).read_text())
    cards = data.get("cards", data)
    bpm = float(data.get("bpm", 0)) if isinstance(data, dict) else 0.0
    if not bpm:
        bpm = 122.8            # the script stores beats; the mix is the clock
    cards = [{"start": c["beat"] * 60.0 / bpm,
              "end": c.get("until", c["beat"]) * 60.0 / bpm,
              "text": c["text"], "line": c.get("line", -1)} for c in cards]
    if a.timeline:
        for c in cards:
            print(f"{c['start']:6.2f}-{c['end']:6.2f}  {c['text']}")
        return 0

    dur = max(c["end"] for c in cards) + 2.0
    windows = window_texts(a.video, dur)
    rows = check(cards, windows)
    print(report(rows))
    out = Path("work/studio/sync_windows.json")
    if out.parent.exists():
        out.write_text(json.dumps(windows, indent=1) + "\n")
    return 0 if all(r["state"] != "FAIL" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
