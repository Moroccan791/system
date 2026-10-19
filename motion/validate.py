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
            show_at = w.get("showAt")
            if show_at is not None:
                if not (it["at"] - 0.05 <= show_at <= until + 0.05):
                    problems.append(f"{it['type']} word {w['w']!r} showAt {show_at} "
                                    f"outside item window {it['at']}..{until}")
                if show_at > w["at"] + 0.005:
                    problems.append(f"{it['type']} word {w['w']!r} showAt {show_at} "
                                    f"is after its spoken time {w['at']}")
                if w["at"] - show_at > 1.5:
                    problems.append(f"{it['type']} word {w['w']!r} is revealed "
                                    f"{w['at'] - show_at:.2f}s early (cap 1.5s)")
        if words and it["type"] in ("poster", "card"):
            last = max(w["at"] for w in words)
            # Speech has some <250ms handoffs. A hard-out caption can
            # leave after 120ms to avoid coexisting with the next
            # caption's 2-frame anticipatory entry. A normal caption
            # still needs the full 200ms readable beat.
            floor = 0.12 if it.get("hardOut") else 0.2
            if until < last + floor - 0.001:
                problems.append(f"{it['type']} at {it['at']}: until {until} cuts "
                                f"the last word (spoken at {last}) - a word needs "
                                f"its entry plus a beat before the exit begins")
        if it["type"] in ("pip", "broll", "proof", "phone"):
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
        # ---- highest-level additions (proof / phone / doodle / marker) --
        if it["type"] == "proof":
            if not 1.5 <= dwell <= 7.0:
                problems.append(f"proof at {it['at']}: dwell {dwell:.2f}s "
                                f"outside 1.5-7.0s (land the receipt, let "
                                f"it be read, take it away)")
            phr = it.get("phrases") or []
            pats = [float(p["at"]) for p in phr]
            if pats != sorted(pats):
                problems.append(f"proof at {it['at']}: phrase times not monotonic")
            for p in phr:
                if not (it["at"] - 0.05 <= float(p["at"]) <= until + 0.05):
                    problems.append(f"proof phrase {p['text'][:24]!r} at "
                                    f"{p['at']} outside the card window")
            if phr and until - pats[-1] > 2.5:
                problems.append(f"proof at {it['at']}: card dwells "
                                f"{until - pats[-1]:.1f}s after its last "
                                f"phrase (cap 2.5s - the highlight is "
                                f"the event, then it leaves)")
            if it.get("hotBox") and it.get("hotAt") is None:
                problems.append(f"proof at {it['at']}: hotBox without "
                                f"hotAt (the box must land on the spoken "
                                f"moment, not float)")
            if it.get("value") is not None and until - it["at"] < \
                    float(it.get("countDur") or 0.9) + 0.3:
                problems.append(f"proof at {it['at']}: no beat after "
                                f"its count-up lands")
        if it["type"] == "phone":
            if not 1.2 <= dwell <= 6.0:
                problems.append(f"phone at {it['at']}: dwell {dwell:.2f}s "
                                f"outside 1.2-6.0s (a scroll, not a scene)")
        if it["type"] == "doodle":
            if not 0.6 <= dwell <= 3.5:
                problems.append(f"doodle at {it['at']}: dwell {dwell:.2f}s "
                                f"outside 0.6-3.5s (point, then vanish)")
        marker_kinds = {"mark", "pay", "grad"}
        if it["type"] in ("poster", "card") and (
                it.get("captionStyle") in ("marker", "impact")
                or any(w.get("kind") in marker_kinds for w in words)):
            problems.append(f"{it['type']} at {it['at']}: marker-swipe and "
                            "rejected impact captions are unavailable for new work")
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
        if it["type"] == "hook":
            if it["at"] > 0.05:
                problems.append(f"hook at {it['at']}: a hook slate opens "
                                f"the video (at must be ~0)")
            if not 0.9 <= dwell <= 1.8:
                problems.append(f"hook at {it['at']}: dwell {dwell:.2f}s "
                                f"outside 0.9-1.8s (promise fast, then "
                                f"get out of the way)")
        if it["type"] == "endcard":
            if not 1.0 <= dwell <= 1.6:
                problems.append(f"endcard at {it['at']}: dwell {dwell:.2f}s "
                                f"outside 1.0-1.6s (a sting, not a scene)")
            if until < dur - 0.35:
                problems.append(f"endcard at {it['at']}: must be tail-"
                                f"anchored (end within the last 0.35s)")
        if it["type"] == "fx" and it.get("kind") == "punch":
            d = float(it.get("dur") or 0)
            if not 0.25 <= d <= 0.6:
                problems.append(f"punch at {it['at']}: dur {d}s outside "
                                f"0.25-0.6s (a punch is a blink, not a zoom)")
        if it["type"] == "fx" and it.get("kind") == "freeze":
            d = float(it.get("dur") or 0)
            if not 0.3 <= d <= 1.0:
                problems.append(f"freeze at {it['at']}: dur {d}s outside "
                                f"0.3-1.0s (hold the beat, then move)")
        # text may never render off-frame: estimate every row's
        # rendered width with the engine's own model (0.62em average
        # advance, hero shrink floor 110px, stack autofit 0.88/0.94)
        if it["type"] in ("poster", "card"):
            sizes = {"hero": float(it.get("heroSize") or 250),
                     "key": float(it.get("keySize") or 118),
                     "neon": float(it.get("keySize") or 118),
                     "word": float(it.get("wordSize") or 96),
                     "conn": float(it.get("connSize") or 58)}
            row_est = []
            for row in (it.get("rows") or it.get("lines") or []):
                est = 0.0
                for w in row:
                    kind = w.get("kind") or "conn"
                    size = float(w.get("size")
                                 or it.get("wordSize")
                                 or (sizes.get(kind, 58)
                                     if it["type"] == "poster" else 120))
                    if kind == "hero":
                        # engine: hero shrinks (floor 110px) until it
                        # alone fits 78% of the frame
                        size = max(110.0, min(
                            size, 0.78 * 1080 / max(len(w["w"]), 1)
                            / 0.62))
                    est += len(w["w"]) * size * 0.62 \
                        + (26 if kind == "key" else 16)
                row_est.append(est)
            if row_est:
                widest = max(row_est)
                scale = min(1.0, (0.94 if it.get("behind") else 0.88)
                            * 1080 / widest)
                if widest * scale > 1060:
                    problems.append(
                        f"{it['type']} at {it['at']}: a row renders "
                        f"~{widest * scale:.0f}px wide in a 1080 frame - "
                        f"shorten the hero word, split the row, or "
                        f"lower heroSize (text may not leave the screen)")
            # a graphic lives exactly as long as its spoken phrase:
            # the moment the words end, it starts leaving
            if words:
                last_at = max(w["at"] for w in words)
                cap = 1.2 if it["type"] == "card" else 1.0
                if until - last_at > cap:
                    problems.append(
                        f"{it['type']} at {it['at']}: outstays its "
                        f"phrase by {until - last_at:.1f}s after the "
                        f"last word (cap {cap}s) - end it with the "
                        f"speech, not after it")
        if it.get("behind") and it["type"] == "poster":
            # the silhouette eats whatever is not wider than the body
            # at that height: hero must be a flanking phrase anchored
            # at head height (hardcoded from the matte, not taste)
            heroes = [w for r in (it.get("rows") or []) for w in r
                      if w.get("kind") == "hero"]
            if heroes:
                hero_row = max(
                    (r for r in it["rows"]
                     if any(w.get("kind") == "hero" for w in r)),
                    key=lambda r: sum(len(w["w"]) for w in r
                                      if w.get("kind") == "hero"))
                n_hero = sum(1 for w in hero_row
                             if w.get("kind") == "hero")
                longest = max(len(w["w"]) for w in hero_row
                              if w.get("kind") == "hero")
                if n_hero < 2 and longest < 8:
                    problems.append(
                        f"behind poster at {it['at']}: a lone short "
                        f"hero word disappears behind the speaker - "
                        f"use a >=2-word hero row (it must flank the "
                        f"silhouette, like '57 MEN', not hide behind it)")
                zone = it.get("zone") or [0.30, 0.42]
                if (zone[0] + zone[1]) / 2 > 0.42:
                    problems.append(
                        f"behind poster at {it['at']}: anchored at "
                        f"y={((zone[0] + zone[1]) / 2):.2f}, where the "
                        f"shoulders/torso eat the words - anchor at "
                        f"head height (zone centre <= 0.42)")
        if it["type"] == "lowerthird" and not 1.8 <= dwell <= 6.0:
            problems.append(f"lowerthird at {it['at']}: dwell {dwell:.2f}s "
                            f"outside 1.8-6.0s (name them, let it be read, "
                            f"take it away)")
        if it["type"] == "chip" and it.get("sub"):
            problems.append(f"chip at {it['at']}: a chip is a single text line "
                            f"(a sub breaks the 6-7% bar height / 3% text floor); "
                            f"merge it into title or drop it")
        if it["type"] == "vector" and it.get("name") not in (
                "hoop", "led", "donut", "arrow", "burst", "cowfield", "roadcar",
                "dominoes", "iceberg", "bulb", "flame", "sprout", "chess",
                "anchor", "balloon", "redflag", "ghost", "wall", "compass",
                "bars", "line", "versus", "people", "stack", "timeline", "quote",
                "chat", "network", "gauge", "map",
                "calendar", "clock", "price", "checklist", "magnet", "funnel", "pyramid", "target", "podium", "beforeafter", "battery", "proscons", "chapter", "bigword", "heart", "alert", "phone", "scale", "brain", "bell", "key", "door", "dice", "venn", "rocket", "shield", "hourglass", "wave", "spotlight", "trophy", "noaward", "ladder", "stars", "countdown", "search", "cash", "crown", "bridge", "puzzle", "cycle", "thermo", "scriptcue", "oaktree", "worth"):
            problems.append(f"vector at {it['at']}: unknown scene "
                            f"{it.get('name')!r} (see motion/MOTIONS.md)")
        if it["type"] == "vector":
            nm = it.get("name")
            if nm == "worth" and not 1.0 <= dwell <= 1.8:
                problems.append(f"worth at {it['at']}: dwell {dwell:.2f}s "
                                "outside 1.0-1.8s (let the measuring grid "
                                "dissolve, then leave the spoken idea)")
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
                if b - a > 1.5 and not (
                        it.get("layout") == "diagram" and b - a <= 2.0):
                    problems.append(f"{it['type']} at {it['at']}: {key} gap "
                                    f"{b - a:.2f}s over 1.5s - a panel may only "
                                    f"live while it keeps adding entries")
            # A diagram continuously draws the rail between words. Its
            # label still lands on the WORD, never 0.3s early to placate
            # a generic plate cadence rule.
            min_read = 0.55 if it.get("layout") == "diagram" else 0.8
            if subs and until < ats[-1] + min_read:
                problems.append(f"{it['type']} at {it['at']}: until {until} gives the "
                                f"last entry no dwell time")
    for tname in ("hook", "endcard"):
        if sum(1 for i in items if i["type"] == tname) > 1:
            problems.append(f"at most one {tname} per video")
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
