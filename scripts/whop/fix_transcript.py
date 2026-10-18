#!/usr/bin/env python3
"""Fix word-level artifacts in the episode transcript.

The ASR drops short function words ("And I" -> "And.", "next to it" ->
"next to?") and sometimes invents a word in a silence. A caption has to
be right AND on time, so the fixes are applied to the transcript itself
- one source of truth for the base, the slice and the captions.

    python scripts/whop/fix_transcript.py            # apply the patches
    python scripts/whop/fix_transcript.py --show     # show the patches

Patch format (work/street/asr/patches.json):
  [{"at": 1829.70, "old": "And.",
    "new": ["And", "I"], "times": [1829.70, 1829.745]}]
  [{"at": 1829.71, "text": "didn't", "set_start": 1829.88}]
  [{"at": 1853.50, "old": "of?", "delete": true}]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("/home/user/system")
EPISODE = ROOT / "work" / "street" / "asr" / "episode_transcript.json"
RAW = ROOT / "work" / "street" / "asr" / "episode_transcript.raw.json"
PATCHES = ROOT / "work" / "street" / "asr" / "patches.json"


def main() -> int:
    if "--show" in sys.argv:
        print(PATCHES.read_text())
        return 0
    if not PATCHES.exists():
        print("no patches file")
        return 0
    patches = json.loads(PATCHES.read_text())
    data = json.loads(RAW.read_text() if RAW.exists() else EPISODE.read_text())
    words = data["words"]
    for p in patches:
        if "old" not in p:
            continue
        hits = [i for i, w in enumerate(words)
                if abs(w["start"] - p["at"]) < 0.05
                and w["text"].lower().strip(".,!?")
                == p["old"].lower().strip(".,!?")]
        if not hits:
            print(f"patch not applied at {p['at']}: {p['old']!r} not found")
            continue
        i = hits[0]
        if p.get("delete"):
            print(f"deleted {p['old']!r} at {p['at']}")
            words.pop(i)
            continue
        words[i] = {**words[i], "text": p["new"][0], "start": p["times"][0]}
        for k, extra in enumerate(p["new"][1:], start=1):
            w = dict(words[i])
            w["text"] = extra
            w["start"] = p["times"][k]
            w["end"] = p["times"][k] + 0.12
            words.insert(i + k, w)
        print(f"patched {p['old']!r} -> {p['new']} at {p['at']}")
    for p in patches:
        if "set_start" in p:
            for w in words:
                if (abs(w["start"] - p["at"]) < 0.02
                        and "text" in p
                        and w["text"].strip(".,!?") == p["text"].strip(".,!?")):
                    w["start"] = round(p["set_start"], 3)
                    w["end"] = round(max(w["end"], p["set_start"] + 0.06), 3)
                    print(f"set {w['text']!r} start -> {p['set_start']}")
    for w in words:
        w["start"] = round(float(w["start"]), 3)
        w["end"] = round(float(w["end"]), 3)
    words.sort(key=lambda w: w["start"])
    data["words"] = words
    EPISODE.write_text(json.dumps(data, indent=1) + "\n")
    print(f"episode transcript: {len(words)} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
