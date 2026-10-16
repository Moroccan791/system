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
