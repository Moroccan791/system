#!/usr/bin/env python3
"""Library demo 2: semantic assignment end-to-end. assign.py proposes
motions from the transcript's spoken triggers; this generator curates
them (documented below) and fills creative params. New scenes on show:
chat (the "put a 1 in the chat" beat) and gauge (the "hundred percent"
beat). Run: python3 motion/timelines/motions_demo2_generator.py

Curation of assign.py proposals on this clip:
  people@3.42   MOVED to 9.40 - the hook stays face-led with a counter;
                the pictogram lands on the "57 men in the group chat"
                restatement instead.
  list@6.11/8.64 REJECTED - "first one/first claim" is a single passing
                ordinal, not an enumeration worth plates.
  counter@7.19  REJECTED - a second number hit 4s after the hook counter
                would repeat the same family back-to-back.
  chat@10.17    MOVED to 20.95 - at 10.17 the people scene owns the beat;
                the chat returns where the speech is literally about
                sending "1" in the chat.
  gauge@28.34   ACCEPTED as proposed ("a hundred percent").
"""
import json
import sys
from pathlib import Path

SYS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SYS / "motion"))
sys.path.insert(0, str(SYS / "motion" / "timelines"))
from assign import propose  # noqa: E402
from sartain_posts_generator import build, probe_dur  # noqa: E402


def main():
    sl = json.load(open(SYS / "work/sartain_new/clip2_words.json"))
    words = sl["words"]
    props = propose(words, sl["duration"])
    print(f"assign.py: {len(props)} proposals")
    for p in props:
        kind = p.get("name") or p.get("type") or p.get("_suggest")
        print(f"  {p['at']:>6.2f}s {kind:<8} {p['_reason']}")
    w57 = next(w for w in words if "57" in w["text"])
    c_at = round(w57["start"] - 0.9, 3)
    specials = [
        {"type": "counter", "at": c_at, "zone": [0.60, 0.82], "value": 57,
         "label": "MEN IN THE GROUP CHAT", "countDur": 0.9,
         "until": round(c_at + 2.7, 3)},
        {"type": "vector", "name": "people", "mode": "fullbleed",
         "label": "MEN IN THE GROUP CHAT", "count": 57, "total": 57,
         "at": 9.40, "until": 11.65},
        {"type": "vector", "name": "quote", "mode": "fullbleed",
         "quoteLines": ["Every single one of them", "should have known"],
         "by": "Michael Sartain", "at": 11.85, "until": 14.10},
        {"type": "vector", "name": "versus", "mode": "fullbleed",
         "label": "HIS POINT",
         "left": {"label": "AWAKE", "value": 57},
         "right": {"label": "STEPPED IN", "value": 0}, "win": "left",
         "at": 16.00, "until": 18.20},
        # NEW: the speech is literally about sending "1" in the chat
        {"type": "vector", "name": "chat", "mode": "fullbleed",
         "title": "THE GROUP CHAT", "label": "PUT A '1' IN THE CHAT",
         "messages": [{"text": "1"}, {"text": "1"}, {"text": "1", "me": True},
                      {"text": "1"}],
         "at": 20.95, "until": 23.05},
        # NEW: proposed by assign.py at the "hundred percent" anchor
        {"type": "vector", "name": "gauge", "mode": "fullbleed",
         "value": 100, "label": "SHOULD SOMEONE HAVE ACTED?",
         "at": 28.34, "until": 30.54},
        {"type": "vector", "name": "timeline", "mode": "fullbleed",
         "label": "THE ARGUMENT",
         "events": [{"x": 0.06, "label": "57 MEN", "sub": "IN THE CHAT"},
                    {"x": 0.5, "label": "ALL AWAKE", "sub": "EVERY ONE"},
                    {"x": 0.94, "label": "NO ONE ACTED", "sub": "HIS POINT"}],
         "at": 31.48, "until": 33.85},
    ]
    base = SYS / "work/michael_sartain/edits/cornell-7-story_M2.mp4"
    tl = build(words, probe_dur(base), specials, [0.68, 0.86])
    out = SYS / "motion/timelines/motions_demo2.json"
    out.write_text(json.dumps(tl, indent=1))
    kinds = {}
    for it in tl["items"]:
        k = it["type"] + (":" + it["name"] if it["type"] == "vector" else "")
        kinds[k] = kinds.get(k, 0) + 1
    print("wrote", out, kinds, "duration", tl["duration"])


if __name__ == "__main__":
    main()
