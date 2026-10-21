"""Every campaign skill this repo has must be in the render, or the gate fails.

This file exists because a renderer was written for a new campaign and shipped
without the motion layer, the end card, the kinetic open or the emphasis ink -
all of which this repo already had, and all of which the campaign's own
`campaign_rules.json` already asked for. Nothing caught it, because nothing
checked that what the rules describe is what the render actually does.

So: a render writes down which features it used, and the gate compares that
list against the campaign's `required_features`. A campaign that asks for
`kinetic_type` and gets a renderer without it now fails instead of shipping.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import qc_gate as QG       # noqa: E402

#: Everything a finished post can be required to have. Kept as one list so the
#: rules file cannot name a feature nobody implements.
KNOWN = {
    "reframe_9x16",     # full-bleed vertical crop that follows the face
    "kinetic_type",     # the opening words land word by word
    "emphasis_ink",     # key words in their own colour, 1.16x
    "punch",            # camera punch on those words
    "ramp",             # slow push across the clip
    "whip",             # transition on a real cut
    "endcard",          # the clip ends on the show card, not on the peak
    "bug",              # show + episode on screen throughout
    "grade",            # the campaign grade
    "bed",              # music bed ducked under the voice
    "voice",            # voice chain, loudness to -16 LUFS
    "keyboard_sfx",     # recorded typing on the caption reveal grid
    "whoosh_sfx",       # whoosh on each cut
}


def check_video(video: Path, manifest: dict, rules: dict) -> dict:
    """Compare what the campaign requires with what the render says it did."""
    required = [f for f in (rules.get("required_features") or []) if f in KNOWN]
    unknown = [f for f in (rules.get("required_features") or []) if f not in KNOWN]
    used = set(manifest.get("features") or [])
    missing = [f for f in required if f not in used]
    rows = []
    rows.append({
        "name": "required_features",
        "status": "fail" if missing or unknown else "pass",
        "detail": (f"missing {missing}" if missing else
                   f"unknown {unknown}" if unknown else
                   f"{len(required)} required, all present"),
    })
    return {"ok": not (missing or unknown), "checks": rows}


def gate(video: Path, manifest: dict, rules: dict) -> dict:
    """The campaign gate, plus the feature contract."""
    report = QG.gate(video, manifest, rules)
    extra = check_video(video, manifest, rules)
    report["checks"].extend(extra["checks"])
    report["ok"] = report["ok"] and extra["ok"]
    return report


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--campaign", required=True)
    args = ap.parse_args()
    rules = json.loads((ROOT / "campaigns" / args.campaign / "campaign_rules.json").read_text())
    rules.setdefault("_campaign", args.campaign)
    man = json.loads(Path(args.manifest).read_text())
    rep = gate(Path(args.video), man, rules)
    for row in rep["checks"]:
        print(f"[{row['status'].upper():4s}] {row['name']}: {row['detail']}")
    raise SystemExit(0 if rep["ok"] else 1)
