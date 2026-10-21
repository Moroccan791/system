"""The feature contract: a campaign that asks for a skill must get it.

Written after a campaign shipped without the motion layer, the end card, the
kinetic open and the emphasis ink - all of which this repo already had, and all
of which that campaign's own rules file already named. The fix is not a note to
remember; it is a check that fails.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import skill_gate as SG       # noqa: E402

CAMPAIGN = "two_bears_ep344"


def rules() -> dict:
    return json.loads((ROOT / "campaigns" / CAMPAIGN / "campaign_rules.json").read_text())


def manifest(**used) -> dict:
    return {"duration": 30.0, "endcard": 29.0, "cards": [], "words_kept": [],
            "features": list(used.get("features", []))}


def test_this_campaign_requires_the_motion_layer() -> None:
    required = set(rules().get("required_features") or [])
    for feature in ("reframe_9x16", "kinetic_type", "emphasis_ink", "whip",
                    "punch", "ramp", "endcard", "bug"):
        assert feature in required, f"{feature} is not in the campaign contract"
        assert feature in SG.KNOWN, f"{feature} is required but not implemented"


def test_a_render_missing_a_feature_fails() -> None:
    r = rules()
    report = SG.check_video(Path("x.mp4"), manifest(features=["reframe_9x16"]), r)
    assert not report["ok"]
    detail = report["checks"][0]["detail"]
    assert "kinetic_type" in detail and "endcard" in detail


def test_a_complete_render_passes() -> None:
    r = rules()
    full = list(r["required_features"])
    report = SG.check_video(Path("x.mp4"), manifest(features=full), r)
    assert report["ok"], report["checks"]


def test_an_unknown_requirement_fails_loudly() -> None:
    r = {**rules(), "required_features": ["kinetic_type", "hologram"]}
    report = SG.check_video(Path("x.mp4"), manifest(features=["kinetic_type"]), r)
    assert not report["ok"]
    assert "hologram" in report["checks"][0]["detail"]


def test_the_renderer_reports_what_it_used() -> None:
    """The manifest is the evidence; if the renderer stops writing it, the
    gate would pass everything."""
    src = (ROOT / "scripts" / "whop" / "render_clip.py").read_text()
    assert '"features"' in src
    for feature in ("kinetic_type", "endcard", "bug", "reframe_9x16"):
        assert f'"{feature}"' in src, f"{feature} is not reported by the renderer"
