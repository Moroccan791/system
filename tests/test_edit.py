"""Stage 4: edit assembly.

The plan is checked as data (boundaries, camera moves) and the render is checked
as pixels (resolution, length, audio, and a camera move that can be measured).
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from clipper import config
from clipper.asr.base import Word
from clipper.edit import plan as plan_mod
from clipper.edit import render as render_mod
from clipper.edit.pipeline import edit_campaign, load_style
from clipper.ffmpeg import iter_frames, probe
from clipper.style.zoom import estimate_scale
from clipper.synth import render_cut_clip, textured_scene, write_video
from clipper.util import jsonio

PUNCH_STYLE = config.deep_merge(config.DEFAULT_STYLE, {
    "pacing": {"avg_shot_len": 2.0},
    "zoom": {"dominant": "punch_in", "punch_in_scale": 1.14, "punch_in_duration": 0.3},
})


@pytest.fixture(scope="module")
def footage(tmp_path_factory):
    """Eight seconds of textured scenes with hard cuts every two seconds."""
    path = tmp_path_factory.mktemp("footage") / "raw.mp4"
    info = render_cut_clip(str(path), shots=[2, 2, 2, 2], size=(480, 270), fps=12)
    info["path"] = str(path)
    return info


def candidate(start=0.5, end=8.5, **extra):
    """A stage-2 style candidate. `file` is filled in by the tests that render."""
    return {"id": "#01", "start": start, "end": end, "score": 0.7,
            "reasons": ["a test moment"], **extra}


def spoken(start=0.5, end=8.5, step=0.45, gap=0.35):
    """Words with audible pauses, so cut snapping has somewhere to land."""
    words, t = [], start + 0.1
    while t < end - 0.3:
        words.append(Word("word", round(t, 3), round(t + step - gap, 3)))
        t += step
    return words


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------
def test_plan_covers_the_window_without_holes_or_overlaps():
    built = plan_mod.build_plan(candidate(1.0, 9.0), style=PUNCH_STYLE)
    shots = built["shots"]
    assert shots[0]["start"] == pytest.approx(1.0)
    assert shots[-1]["end"] == pytest.approx(9.0)
    for previous, shot in zip(shots, shots[1:]):
        assert shot["start"] == pytest.approx(previous["end"])
    assert sum(s["duration"] for s in shots) == pytest.approx(8.0, abs=0.01)


def test_plan_shot_count_follows_the_profile_pacing():
    built = plan_mod.build_plan(candidate(0.0, 12.0), style=PUNCH_STYLE)
    assert len(built["shots"]) == pytest.approx(6, abs=1)
    for shot in built["shots"]:
        assert 1.4 <= shot["duration"] <= 2.6


def test_plan_uses_the_campaign_pacing_by_default():
    built = plan_mod.build_plan(candidate(0.0, 6.0), style={"pacing": {"avg_shot_len": 3.0}})
    assert len(built["shots"]) == pytest.approx(2, abs=1)
    assert built["style"]["avg_shot_len"] == 3.0


def test_plan_is_deterministic():
    first = plan_mod.build_plan(candidate(0.35, 12.0), style=PUNCH_STYLE)
    second = plan_mod.build_plan(candidate(0.35, 12.0), style=PUNCH_STYLE)
    assert first == second, "the same moment must always produce the same edit"


def test_a_short_window_becomes_one_shot():
    built = plan_mod.build_plan(candidate(2.0, 3.2), style=PUNCH_STYLE)
    assert len(built["shots"]) == 1
    assert built["shots"][0]["duration"] == pytest.approx(1.2, abs=0.01)


def test_cuts_snap_to_pauses_between_words():
    words = spoken(0.5, 8.5)
    plain = plan_mod.build_plan(candidate(0.5, 8.5), style=PUNCH_STYLE)
    snapped = plan_mod.build_plan(candidate(0.5, 8.5), style=PUNCH_STYLE, words=words)
    gaps = plan_mod._word_gaps(words, 0.5, 8.5)
    assert gaps
    for shot in snapped["shots"][1:]:
        nearest = min(gaps, key=lambda g: abs(g - shot["start"]))
        assert abs(nearest - shot["start"]) <= 0.5
    # snapping actually moved cuts, and never created a shot shorter than the floor
    assert [s["start"] for s in snapped["shots"]] != [s["start"] for s in plain["shots"]]
    assert all(s["duration"] >= plan_mod.MIN_SHOT_LEN for s in snapped["shots"])


def test_shot_length_override_is_honoured():
    built = plan_mod.build_plan(candidate(0.0, 10.0), style=PUNCH_STYLE, shot_len=1.0)
    assert len(built["shots"]) == pytest.approx(10, abs=2)
    assert all(0.7 <= s["duration"] <= 1.4 for s in built["shots"])


@pytest.mark.parametrize("dominant,expect", [
    ("punch_in", "punch_in"), ("slow_push", "slow_push"),
    ("pull_out", "pull_out"), ("static", "static"),
])
def test_camera_moves_follow_the_profile(dominant, expect):
    style = {"pacing": {"avg_shot_len": 2.0},
             "zoom": {"dominant": dominant, "punch_in_scale": 1.2, "punch_in_duration": 0.3}}
    built = plan_mod.build_plan(candidate(0.0, 4.0), style=style)
    move = built["shots"][0]["zoom"]
    assert move["type"] == expect
    if expect == "static":
        assert "to" not in move
    elif expect == "pull_out":            # starts wide, settles back
        assert move["from"] == 1.2 and move["to"] == 1.0
    else:
        assert move["to"] == 1.2


def test_slow_push_ramps_across_the_whole_shot():
    style = {"pacing": {"avg_shot_len": 2.0},
             "zoom": {"dominant": "slow_push", "punch_in_scale": 1.2, "punch_in_duration": 0.3}}
    built = plan_mod.build_plan(candidate(0.0, 4.0), style=style)
    for shot in built["shots"]:
        assert shot["zoom"]["over"] == pytest.approx(shot["duration"], abs=0.01)


def test_unknown_transition_falls_back_to_a_cut_with_a_note():
    style = config.deep_merge(PUNCH_STYLE, {"transitions": {"in": "whip_pan"}})
    built = plan_mod.build_plan(candidate(0.0, 4.0), style=style)
    assert built["style"]["transition"] == "cut"
    assert any("whip_pan" in note for note in built["notes"])


def test_plan_records_the_caption_window():
    words = spoken(0.5, 8.5)
    built = plan_mod.build_plan(candidate(2.0, 6.0), style=PUNCH_STYLE, words=words)
    window = built["captions"]["window"]
    assert window and 2.0 <= window[0] < window[1] <= 6.0
    assert built["captions"]["words"] > 0


def test_plan_survives_json(tmp_path):
    built = plan_mod.build_plan(candidate(0.35, 6.0), style=PUNCH_STYLE)
    path = tmp_path / "plan.json"
    jsonio.save(path, built)
    assert jsonio.load(path) == built


# ---------------------------------------------------------------------------
# filtergraph
# ---------------------------------------------------------------------------
def test_filtergraph_trims_every_shot_at_the_plan_times():
    built = plan_mod.build_plan(candidate(1.0, 7.0), style=PUNCH_STYLE)
    graph = render_mod.build_filtergraph(built)
    for shot in built["shots"]:
        assert f"trim=start={shot['start']:.3f}:end={shot['end']:.3f}" in graph
        assert f"atrim=start={shot['start']:.3f}:end={shot['end']:.3f}" in graph
    assert f"concat=n={len(built['shots'])}:v=1:a=1" in graph


def test_filtergraph_only_zooms_when_the_profile_moves_the_camera():
    moving = render_mod.build_filtergraph(plan_mod.build_plan(candidate(0.0, 4.0), style=PUNCH_STYLE))
    still_style = config.deep_merge(config.DEFAULT_STYLE, {"zoom": {"dominant": "static"}})
    still = render_mod.build_filtergraph(
        plan_mod.build_plan(candidate(0.0, 4.0), style=still_style))
    assert "zoompan" in moving and "zoompan" not in still


def test_filtergraph_zoom_expression_takes_the_profile_duration():
    style = config.deep_merge(PUNCH_STYLE, {"zoom": {"punch_in_scale": 1.5,
                                                     "punch_in_duration": 0.5}})
    built = plan_mod.build_plan(candidate(0.0, 4.0), style=style)
    graph = render_mod.build_filtergraph(built, source_fps=30)
    assert "1.0000+(1.5000-1.0000)*min(on/15.000,1)" in graph


def test_filtergraph_uses_the_source_frame_rate_for_zoompan():
    """Asking zoompan for the output rate instead makes it duplicate frames."""
    built = plan_mod.build_plan(candidate(0.0, 4.0), style=PUNCH_STYLE)
    graph = render_mod.build_filtergraph(built, source_fps=24)
    assert ":fps=24" in graph
    assert ":fps=30" not in graph


def test_focus_changes_the_crop():
    built = plan_mod.build_plan(candidate(0.0, 4.0), style=PUNCH_STYLE)
    centre = render_mod.build_filtergraph(built, focus="centre")
    top = render_mod.build_filtergraph(built, focus="top")
    assert centre != top
    assert "*0.18" in top


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------
def _scale_between(first, later):
    gray = lambda img: cv2.cvtColor(np.asarray(img), cv2.COLOR_BGR2GRAY).astype(np.float32)  # noqa: E731
    return estimate_scale(gray(first), gray(later), size=200)


def test_single_shot_render_moves_the_camera(footage, tmp_path):
    """A punch-in must be visible in the rendered pixels, not just in the plan."""
    built = plan_mod.build_plan(candidate(0.2, 3.2, file=footage["path"]), style=PUNCH_STYLE)
    assert len(built["shots"]) == 1
    out = render_mod.render_plan(built, tmp_path / "one.mp4")
    frames = list(iter_frames(str(out), fps=12))
    scale, response = _scale_between(frames[0], frames[min(8, len(frames) - 1)])
    assert response > 0.5, "frames should correlate well enough to measure"
    assert scale >= 1.06, f"the camera should have pushed in, measured {scale}"


def test_static_profile_keeps_the_camera_still(footage, tmp_path):
    still_style = config.deep_merge(config.DEFAULT_STYLE, {"zoom": {"dominant": "static"}})
    built = plan_mod.build_plan(candidate(0.2, 3.2, file=footage["path"]), style=still_style)
    out = render_mod.render_plan(built, tmp_path / "still.mp4")
    frames = list(iter_frames(str(out), fps=12))
    scale, response = _scale_between(frames[0], frames[min(8, len(frames) - 1)])
    assert scale <= 1.02, f"a static profile should not move, measured {scale}"


def test_render_shape_length_and_audio(footage, tmp_path):
    built = plan_mod.build_plan(candidate(0.5, 6.5, file=footage["path"]), style=PUNCH_STYLE)
    out = render_mod.render_plan(built, tmp_path / "clip.mp4")
    info = probe(out)
    assert (info.width, info.height) == (1080, 1920)
    assert info.duration == pytest.approx(built["clip"]["duration"], abs=0.35)


def test_render_handles_silent_footage(tmp_path, footage):
    """Silent footage still edits - it just comes out without an audio track."""
    clip = str(tmp_path / "silent.mp4")
    write_video(clip, (textured_scene(480, 270, seed=3) for _ in range(48)), fps=12)
    built = plan_mod.build_plan(candidate(0.1, 2.5, file=clip), style=PUNCH_STYLE)
    out = render_mod.render_plan(built, tmp_path / "silent_edit.mp4")
    info = probe(out)
    assert info.has_video and not info.has_audio
    assert info.duration == pytest.approx(built["clip"]["duration"], abs=0.35)


def test_render_trims_a_plan_that_runs_past_the_footage(footage, tmp_path):
    """Asking for footage the file does not contain trims the tail, it does not pad."""
    built = plan_mod.build_plan(candidate(6.0, 9.0, file=footage["path"]), style=PUNCH_STYLE)
    out = render_mod.render_plan(built, tmp_path / "long.mp4")
    info = probe(out)
    assert info.duration == pytest.approx(2.0, abs=0.35)   # footage ends at 8 s
    assert built["shots"][-1]["end"] > info.duration        # the input plan is untouched


def test_render_refuses_a_missing_source(tmp_path):
    built = plan_mod.build_plan(candidate(0.0, 2.0), style=PUNCH_STYLE)
    built["clip"]["source"] = str(tmp_path / "gone.mp4")
    with pytest.raises(FileNotFoundError):
        render_mod.render_plan(built, tmp_path / "out.mp4")


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------
def write_candidates(work_dir, footage, count=2, **payload_extra):
    payload = {
        "version": 1, "campaign": "edittest", "mode": "audio-only",
        "source": {"file": footage["path"], "name": "raw.mp4", "duration": 6.0},
        "target": {"platform": "tiktok", "min_seconds": 1.0, "max_seconds": 6.0},
        "analysis": {"hot_spots": [], "baseline_db": -30.0, "peak_db": -12.0,
                     "sentences": 0, "words": 0},
        "candidates": [
            {"id": f"#{i + 1:02d}", "start": 0.1 + i * 3.0, "end": 2.6 + i * 3.0,
             "duration": 2.5, "score": 0.8 - 0.1 * i, "text": None,
             "reasons": ["a loud stretch"], "signals": {"text": None, "audio": 0.8, "burst": True},
             "burst_span": [0.5 + i * 3.0, 1.5 + i * 3.0], "burst_id": i}
            for i in range(count)
        ],
        **payload_extra,
    }
    folder = work_dir / "candidates"
    folder.mkdir(parents=True, exist_ok=True)
    jsonio.save(folder / "raw.json", payload)
    return payload


def test_edit_campaign_writes_plans_and_clips(footage, tmp_path, monkeypatch):
    work = tmp_path / "work"
    write_candidates(work, footage)
    monkeypatch.setattr(config, "WORK", work)
    results = edit_campaign("edittest", work_dir=work, style_path=None)
    assert len(results) == 2
    for record in results:
        assert str(record["clip"]).endswith(".mp4")
        assert jsonio.load(record["plan_path"])["shots"]
    assert probe(results[0]["clip"]).has_video


def test_edit_campaign_can_write_plans_only(footage, tmp_path, monkeypatch):
    work = tmp_path / "work"
    write_candidates(work, footage, count=1)
    monkeypatch.setattr(config, "WORK", work)
    results = edit_campaign("edittest", work_dir=work, render=False)
    assert results[0]["clip"] is None
    assert jsonio.load(results[0]["plan_path"])["clip"]["duration"] == pytest.approx(2.5)


def test_edit_campaign_limits_with_top_and_ids(footage, tmp_path, monkeypatch):
    work = tmp_path / "work"
    write_candidates(work, footage, count=2)
    monkeypatch.setattr(config, "WORK", work)
    only_second = edit_campaign("edittest", work_dir=work, ids=["#02"], render=False)
    assert len(only_second) == 1
    assert only_second[0]["plan"]["clip"]["id"] == "#02"
    best_only = edit_campaign("edittest", work_dir=work, top=1, render=False)
    assert len(best_only) == 1
    assert best_only[0]["plan"]["clip"]["score"] == 0.8


def test_edit_campaign_without_candidates_explains_itself(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORK", tmp_path / "work")
    with pytest.raises(RuntimeError, match="select"):
        edit_campaign("nothing", work_dir=tmp_path / "work")


def test_load_style_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STYLES", tmp_path / "styles")
    style = load_style("no-such-campaign")
    assert style["pacing"]["avg_shot_len"] is None
    assert style["zoom"]["dominant"] == config.DEFAULT_STYLE["zoom"]["dominant"]
