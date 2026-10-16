#!/usr/bin/env python3
"""Library demo 2: semantic assignment end-to-end. assign.py proposes
motions from the transcript's spoken triggers; this generator curates
them (documented below) and fills creative params.

TIMING LAW (learned from review of the first cut): a scene's window IS
its spoken beat - it starts on the trigger word and is gone within
~0.3s of the beat ending. A scene that outlives its beat swallows the
next sentence's captions (the words are never shown) and reads as a
glitch when it finally leaves. If a beat is shorter than a full
scene's minimum readable dwell, use the lighter card form (captions
keep flowing underneath) instead of forcing the full-bleed.

Curation of assign.py proposals on this clip (word times re-derived
from the energy-aligned base transcript, so anchors cannot drift):
  people@3.52   the pictogram belongs to the RESTATED "57 men" at
                9.88 - the hook stays face-led with just the counter.
  list@6.21/8.74 REJECTED - "first one/first claim" is a single passing
                ordinal, not an enumeration worth plates.
  counter@7.29  REJECTED - a second number hit seconds after the hook
                counter would repeat the same family back-to-back.
                (The hook counter itself is kept: it counts 0->57 and
                lands exactly as he says "57", exits 0.8s later.)
  chat@10.27    that beat is owned by the people pictogram; the chat
                scene moves to where he literally says "put a '1' in
                the chat" (21.86) and cascades its "1" bubbles there.
  gauge@28.34   ACCEPTED but as a CARD: "a hundred percent" is a 0.7s
                phrase - too short for a full-bleed hold (validator
                floor 1.2s) without eating the next sentence. As a card
                it sweeps to 100% on the phrase while captions continue.
  versus, timeline (hand-added in v1) REMOVED: after their beats the
                speech runs on without a pause ("We know that for a
                fact...", "The thing is we don't know if..."), so any
                honest window would swallow spoken words. They stay in
                the library for clips that give them a real window.
Run: python3 motion/timelines/motions_demo2_generator.py
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

    def find(text, after=0.0, nth=0):
        hits = [w for w in words
                if w["text"].strip(".,").lower() == text.lower()
                and w["start"] >= after]
        return hits[nth]

    # "57 men" is said twice: the hook (face + counter) and the
    # restatement (pictogram). Anchor to the word pair, not a bare count.
    men57 = [words[i] for i, w in enumerate(words[:-1])
             if "57" in w["text"]
             and words[i + 1]["text"].strip(".,").lower() == "men"]
    hook57, rest57 = men57[0], men57[-1]
    every = find("every")
    ki = next(i for i, w in enumerate(words)
              if w["text"].strip(".,").lower() == "known")
    known, after_known = words[ki], words[ki + 1]
    put = find("put", after=20.0)
    hundred = find("hundred")

    specials = [
        # hook counter: lands on the first "57", out 0.8s later
        {"type": "counter", "at": round(hook57["start"] - 0.9, 3),
         "zone": [0.60, 0.82], "value": 57,
         "label": "MEN IN THE GROUP CHAT", "countDur": 0.9,
         "until": round(hook57["start"] + 0.83, 3)},
        # pictogram on the restated "57 men in the group chat": a CARD
        # in the chest band (face above, captions below keep flowing) -
        # also keeps it out of the full-bleed chain with the quote that
        # starts on "Every..." 1.3s later
        {"type": "vector", "name": "people", "mode": "card",
         "zone": [0.53, 0.66], "w": 0.55, "blocks": False,
         "count": 57, "total": 57,
         "at": round(rest57["start"] - 0.03, 3),
         "until": round(rest57["start"] + 1.21, 3)},
        # the quote IS the sentence "Every single one of them should
        # have known" - window ends with the sentence, so "exactly!"
        # gets its caption back
        {"type": "vector", "name": "quote", "mode": "fullbleed",
         "quoteLines": ["Every single one of them", "should have known"],
         "by": "Michael Sartain",
         "at": round(every["start"], 3),
         # out with the sentence: never past the next word ("exactly!")
         "until": round(min(known["end"] + 0.12,
                            after_known["start"] - 0.01), 3)},
        # "put a '1' in the chat": bubbles land as he says it
        {"type": "vector", "name": "chat", "mode": "fullbleed",
         "title": "THE GROUP CHAT", "label": "PUT A '1' IN THE CHAT",
         "messages": [{"text": "1"}, {"text": "1"}, {"text": "1", "me": True},
                      {"text": "1"}],
         "at": round(put["start"] - 0.04, 3),
         "until": round(put["start"] + 1.18, 3)},
        # "a hundred percent": card form in the same chest band,
        # captions keep flowing (the question is in the captions;
        # the gauge is the answer hitting 100%)
        {"type": "vector", "name": "gauge", "mode": "card",
         "zone": [0.53, 0.66], "w": 0.55, "blocks": False,
         "value": 100,
         "at": round(hundred["start"] - 0.14, 3),
         "until": round(hundred["start"] + 1.11, 3)},
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
    for it in tl["items"]:
        if it["type"] != "poster":
            print(f"  {it['at']:>6.2f}-{it.get('until')}  "
                  f"{it['type']}:{it.get('name', '')}")


if __name__ == "__main__":
    main()
