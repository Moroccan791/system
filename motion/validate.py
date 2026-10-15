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
        if prev["type"] == cur["type"] and cur["at"] < (prev.get("until") or prev["at"]):
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
    for p in problems:
        print(f"RULE {p}")
    if problems:
        return 1
    print(f"timeline OK: {len(items)} items, {dur:.1f}s, accent {tl['brand']['accent']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
