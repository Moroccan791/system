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

# a blend needs two *different* pictures on screen at once, and it draws them
# from the two shots it joins - so the test footage changes scene exactly where
# the plan cuts, otherwise a dissolve would mix a frame with itself
BRIGHT = ((180, 190, 210), (230, 240, 250), (255, 255, 255), (200, 220, 240))
WARM = ((220, 170, 120), (255, 205, 150), (255, 240, 210), (230, 190, 140))


def blend_style(kind: str, seconds: float = 0.5) -> dict:
    return config.deep_merge(config.DEFAULT_STYLE, {
        "pacing": {"avg_shot_len": 2.0},
        "zoom": {"dominant": "static"},
        "transitions": {"in": kind, "duration": seconds},
    })


@pytest.fixture(scope="module")
def footage(tmp_path_factory):
    """Eight seconds of textured scenes with hard cuts every two seconds."""
    path = tmp_path_factory.mktemp("footage") / "raw.mp4"
    info = render_cut_clip(str(path), shots=[2, 2, 2, 2], size=(480, 270), fps=12)
    info["path"] = str(path)
    return info


@pytest.fixture(scope="module")
def bright_footage(tmp_path_factory):
    """Bright scene A for 2 s, bright scene B after - a cut a dissolve can show."""
    path = tmp_path_factory.mktemp("blend") / "scenes.mp4"
    scene_a = textured_scene(480, 270, seed=5, palette=BRIGHT)
    scene_b = textured_scene(480, 270, seed=31, palette=WARM)
    write_video(str(path), [scene_a] * 24 + [scene_b] * 24, fps=12,
                audio_source="sine=frequency=220:duration=4")
    return str(path)


@pytest.fixture(scope="module")
def blend_renders(tmp_path_factory, bright_footage):
    """Render the same moment cut, crossfaded and dipped: measure all three once."""
    out: dict[str, dict] = {}
    folder = tmp_path_factory.mktemp("blend_renders")
    # cut exactly on the footage's scene change (no jitter, so 0.0 + 2.0 s) and
    # the dissolve has scene A running out and scene B coming in, like footage cut
    # in a real editor
    candidate_at = {"id": "#01", "start": 0.0, "end": 3.9, "score": 1.0,
                    "file": bright_footage, "source_name": "scenes"}
    for name, style in (("cut", blend_style("cut", 0.0)),
                        ("fade", blend_style("fade", 0.5)),
                        ("fade_black", blend_style("fade_black", 0.4))):
        built = plan_mod.build_plan(candidate_at, style=style, shot_len=2.0)
        if name != "cut":
            assert built["shots"][1]["out_start"] != built["shots"][1]["start"]
        path = folder / f"{name}.mp4"
        render_mod.render_plan(built, path)
        frames = [np.asarray(f, dtype=np.float32) for f in iter_frames(str(path), fps=12)]
        diffs = np.array([np.abs(b - a).mean() for a, b in zip(frames, frames[1:])])
        lums = np.array([f.mean() for f in frames])
        out[name] = {"plan": built, "path": path, "frames": len(frames),
                     "max_diff": float(diffs.max()), "min_lum": float(lums.min()),
                     "scene_lum": float(np.mean(lums[:10]))}
    return out


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


def test_blends_shorten_the_clip_and_record_the_new_timeline():
    """A dissolve shows two moments at once, so it costs one blend of length."""
    built = plan_mod.build_plan(candidate(0.1, 3.9), style=blend_style("fade", 0.5))
    clip = built["clip"]
    assert clip["source_duration"] == pytest.approx(3.8)
    assert clip["blend_shortening"] == pytest.approx(0.5)
    assert clip["duration"] == pytest.approx(3.3)
    first, second = built["shots"]
    assert second["transition"] == "fade"
    assert second["transition_duration"] == pytest.approx(0.5)
    assert first["out_end"] - second["out_start"] == pytest.approx(0.5)   # they overlap
    assert second["out_end"] == pytest.approx(clip["duration"])
    assert any("shorter" in note for note in built["notes"])


def test_cut_plans_have_no_shortening_and_no_stray_blend_length():
    built = plan_mod.build_plan(candidate(0.1, 3.9), style=PUNCH_STYLE)
    assert built["clip"]["blend_shortening"] == 0
    assert built["clip"]["duration"] == pytest.approx(built["clip"]["source_duration"])
    assert all(shot["transition_duration"] == 0 for shot in built["shots"])
    assert not any("blend" in note for note in built["notes"])


