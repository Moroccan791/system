"""Next-level format: poster stacks, claim cards, stickers, music beds."""

import re
import wave

from clipper.asr.base import Word
from clipper.captions.musicbed import synthesize_beds
from clipper.captions.poster import build_poster_ass
from clipper.qc import check_visual_pacing, parse_ass_events

STYLE = {"captions": {"font_name": "Montserrat", "primary_text_color": "#FDFCFD",
                      "outline_color": "#0B090B",
                      "poster": {"keyword_color": "#9BE82E",
                                 "card_bg": "#0B1F14",
                                 "sticker_bg": "#9BE82E"}}}


def W(start, dur, text):
    return Word(text=text, start=start, end=start + dur)


def test_poster_stacks_keyword_biggest_and_in_sync():
    words = [W(0.0, 0.25, "Nobody"), W(0.3, 0.25, "believes"),
             W(0.6, 0.3, "me."), W(1.2, 0.25, "Ten"),
             W(1.5, 0.25, "thousand"), W(1.8, 0.3, "dollars.")]
    ass, blocks = build_poster_ass(words, STYLE, end=6.0)
    poster = [ln for ln in ass.splitlines() if ",Poster," in ln]
    assert poster
    sizes = [float(m.group(1)) for ln in poster
             for m in [re.search(r"\\fs([\d.]+)", ln)] if m]
    assert max(sizes) > min(sizes)  # the keyword towers over connectives
    # every word appears at (not before) its spoken start
    first = re.match(r"Dialogue: 1,([\d:.]+),", poster[0]).group(1)
    assert first == "0:00:00.00"
    assert all(0 < b["bbox"][1] < 1920 for b in blocks if b["bbox"])


def test_poster_serif_for_pure_filler_rows():
    words = [W(0.0, 0.2, "It"), W(0.25, 0.2, "is"), W(0.5, 0.35, "over.")]
    ass, _ = build_poster_ass(words, STYLE, end=4.0)
    assert "DejaVu Serif" in ass  # the connective row gets the serif


def test_claim_card_and_sticker_and_list_events():
    words = [W(0.0, 0.3, "Hello.")]
    ass, _ = build_poster_ass(
        words, STYLE, end=12.0,
        cards=[{"at": 4.0, "dur": 1.8, "lines": ["NEXT TIME", "A PLUS"]}],
        stickers=[{"at": 6.0, "dur": 4.0, "text": "$20,000",
                   "sub": "FIRST MONTH", "pos": "tl"}],
        lists=[{"at": 8.0, "dur": 3.0, "items": ["EGOS", "DESIRES"]}])
    cards = [ln for ln in ass.splitlines() if ",Card," in ln]
    assert any(r"\p1" in ln for ln in cards)          # the brand panel
    assert any("A PLUS" in ln for ln in cards)
    sticker = [ln for ln in ass.splitlines() if ",Sticker," in ln]
    assert any("$20,000" in ln for ln in sticker)
    assert any("1  EGOS" in ln and "2  DESIRES" in ln for ln in sticker)


def test_visual_pacing_flags_dead_stretches(tmp_path):
    ass = ("Dialogue: 1,0:00:00.00,0:00:01.00,Poster,,0,0,0,,A\n"
           "Dialogue: 1,0:00:09.00,0:00:10.00,Poster,,0,0,0,,B\n")
    p = tmp_path / "x.ass"
    p.write_text("[Events]\n" + ass)
    events = parse_ass_events(p)
    assert check_visual_pacing(events)["status"] == "fail"


def test_music_beds_are_32s_and_distinct(tmp_path):
    written = synthesize_beds(tmp_path)
    assert len(written) == 3
    blobs = set()
    for p in written:
        with wave.open(str(p)) as wf:
            assert wf.getframerate() == 48000
            assert abs(wf.getnframes() / wf.getframerate() - 32.0) < 0.1
        blobs.add(p.read_bytes()[:4096])
    assert len(blobs) == 3
