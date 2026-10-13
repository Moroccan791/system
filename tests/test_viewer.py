"""The viewer is the only way to actually watch what the pipeline produced."""
from __future__ import annotations

import json

import pytest

from clipper import config
from clipper.serve import viewer


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A miniature workspace: one campaign, one raw file, one rendered edit."""
    root = tmp_path / "ws"
    for name in ("campaigns", "samples", "styles", "output", "work"):
        (root / name).mkdir(parents=True, exist_ok=True)
    raw = root / "campaigns" / "demo" / "raw"
    raw.mkdir(parents=True)
    (raw / "talk.mp4").write_bytes(b"\x00" * 2048)
    edits = root / "work" / "demo" / "edits"
    edits.mkdir(parents=True)
    (edits / "talk_01.mp4").write_bytes(b"\x00" * 4096)
    (edits / "talk_01.plan.json").write_text(json.dumps({
        "version": 1, "campaign": "demo",
        "clip": {"id": "#01", "source": str(raw / "talk.mp4"), "start": 0.5,
                 "end": 8.5, "duration": 8.0, "score": 0.7, "reasons": ["a hook"]},
        "target": {"platform": "tiktok", "width": 1080, "height": 1920, "fps": 30},
        "style": {"avg_shot_len": 2.0, "zoom": "punch_in", "transition": "cut"},
        "shots": [{"index": 1, "start": 0.5, "end": 2.5, "duration": 2.0,
                   "zoom": {"type": "punch_in"}, "transition": "cut"},
                  {"index": 2, "start": 2.5, "end": 8.5, "duration": 6.0,
                   "zoom": {"type": "static"}, "transition": "cut"}],
        "captions": {"words": 0, "window": [0.5, 8.5]}, "notes": [],
    }), encoding="utf-8")
    monkeypatch.setattr(config, "ROOT", root)
    for attr in ("CAMPAIGNS", "SAMPLES", "STYLES", "OUTPUT", "WORK"):
        monkeypatch.setattr(config, attr, root / attr.lower())
    monkeypatch.setattr(viewer.config, "ROOT", root)
    return root


def test_viewer_shows_rendered_edits_with_their_plan(workspace):
    page = viewer.build_index(workspace)
    assert "/media/work/demo/edits/talk_01.mp4" in page
    assert "#01 · 8.0s · 2 shots" in page
    assert "punch_in · cut · 1080x1920 · tiktok" in page
    assert "shots 2.00s 6.00s" in page
    assert "/media/work/demo/edits/talk_01.plan.json" in page
    assert "Assembled clips" in page


def test_viewer_lists_raw_footage_so_it_can_be_watched(workspace):
    page = viewer.build_index(workspace)
    assert "/media/campaigns/demo/raw/talk.mp4" in page
    assert "raw · talk.mp4" in page


def test_edits_are_not_listed_twice(workspace):
    """The dedicated section replaces the generic work-file listing for them."""
    page = viewer.build_index(workspace)
    assert page.count('src="/media/work/demo/edits/talk_01.mp4"') == 1


def test_viewer_handles_an_empty_workspace(tmp_path, monkeypatch):
    root = tmp_path / "empty"
    root.mkdir()
    monkeypatch.setattr(viewer.config, "ROOT", root)
    for attr in ("CAMPAIGNS", "SAMPLES", "STYLES", "OUTPUT", "WORK"):
        monkeypatch.setattr(viewer.config, attr, root / attr.lower())
    page = viewer.build_index(root)
    assert "No campaigns found" in page
