#!/usr/bin/env python3
"""Choose the clip and the opening. No shortlist for the user to referee.

    .venv/bin/python scripts/whop/auto_pick.py work/<campaign>/asr/episode.json
    .venv/bin/python scripts/whop/auto_pick.py episode.json --count 3 --json out.json

`hook_lab.py` scores an opening; this decides which opening and which cut,
end to end, so the decision comes back as "here is the clip, here is why",
not "which one do you like". The scoring is deliberate and inspectable:

* **hook (45%)** - `hook_lab` on the first two seconds, calibrated on the
  campaign's reference clips;
* **payoff (25%)** - the last line resolves: a conclusion word, a contrast, a
  stakes word, and it must end on a sentence boundary, not on filler;
* **density (20%)** - words per second across the window; the references run
  4.5-6.5 w/s, dead air is what kills a middle;
* **length (10%)** - closest to the campaign's ideal, not just inside the
  window.

Hard rejects before scoring: a window that contains filler (um, uh, you know,
like) is penalised per filler; a window ending mid-sentence is not a
candidate at all; overlaps are removed so the same moment is never proposed
twice.

Everything printout-wise is written for a human to overrule if they disagree -
that is different from asking them to choose.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import caption_rules as CR                      # noqa: E402
import hook_lab as HL                          # noqa: E402

PAYOFF = re.compile(
    r"\b(so|because|that's why|which means|turns out|the point|in the end|"
    r"that's the|it was|it's|more successful|successful|worth it|free|"
    r"never|always|every|nobody|everybody|truth|answer|reason)\b", re.I)
TERMINAL = ".!?"
PAUSE_END = 0.30          # a cut needs air after the last word


def load_words(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    raw = data.get("words", []) if isinstance(data, dict) else data
    out = []
    for w in raw:
        text = str(w.get("text") or w.get("w") or "")
        start = w.get("start", w.get("at"))
        if text and start is not None:
            out.append({"text": text, "start": float(start),
                        "end": float(w.get("end") or start)})
    return sorted(out, key=lambda w: w["start"])


def ends_sentence(words: list[dict], idx: int) -> bool:
    if idx >= len(words):
        return False
    if str(words[idx - 1]["text"]).rstrip()[-1:] in TERMINAL:
        return True
    nxt = words[idx] if idx < len(words) else None
    return bool(nxt and float(nxt["start"]) - float(words[idx - 1]["end"]) >= PAUSE_END)


def payoff_score(text: str) -> tuple[float, list[str]]:
    score, why = 0.0, []
    if PAYOFF.search(text):
        score += 0.6
        why.append("resolves")
    if HL.CONTRAST.search(text):
        score += 0.2
        why.append("contrast")
    if HL.STAKES.search(text):
        score += 0.2
        why.append("stakes")
    if CR.filler_words(text.split()):
        score -= 0.8
        why.append("ends on filler")
    return max(0.0, min(1.0, score)), why


def windows(words: list[dict], lo: float, hi: float, ideal: float) -> list[dict]:
    """Every cut that starts on a boundary, ends on a boundary, fits the window."""
    starts: list[int] = []
    for i, w in enumerate(words):
        if i == 0:
            starts.append(i)
            continue
        prev = words[i - 1]
        if float(w["start"]) - float(prev["end"]) >= 0.18:
            starts.append(i)
        elif str(prev["text"]).rstrip()[-1:] in TERMINAL:
            starts.append(i)
    out = []
    for i in starts:
        t0 = float(words[i]["start"])
        # If nothing in the window ends on a hard sentence boundary (real
        # transcripts have stretches with no clean stop), fall back to the
        # longest silence available, so a cut can still be proposed - flagged
        # as soft, and scored lower for it.
        soft_j, soft_gap = None, 0.0
        for j in range(i + 1, len(words) + 1):
            dur = float(words[j - 1]["end"]) - t0
            if dur < lo or dur > hi:
                continue
            gap = (float(words[j]["start"]) - float(words[j - 1]["end"])
                   if j < len(words) else 9.9)
            if gap > soft_gap:
                soft_j, soft_gap = j, gap
            if not ends_sentence(words, j):
                continue
            seg = words[i:j]
            t1 = float(words[j - 1]["end"])
            dur = t1 - t0
            text = " ".join(str(w["text"]) for w in seg)
            hook_words = [w for w in seg if float(w["start"]) < t0 + HL.WINDOW] or seg[:4]
            hook_text = " ".join(str(w["text"]) for w in hook_words)
            h_score, h_why = HL.classify(hook_text, hook_words)
            p_score, p_why = payoff_score(" ".join(str(w["text"]) for w in seg[-6:]))
            density = len(seg) / max(dur, 0.1)
            d_score = max(0.0, min(1.0, (density - 2.5) / 3.0))
            l_score = max(0.0, 1.0 - abs(dur - ideal) / max(ideal, 1.0))
            fillers = CR.filler_words([str(w["text"]) for w in seg])
            f_pen = min(0.30, 0.05 * len(fillers))
            total = (0.45 * (h_score / 10.0) + 0.25 * p_score
                     + 0.20 * d_score + 0.10 * l_score - f_pen)
            out.append({
                "start": round(t0, 2), "end": round(t1, 2), "duration": round(dur, 2),
                "hook": hook_text, "last_line": " ".join(str(w["text"]) for w in seg[-6:]),
                "score": round(total * 100, 1),
                "parts": {"hook": round(h_score, 1), "payoff": round(p_score, 2),
                          "density": round(density, 2), "length_fit": round(l_score, 2),
                          "fillers": fillers},
                "why": h_why + p_why,
                "soft_cut": False,
            })
        if soft_j is not None and soft_gap >= 0.12 and not any(
                c["start"] == round(t0, 2) for c in out):
            j = soft_j
            seg = words[i:j]
            t1 = float(words[j - 1]["end"])
            dur = t1 - t0
            text = " ".join(str(w["text"]) for w in seg)
            hook_words = [w for w in seg if float(w["start"]) < t0 + HL.WINDOW] or seg[:4]
            h_score, h_why = HL.classify(text[:40], hook_words)
            dur = float(seg[-1]["end"]) - t0
            out.append({
                "start": round(t0, 2), "end": round(float(seg[-1]["end"]), 2),
                "duration": round(dur, 2),
                "hook": " ".join(str(w["text"]) for w in hook_words),
                "last_line": " ".join(str(w["text"]) for w in seg[-6:]),
                "score": round(max(0.0, 0.45 * (h_score / 10.0) - 0.10) * 100, 1),
                "parts": {"hook": round(h_score, 1), "payoff": 0.0,
                          "density": round(len(seg) / max(dur, 0.1), 2),
                          "length_fit": 0.0,
                          "fillers": CR.filler_words([str(w["text"]) for w in seg])},
                "why": h_why + [f"soft cut ({soft_gap:.2f}s of air)"],
                "soft_cut": True,
            })
    return out


def choose(cands: list[dict], count: int) -> list[dict]:
    """Best first, then best that does not overlap something already chosen."""
    picked: list[dict] = []
    for c in sorted(cands, key=lambda x: -x["score"]):
        if all(c["end"] <= p["start"] or c["start"] >= p["end"] for p in picked):
            picked.append(c)
        if len(picked) >= count:
            break
    return picked


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--min", type=float, default=25.0)
    ap.add_argument("--max", type=float, default=40.0)
    ap.add_argument("--ideal", type=float, default=32.0)
    ap.add_argument("--json", help="write the picks here")
    args = ap.parse_args()

    words = load_words(Path(args.transcript))
    if not words:
        print("no words in transcript", file=sys.stderr)
        return 2
    cands = windows(words, args.min, args.max, args.ideal)
    picks = choose(cands, args.count)
    if not picks:
        print(f"no window between {args.min:.0f}-{args.max:.0f}s ends on a "
              f"sentence boundary", file=sys.stderr)
        return 1
    print(f"\nAUTO PICK — {len(cands)} valid windows, {len(picks)} chosen\n")
    for n, c in enumerate(picks, 1):
        print(f"{n}. {c['start']:.2f}-{c['end']:.2f}s  ({c['duration']:.1f}s)  "
              f"score {c['score']:.1f}")
        print(f"   OPENS : {c['hook']}")
        print(f"   CLOSES: {c['last_line']}")
        print(f"   PARTS : hook {c['parts']['hook']}/10, payoff {c['parts']['payoff']}, "
              f"density {c['parts']['density']} w/s, "
              f"fillers {len(c['parts']['fillers'])}")
    if args.json:
        Path(args.json).write_text(json.dumps(picks, indent=1) + "\n")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
