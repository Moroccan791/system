"""Stage 1: reading caption style out of rendered references.

Ground truth is generated, not guessed: clips are rendered through the same
renderer the pipeline uses, then the extractor has to recover the values it was
given. Tolerances are the ones the implementation actually achieves - they are
regression guards, and they document how accurate each measurement is.
"""
from __future__ import annotations

import subprocess

import cv2
import numpy as np
import pytest

from clipper import config
from clipper.asr.base import Word
from clipper.captions.ass import write_ass
from clipper.captions.cues import group_words
from clipper.captions.render import subtitles_filter
from clipper.ffmpeg import ffmpeg_exe
from clipper.style import captions_detect as cd
from clipper.style.frames import sample_video

BASE_STYLE = config.deep_merge(config.DEFAULT_STYLE, {
    "captions": {
        "font_family": "Montserrat", "font_size_ass": 120, "casing": "upper",
        "primary_color": "#FFFFFF", "outline_color": "#000000", "outline_width": 6,
        "position": {"anchor": "bottom_center", "cx": 0.5, "cy": 0.72},
        "karaoke": {"enabled": True, "highlight_color": "#FFE14D"},
        "animation": {"in": "none"},
        "max_words_per_cue": 3, "max_lines": 1, "max_chars_per_line": 16,
    },
})

SCRIPT = [("THIS", "IS", "ONE"), ("NEXT", "LINE", "HERE"), ("THIRD", "CLIP", "SET"),
          ("LAST", "WORDS", "NOW")]


def _words(script=SCRIPT, per_word=0.42, gap=0.06, cue_gap=0.22, start=0.35):
    out, t = [], start
    for cue in script:
        for token in cue:
            out.append(Word(text=token, start=round(t, 3), end=round(t + per_word, 3)))
            t += per_word + gap
        t += cue_gap
    return out


def render_reference(path, style, *, script=SCRIPT, duration=6.0, background="0x1a1a1a",
                     autofit: bool = False):
    """A 9:16 clip with captions burned in using `style`.

    `autofit` is off by default: it shrinks oversized lines to fit the safe
    area, which would make the rendered font size differ from the requested one
    and turn every "did we recover the size" assertion into a lie.
    """
    cues = group_words(_words(script), max_words=style["captions"]["max_words_per_cue"],
                       max_chars=style["captions"]["max_chars_per_line"], max_lines=1,
                       gap_break=9)
    ass = path.with_suffix(".ass")
    write_ass(ass, cues, style, width=1080, height=1920, autofit=autofit)
    subprocess.run([
        ffmpeg_exe(), "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c={background}:s=1080x1920:d={duration}",
        "-vf", subtitles_filter(ass),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-t", str(duration), str(path),
    ], check=True)
    ass.unlink(missing_ok=True)
    return path


def analyse(path, fps=6.0, width=480):
    """Analyse the way stage 1 does, including renderer self-calibration."""
    from clipper.style.extract import DEFAULT_SAMPLE_WIDTH

    width = width or DEFAULT_SAMPLE_WIDTH
    cap_height_em = cd.calibrate_cap_height(path.parent / "_calib", sampled_width=width)
    return cd.analyze_captions(list(sample_video(str(path), fps=fps, width=width)),
                               cap_height_em=cap_height_em)


# ---------------------------------------------------------------------------
# calibration
# ---------------------------------------------------------------------------
def test_font_size_calibration(tmp_path):
    """CAP_HEIGHT_EM must match what our own renderer produces.

    If a font, libass or ffmpeg change moves the ratio, this fails loudly rather
    than silently skewing every extracted font size.
    """
    style = config.deep_merge(BASE_STYLE, {"captions": {"font_size_ass": 200, "casing": "upper"}})
    path = render_reference(tmp_path / "cal.mp4", style, script=[("HANDSOME",)], duration=1.5)
    result = analyse(path)
    assert result["present"], "calibration clip was not detected at all"
    measured = result["font_size_ass"]
    assert measured == pytest.approx(200, rel=0.10), (
        f"cap-height constant drifted: asked for 200, measured {measured} "
        f"(CAP_HEIGHT_EM={cd.CAP_HEIGHT_EM})"
    )


