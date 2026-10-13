"""ASS generation: colours, karaoke tags, sizing and position maths."""
from __future__ import annotations

from clipper import config
from clipper.asr.base import Word
from clipper.captions.ass import ass_color, build_ass, write_ass
from clipper.captions.cues import group_words


def W(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end, source="test")


def sample_cues():
    words = [W("Make", 0.0, 0.4), W("it", 0.4, 0.6), W("viral.", 0.6, 1.1)]
    return group_words(words, max_words=4, max_chars=30, gap_break=9)


def test_ass_color_roundtrip():
    assert ass_color("#FFFFFF") == "&H00FFFFFF"
    assert ass_color("#FF0000") == "&H000000FF"   # ASS is BGR
    assert ass_color([0, 255, 0]) == "&H0000FF00"
    assert ass_color("#123456", alpha=0x80) == "&H80563412"


def test_build_ass_has_header_style_and_events():
    text = build_ass(sample_cues(), config.DEFAULT_STYLE, width=1080, height=1920)
    assert "[Script Info]" in text and "PlayResX: 1080" in text and "PlayResY: 1920" in text
    assert "[V4+ Styles]" in text
    style_line = next(l for l in text.splitlines() if l.startswith("Style: Cap"))
    assert "Montserrat" in style_line
    events = [l for l in text.splitlines() if l.startswith("Dialogue:")]
    assert len(events) == 1
    assert "Make" in events[0] and "viral." in events[0]


def test_karaoke_tags_match_word_durations():
    text = build_ass(sample_cues(), config.DEFAULT_STYLE)
    event = next(l for l in text.splitlines() if l.startswith("Dialogue:"))
    assert r"\k40" in event   # 0.40 s -> 40 cs
    assert r"\k20" in event
    assert r"\k50" in event


def test_karaoke_can_be_disabled():
    style = config.deep_merge(config.DEFAULT_STYLE, {"captions": {"karaoke": {"enabled": False}}})
    event = next(l for l in build_ass(sample_cues(), style).splitlines() if l.startswith("Dialogue:"))
    assert r"\k" not in event


def test_font_size_scales_with_canvas():
    style = config.deep_merge(config.DEFAULT_STYLE, {"captions": {"font_size_ass": 96}})
    big = next(l for l in build_ass(sample_cues(), style, width=1080, height=1920).splitlines()
               if l.startswith("Style: Cap"))
    small = next(l for l in build_ass(sample_cues(), style, width=540, height=960).splitlines()
                 if l.startswith("Style: Cap"))
    assert big.split(",")[2] == "96"
    assert small.split(",")[2] == "48"


def test_uppercase_casing_is_applied():
    style = config.deep_merge(config.DEFAULT_STYLE, {"captions": {"casing": "upper"}})
    event = next(l for l in build_ass(sample_cues(), style).splitlines() if l.startswith("Dialogue:"))
    assert "VIRAL." in event and "viral." not in event


def test_word_mode_emits_one_event_per_word():
    text = build_ass(sample_cues(), config.DEFAULT_STYLE, mode="word")
    events = [l for l in text.splitlines() if l.startswith("Dialogue:")]
    assert len(events) == 3
    assert all("viral." in e for e in events)   # full cue stays visible
    assert any(r"\c&H00" in e for e in events)  # active word recoloured


def test_position_controls_margin():
    style = config.deep_merge(config.DEFAULT_STYLE,
                              {"captions": {"position": {"anchor": "bottom_center", "cy": 0.80}}})
    style_line = next(l for l in build_ass(sample_cues(), style, height=1920).splitlines()
                      if l.startswith("Style: Cap"))
    margin_v = int(style_line.split(",")[21])
    assert 250 < margin_v < 500     # ~384 - half a line: sits around 80% height


def test_write_ass(tmp_path):
    p = write_ass(tmp_path / "x.ass", sample_cues(), config.DEFAULT_STYLE)
    assert p.exists() and p.read_text(encoding="utf-8").startswith("[Script Info]")
