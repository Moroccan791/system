#!/usr/bin/env python3
"""Pick the clips worth cutting from the episode transcript.

    python scripts/whop/pick_clips.py            # top candidates
    python scripts/whop/pick_clips.py --top 20

Rules that come from recipes/editing_brain.md and the reference clips:
  * the FIRST line must open a loop (a claim, a contrast, a number,
    a confession) - never a preamble like "so I was thinking about";
  * the clip ends on a sentence boundary with a real pause, so no
    important line is cut off;
  * the closing line must resolve what the open promised;
  * length 25-50s, dense enough to hold, short enough to watch twice.

Scoring is a heuristic ranking, not the decision: the editor (us)
reads the shortlist and picks.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path("/home/user/system")
ASR = ROOT / "work" / "street" / "asr" / "episode_transcript.json"

# ---------------------------------------------------------------- lexicon
HOOK = {
    # a contrast / surprise lands immediately
    "contrast": 3.0, "never": 1.6, "don't": 1.4, "not": 0.8, "instead": 1.8,
    "nobody": 2.2, "nobody's": 2.2, "everyone": 1.2, "actually": 0.9,
    "turns out": 2.6, "the truth": 2.4, "honest": 1.6, "realized": 2.0,
    "scared": 2.4, "afraid": 2.4, "terrified": 2.6, "hate": 1.8, "loved": 1.8,
    "cried": 2.6, "cry": 1.6, "broke": 2.0, "failed": 1.8, "struggled": 1.6,
    "quit": 1.8, "began": 1.2, "started": 0.8, "wasn't": 1.0, "weren't": 1.0,
    "knew": 1.4, "wished": 1.8, "wanted": 0.9, "needed": 0.9, "why": 1.2,
    "because": 1.0, "important": 1.4, "matters": 1.4, "matter": 1.2,
    "connection": 1.8, "connected": 1.6, "alone": 1.8, "lonely": 2.2,
    "enough": 1.4, "everything": 1.2, "nothing": 1.2, "always": 0.8,
    "home": 1.4, "family": 1.4, "kids": 1.2, "daughter": 1.2, "mother": 1.2,
    "therapy": 1.6, "diagnosed": 2.2, "recovery": 1.8, "sober": 2.4,
    "first": 0.8, "biggest": 1.6, "worst": 2.0, "best": 1.2, "hardest": 1.8,
    "secret": 2.4, "lie": 1.8, "told": 0.8, "saying": 0.8, "learned": 1.4,
}
# words that read as filler in the first second - a clip that starts
# with these is a bad hook
FILLER = {"so", "and", "but", "yeah", "like", "you", "know", "i", "um", "uh",
          "well", "right", "okay", "ok", "anyway", "basically", "literally",
          "actually", "just", "really", "very", "kind", "sort", "thing",
          "stuff", "gonna", "wanna", "mhm", "mm", "uhh", "anyways"}
# a good closing line resolves
CLOSE = {"home", "family", "love", "loved", "kids", "daughter", "husband",
         "enough", "important", "matters", "matter", "connection", "together",
         "finally", "peace", "happy", "joy", "grateful", "thankful", "proud"}

QUESTIONY = re.compile(r"\?")


def sentences(words, gap=0.32):
    """Group words into utterance sentences at real pauses."""
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and w["start"] - cur[-1]["end"] >= gap:
            out.append(cur)
            cur = []
        cur.append(w)
        if str(w.get("text", "")).strip().endswith((".", "?", "!")):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def score_open(sent):
    """How good is this sentence as the first line of a clip?"""
    text = " ".join(w["text"] for w in sent).lower()
    toks = [t for t in re.findall(r"[a-z']+", text)]
    if not toks:
        return -99, "empty"
    why = []
    s = 0.0
    # opening with filler kills the hook
    lead = toks[0]
    if lead in FILLER:
        s -= 3.0
        why.append("starts on filler")
    # a first/second person claim scores
    if lead in ("i", "i'm", "i've", "my", "we", "you", "you've"):
        s += 1.2
        why.append("first-person open")
    for t in toks:
        if t in HOOK:
            s += HOOK[t]
            why.append(t)
    if QUESTIONY.search(text):
        s += 1.2
        why.append("question")
    # concrete numbers / names pull the eye
    if re.search(r"\b\d+\b", text):
        s += 1.6
        why.append("number")
    # very long sentences do not work as an open
    if len(toks) > 26:
        s -= 1.6
        why.append("long open")
    if len(toks) < 3:
        s -= 2.0
        why.append("too short")
    # a mid-sentence start (lowercase continuation) is weak
    if sent and sent[0]["text"][0].islower() and lead not in ("i", "my", "the"):
        s -= 0.6
    return s, ", ".join(sorted(set(why))[:4])


def score_close(sent):
    text = " ".join(w["text"] for w in sent).lower()
    toks = set(re.findall(r"[a-z']+", text))
    s = 0.0
    for t in toks:
        if t in CLOSE:
            s += 1.4
    if 4 <= len(toks) <= 18:
        s += 0.8
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=18)
    ap.add_argument("--min", type=float, default=25.0, help="min clip length (default: 25s)")
    ap.add_argument("--max", type=float, default=40.0,
                    help="max clip length (default: 40s; extend toward 50 only when the payoff warrants it)")
    ap.add_argument("--transcript", default=str(ASR))
    a = ap.parse_args()

    data = json.loads(Path(a.transcript).read_text())
    words = data["words"]
    sents = sentences(words)
    print(f"{len(words)} words, {len(sents)} sentences "
          f"({round(data.get('duration', 0), 1)}s)\n")

    cands = []
    for i, s0 in enumerate(sents):
        op, why = score_open(s0)
        if op <= 0:
            continue
        # extend over following sentences up to the max length, keeping
        # only sentence boundaries
        t0 = s0[0]["start"]
        end_i = i
        t1 = s0[-1]["end"]
        for j in range(i + 1, len(sents)):
            dur = sents[j][-1]["end"] - t0
            if dur > a.max:
                break
            end_i, t1 = j, sents[j][-1]["end"]
            if dur >= a.min:
                break
        if t1 - t0 < a.min:
            continue
        # the pause after the last word must be real (a sentence end)
        nxt = sents[end_i + 1][0]["start"] if end_i + 1 < len(sents) else t1 + 1
        pause = nxt - t1
        if pause < 0.30:
            continue
        close = score_close(sents[end_i])
        total = op + close
        cands.append({
            "start": round(t0, 2), "end": round(t1, 2),
            "length": round(t1 - t0, 2), "pause": round(pause, 2),
            "open": " ".join(w["text"] for w in s0)[:120],
            "close": " ".join(w["text"] for w in sents[end_i])[:120],
            "score": round(total, 2), "open_score": round(op, 2),
            "why": why, "sent_from": i, "sent_to": end_i,
        })

    cands.sort(key=lambda c: -c["score"])
    print(f"{'score':>6} {'len':>6} {'start':>8}  why")
    for c in cands[:a.top]:
        print(f"{c['score']:6.2f} {c['length']:6.1f} {c['start']:8.2f}  "
              f"[{c['why']}]")
        print(f"        OPEN : {c['open']}")
        print(f"        CLOSE: {c['close']}")
        print()
    out = ROOT / "work" / "street" / "asr" / "candidates.json"
    out.write_text(json.dumps(cands[:120], indent=1))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