@pytest.mark.parametrize("asked,expected", [
    ("dissolve", "fade"), ("crossfade", "fade"), ("fade", "fade"),
    ("dip to black", "fade_black"), ("fade_black", "fade_black"),
    ("flash", "fade_white"), ("wipeleft", "wipeleft"), ("circleopen", "circleopen"),
    ("zoomin", "zoomin"), ("squeezeh", "squeezeh"), ("cut", "cut"), ("none", "cut"),
])
def test_transition_names_people_use_map_to_ffmpeg_names(asked, expected):
    assert plan_mod.resolve_transition(asked) == expected


def test_an_impossible_transition_falls_back_to_a_cut_and_says_so():
    assert plan_mod.resolve_transition("sparkle-explosion") is None
    built = plan_mod.build_plan(candidate(0.1, 3.9), style=blend_style("sparkle", 0.5))
    assert built["style"]["transition"] == "cut"
    assert any("not one ffmpeg can blend" in note for note in built["notes"])


def test_a_blend_too_long_for_its_shots_is_shortened():
    style = blend_style("fade", 0.8)
    style["pacing"]["avg_shot_len"] = 1.0            # 1 s shots, 0.8 s blend
    built = plan_mod.build_plan(candidate(0.1, 2.1), style=style)
    shortest = min(shot["duration"] for shot in built["shots"])
    assert built["shots"][0]["transition_duration"] <= shortest * 0.5 + 0.001
    assert any("blend shortened" in note for note in built["notes"])


# ---------------------------------------------------------------------------
# filtergraph
# ---------------------------------------------------------------------------
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


def test_filtergraph_blends_before_the_cut_using_both_shots():
    """The blend has to start one blend-length *before* the cut, not at it.

    Starting it at the cut mixes each frame with itself, which renders as a hard
    cut no matter what the profile says - verified by measuring the output.
    """
    built = plan_mod.build_plan(candidate(0.1, 3.9), style=blend_style("fade", 0.5))
    graph = render_mod.build_filtergraph(built, source_fps=12, source_duration=4.0)
    incoming = built["shots"][1]
    assert (f"xfade=transition=fade:duration=0.500:offset={incoming['out_start']:.3f}"
            in graph)
    assert "acrossfade=d=0.500" in graph
    # both shots keep exactly their own material: no tail is invented
    for shot in built["shots"]:
        assert f"trim=start={shot['start']:.3f}:end={shot['end']:.3f}" in graph


def test_filtergraph_maps_blend_names_to_ffmpeg_names():
    black = plan_mod.build_plan(candidate(0.1, 3.9), style=blend_style("dip to black", 0.4))
    white = plan_mod.build_plan(candidate(0.1, 3.9), style=blend_style("flash", 0.4))
    wipes = plan_mod.build_plan(candidate(0.1, 3.9), style=blend_style("circleopen", 0.4))
    assert "xfade=transition=fadeblack:duration=0.400" in render_mod.build_filtergraph(black)
    assert "xfade=transition=fadewhite:duration=0.400" in render_mod.build_filtergraph(white)
    assert "xfade=transition=circleopen:duration=0.400" in render_mod.build_filtergraph(wipes)


def test_filtergraph_stays_on_the_concat_path_when_nothing_blends():
    graph = render_mod.build_filtergraph(plan_mod.build_plan(candidate(0.1, 3.9), style=PUNCH_STYLE))
    assert "xfade" not in graph and "acrossfade" not in graph
    assert "concat=n=" in graph


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


def test_render_crossfade_spreads_the_change_over_the_blend(blend_renders):
    """A dissolve must be visible in the pixels: no single frame jumps."""
    cut, fade = blend_renders["cut"], blend_renders["fade"]
    assert cut["max_diff"] > 20, "the cut version should show one hard jump"
    assert fade["max_diff"] < cut["max_diff"] * 0.5, (
        f"the dissolve should spread the change over its length, "
        f"but the biggest step was {fade['max_diff']:.1f} vs {cut['max_diff']:.1f}")


def test_render_dip_to_black_goes_through_black(blend_renders):
    black = blend_renders["fade_black"]
    assert black["scene_lum"] > 150, "the test footage is meant to be bright"
    assert black["min_lum"] < black["scene_lum"] * 0.25, (
        f"a dip to black should reach black, darkest frame was {black['min_lum']:.0f} "
        f"against scenes at {black['scene_lum']:.0f}")


