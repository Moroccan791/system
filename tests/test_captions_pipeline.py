"""End to end stage 3: text -> cues -> .ass -> pixels in a 1080x1920 mp4.

The pixel check is the important one: it proves captions are really burned in,
not just written to a file somewhere.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from clipper import config
from clipper.captions import run_captions
from clipper.ffmpeg import iter_frames, probe
from clipper.samples import demo_words


@pytest.fixture()
def captioned(tmp_path):
    """Render the tone video with fixture words (no ASR needed)."""
    from clipper.asr.fixture import FixtureProvider

    words = [w for w in demo_words() if w.end <= 4.8]  # keep inside the 5 s tone clip
    src = tmp_path / "src.mp4"
    import subprocess

    from clipper.ffmpeg import ffmpeg_exe

    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=540x960:d=5:r=30", "-f", "lavfi", "-i",
                    "sine=frequency=300:sample_rate=48000:duration=5",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-shortest",
                    str(src)], check=True, capture_output=True)
    result = run_captions(
        src, tmp_path / "out.mp4", provider="fixture",
        asr_kwargs={"words": words}, work_name="test-captions",
    )
    return result


def test_result_is_complete(captioned):
    assert captioned.n_words > 0 and captioned.n_cues > 0
    assert captioned.ass and captioned.output
    from pathlib import Path

    assert Path(captioned.ass).exists() and Path(captioned.output).exists()
    assert Path(captioned.report).exists()


def test_output_is_vertical_1080x1920(captioned):
    info = probe(captioned.output)
    assert (info.width, info.height) == (1080, 1920)
    assert info.has_audio


def test_output_duration_matches_source(captioned):
    info = probe(captioned.output)
    assert 4.4 < info.duration < 5.6


def test_captions_are_actually_burned_in(captioned):
    """Look at the pixels: white glyphs, black outline, karaoke highlight.

    This is the test that would have caught filter tags leaking into the caption
    text, so it checks all three visual signatures, not just "something bright".
    """
    from clipper.captions.pipeline import resolve_style

    style, _ = resolve_style()
    cap = style["captions"]
    cy = cap["position"]["cy"]
    band_top, band_bottom = int(1920 * (cy - 0.09)), int(1920 * (cy + 0.07))
    hl = cap["karaoke"]["highlight_color"].lstrip("#")
    want_bgr = np.array([int(hl[4:6], 16), int(hl[2:4], 16), int(hl[0:2], 16)], dtype=np.int16)

    frames = list(iter_frames(captioned.output, size=(1080, 1920), fps=4, start=0.2, duration=4.4))
    assert frames, "could not read frames"

    white_ratio = dark_ratio = highlight_ratio = 0.0
    for frame in frames:
        band = frame[band_top:band_bottom].astype(np.int16)
        gray = band.mean(axis=2)
        white_ratio = max(white_ratio, float((gray > 235).mean()))
        dark_ratio = max(dark_ratio, float((gray < 25).mean()))
        dist = np.abs(band - want_bgr).sum(axis=2)
        highlight_ratio = max(highlight_ratio, float((dist < 90).mean()))

    assert white_ratio > 0.002, f"no white glyph pixels in the caption band ({white_ratio:.4f})"
    assert dark_ratio > 0.002, f"no outline pixels in the caption band ({dark_ratio:.4f})"
    assert highlight_ratio > 0.0005, f"no karaoke highlight pixels ({highlight_ratio:.5f})"


def test_caption_text_never_leaks_override_tags(captioned):
    """Regression: a tag outside {} is rendered as literal text on screen."""
    from pathlib import Path

    ass = Path(captioned.ass).read_text(encoding="utf-8")
    for line in ass.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        body = line.split(",,", 1)[-1]
        # remove override blocks, then no backslash tag may remain in the text
        import re

        stripped = re.sub(r"\{[^}]*\}", "", body)
        assert "\\" not in stripped, f"leaked tag in caption text: {stripped[:120]!r}"


def test_work_artifacts_written(captioned):
    work = __import__("pathlib").Path(captioned.work_dir)
    for name in ("transcript.json", "cues.json", "captions.ass", "report.json", "style.used.json"):
        assert (work / name).exists(), name
    cues = json.loads((work / "cues.json").read_text())
    assert cues["count"] == captioned.n_cues
    assert cues["cues"][0]["words"][0]["text"]


def test_ass_only_skips_video(tmp_path):
    from clipper.asr.fixture import FixtureProvider  # noqa: F401

    result = run_captions(
        __import__("pathlib").Path(__file__).parent.parent / "samples" / "campaign_demo" / "raw" / "raw_01.mp4",
        tmp_path / "never.mp4", provider="fixture", asr_kwargs={"script": ["hello", "world"]},
        ass_only=True, work_name="test-ass-only",
    ) if (__import__("pathlib").Path(__file__).parent.parent / "samples" / "campaign_demo" / "raw" / "raw_01.mp4").exists() else None
    if result is not None:
        assert result.output is None and result.ass
