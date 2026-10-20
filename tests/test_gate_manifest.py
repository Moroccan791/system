"""The bridge between a rendered job and the campaign gate.

The gate must judge what is on screen, so the manifest is read from the
pipeline's own `timeline.json` (posters = the captions that were built) and
`slice.json` (the kept words on the cut's clock) rather than re-derived from
the plan. This pins that bridge: if the timeline's item vocabulary changes,
this fails before a render ships.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import manifest_from_timeline as MFT  # noqa: E402


def write_job(work: Path) -> None:
    timeline = {
        "version": 1, "duration": 21.8,
        "items": [
            {"type": "poster", "at": 0.1, "until": 1.4, "zone": "low",
             "rows": [[{"w": "I"}, {"w": "will"}], [{"w": "never"}, {"w": "be"}]]},
            {"type": "vector", "name": "doors", "at": 5.0, "until": 6.5},
            {"type": "poster", "at": 6.6, "until": 8.0, "zone": "low",
             "rows": [[{"w": "she"}, {"w": "went"}], [{"w": "into"}]]},
            {"type": "endcard", "at": 20.4, "until": 21.8},
        ],
    }
    (work / "timeline.json").write_text(json.dumps(timeline))
    (work / "slice.json").write_text(json.dumps({
        "text": "I will never be she went into",
        "words": [
            {"text": "I", "start": 0.1, "end": 0.3},
            {"text": "will", "start": 0.3, "end": 0.6},
            {"text": "never", "start": 0.6, "end": 1.0},
            {"text": "be", "start": 1.0, "end": 1.3},
            {"text": "she", "start": 6.6, "end": 6.9},
            {"text": "went", "start": 6.9, "end": 7.2},
            {"text": "into", "start": 7.2, "end": 7.5},
        ],
    }))


def test_manifest_reads_the_posters_that_were_built(tmp_path: Path) -> None:
    write_job(tmp_path)
    manifest = MFT.build(tmp_path)
    assert len(manifest["cards"]) == 2, "vectors are not captions"
    assert manifest["cards"][0]["lines"] == [["I", "will"], ["never", "be"]]
    assert manifest["cards"][1]["show_from"] == 6.6


def test_manifest_carries_endcard_words_and_duration(tmp_path: Path) -> None:
    write_job(tmp_path)
    manifest = MFT.build(tmp_path)
    assert manifest["endcard"] == 20.4
    assert manifest["duration"] == 21.8
    assert [w["w"] for w in manifest["words_kept"]] == [
        "I", "will", "never", "be", "she", "went", "into"]
    assert manifest["words_kept"][0]["at"] == 0.1


def test_manifest_survives_a_job_without_a_slice(tmp_path: Path) -> None:
    write_job(tmp_path)
    (tmp_path / "slice.json").unlink()
    manifest = MFT.build(tmp_path)
    assert manifest["words_kept"] == []
    assert len(manifest["cards"]) == 2