def test_blended_renders_match_the_planned_length(blend_renders):
    """Every variant has to land where its plan says, shortening and all."""
    for name, record in blend_renders.items():
        planned = record["plan"]["clip"]["duration"]
        rendered = record["frames"] / 12
        assert rendered == pytest.approx(planned, abs=0.35), f"{name}: {rendered} vs {planned}"


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
# blend sampler
# ---------------------------------------------------------------------------
def test_sampler_knows_every_blend_this_ffmpeg_has(tmp_path):
    from clipper.edit.sampler import available_blends

    names = available_blends()
    assert len(names) >= 40, "ffmpeg's xfade catalogue should be there in full"
    for expected in ("fade", "fadeblack", "wipeleft", "circleopen", "zoomin", "pixelize"):
        assert expected in names
    assert "custom" not in names, "custom is the 'bring your own' slot, not a blend"


def test_sampler_refuses_names_ffmpeg_does_not_have(tmp_path):
    from clipper.edit.sampler import render_sampler

    with pytest.raises(ValueError, match="sparkle"):
        render_sampler(tmp_path / "no.mp4", blends=["fade", "sparkle"], seconds=0.5,
                       size=(160, 284), fps=12, work_dir=tmp_path / "scratch")


def test_sampler_renders_a_labelled_reel(tmp_path):
    """Each blend gets its own labelled segment, so the names are checkable."""
    from clipper.edit.sampler import render_sampler

    out = render_sampler(tmp_path / "sampler.mp4", blends=["fade", "wipeleft"],
                         seconds=0.8, size=(240, 426), fps=12,
                         work_dir=tmp_path / "scratch")
    info = probe(out)
    assert (info.width, info.height) == (240, 426)
    assert info.has_audio
    # two segments of two 0.8 s shots, each blend 0.32 s long
    assert info.duration == pytest.approx(2 * (0.8 + 0.8 - 0.32), abs=0.4)
    labels = (tmp_path / "scratch" / "labels.ass").read_text()
    assert "FADE" in labels and "WIPELEFT" in labels


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


def test_focus_x_moves_the_vertical_window_sideways():
    from clipper.edit.render import build_filtergraph, crop_offset

    assert crop_offset("centre")[0] == "(iw-ow)/2"
    assert crop_offset("centre", 0.35)[0] == "(iw-ow)*0.3500"
    assert crop_offset("centre", -4)[0] == "(iw-ow)*0.0000"      # clamped
    assert crop_offset("centre", 9)[0] == "(iw-ow)*1.0000"

    plan = {"target": {"width": 1080, "height": 1920, "fps": 30},
            "shots": [{"start": 0, "end": 2, "zoom": {"type": "static"}}]}
    graph = build_filtergraph(plan, focus="top", focus_x=0.25)
    assert "crop=1080:1920:(iw-ow)*0.2500:(ih-1920)*0.18" in graph


def test_zoom_punches_when_the_profile_measured_static():
    from clipper.edit.plan import camera_moves

    style = {"zoom": {"dominant": "static", "punch_in_scale": 1.14,
                      "punch_in_duration": 0.58}}
    assert {m["type"] for m in camera_moves(style, [1.4] * 5)} == {"static"}

    punches = camera_moves(style, [1.4] * 5, override="punch")
    assert all(m["type"] == "punch_in" and abs(m["to"] - 1.14) < 1e-6 for m in punches)

    mixed = camera_moves({**style, "zoom": {**style["zoom"], "punch_in_ratio": 0.5}},
                         [1.4] * 8, override="mixed")
    kinds = [m["type"] for m in mixed]
    assert kinds[0] == "punch_in"                    # the opening shot always moves
    assert 0 < kinds.count("punch_in") < len(kinds)  # and the rest breathe

    pull = camera_moves(style, [2.0], override="pull")[0]
    assert pull["from"] == 1.14 and pull["to"] == 1.0  # zoompan never drops below 1.0


def test_zoompan_expression_never_goes_below_one():
    from clipper.edit.render import _zoom_expression

    z = _zoom_expression({"type": "pull_out", "from": 1.14, "to": 1.0, "over": 2.0}, 30)
    assert z is not None
    z = _zoom_expression({"type": "pull_out", "from": 0.85, "to": 1.0, "over": 2.0}, 30)
    assert z is None                                  # sub-1.0 is clamped, so it collapses
    z2 = _zoom_expression({"type": "punch_in", "from": 1.0, "to": 1.0, "over": 0.5}, 30)
    assert z2 is None                               # a zero move renders as static
