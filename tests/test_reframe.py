"""The reframe map: per-segment crop focus for multi-speaker sources.

The helpers are pure arithmetic (checked exactly); the end-to-end scan is
checked on synthetic footage with known cuts - textured scenes have no
faces, so segments must come back with boundaries but no focus values.
"""
import pytest

from clipper.edit import reframe
from clipper.edit.pipeline import candidates_for
from clipper.synth import render_cut_clip
from clipper.util import jsonio


def test_crop_fraction_for_landscape_to_vertical():
    assert reframe.crop_fraction(1920, 1080) == pytest.approx(0.3164, abs=1e-3)
    # already vertical: the crop is the whole width
    assert reframe.crop_fraction(1080, 1920) == 1.0


def test_focus_for_centres_the_median_face():
    frac = reframe.crop_fraction(1920, 1080)
    assert reframe.focus_for([0.5], frac) == pytest.approx(0.5)
    # a face at the left edge clamps to hard-left, not negative
    assert reframe.focus_for([0.05], frac) == 0.0
    # median, not mean: one stray detection must not drag the window
    assert reframe.focus_for([0.48, 0.5, 0.52, 0.99], frac) == \
        reframe.focus_for([0.52], frac)
    assert reframe.focus_for([], frac) is None


def test_merge_bounds_drops_twitchy_segments():
    bounds = [0.0, 0.4, 2.0, 2.3, 5.0]
    assert reframe.merge_bounds(bounds, 1.1) == [0.0, 2.0, 5.0]
    assert reframe.merge_bounds(bounds, 0.1) == bounds


def test_reframe_map_finds_the_sources_own_cuts(tmp_path):
    path = tmp_path / "cuts.mp4"
    render_cut_clip(str(path), shots=[2, 2, 2], size=(480, 270), fps=12)
    segments = reframe.reframe_map(path, 0.0, 6.0, min_seg=1.1)
    starts = [s["start"] for s in segments]
    assert starts[0] == 0.0 and segments[-1]["end"] == 6.0
    assert any(abs(s - 2.0) < 0.35 for s in starts[1:])
    assert any(abs(s - 4.0) < 0.35 for s in starts[1:])
    # textured scenes: no faces, so no focus - the global crop applies
    assert all("focus_x" not in s for s in segments)


def test_candidates_fall_back_to_the_campaign_folder(tmp_path, monkeypatch):
    from clipper import config

    monkeypatch.setattr(config, "WORK", tmp_path / "work")
    monkeypatch.setattr(config, "CAMPAIGNS", tmp_path / "campaigns")
    folder = tmp_path / "campaigns" / "demo" / "candidates"
    folder.mkdir(parents=True)
    jsonio.save(folder / "manual.json", {
        "source": {"file": "x.mp4", "name": "x.mp4"}, "campaign": "demo",
        "candidates": [{"id": "#A1", "start": 1.0, "end": 9.0}]})
    found = candidates_for("demo")
    assert len(found) == 1
    assert found[0]["candidates"][0]["id"] == "#A1"
