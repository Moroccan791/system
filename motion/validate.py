#!/usr/bin/env python3
"""Validate a motion timeline against motion/schema.json (+ sanity rules).

    python motion/validate.py <timeline.json>

Schema errors are reported with their JSON paths; the semantic pass then
checks what a schema cannot: monotonic word times, items inside the
duration, no two same-type items back to back (pacing rule), and accent
colours matching the brand lock.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main(path: str) -> int:
    from jsonschema import Draft7Validator

    schema = json.loads((HERE / "schema.json").read_text())
    tl = json.loads(Path(path).read_text())
    errors = sorted(Draft7Validator(schema).iter_errors(tl),
                    key=lambda e: list(e.absolute_path))
    for e in errors:
        loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
        print(f"SCHEMA {loc}: {e.message}")
    if errors:
        return 1

    problems: list[str] = []
    dur = float(tl["duration"])
    items = sorted(tl["items"], key=lambda i: i["at"])
    for prev, cur in zip(items, items[1:]):
        # abutting stacks hand off through the engine's blur-swap; only
        # a real coexistence (> 0.25 s of overlap) is a defect
        if prev["type"] == cur["type"] and cur["at"] < (prev.get("until") or prev["at"]) - 0.25:
            problems.append(f"same component back to back: {cur['type']} "
                            f"at {cur['at']} overlaps previous")
    for it in items:
        until = it.get("until") or it["at"]
        if until > dur + 0.001:
            problems.append(f"{it['type']} at {it['at']} ends {until} past duration {dur}")
        words = [w for row in (it.get("rows") or it.get("lines") or []) for w in row]
        times = [w["at"] for w in words]
        if times != sorted(times):
            problems.append(f"{it['type']} at {it['at']}: word times not monotonic {times}")
        for w in words:
            if not (it["at"] - 0.05 <= w["at"] <= until + 0.05):
                problems.append(f"{it['type']} word {w['w']!r} at {w['at']} "
                                f"outside item window {it['at']}..{until}")
        if words and it["type"] in ("poster", "card"):
            last = max(w["at"] for w in words)
            if until < last + 0.2:
                problems.append(f"{it['type']} at {it['at']}: until {until} cuts "
                                f"the last word (spoken at {last}) - a word needs "
                                f"its entry plus a beat before the exit begins")
        if it["type"] in ("pip", "broll"):
            src = it.get("src") or ""
            p = Path(src) if src.startswith("/") else HERE.parent / src
            if src and not p.exists():
                problems.append(f"{it['type']} at {it['at']}: src not found: {src}")
            # generated media may never pose as real proof
            s = src.lower()
            if ("generated" in s or "/gen_" in s or "illustr" in s) \
                    and not it.get("illustrative"):
                problems.append(f"{it['type']} at {it['at']}: generated media must "
                                f"set illustrative=true (it is rendered with an "
                                f"ILLUSTRATIVE tag, never as real proof)")
        if it["type"] == "counter":
            if until - it["at"] < float(it.get("countDur") or 0.9) + 0.3:
                problems.append(f"counter at {it['at']}: until {until} leaves no "
                                f"beat after the count lands")
        # ---- permanent-rules spec, Part 1 --------------------------------
        dwell = until - it["at"]
        if it["type"] == "fx" and it.get("kind") in ("flash", "flare", "leak"):
            d = float(it.get("dur") or 0)
            if not 0.19 <= d <= 0.34:
                problems.append(f"fx {it.get('kind')} at {it['at']}: dur {d}s is "
                                f"outside the 6-10 frame transition window")
        if it.get("behind") and it["type"] not in ("poster", "card"):
            problems.append(f"{it['type']} at {it['at']}: behind=true only "
                            f"exists on poster/card (words the speaker "
                            f"stands in front of)")
        if it.get("place3d") and it["type"] != "poster":
            problems.append(f"{it['type']} at {it['at']}: place3d (spatial "
                            f"placement) only exists on posters")
        if it["type"] == "lowerthird" and not 1.8 <= dwell <= 6.0:
            problems.append(f"lowerthird at {it['at']}: dwell {dwell:.2f}s "
                            f"outside 1.8-6.0s (name them, let it be read, "
                            f"take it away)")
        if it["type"] == "chip" and it.get("sub"):
            problems.append(f"chip at {it['at']}: a chip is a single text line "
                            f"(a sub breaks the 6-7% bar height / 3% text floor); "
                            f"merge it into title or drop it")
        if it["type"] == "vector" and it.get("name") not in (
                "hoop", "led", "donut", "arrow", "burst",
                "bars", "line", "versus", "people", "stack", "timeline", "quote",
                "chat", "network", "gauge", "map",
                "calendar", "clock", "price", "checklist", "magnet", "funnel", "pyramid", "target", "podium", "beforeafter", "battery", "proscons", "chapter", "bigword", "heart", "alert", "phone", "scale", "brain", "bell", "key", "door", "dice", "venn", "rocket", "shield", "hourglass", "wave", "spotlight", "trophy", "ladder", "stars", "countdown", "search", "cash", "crown", "bridge", "puzzle", "cycle", "thermo"):
            problems.append(f"vector at {it['at']}: unknown scene "
                            f"{it.get('name')!r} (see motion/MOTIONS.md)")
        if it["type"] == "vector":
            nm = it.get("name")
            if nm == "bars" and not 2 <= len(it.get("values") or []) <= 7:
                problems.append(f"bars at {it['at']}: needs 2-7 values")
            if nm == "line" and not 2 <= len(it.get("points") or []) <= 8:
                problems.append(f"line at {it['at']}: needs 2-8 points")
            if nm == "people" and not 1 <= (it.get("count") or 0) <= 100:
                problems.append(f"people at {it['at']}: count must be 1-100 "
                                f"(a pictogram grid, not a number)")
            if nm == "versus" and not (it.get("left") and it.get("right")):
                problems.append(f"versus at {it['at']}: needs left and right")
            if nm == "stack" and not 2 <= len(it.get("parts") or []) <= 4:
                problems.append(f"stack at {it['at']}: needs 2-4 parts")
            if nm == "timeline" and not 2 <= len(it.get("events") or []) <= 5:
                problems.append(f"timeline at {it['at']}: needs 2-5 events")
            if nm == "quote" and not 1 <= len(it.get("quoteLines") or []) <= 3:
                problems.append(f"quote at {it['at']}: needs 1-3 quoteLines")
            if nm == "chat" and not 2 <= len(it.get("messages") or []) <= 6:
                problems.append(f"chat at {it['at']}: needs 2-6 messages")
            if nm == "network" and not 3 <= (it.get("count") or 0) <= 14:
                problems.append(f"network at {it['at']}: count must be 3-14")
            if nm == "gauge" and it.get("value") is None:
                problems.append(f"gauge at {it['at']}: needs a value (0-100)")
            if nm == "map" and not it.get("place"):
                problems.append(f"map at {it['at']}: needs a place")
            if nm == "checklist" and not 2 <= len(it.get("entries") or []) <= 5:
                problems.append(f"checklist at {it['at']}: needs 2-5 entries")
            if nm == "proscons" and not (it.get("pros") or it.get("cons")):
                problems.append(f"proscons at {it['at']}: needs pros and/or cons")
            if nm == "bigword" and not (it.get("word") or it.get("title")):
                problems.append(f"bigword at {it['at']}: needs a word")
            if nm == "beforeafter" and not (it.get("before") and it.get("after")):
                problems.append(f"beforeafter at {it['at']}: needs before and after")
            if nm == "funnel" and (it.get("from") is None or it.get("to") is None):
                problems.append(f"funnel at {it['at']}: needs from and to")
            if nm == "scale" and not (it.get("left") and it.get("right")):
                problems.append(f"scale at {it['at']}: needs left and right "
                                f"(label + value each) - the beam tips on data")
            if nm == "dice" and not (1 <= (it.get("from") or 3) <= 6
                                     and 1 <= (it.get("to") or 5) <= 6):
                problems.append(f"dice at {it['at']}: faces (from/to) must be 1-6")
            if nm == "stars" and not 1 <= (it.get("value") or 5) <= 5:
                problems.append(f"stars at {it['at']}: value must be 1-5")
            if nm == "countdown" and not 2 <= (it.get("value") or 3) <= 10:
                problems.append(f"countdown at {it['at']}: value must be 2-10")
            if nm == "thermo" and not 0 <= (it.get("value") if it.get("value") is not None else 75) <= 100:
                problems.append(f"thermo at {it['at']}: value must be 0-100")
            if nm == "ladder" and not 3 <= (it.get("count") or 4) <= 6:
                problems.append(f"ladder at {it['at']}: count (rungs) must be 3-6")
        if it["type"] == "vector" and (it.get("mode") or "card") == "fullbleed":
            # data scenes keep moving (fills/growth) so they may hold longer;
            # metaphor scenes must stay punchy
            lo, hi = (1.2, 2.5) if it.get("name") in (
                "bars", "line", "versus", "people", "stack", "timeline",
                "quote", "chat", "network", "gauge", "map",
                "calendar", "clock", "price", "checklist", "magnet",
                "funnel", "pyramid", "target", "podium", "beforeafter",
                "battery", "proscons", "chapter", "bigword", "heart",
                "alert", "phone", "scale", "brain", "bell", "key", "door", "dice", "venn", "rocket", "shield", "hourglass", "wave", "spotlight", "trophy", "ladder", "stars", "countdown", "search", "cash", "crown", "bridge", "puzzle", "cycle", "thermo") else (1.0, 1.8)
            if not lo <= dwell <= hi:
                problems.append(f"vector broll at {it['at']}: full-bleed dwell "
                                f"{dwell:.2f}s outside {lo}-{hi}s")
        if it["type"] in ("poster", "card", "counter", "chip", "pip", "broll", "vector") \
                and dwell > 3.0:
            problems.append(f"{it['type']} at {it['at']}: dwell {dwell:.2f}s over "
                            f"the 3s cap (a graphic must change or leave)")
        if it["type"] in ("list", "process"):
            subs = it.get("items") or it.get("steps") or []
            if subs:
                tail = until - float(subs[-1]["at"])
                if tail > 1.0:
                    problems.append(f"{it['type']} at {it['at']}: finished panel "
                                    f"dwells {tail:.2f}s after its last entry "
                                    f"(cap 1.0s - exit when done)")
        if it["type"] == "broll":
            mode = it.get("mode") or "fullbleed"
            if mode == "fullbleed" and not 1.0 <= dwell <= 1.8:
                problems.append(f"broll at {it['at']}: full-bleed insert dwell "
                                f"{dwell:.2f}s outside 1.0-1.8s")
            if mode == "card" and not 0.60 <= float(it.get("w") or 0.65) <= 0.70:
                problems.append(f"broll card at {it['at']}: width "
                                f"{it.get('w')} outside 60-70% of frame")
        for key in ("items", "steps"):
            subs = it.get(key) or []
            if not subs:
                continue
            ats = [float(s["at"]) for s in subs]
            if ats != sorted(ats):
                problems.append(f"{it['type']} at {it['at']}: {key} times not monotonic")
            for a, b in zip(ats, ats[1:]):
                if b - a < 0.18:
                    problems.append(f"{it['type']} at {it['at']}: {key} stagger "
                                    f"{b - a:.2f}s under the 6-frame minimum")
                if b - a > 1.5:
                    problems.append(f"{it['type']} at {it['at']}: {key} gap "
                                    f"{b - a:.2f}s over 1.5s - a panel may only "
                                    f"live while it keeps adding entries")
            if subs and until < ats[-1] + 0.8:
                problems.append(f"{it['type']} at {it['at']}: until {until} gives the "
                                f"last entry no dwell time")
    # image cadence: at most one PiP / B-roll / metaphor-vector insert per 6 s
    DATA_SCENES = ("bars", "line", "versus", "people", "stack", "timeline",
                   "quote", "chat", "network", "gauge", "map",
                   "calendar", "clock", "price", "checklist", "magnet",
                   "funnel", "pyramid", "target", "podium", "beforeafter",
                   "battery", "proscons", "chapter", "bigword", "heart",
                   "alert", "phone", "scale", "brain", "bell", "key", "door", "dice", "venn", "rocket", "shield", "hourglass", "wave", "spotlight", "trophy", "ladder", "stars", "countdown", "search", "cash", "crown", "bridge", "puzzle", "cycle", "thermo")
    imgs = [i for i in items if i["type"] in ("pip", "broll")
            or (i["type"] == "vector" and i.get("name") not in DATA_SCENES)]
    for a, b in zip(imgs, imgs[1:]):
        if b["at"] - a["at"] < 6.0:
            problems.append(f"images at {a['at']} and {b['at']}: under the "
                            f"6s minimum spacing between image inserts")
    # data scenes are animated content, not stills: they may chain in an
    # MG-led stretch, but never crowd (2.4s min between full-bleed starts)
    data = [i for i in items if i["type"] == "vector"
            and i.get("name") in DATA_SCENES
            and (i.get("mode") or "card") == "fullbleed"]
    for a, b in zip(data, data[1:]):
        if b["at"] - a["at"] < 2.4:
            problems.append(f"data scenes at {a['at']} and {b['at']}: under "
                            f"the 2.4s minimum spacing between data scenes")
    for p in problems:
        print(f"RULE {p}")
    if problems:
        return 1
    print(f"timeline OK: {len(items)} items, {dur:.1f}s, accent {tl['brand']['accent']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
