#!/usr/bin/env python3
"""Library demo timeline: the M2 '57 men' clip re-cut with the MOTIONS.md
data scenes attached. Real anchors only: people=the spoken 57, quote=the
spoken words verbatim; versus/bars/line/stack visualise the speaker's argument.
Run: python3 motion/timelines/motions_demo_generator.py
"""
import json
import sys
from pathlib import Path

SYS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SYS / "motion" / "timelines"))
from sartain_posts_generator import build, probe_dur  # noqa: E402


def main():
    sl = json.load(open(SYS / "work/sartain_new/clip2_words.json"))
    words = sl["words"]
    w57 = next(w for w in words if "57" in w["text"])
    c_at = round(w57["start"] - 0.9, 3)
    specials = [
        {"type": "counter", "at": c_at, "zone": [0.60, 0.82], "value": 57,
         "label": "MEN IN THE GROUP CHAT", "countDur": 0.9,
         "until": round(c_at + 2.7, 3)},
        # SHOW the crowd quantity (spoken number, real)
        {"type": "vector", "name": "people", "mode": "fullbleed",
         "label": "MEN IN THE GROUP CHAT", "count": 57, "total": 57,
         "at": 9.30, "until": 11.55},
        # PROVE with his exact words (verbatim)
        {"type": "vector", "name": "quote", "mode": "fullbleed",
         "quoteLines": ["Every single one of them", "should have known"],
         "by": "Michael Sartain", "at": 11.75, "until": 14.00},
        # COMPARE the argument (illustrative)
        {"type": "vector", "name": "versus", "mode": "fullbleed",
         "label": "HIS POINT",
         "left": {"label": "AWAKE", "value": 57},
         "right": {"label": "STEPPED IN", "value": 0}, "win": "left",
         "at": 15.90, "until": 18.10},
        {"type": "vector", "name": "bars", "mode": "fullbleed",
         "label": "OF THE 57 IN THE CHAT",
         "values": [57, 57, 0], "labels": ["IN CHAT", "AWAKE", "STEPPED IN"],
         "hot": 2, "at": 20.85, "until": 22.90},
        # SHOW change (illustrative)
        {"type": "vector", "name": "line", "mode": "fullbleed",
         "label": "HOW THE CHAT FILLED UP",
         "points": [4, 14, 11, 33, 57], "at": 24.60, "until": 26.90},
        # SHOW the split (illustrative)
        {"type": "vector", "name": "stack", "mode": "fullbleed",
         "label": "EVERY SINGLE ONE OF THEM",
         "parts": [99, 1], "labels": ["KNEW BETTER", "EXCUSED"],
         "at": 28.90, "until": 31.05},
        # ORIENT: the argument's beats
        {"type": "vector", "name": "timeline", "mode": "fullbleed",
         "label": "THE ARGUMENT",
         "events": [{"x": 0.06, "label": "57 MEN", "sub": "IN THE CHAT"},
                    {"x": 0.5, "label": "ALL AWAKE", "sub": "EVERY ONE"},
                    {"x": 0.94, "label": "NO ONE ACTED", "sub": "HIS POINT"}],
         "at": 31.38, "until": 33.75},
    ]
    base = SYS / "work/michael_sartain/edits/cornell-7-story_M2.mp4"
    tl = build(words, probe_dur(base), specials, [0.68, 0.86])
    out = SYS / "motion/timelines/motions_demo.json"
    out.write_text(json.dumps(tl, indent=1))
    kinds = {}
    for it in tl["items"]:
        k = it["type"] + (":" + it["name"] if it["type"] == "vector" else "")
        kinds[k] = kinds.get(k, 0) + 1
    print("wrote", out, kinds, "duration", tl["duration"])


if __name__ == "__main__":
    main()
