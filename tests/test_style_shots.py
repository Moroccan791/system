"""Stage 1: cuts and zoom, checked against clips whose truth we generated."""
from __future__ import annotations

import numpy as np
import pytest

from clipper.style.frames import sample_video
from clipper.style.shots import detect_cuts, detect_from_video
from clipper.style.zoom import analyze_zoom, estimate_scale
from clipper.synth import render_cut_clip, render_zoom_clip, textured_scene, zoom_frame


def test_cuts_are_found_exactly(tmp_path):
    clip = render_cut_clip(str(tmp_path / "cuts.mp4"), shots=[2, 2, 2],
                           size=(540, 960), fps=15)
    result = detect_from_video(clip["path"], fps=6, width=240)
    assert result.cuts == pytest.approx([2.0, 4.0], abs=0.2)
    stats = result.stats()
    assert stats["shot_count"] == 3
    assert stats["avg_shot_len"] == pytest.approx(2.0, abs=0.25)
    assert stats["cuts_per_minute"] == pytest.approx(20.0, abs=2.5)


def test_static_clip_has_no_cuts(tmp_path):
    from clipper.synth import write_video

    base = textured_scene(320, 568, seed=5)
    clip = str(tmp_path / "static.mp4")
    write_video(clip, (base for _ in range(60)), fps=15)
    result = detect_from_video(clip, fps=6, width=240)
    assert result.cuts == []


def test_estimate_scale_measures_known_zoom():
    base = textured_scene(320, 568, seed=3)
    gray = lambda img: np.asarray(img).mean(axis=2)  # noqa: E731
    for truth in (1.00, 1.06, 1.15):
        scale, response = estimate_scale(gray(base), gray(zoom_frame(base, truth)), size=200)
        assert response > 0.5, "NCC should lock onto textured frames"
        assert scale == pytest.approx(truth, abs=0.04)
    scale, response = estimate_scale(gray(base), gray(zoom_frame(base, 1.5)), size=200)
    assert scale > 1.0, "direction must be right even outside the default range"


def test_estimate_scale_reports_no_confidence_on_flat_frames():
    flat = np.full((200, 200), 128, dtype=np.uint8)
    scale, response = estimate_scale(flat, flat)
    assert scale == 1.0 and response == 0.0


def test_punch_in_is_detected(tmp_path):
    clip = render_zoom_clip(str(tmp_path / "punch.mp4"), duration=3.0, fps=15,
                            punch_scale=1.15, punch_over=0.3, size=(540, 960))
    frames = list(sample_video(clip["path"], fps=8, width=240))
    result = analyze_zoom(frames, [])
    assert result.pattern == "punch_in"
    assert result.scale == pytest.approx(1.15, abs=0.05)
    assert result.duration == pytest.approx(0.3, abs=0.15)


def test_static_clip_is_called_static(tmp_path):
    from clipper.synth import write_video

    base = textured_scene(540, 960, seed=9)
    clip = str(tmp_path / "still.mp4")
    write_video(clip, (base for _ in range(45)), fps=15)
    frames = list(sample_video(clip, fps=8, width=240))
    assert analyze_zoom(frames, []).pattern == "static"


def test_zoom_resets_at_cuts(tmp_path):
    """Two shots, each with its own punch-in, must be measured separately."""
    from clipper.synth import write_video

    frames = []
    for seed in (1, 2):                      # 45 frames at 15 fps = 3 s per shot
        base = textured_scene(540, 960, seed=seed)
        for j in range(45):
            elapsed = j / 15
            frames.append(zoom_frame(base, 1.0 + 0.14 * min(1.0, elapsed / 0.3)))
    clip = str(tmp_path / "two.mp4")
    write_video(clip, iter(frames), fps=15)
    sampled = list(sample_video(clip, fps=8, width=240))
    cuts = detect_cuts(sampled).cuts
    assert cuts == pytest.approx([3.0], abs=0.3)
    result = analyze_zoom(sampled, cuts)
    assert result.pattern == "punch_in"
    assert result.scale == pytest.approx(1.14, abs=0.05)
