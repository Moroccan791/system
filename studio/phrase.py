"""Where the words actually are, from a decode sweep of the vocal.

The problem this solves: the lyric arrives with no times, in a language whose
aligners are not available here, over a mix loud enough that the vocal is not
separable by filter. Two facts make it tractable anyway.

1. A speech model never returns silence. Over an instrumental it emits one
   syllable repeated, or punctuation, or a single vowel. So a window whose
   transcript looks like a stutter is a window with no vocal in it — the
   transcript doubles as voice activity.
2. The lyric is known. Character trigrams of a line are a robust fingerprint:
   they survive a recogniser that misspells every word, because a window that
   really contains the line still contains most of its character shapes.

Put together: find the windows that carry voice, and inside them find the
windows that carry a given line. What comes out is a start and an end per sung
line — which is what the captions need, and what an onset detector cannot give.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

NGRAM = 3


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat.startswith("L") or cat.startswith("M"):
            out.append(ch)
    return "".join(out)


def grams(s: str, n: int = NGRAM) -> set[str]:
    s = norm(s)
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def overlap(a: str, b: str) -> float:
    """Share of a's character shape that also occurs in b."""
    ga = grams(a)
    if not ga:
        return 0.0
    return len(ga & grams(b)) / len(ga)


def sweep_curve(sweep: list[dict], line: str) -> list[tuple[float, float]]:
    return [(w["start"], overlap(line, w["text"])) for w in sweep]


def voice(sweep: list[dict], hop: float, keep: float = 0.55) -> list[tuple[float, float]]:
    """Intervals where a window was not stuttering to itself."""
    live = [(w["start"], 1.0 - float(w.get("junk", 0.0))) for w in sweep]
    out: list[tuple[float, float]] = []
    run: list[float] | None = None
    for t, v in live:
        if v >= keep:
            run = [t] if run is None else run
        elif run is not None:
            out.append((run[0], t + hop))
            run = None
    if run is not None:
        out.append((run[0], live[-1][0] + hop))
    return out


def line_spans(sweep: list[dict], lines: list[str], hop: float,
               win: float, thr: float = 0.30) -> list[dict]:
    """Every place each line is sung, in order, allowing the lyric to cycle.

    A window's score for a line is the share of the line's trigrams it contains,
    renormalised by how much of the line a window of that length could hold —
    a six-second window cannot contain an eight-second line, and would otherwise
    score every long line at half.
    """
    found: list[dict] = []
    for i, line in enumerate(lines):
        cover = min(1.0, (win / max(1e-6, 0.28 * len(norm(line)) + 0.8)))
        floor = thr * max(0.55, cover)
        hits = [(t, s) for t, s in sweep_curve(sweep, line) if s >= floor]
        # group contiguous hits into one occurrence
        group: list[tuple[float, float]] = []
        for t, s in hits:
            if group and t - group[-1][0] > win:
                found.append({"line": i, "start": group[0][0],
                              "end": group[-1][0] + win, "score": max(x[1] for x in group)})
                group = []
            group.append((t, s))
        if group:
            found.append({"line": i, "start": group[0][0],
                          "end": group[-1][0] + win, "score": max(x[1] for x in group)})
    found.sort(key=lambda d: d["start"])
    return found


def report(asr: dict, lines: list[str]) -> str:
    sweep = asr["sweep"]
    hop = float(asr.get("hop", 0.5))
    win = float(asr.get("win", 6.0))
    out = [f"{len(sweep)} windows, hop {hop}s, win {win}s"]
    for a, b in voice(sweep, hop):
        out.append(f"  voice {a:7.2f} - {b:7.2f}   ({b - a:5.2f}s)")
    out.append("lines:")
    for sp in line_spans(sweep, lines, hop, win):
        out.append(f"  L{sp['line']}  {sp['start']:7.2f} - {sp['end']:7.2f}  "
                   f"{sp['end'] - sp['start']:5.2f}s  score {sp['score']:.2f}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="where the sung lines are")
    ap.add_argument("asr")
    ap.add_argument("lyric")
    ap.add_argument("--hop", type=float, default=0.5)
    ap.add_argument("--win", type=float, default=6.0)
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    asr = json.loads(Path(a.asr).read_text())
    asr.setdefault("hop", a.hop)
    asr.setdefault("win", a.win)
    lines = [l.strip() for l in Path(a.lyric).read_text().splitlines() if l.strip()]
    print(report(asr, lines))
    if a.json:
        spans = line_spans(asr["sweep"], lines, a.hop, a.win)
        Path(a.json).write_text(json.dumps({"spans": spans, "lines": lines}, indent=1) + "\n")
        print("wrote", a.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
