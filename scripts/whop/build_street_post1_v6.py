#!/usr/bin/env python3
"""Whop post1 v6 editorial proof cut (working file, not approved).

Build from the re-aligned base word clock, using the pre-edit style card.
The saved card is the provisional look until the user approves a style
for post1; no font or colour is hard-coded in this creative timeline.

Story: an open loop (space) -> craft builds a structure -> not an award
(the negated cup is a real vector animation) -> the human payoff ->
connection (a developing network, never superimposed on her face) -> outro.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "work" / "street" / "whop_v6"
CAMPAIGN = ROOT / "campaigns" / "street_you_grew_up_on"
WORDS = json.loads((HERE / "slice.json").read_text())["words"]
style_file = CAMPAIGN / "post1" / "style.json"
if not style_file.exists():
    style_file = CAMPAIGN / "style.json"
STYLE = json.loads(style_file.read_text())
ACCENT = STYLE["colors"]["accent"]
CURSOR = [0]  # index, not time: repeated words cannot reuse a match


def wt(text: str) -> float:
    """The next occurrence of a word, not a timestamp guessed by hand."""
    for i in range(CURSOR[0], len(WORDS)):
        w = WORDS[i]
        if w["text"] == text:
            CURSOR[0] = i + 1
            return round(w["start"], 2)
    raise ValueError(f"{text!r} missing from speech after word {CURSOR[0]}")


def word_time(text: str) -> float:
    """A keyword already spoken between caption groups: the graphic
    names it on the same syllable. Never consumes the caption cursor."""
    return round(next(w["start"] for w in WORDS if w["text"] == text), 2)


def card(rows, *, scene=False, graphic=False, payoff=False, hero_size=242,
         conn=84):
    """Two-line maximum; each row is [(word, kind)]; one fixed eye path."""
    zone = [0.30, 0.36] if graphic else [0.55, 0.66]
    if scene:
        zone = [0.30, 0.36]
    if payoff:
        # The two-shot has moving hands at .47–.64 of the picture.
        # Put the payoff text below them, on the skirt/chair, not on
        # either speaker's face or hands.
        zone = [0.73, 0.84]
    out, ats = [], []
    for row in rows:
        rr = []
        for text, kind in row:
            at = max(0, wt(text))
            rr.append({"w": text, "at": at, "kind": kind})
            ats.append(at)
        out.append(rr)
    if len(out) > 2:
        raise ValueError("captions never exceed two lines")
    if any(len(r) > 4 for r in out):
        raise ValueError("caption line exceeds four words")
    return {"type": "poster", "at": min(ats), "rows": out,
            "zone": zone, "captionStyle": STYLE["captionStyle"],
            "connSize": conn, "heroSize": hero_size,
            "hardOut": True}


C = [
    # Hooks on her face (face ends at .45 of the frame; captions start .55).
    card([[ ("I'm","conn"),("able","conn"),("to","conn"),("hold","conn") ]]),
    card([[ ("space","hero") ]], hero_size=260),
    card([[ ("because","conn"),("my","conn"),("my","conn") ]]),
    card([[ ("craft","hero") ]], hero_size=248),
    # Full-screen diagram begins two frames before "keeps" is spoken.
    # Over a full-screen graphic the caption is a HEADLINE: big, one
    # stable band, held long enough to read as a line. A 84px caption
    # left a single word floating in an empty dark frame.
    card([[ ("keeps","conn"),("me.","conn") ]], graphic=True, conn=118),
    card([[ ("it","conn"),("keeps","conn"),("me","conn") ]], graphic=True, conn=118),
    card([[ ("It","conn"),("keeps","conn"),("me,","conn") ]], graphic=True, conn=118),
    card([[ ("It","conn"),("gives","conn"),("me","conn") ]], graphic=True, conn=118),
    # Back to the face on the structural payoff.
    card([[ ("But","conn"),("at","conn"),("the","conn"),("end","conn") ]]),
    card([[ ("of","conn"),("the","conn"),("day,","conn") ]]),
    card([[ ("I","conn"),("don't","conn"),("come","conn"),("home","conn") ]]),
    # Full-bleed cup drawing: caption placed in open sky above the cup.
    card([[ ("to","conn"),("an","conn") ],[("award","hero")]], scene=True,
         hero_size=250, conn=104),
    # Cut to her face for the emotional reveal, not on the picture of a cup.
    card([[ ("I","conn"),("come","conn"),("to","conn") ]], payoff=True),
    card([[ ("my","conn") ],[("dogs","hero")]],
         payoff=True, hero_size=258),
    card([[ ("and","conn"),("my","conn") ],[("husband","hero")]],
         payoff=True, hero_size=225),
    card([[ ("and","conn"),("that's","conn"),("what","conn") ]], payoff=True),
    card([[ ("brings","conn"),("me","conn") ],[("joy.","hero")]],
         payoff=True, hero_size=260),
    card([[ ("All","conn"),("of","conn"),("this","conn") ]]),
    card([[ ("can","conn"),("go","conn") ],[("away.","hero")]],
         hero_size=260),
    card([[ ("What's","conn"),("important","conn") ]]),
    card([[ ("in","conn"),("life","conn"),("is","conn") ]]),
    # No footage under the word CONNECTION. It sits above the network.
    card([[ ("connection.","hero") ]], scene=True, hero_size=190),
]

# Exact group windows. In the rare natural coarticulation, keep both words
# on their true acoustic onset. The prior card cuts before the next one.
for i, it in enumerate(C):
    nxt = C[i+1]["at"] if i+1 < len(C) else None
    last = max(w["at"] for row in it["rows"] for w in row)
    # The next word enters 2 frames ahead of its syllable. Hard-cut the
    # old phrase at that exact visual handoff; do not stack two captions.
    visual_next = nxt - 2 / 30 if nxt is not None else 20.58
    it["until"] = round(max(last + .12, min(last + .95, visual_next)), 3)
    if nxt is not None and it["until"] > visual_next + .025:
        raise ValueError(f"phrases overlap acoustically at {last:.2f} -> {nxt:.2f}")

# The previous caption must not pop at head height in the two frames before
# the dark diagram takes over the footage.
next(it for it in C if it["rows"][0][0]["w"] == "craft")["until"] = 3.23

LIST = {"type": "list", "layout": "diagram", "at": 3.23,
        "until": 9.57, "hardOut": True, "accent": ACCENT,
        # no label: the running caption says "my craft" - a second
        # label at the foot of the graphic split the sentence.
        
        "items": [
            {"text": "BUSY", "at": word_time("Busy,")},
            {"text": "SANE", "at": word_time("sane.")},
            {"text": "FOCUSED", "at": word_time("focused.")},
            # The diagram line anticipates the next label; the word itself
            # must not appear before the voice says it.
            {"text": "STRUCTURE", "at": word_time("structure.")},
        ]}
NOAWARD = {"type": "vector", "name": "noaward", "mode": "fullbleed",
           "at": 11.95, "until": 12.98, "offsetY": 250, "accent": ACCENT}
NETWORK = {"type": "vector", "name": "network", "mode": "fullbleed",
           "at": 19.51, "until": 20.72, "offsetY": 150,
           "radius": 145, "title": "YOU", "count": 7,
           "accent": ACCENT}
ENDCARD = {"type": "endcard", "at": 20.72, "until": 21.79,
           "title": "STREET YOU GREW UP ON",
           "titleLines": ["STREET YOU", "GREW UP ON"],
           "sub": "@street_you_grew_up_on", "wordSize": 148,
           "accent": ACCENT}

T = {
    "version": 1, "width": 1080, "height": 1920, "fps": 30,
    "duration": 21.81,
    "brand": {"accent": ACCENT},
    "posting": {
        "title": "Demi Lovato: I Don't Come Home to an Award",
        "hookVariants": [
            {"strategy": "current face-first cut",
             "hook": "I'm able to hold space"},
            {"strategy": "quoted contrast",
             "hook": "I don't come home to an award"},
            {"strategy": "quoted closing thought",
             "hook": "What's important in life is connection"},
        ],
        "alternativeTitles": [
            "Demi Lovato on What Brings Her Joy",
            "Demi Lovato: What's Important in Life Is Connection",
        ],
        "description": (
            "Demi Lovato says her craft keeps her busy, sane and focused. "
            "But home means her dogs and husband, not an award. "
            "What's important in life is connection."
        ),
        "disclosure": "#ad",
        "requiredLine": (
            "The podcast name is Street You Grew Up On - full episode is "
            "available on YT and other podcast platforms"
        ),
        "hashtags": [
            "#DemiLovato", "#StreetYouGrewUpOn", "#PodcastClips",
            "#DemiLovatoInterview", "#PodcastMoments", "#SelfReflection",
            "#Connection", "#MusicAndLife",
        ],
        "coverMoments": [1.35, 12.66, 16.25],
    },
    "theme": {"radius": STYLE.get("radius","sharp"), "glow": 0,
              "speed": 1.0, "easing": "pop", "fontMode": "sans",
              "captionStyle": STYLE["captionStyle"],
              "fontPack": STYLE["caption"],
              "fonts": {k: STYLE[k] for k in
                        ("caption","keyword","serif","list","endcard")},
              "colors": STYLE["colors"]},
    "items": sorted(C+[LIST,NOAWARD,NETWORK,ENDCARD],key=lambda x:x["at"]),
}
(HERE / "timeline.json").write_text(json.dumps(T,indent=2)+"\n")
print(f"v6: {len(T['items'])} items, {T['duration']}s, look {STYLE['captionStyle']}, accent {ACCENT}")
for it in T["items"]:
    text = "/".join(" ".join(w["w"] for w in row) for row in it.get("rows",[]))
    if it["type"] == "list": text = "/".join(x["text"] for x in it["items"])
    print(f'{it["type"]:<8} {it["at"]:5.2f}–{it["until"]:5.2f}  {text}')
