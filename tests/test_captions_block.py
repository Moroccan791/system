"""Block captions: the tutorial recipe as tests."""

import re

from clipper.asr.base import Word
from clipper.captions.block import (build_fade_bar, declutter, pick_emphasis,
                                    segment_sentences, write_block_ass)
from clipper.captions.render import _insert_chains, grade_chain

STYLE = {"captions": {"font_name": "Montserrat", "primary_text_color": "#FDFCFD",
                      "outline_color": "#275B77", "position": {"margin_v": 420},
                      "block": {"base_size_ass": 84, "emphasis_scale": 1.6}}}


def W(start, dur, text):
    return Word(text=text, start=start, end=start + dur)


def test_segmenting_respects_punctuation_pauses_and_size():
    words = [W(0.0, 0.3, "Ever"), W(0.3, 0.4, "friendzoned?"),
             W(1.0, 0.3, "Always"), W(1.3, 0.3, "have.")]
    sents = segment_sentences(words)
    assert len(sents) == 2 and sents[0][-1].text == "friendzoned?"

    paused = [W(0.0, 0.3, "ready."), W(9.0, 0.3, "now")]
    assert len(segment_sentences(paused)) == 2

    many = [W(i * 0.3, 0.2, f"w{i}") for i in range(30)]
    assert all(len(s) <= 10 for s in segment_sentences(many, max_words=10))


def test_emphasis_picks_content_and_numbers_never_filler():
    sent = [W(0, 0.3, t) for t in "Sixty eight percent of men report getting friend zoned.".split()]
    assert pick_emphasis(sent) == 2                      # "percent" beats "getting"

    sent2 = [W(0, 0.3, t) for t in "Love is understanding and giving space".split()]
    big = sent2[pick_emphasis(sent2)].text.lower()
    assert big in ("understanding", "space")
    assert big not in ("is", "and")


def test_block_events_never_overlap_the_next_block_and_x_advances(tmp_path):
    words = [W(0.0, 0.3, "Worst"), W(0.3, 0.5, "statistic"), W(0.8, 0.3, "ever?"),
             W(1.2, 0.3, "Ready"), W(1.5, 0.3, "now.")]
    path, blocks = write_block_ass(tmp_path / "b.ass", words, STYLE, end=2.2)
    events = [l for l in path.read_text().splitlines()
              if l.startswith("Dialogue") and ",Block," in l]
    assert events, "no word events written"
    xs = [float(re.search(r"\\pos\(([-\d.]+),", ev).group(1)) for ev in events]
    assert all(x >= 0 for x in xs), "a word landed off the left edge"

    # every word of block 1 must clear before "Ready" paints at 1.2s
    for ev in events:
        if "}Worst" in ev or "}statistic" in ev or "}ever?" in ev:
            end_t = re.search(r"Dialogue: 1,[\d:.]+,([\d:.]+)", ev).group(1)
            h, m, s = end_t.split(":")
            assert float(h) * 3600 + float(m) * 60 + float(s) <= 1.2 + 0.001


def test_fade_bar_is_a_gradient_of_strips():
    bars = build_fade_bar(1080, 1920, alpha=0.5, zone=600, strips=18)
    assert len(bars) == 18
    alphas = [int(re.search(r"\\1a&H([0-9A-F]{2})&", b).group(1), 16) for b in bars]
    assert alphas[0] > alphas[-1]                 # top of the zone is nearest transparent
    assert alphas[-1] <= 130                      # bottom reaches roughly 0.5 opacity


def test_grade_and_insert_chains():
    assert grade_chain(None) == "" and grade_chain({}) == ""
    chain = grade_chain({"vignette": 0.26, "contrast": 1.05, "saturation": 1.06})
    assert "vignette=angle=" in chain and "contrast=1.050" in chain

    joiner, pre = _insert_chains(
        [{"start": 5.0, "duration": 2.0, "file": "a.png"},
         {"start": 9.0, "duration": 1.5, "file": "b.png", "at": "top_safe"}],
        1080, 1920, "vsub")
    assert "[vsub][ov0]overlay" in joiner and "[vins0][ov1]overlay" in joiner
    assert len(pre) == 2 and "setpts=PTS-STARTPTS+5.000/TB" in pre[0]

    # a full-frame insert is a cutaway (crop to frame), never a face sticker
    _, pre_full = _insert_chains(
        [{"start": 1.0, "duration": 2.0, "file": "a.png", "at": "full"}], 1080, 1920, "vsub")
    assert "crop=1080:1920" in pre_full[0]


def test_block_lines_never_run_off_the_frame(tmp_path):
    words = [W(i * 0.3, 0.25, t) for i, t in enumerate(
        "All right well anyway let us go around the table and ask everybody".split())]
    path, _ = write_block_ass(tmp_path / "w.ass", words, STYLE, end=5.0)
    for line in path.read_text().splitlines():
        m = re.search(r"\\pos\(([-\d.]+),", line)
        if m:
            assert float(m.group(1)) >= 0, "a caption word starts off-frame"


def test_declutter_keeps_one_voice_when_speakers_collide():
    # two voices woven into one stream at the same timestamps (moonshine ASR
    # under crosstalk): the tiling speaker survives, the talk-over drops
    words = [W(0.0, 0.30, "No"), W(0.02, 0.28, "yeah"), W(0.32, 0.30, "offense"),
             W(0.34, 0.25, "right"), W(0.64, 0.30, "waiting"), W(1.40, 0.25, "months.")]
    kept = [w.text for w in declutter(words)]
    assert kept == ["No", "offense", "waiting", "months."]


def test_accent_colors_only_the_emphasis_word(tmp_path):
    style = {"captions": {"font_name": "Montserrat", "primary_text_color": "#FDFCFD",
                          "outline_color": "#275B77", "position": {"margin_v": 420},
                          "block": {"base_size_ass": 84, "emphasis_scale": 1.6,
                                    "emphasis_color": "#FFC531"}}}
    words = [W(0.0, 0.3, "Men"), W(0.3, 0.3, "need"), W(0.6, 0.4, "validation.")]
    path, blocks = write_block_ass(tmp_path / "a.ass", words, style, end=2.0)
    colored = [l for l in path.read_text().splitlines() if "\\1c" in l]
    assert len(colored) == 1 and "Validation." in colored[0]
    assert "\\1c&H0031C5FF" in colored[0]          # ASS colors are BBGGRR
