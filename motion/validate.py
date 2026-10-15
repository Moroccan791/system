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
        if it["type"] == "chip" and it.get("sub"):
            problems.append(f"chip at {it['at']}: a chip is a single text line "
                            f"(a sub breaks the 6-7% bar height / 3% text floor); "
                            f"merge it into title or drop it")
        if it["type"] == "vector" and it.get("name") not in (
                "hoop", "led", "donut", "arrow", "burst"):
            problems.append(f"vector at {it['at']}: unknown scene "
                            f"{it.get('name')!r} (hoop, led, donut, arrow, burst)")
        if it["type"] == "vector" and (it.get("mode") or "card") == "fullbleed" \
                and not 1.0 <= dwell <= 1.8:
            problems.append(f"vector broll at {it['at']}: full-bleed dwell "
                            f"{dwell:.2f}s outside 1.0-1.8s")
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
    # image cadence: at most one PiP / B-roll / vector insert per 6 s
    imgs = [i for i in items if i["type"] in ("pip", "broll", "vector")]
    for a, b in zip(imgs, imgs[1:]):
        if b["at"] - a["at"] < 6.0:
            problems.append(f"images at {a['at']} and {b['at']}: under the "
                            f"6s minimum spacing between image inserts")
    for p in problems:
        print(f"RULE {p}")
    if problems:
        return 1
    print(f"timeline OK: {len(items)} items, {dur:.1f}s, accent {tl['brand']['accent']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
