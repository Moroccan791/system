#!/usr/bin/env python3
"""Retention analysis for a finished timeline (report-only).

The motion system guarantees a video LOOKS right (QC v2); this
scores whether it is built to be WATCHED to the end:

  hook (25)        the quality of the actual spoken first seconds;
                   an opening slate never earns hook points
  pacing (30)      no dead air: a visual event (item start, spoken
                   word onset, panel step) at least every 2.5 s
  open loop (20)   the first 35% of the words plants a question the
                   rest of the clip answers (teaser markers: but /
                   wait / secret / mistake / last / why / never...)
  loop closure (15) the ending hands back to the opening (shared
                   words), so a replay feels seamless
  ending (10)      the clip finishes ON something - an end card or
                   a graphic alive into the last 1.6 s, not a fade
                   to a bare talking head

Usage: python motion/retention.py <timeline.json> <transcript.json>
Prints JSON; produce.py files it in the review pack. It never
fails a render - it tells the author what to fix next time.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TEASERS = {"but", "wait", "secret", "nobody", "mistake", "last",
           "finally", "shocked", "truth", "never", "why", "how",
           "actually", "wrong", "nobody's", "stop", "before"}


def words_of(tr) -> list[dict]:
    if isinstance(tr, dict):
        tr = tr.get("words") or []
    return [{"text": str(w.get("text") or w.get("word") or ""),
             "start": float(w["start"])} for w in tr
            if str(w.get("text") or w.get("word") or "").strip()]


def norm(t: str) -> str:
    return re.sub(r"[^a-z0-9']", "", t.lower())


def spoken_hook_score(words: list[dict]) -> tuple[int, list[str]]:
    """Score the actual spoken open; a title slate never earns hook points."""
    if not words:
        return 0, ["no transcript words in the opening"]
    t0 = float(words[0]["start"])
    head = []
    for w in words:
        if float(w["start"]) - t0 > 2.1 and head:
            break
        head.append(w)
        if str(w["text"]).strip().endswith((".", "?", "!")):
            break
    text = " ".join(str(w["text"]) for w in head).strip()
    toks = [norm(w["text"]) for w in head]
    score, notes = 0, []
    filler = {"so", "and", "but", "yeah", "like", "well", "okay", "um", "uh", "basically"}
    if toks and toks[0] in filler:
        score -= 5
        notes.append("spoken open starts with filler")
    else:
        score += 4
    if any(t in TEASERS for t in toks):
        score += 6
        notes.append("spoken claim/contrast opens a loop")
    if "?" in text:
        score += 4
        notes.append("spoken question")
    if any(re.search(r"\d", str(w["text"])) for w in head):
        score += 5
        notes.append("spoken number")
    if 4 <= len(toks) <= 15:
        score += 3
    if len(toks) > 22:
        score -= 3
        notes.append("spoken opening is long")
    return max(0, min(25, score)), notes


def analyse(tl: dict, tr) -> dict:
    dur = float(tl.get("duration") or 0)
    items = tl.get("items") or []
    words = words_of(tr)
    events = set()
    for it in items:
        events.add(round(float(it["at"]), 3))
        for row in (it.get("rows") or it.get("lines") or []):
            for w in row:
                events.add(round(float(w["at"]), 3))
        for sub in (it.get("items") or it.get("steps") or []):
            events.add(round(float(sub["at"]), 3))
    ev = sorted(events)
    gaps = [(round(b - a, 2), a) for a, b in zip(ev, ev[1:]) if b - a > 2.5]

    hook_slate = any(i["type"] == "hook" and float(i["at"]) <= 0.1
                     for i in items)
    first_ev = ev[0] if ev else dur
    hook, hook_notes = spoken_hook_score(words)
    pacing = max(0, 30 - 6 * len(gaps))

    toks = [norm(w["text"]) for w in words]
    head = toks[:max(4, int(len(toks) * 0.35))]
    teaser = sorted({t for t in head if t in TEASERS})
    has_q = any("?" in w["text"] for w in words[:len(head) + 2])
    open_loop = 20 if (teaser or has_q) else 0

    first8, last8 = set(toks[:8]), set(toks[-8:])
    shared = sorted(first8 & last8 - {""})
    loop_closure = 15 if len(shared) >= 2 else 8 if len(shared) == 1 else 0

    last_until = max((float(i.get("until") or i["at"]) for i in items),
                     default=0)
    ending = 10 if any(i["type"] == "endcard" for i in items) else \
        6 if last_until >= dur - 1.6 else 0

    score = hook + pacing + open_loop + loop_closure + ending
    notes = []
    if hook < 12:
        notes.extend(hook_notes)
        notes.append("spoken hook is weak or delayed; a title slate earns no hook points")
    if first_ev > 0.5:
        notes.append(f"first visual event at {first_ev:.2f}s - start the spoken captions or picture event sooner")
    for g, at in gaps[:4]:
        notes.append(f"pacing gap {g:.1f}s at {at:.1f}s - add a beat "
                     f"(chip / vector card / punch) or extend a hold")
    if not teaser and not has_q:
        notes.append("no open loop in the first 35% - plant the "
                     "question early (but / wait / the last one...)")
    if not shared:
        notes.append("ending does not hand back to the opening words "
                     "- a loopable ending replays seamlessly")
    if ending == 0:
        notes.append("nothing lands at the end - add an end card or "
                     "hold the last graphic into the final beat")
    return {"score": score, "of": 100,
            "band": "strong" if score >= 75 else
                    "ok" if score >= 55 else "weak",
            "hook": hook, "pacing": pacing, "open_loop": open_loop,
            "loop_closure": loop_closure, "ending": ending,
            "hook_slate_present": hook_slate, "spoken_hook_notes": hook_notes,
            "first_event_s": first_ev,
            "gaps_over_2_5s": gaps, "teasers_found": teaser,
            "loop_shared_words": shared, "notes": notes}


def main() -> int:
    tl = json.loads(Path(sys.argv[1]).read_text())
    tr = json.loads(Path(sys.argv[2]).read_text())
    print(json.dumps(analyse(tl, tr), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
