"""A user must be able to choose fonts and colours independently per video."""
from __future__ import annotations

import json

import pytest

from scripts.whop import style_card


def test_video_style_inherits_campaign_then_stays_independent(tmp_path, monkeypatch):
    monkeypatch.setattr(style_card, "ROOT", tmp_path)
    theme_dir = tmp_path / "motion" / "themes"
    theme_dir.mkdir(parents=True)
    (theme_dir / "whop.json").write_text(json.dumps({
        "name": "whop", "accent": "#14E5C5", "cutTransitions": "hard"}))

    base = style_card.load_style("street")
    base["caption"] = "oblique"
    base["colors"]["accent"] = "#4D6ECC"
    style_card.save_style("street", base)

    post1 = style_card.load_style("street", "post1")
    assert post1["caption"] == "oblique"
    assert post1["colors"]["accent"] == "#4D6ECC"
    post1["caption"] = "grande"
    post1["keyword"] = "displaybook"
    post1["colors"]["accent"] = "#E6B14C"
    post1["colors"]["endcard"] = "#E6B14C"
    p = style_card.save_style("street", post1, "post1")
    assert p == tmp_path / "campaigns" / "street" / "post1" / "style.json"

    assert style_card.load_style("street", "post1")["caption"] == "grande"
    assert style_card.load_style("street", "post2")["caption"] == "oblique"
    assert style_card.load_style("street", "post2")["colors"]["accent"] == "#4D6ECC"
    t1 = json.loads((theme_dir / "street__post1.json").read_text())
    tc = json.loads((theme_dir / "street.json").read_text())
    assert (t1["fontPack"], t1["fonts"]["keyword"], t1["accent"]) == (
        "grande", "displaybook", "#E6B14C")
    assert (tc["fontPack"], tc["accent"]) == ("oblique", "#4D6ECC")
    assert t1["cutTransitions"] == "hard"
    assert t1["colors"]["keyword"] == t1["accent"]
    assert tc["colors"]["keyword"] == tc["accent"]


def test_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(style_card, "ROOT", tmp_path)
    for video in ("../post1", "post/1", "post 1"):
        with pytest.raises(ValueError):
            style_card.style_path("street", video)
    with pytest.raises(ValueError):
        style_card.style_path("../street")


def test_rejects_unsafe_css_or_unlicensed_font_in_saved_choice():
    import copy
    st = copy.deepcopy(style_card.DEFAULT_STYLE)
    assert style_card.validate_style(st)
    st["colors"]["serif"] = "red;position:absolute"
    assert not style_card.validate_style(st)
    st["colors"]["serif"] = "#AABBCC"
    st["caption"] = "unknown-font"
    assert not style_card.validate_style(st)


def test_browser_preview_uses_real_fonts_full_frame_and_milliseconds():
    html = style_card.PAGE
    assert "__FONT_FACES__" in html
    assert "width:1080px; height:1920px" in html
    assert "transform:scale(0.3333333)" in html
    assert "renderAt(t * 1000)" in html
    assert 'layout:"diagram"' in html
    assert "titleLines" in html