# ---------------------------------------------------------------------------
# measurements
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def karaoke_ref(tmp_path_factory):
    return analyse(render_reference(tmp_path_factory.mktemp("s1") / "karaoke.mp4", BASE_STYLE))


def test_captions_are_found(karaoke_ref):
    assert karaoke_ref["present"] is True
    assert karaoke_ref["confidence"] > 0.5
    assert karaoke_ref["evidence"]["cue_count"] >= 2


def test_position_is_recovered(karaoke_ref):
    assert karaoke_ref["position"]["cx"] == pytest.approx(0.5, abs=0.06)
    assert karaoke_ref["position"]["cy"] == pytest.approx(0.72, abs=0.05)


def test_font_size_is_recovered(karaoke_ref):
    # size carries ~±25% uncertainty because the font face cannot be identified
    assert karaoke_ref["font_size_ass"] == pytest.approx(120, rel=0.25)


def test_colours_are_recovered(karaoke_ref):
    def close(hex_a, hex_b, tol=60):
        a = np.array([int(hex_a[i:i + 2], 16) for i in (1, 3, 5)], dtype=int)
        b = np.array([int(hex_b[i:i + 2], 16) for i in (1, 3, 5)], dtype=int)
        return int(np.abs(a - b).sum()) <= tol

    assert close(karaoke_ref["primary_color"], "#FFFFFF"), karaoke_ref["primary_color"]
    assert close(karaoke_ref["outline_color"], "#000000"), karaoke_ref["outline_color"]
    assert close(karaoke_ref["karaoke"]["highlight_color"], "#FFE14D"), \
        karaoke_ref["karaoke"]["highlight_color"]


def test_casing_is_recovered(karaoke_ref):
    assert karaoke_ref["casing"] == "upper"


def test_karaoke_is_detected_when_present(karaoke_ref):
    assert karaoke_ref["karaoke"]["enabled"] is True
    assert karaoke_ref["karaoke"]["highlight_color"] is not None


def test_karaoke_is_not_invented_when_absent(tmp_path):
    style = config.deep_merge(BASE_STYLE,
                              {"captions": {"karaoke": {"enabled": False, "highlight_color": None}}})
    result = analyse(render_reference(tmp_path / "plain.mp4", style))
    assert result["present"] is True
    assert result["karaoke"]["enabled"] is False
    assert result["karaoke"]["highlight_color"] is None


def test_lowercase_is_not_reported_as_upper(tmp_path):
    style = config.deep_merge(BASE_STYLE, {"captions": {"casing": None}, "karaoke": {"enabled": False}})
    script = [("this", "is", "one"), ("next", "line", "here"), ("third", "clip", "set")]
    result = analyse(render_reference(tmp_path / "lower.mp4", style, script=script))
    assert result["present"] is True
    assert result["casing"] is None


def test_word_count_is_close(karaoke_ref):
    assert karaoke_ref["max_words_per_cue"] == pytest.approx(3, abs=1)


def test_no_captions_reports_absent(tmp_path):
    path = tmp_path / "blank.mp4"
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=0x202020:s=1080x1920:d=3", "-c:v", "libx264", "-preset",
                    "ultrafast", "-pix_fmt", "yuv420p", str(path)], check=True)
    result = analyse(path)
    assert result["present"] is False
    assert result["confidence"] < 0.3


def test_evidence_frames_are_written(tmp_path):
    from clipper.style.extract import analyze_reference

    style = BASE_STYLE
    path = render_reference(tmp_path / "ev.mp4", style)
    out = analyze_reference(path, evidence_dir=tmp_path / "evidence")
    frames = out["captions"]["evidence"]["frames"]
    assert frames, "no evidence frame was written"
    import pathlib

    for f in frames:
        assert pathlib.Path(f).exists()
        img = cv2.imread(f)
        assert img is not None and img.shape[0] > 10
