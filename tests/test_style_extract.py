"""Stage 1 end to end: a campaign folder becomes a valid style profile."""
from __future__ import annotations

import numpy as np
import pytest

from clipper import config
from clipper.style import extract as extract_mod
from clipper.style import profile as profile_mod
from clipper.util import jsonio


def test_profile_defaults_are_complete():
    filled = profile_mod.apply_defaults({"captions": {"font_size_ass": 104}})
    for key in ("pacing", "zoom", "captions", "audio"):
        assert key in filled
    assert filled["captions"]["font_size_ass"] == 104
    assert filled["captions"]["primary_color"] == config.DEFAULT_STYLE["captions"]["primary_color"]


def test_sanitize_clamps_nonsense():
    out = profile_mod.sanitize({"captions": {"font_size_ass": 9999, "max_lines": 12},
                                "zoom": {"punch_in_scale": 9.0},
                                "pacing": {"avg_shot_len": -4}})
    assert out["captions"]["font_size_ass"] <= 260
    assert out["captions"]["max_lines"] <= 3
    assert out["zoom"]["punch_in_scale"] <= 2.0
    assert out["pacing"]["avg_shot_len"] >= 0.1


def test_aggregate_takes_medians_across_references():
    def ref(shots, cy, dur):
        return {
            "duration": dur,
            "pacing": {"avg_shot_len": shots, "median_shot_len": shots,
                       "cuts_per_minute": 60 / shots, "confidence": 0.8},
            "zoom": {"dominant": "punch_in", "punch_in_scale": 1.1, "punch_in_duration": 0.3,
                     "confidence": 0.7},
            "captions": {"present": True, "font_size_ass": cy, "primary_color": "#FFFFFF",
                         "outline_color": "#000000", "outline_width": 5, "casing": "upper",
                         "position": {"cx": 0.5, "cy": 0.7},
                         "karaoke": {"enabled": True, "highlight_color": "#FFE14D"},
                         "animation": {"in": "none"}, "max_lines": 1,
                         "max_words_per_cue": 3, "max_chars_per_line": 18,
                         "confidence": 0.8, "evidence": {"cue_count": 4, "frames": []}},
            "audio": {"music_bed": False, "target_lufs": -14.0, "speech_ratio": 0.8,
                      "confidence": 0.5},
        }

    agg = extract_mod.aggregate([ref(1.0, 100, 10), ref(2.0, 140, 10), ref(3.0, 120, 10)])
    assert agg["pacing"]["avg_shot_len"] == 2.0
    assert agg["captions"]["font_size_ass"] == 120
    assert agg["captions"]["position"]["cy"] == pytest.approx(0.7, abs=0.01)


def test_aggregate_handles_missing_captions():
    ref = {"duration": 5, "pacing": {"avg_shot_len": 2.0, "confidence": 0.5, "shot_count": 2},
           "zoom": {"dominant": "static", "confidence": 0.5},
           "captions": {"present": False, "confidence": 0.0, "evidence": {"cue_count": 0, "frames": []}},
           "audio": {"confidence": 0.2}}
    agg = extract_mod.aggregate([ref])
    assert agg["captions"]["present"] is False
    assert agg["pacing"]["avg_shot_len"] == 2.0


def test_extract_writes_profile_and_report(tmp_path, monkeypatch):
    """Runs the real thing on the generated sample campaign."""
    samples = config.SAMPLES / "campaign_demo"
    if not (samples / "references").exists():
        pytest.skip("run `python -m clipper samples` first")

    monkeypatch.setattr(config, "STYLES", tmp_path / "styles")
    monkeypatch.setattr(config, "WORK", tmp_path / "work")

    profile = extract_mod.extract_style(samples)
    assert profile["campaign"] == "campaign_demo"
    assert profile["version"] == config.DEFAULT_STYLE["version"]

    written = jsonio.load(tmp_path / "styles" / "campaign_demo.style.json")
    assert written["captions"]["present"] is True
    assert written["pacing"]["avg_shot_len"] is not None
    assert written["zoom"]["dominant"] in ("punch_in", "static", "slow_push", "mixed")

    report = jsonio.load(tmp_path / "work" / "campaign_demo" / "style" / "report.json")
    assert report["references"] and "aggregate" in report


def test_extract_refuses_a_campaign_without_references(tmp_path, monkeypatch):
    empty = tmp_path / "nocampaign"
    (empty / "references").mkdir(parents=True)
    (empty / "raw").mkdir(parents=True)
    monkeypatch.setattr(config, "WORK", tmp_path / "work")
    with pytest.raises(RuntimeError, match="no reference clips"):
        extract_mod.extract_style(empty)


def test_notes_explain_what_could_not_be_measured():
    profile = profile_mod.apply_defaults({"captions": {"present": True, "font_family": None,
                                                       "confidence": 0.9},
                                          "pacing": {"confidence": 0.9}})
    notes = profile_mod.notes_for(profile)
    assert any("font family" in n for n in notes)
