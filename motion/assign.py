#!/usr/bin/env python3
"""Semantic motion assignment - the anti-random layer (see MOTIONS.md
"Blending rules"). Scans timed words and PROPOSES motion specials, each
anchored to the spoken word that triggers it, with its reason recorded.
Nothing is placed by taste or rotation: a motion exists only because a
word in the speech called for it.

The proposal is a starting point for the timeline author (agent/human),
who fills creative params (bubble texts, chart values) and accepts or
rejects each candidate. Poster captions remain the default everywhere
else; full-bleed budget and cadence are enforced later by validate.py.

Usage:
  python3 motion/assign.py <words.json> [--out proposal.json]
words.json: {"words": [{"text","start","end"}, ...]} (base transcript)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

NUM = re.compile(r"^(\d[\d,]*(?:\.\d+)?)(%?)$")
PLACES = {"cornell", "harvard", "yale", "princeton", "columbia", "stanford",
          "mit", "nyu", "ucla", "oxford", "cambridge"}
PEOPLE_NOUNS = {"men", "women", "people", "guys", "girls", "users",
                "followers", "students", "members", "friends"}
CHAT_WORDS = {"chat", "text", "texted", "texting", "message", "messages",
              "dm", "dms", "group"}
WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}


def _num(tok: str):
    m = NUM.match(tok.strip(".,!?\"'()"))
    if not m:
        return None, False
    return float(m.group(1).replace(",", "")), bool(m.group(2))


def propose(words: list[dict], duration: float) -> list[dict]:
    out: list[dict] = []
    used: list[tuple[float, float]] = []

    def free(at: float, until: float) -> bool:
        return all(until <= a + 0.05 or at >= u - 0.05 for a, u in used)

    def add(item: dict, reason: str, anchor: str):
        item = dict(item)
        item["_reason"] = reason
        item["_anchor"] = anchor
        out.append(item)
        used.append((item["at"], item["until"]))

    texts = [w["text"].strip(".,!?\"'()").lower() for w in words]
    for i, w in enumerate(words):
        t = texts[i]
        ctx = " ".join(texts[max(0, i - 4): i + 5])
        at = float(w["start"])
        # --- "hundred percent" / 100% -> gauge --------------------------------
        if (t in ("hundred", "100") and "percent" in ctx) or t == "100%":
            s, u = round(at - 0.15, 2), round(at + 2.15, 2)
            if free(s, u):
                add({"type": "vector", "name": "gauge", "mode": "fullbleed",
                     "value": 100, "label": "HUNDRED PERCENT",
                     "at": s, "until": u},
                    "certainty stated as a number", w["text"])
            continue
        # --- numbers -----------------------------------------------------------
        val, pct = _num(w["text"])
        if val is not None and val >= 2:
            noun = next((x for x in texts[i:i + 4] if x in PEOPLE_NOUNS), None)
            s = round(max(0.0, at - 0.9), 2)
            if noun and val >= 5 and val == int(val):
                u = round(at + 1.6, 2)
                if free(s, u):
                    add({"type": "vector", "name": "people", "mode": "fullbleed",
                         "count": int(val), "total": int(val),
                         "label": f"{noun} ".upper() + "IN THE GROUP CHAT"
                         if "chat" in ctx else noun.upper(),
                         "at": s, "until": u},
                        f"crowd quantity: {int(val)} {noun}", w["text"])
                    continue
            if any(x in ctx for x in ("$", "dollars", "dollar", "price",
                                       "cost", "bucks", "paid", "pay")):
                # a number in money context is a price, not a stat:
                # the tag swings in and the amount counts onto it
                u = round(at + 2.1, 2)
                if free(s, u):
                    add({"type": "vector", "name": "price", "mode": "fullbleed",
                         "value": int(val) if val == int(val) else val,
                         "prefix": "$", "label": "THE PRICE",
                         "at": s, "until": u},
                        "an amount of money - tag it", w["text"])
                    continue
            u = round(at + 1.8, 2)
            if free(s, u):
                add({"type": "counter", "value": int(val) if val == int(val) else val,
                     "label": "", "countDur": 0.9, "zone": [0.60, 0.84],
                     "at": s, "until": u},
                    "spoken number lands here", w["text"])
                continue
        # --- group chat / messaging -> chat ------------------------------------
        if t in CHAT_WORDS and "chat" in ctx:
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u) and not any(o.get("name") == "chat" for o in out):
                add({"type": "vector", "name": "chat", "mode": "fullbleed",
                     "title": "GROUP CHAT",
                     "messages": [{"text": "...", "me": False},
                                  {"text": "...", "me": True},
                                  {"text": "...", "me": False}],
                     "_note": "fill bubble texts with what was actually sent",
                     "at": s, "until": u},
                    "a chat is being talked about - show the chat", w["text"])
                continue
        # --- circle / network ---------------------------------------------------
        if t in ("network", "circle", "connections", "networking"):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u):
                add({"type": "vector", "name": "network", "mode": "fullbleed",
                     "count": 8, "title": "YOU", "label": "THE CIRCLE",
                     "at": s, "until": u},
                    "a network/circle is the subject", w["text"])
                continue
        # --- a named place -> map ------------------------------------------------
        if t in PLACES:
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u):
                add({"type": "vector", "name": "map", "mode": "fullbleed",
                     "place": w["text"].strip(".,!?").upper(),
                     "label": "WHERE IT HAPPENED", "at": s, "until": u},
                    "a named place anchors the story", w["text"])
                continue
        # --- a weekday -> calendar ----------------------------------------------
        if t in WEEKDAYS:
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u) and not any(o.get("name") == "calendar" for o in out):
                add({"type": "vector", "name": "calendar", "mode": "fullbleed",
                     "day": WEEKDAYS[t], "label": t.upper(),
                     "at": s, "until": u},
                    "a specific day is named - light it up", w["text"])
                continue
        # --- a time of day -> clock ----------------------------------------------
        if t in ("o'clock", "midnight", "noon") or (
                t in ("minutes", "hours") and _num(words[i - 1]["text"])[0]):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u) and not any(o.get("name") == "clock" for o in out):
                add({"type": "vector", "name": "clock", "mode": "fullbleed",
                     "title": "", "sweep": 1,
                     "_note": "set title to the spoken time",
                     "at": s, "until": u},
                    "a time is stated - show the clock", w["text"])
                continue
        # --- money -> price tag ----------------------------------------------------
        if t.startswith("$") or t in ("price", "cost", "costs", "dollars",
                                      "bucks", "expensive"):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u):
                add({"type": "vector", "name": "price", "mode": "fullbleed",
                     "value": 0, "prefix": "$",
                     "_note": "set value to the spoken amount",
                     "at": s, "until": u},
                    "money is the subject - tag it", w["text"])
                continue
        # --- attraction -> magnet ---------------------------------------------------
        if t in ("attract", "attracts", "attracted", "attraction",
                 "attractive", "magnetic", "magnet"):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u):
                add({"type": "vector", "name": "magnet", "mode": "fullbleed",
                     "count": 9, "label": "ATTRACTION",
                     "at": s, "until": u},
                    "attraction is the metaphor - filings fly in", w["text"])
                continue
        # --- aim -> target ------------------------------------------------------------
        if t in ("target", "goal", "goals", "aim", "focus", "focused"):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u):
                add({"type": "vector", "name": "target", "mode": "fullbleed",
                     "label": t.upper(), "at": s, "until": u},
                    "an aim is stated - strike the target", w["text"])
                continue
        # --- feeling -> heart ------------------------------------------------------------
        if t in ("love", "loved", "heart", "hearts", "feelings"):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u):
                add({"type": "vector", "name": "heart", "mode": "fullbleed",
                     "label": t.upper(), "at": s, "until": u},
                    "an emotional beat - let it beat", w["text"])
                continue
        # --- warning -> alert ---------------------------------------------------------------
        if t in ("warning", "danger", "dangerous", "mistake", "mistakes"):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u):
                add({"type": "vector", "name": "alert", "mode": "fullbleed",
                     "label": t.upper(), "at": s, "until": u},
                    "a warning lands - shake the sign", w["text"])
                continue
        # --- structure -> chapter marker -------------------------------------------------------
        if t == "chapter" or (t == "part" and i + 1 < len(texts)
                              and texts[i + 1] in ("one", "two", "three", "1", "2", "3")):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u):
                add({"type": "vector", "name": "chapter", "mode": "fullbleed",
                     "index": 1, "total": 3, "title": "",
                     "_note": "set index/total/title from the structure",
                     "at": s, "until": u},
                    "a structural break - mark the chapter", w["text"])
                continue
        # --- a call -> phone (it rings) ------------------------------------------
        if t in ("call", "called", "calling", "phone", "rang", "facetime",
                 "facetimed"):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u) and not any(o.get("name") == "phone" for o in out):
                add({"type": "vector", "name": "phone", "mode": "fullbleed",
                     "title": "", "label": "THE CALL",
                     "_note": "set title to the caller ('HER', 'MOM'...)",
                     "at": s, "until": u},
                    "a call happens - show the phone ringing", w["text"])
                continue
        # --- notifications -> bell ------------------------------------------------
        if t in ("notification", "notifications", "alerts"):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u) and not any(o.get("name") == "bell" for o in out):
                add({"type": "vector", "name": "bell", "mode": "fullbleed",
                     "count": 3, "label": "BLOWING UP",
                     "_note": "set count to the spoken number of pings",
                     "at": s, "until": u},
                    "notifications stack up - ring the bell", w["text"])
                continue
        # --- "the key" -> key ------------------------------------------------------
        if t == "key" and i > 0 and texts[i - 1] == "the":
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u):
                add({"type": "vector", "name": "key", "mode": "fullbleed",
                     "label": "THE KEY", "at": s, "until": u},
                    "'the key' is named - slide it into the lock", w["text"])
                continue
        # --- takeoff -> rocket -------------------------------------------------------
        if t in ("launched", "launch", "viral") or t.startswith("skyrocket"):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u):
                add({"type": "vector", "name": "rocket", "mode": "fullbleed",
                     "label": t.upper(), "at": s, "until": u},
                    "takeoff/growth - launch it", w["text"])
                continue
        # --- literal metaphors: show the analogy itself ----------------------
        if t in ("cow", "cows", "sheep", "herd") or \
                (t in ("stand", "stands") and "out" in ctx):
            s, u = round(max(0.0, at - 0.1), 2), round(at + 1.6, 2)
            if free(s, u) and not any(o.get("name") == "cowfield" for o in out):
                add({"type": "vector", "name": "cowfield", "mode": "fullbleed",
                     "label": "ONE STANDS OUT", "at": s, "until": u},
                    "the herd/stand-out analogy - show it, one turns "
                    "the accent on the point", w["text"])
                continue
        if t in ("road", "drive", "drives", "driving", "drove", "highway"):
            s, u = round(max(0.0, at - 0.1), 2), round(at + 1.6, 2)
            if free(s, u) and not any(o.get("name") == "roadcar" for o in out):
                add({"type": "vector", "name": "roadcar", "mode": "fullbleed",
                     "label": "DOWN THE ROAD", "at": s, "until": u},
                    "driving is the analogy - a car crosses the frame",
                    w["text"])
                continue
        # --- a win -> trophy -----------------------------------------------------------
        if t in ("trophy", "won", "winner", "champion", "championship"):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u) and not any(o.get("name") == "trophy" for o in out):
                add({"type": "vector", "name": "trophy", "mode": "fullbleed",
                     "label": "THE WIN", "at": s, "until": u},
                    "a win is claimed - raise the cup", w["text"])
                continue
        # --- searching -> search ---------------------------------------------------------
        if t in ("search", "searching", "searches"):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u):
                add({"type": "vector", "name": "search", "mode": "fullbleed",
                     "label": "LOOKING", "at": s, "until": u},
                    "a search is on - scan with the glass", w["text"])
                continue
        # --- money (general) -> cash -------------------------------------------------------
        if t in ("money", "cash", "rich", "wealth", "wealthy"):
            s, u = round(at - 0.2, 2), round(at + 2.1, 2)
            if free(s, u) and not any(o.get("name") == "cash" for o in out):
                add({"type": "vector", "name": "cash", "mode": "fullbleed",
                     "label": "THE MONEY",
                     "_note": "set value to the spoken amount if one is named",
                     "at": s, "until": u},
                    "money as a thing - fan the bills (an amount is a price)",
                    w["text"])
                continue
        # --- suggestions (creative params are prose; the author fills them) ----------------------
        if t in ("rules", "steps", "checklist", "habits", "routine"):
            out.append({"_suggest": "checklist", "_anchor": w["text"],
                        "_reason": "a set of rules/steps - tick them off",
                        "at": round(at, 2)})
        if t in ("downside", "drawback", "pros", "cons", "advantage"):
            out.append({"_suggest": "proscons", "_anchor": w["text"],
                        "_reason": "two sides are weighed - split the screen",
                        "at": round(at, 2)})
        if t in ("funnel", "filter", "filters", "filtered", "screen"):
            out.append({"_suggest": "funnel", "_anchor": w["text"],
                        "_reason": "drop-off/filtering - many in, few out",
                        "at": round(at, 2)})
        if t in ("hierarchy", "pyramid", "elite", "levels"):
            out.append({"_suggest": "pyramid", "_anchor": w["text"],
                        "_reason": "a hierarchy is described - stack it",
                        "at": round(at, 2)})
        if t in ("energy", "tired", "exhausted", "drained", "battery"):
            out.append({"_suggest": "battery", "_anchor": w["text"],
                        "_reason": "an energy level is felt - show the charge",
                        "at": round(at, 2)})
        if t == "one" and i > 0 and texts[i - 1] == "number":
            out.append({"_suggest": "podium", "_anchor": "number one",
                        "_reason": "a ranking peaks - podium finish",
                        "at": round(at, 2)})
        if t in ("weigh", "weighing", "balance", "balanced"):
            out.append({"_suggest": "scale", "_anchor": w["text"],
                        "_reason": "two options weighed - tip the beam "
                                   "(left/right = the two claims)",
                        "at": round(at, 2)})
        if t in ("mindset", "psychology", "brain", "mentality", "thinking"):
            out.append({"_suggest": "brain", "_anchor": w["text"],
                        "_reason": "it's in the head - draw the brain",
                        "at": round(at, 2)})
        if t in ("door", "doors", "opportunity", "opportunities"):
            out.append({"_suggest": "door", "_anchor": w["text"],
                        "_reason": "an opening appears - swing the door",
                        "at": round(at, 2)})
        if t in ("gamble", "gambling", "bet", "dice", "risky"):
            out.append({"_suggest": "dice", "_anchor": w["text"],
                        "_reason": "a chance is taken - roll the dice",
                        "at": round(at, 2)})
        if t == "common" and ("ground" in ctx or " in " in f" {ctx} "):
            out.append({"_suggest": "venn", "_anchor": w["text"],
                        "_reason": "common ground - overlap the circles "
                                   "(labels = the two sides + the overlap)",
                        "at": round(at, 2)})
        if t in ("protect", "protected", "safe", "safety", "boundaries",
                 "guard"):
            out.append({"_suggest": "shield", "_anchor": w["text"],
                        "_reason": "protection/boundaries - raise the shield",
                        "at": round(at, 2)})
        if t == "out" and i > 0 and texts[i - 1] == "running":
            out.append({"_suggest": "hourglass", "_anchor": "running out",
                        "_reason": "time is running out - drain the glass",
                        "at": round(at, 2)})
        if t in ("podcast", "voice", "recording", "audio"):
            out.append({"_suggest": "wave", "_anchor": w["text"],
                        "_reason": "a voice/podcast moment - show the waveform",
                        "at": round(at, 2)})
        if t in ("spotlight", "attention", "eyes", "famous"):
            out.append({"_suggest": "spotlight", "_anchor": w["text"],
                        "_reason": "all eyes on them - sweep the spotlight",
                        "at": round(at, 2)})
        if t in ("level", "levels", "leveling", "levelling", "climb",
                 "climbing", "ladder") and "up" in ctx:
            out.append({"_suggest": "ladder", "_anchor": w["text"],
                        "_reason": "levelling up - climb the rungs "
                                   "(count = the levels)",
                        "at": round(at, 2)})
        if t in ("stars", "rating", "rated", "ten", "perfect"):
            out.append({"_suggest": "stars", "_anchor": w["text"],
                        "_reason": "a rating is implied - fill the stars "
                                   "(value = the score out of 5)",
                        "at": round(at, 2)})
        if t == "countdown" or (t == "days" and "left" in texts[i:i + 3]):
            out.append({"_suggest": "countdown", "_anchor": w["text"],
                        "_reason": "a deadline counts down - burn the digits "
                                   "(value = where it starts)",
                        "at": round(at, 2)})
        if t in ("king", "crown", "boss", "alpha"):
            out.append({"_suggest": "crown", "_anchor": w["text"],
                        "_reason": "top-dog status - drop the crown",
                        "at": round(at, 2)})
        if t in ("bridge", "connect", "connects", "gap", "between"):
            out.append({"_suggest": "bridge", "_anchor": w["text"],
                        "_reason": "a gap gets closed - draw the bridge",
                        "at": round(at, 2)})
        if t in ("fit", "fits", "puzzle", "compatible", "match"):
            out.append({"_suggest": "puzzle", "_anchor": w["text"],
                        "_reason": "a fit/compatibility call - click the "
                                   "pieces (labels = the two sides)",
                        "at": round(at, 2)})
        if t in ("cycle", "loop", "routine", "habit", "daily"):
            out.append({"_suggest": "cycle", "_anchor": w["text"],
                        "_reason": "a repeating loop - spin the cycle",
                        "at": round(at, 2)})
        if t in ("heating", "temperature", "hotter", "rising"):
            out.append({"_suggest": "thermo", "_anchor": w["text"],
                        "_reason": "it's heating up - climb the mercury "
                                   "(value = how hot, 0-100)",
                        "at": round(at, 2)})
        if t == "before" and "after" in texts[i:i + 7]:
            out.append({"_suggest": "beforeafter", "_anchor": w["text"],
                        "_reason": "a before/after contrast - split panels",
                        "at": round(at, 2)})
        # --- enumeration -> list (typography, no face cost) ----------------------
        if t in ("first", "second", "third") and i > 0 and texts[i - 1] in (
                "the", "a", "is", "was"):
            out.append({"_suggest": "list", "_anchor": w["text"],
                        "_reason": "enumeration begins - list plates fit",
                        "at": round(at, 2)})
    return sorted(out, key=lambda o: o["at"])


def main() -> int:
    src = json.loads(Path(sys.argv[1]).read_text())
    words = src["words"] if isinstance(src, dict) else src
    dur = float(src.get("duration") or words[-1]["end"]) if words else 0.0
    prop = propose(words, dur)
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    text = json.dumps(prop, indent=1)
    if out:
        Path(out).write_text(text)
    for p in prop:
        kind = p.get("name") or p.get("type") or p.get("_suggest")
        print(f"{p['at']:>6.2f}s  {kind:<8}  {p['_reason']}  "
              f"(anchor: {p['_anchor']!r})")
    print(f"{len(prop)} proposals -> {out or 'stdout'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
