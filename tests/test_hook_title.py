"""The hook title and the synthesised bed.

Two things the user asked for and one thing the gate must keep honest: the
opening line set large where the platform UI is not, a bed that is felt rather
than heard, and the voice staying clear on top of it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import font_refresh as FR   # noqa: E402
import sound_design as SD   # noqa: E402


def cells(*words: str, key: tuple[int, ...] = (2,)) -> list[dict]:
    return [{"w": w.upper(), "at": 0.15 * i + 0.2, "end": 0.15 * i + 0.32,
             "kind": "key" if i in key else "body"}
            for i, w in enumerate(words)]


# ------------------------------------------------------------------ hook title
def test_title_is_empty_until_its_first_word() -> None:
    t = FR.Typesetter.__new__(FR.Typesetter)
    style = {"colors": {"caption": "#F4EFE6", "accent": "#E8C36A",
                        "keyword": "#E23B2F", "sceneBg": "#0B0E11"}}
    t.__init__(style)
    img = t.hook_image(cells("I", "will", "never"), -1.0)
    assert img.shape == (FR.H, FR.W, 4)
    assert img[:, :, 3].max() == 0, "nothing on screen before the first word"


def test_title_reveals_and_sits_in_the_top_third() -> None:
    t = FR.Typesetter({"colors": {"caption": "#F4EFE6", "accent": "#E8C36A",
                                  "keyword": "#E23B2F", "sceneBg": "#0B0E11"}})
    img = t.hook_image(cells("I", "will", "never", "be"), 1.0, y=300)
    a = img[:, :, 3]
    rows = np.where(a.max(axis=1) > 0)[0]
    assert len(rows), "title must be drawn once its words are due"
    assert rows.max() < FR.H * 0.42, "must stay out of the caption band"
    assert rows.min() > 120, "must clear the platform's top chrome"


def test_title_never_runs_past_the_safe_width() -> None:
    t = FR.Typesetter({"colors": {"caption": "#F4EFE6", "accent": "#E8C36A",
                                  "keyword": "#E23B2F", "sceneBg": "#0B0E11"}})
    long = cells("this", "is", "a", "very", "long", "opening", "line", "indeed")
    img = t.hook_image(long, 9.0, max_w=900)
    cols = np.where(img[:, :, 3].max(axis=0) > 0)[0]
    assert cols.min() > 40 and cols.max() < FR.W - 40, (cols.min(), cols.max())


def test_emphasis_keeps_its_own_ink_in_the_title() -> None:
    t = FR.Typesetter({"colors": {"caption": "#F4EFE6", "accent": "#E8C36A",
                                  "keyword": "#E23B2F", "sceneBg": "#0B0E11"}})
    img = t.hook_image(cells("I", "will", "never"), 9.0)
    rgb = img[:, :, :3].reshape(-1, 3)
    red = ((rgb[:, 0] > 180) & (rgb[:, 1] < 90) & (rgb[:, 2] < 80)).sum()
    ivory = ((rgb[:, 0] > 220) & (rgb[:, 1] > 210) & (rgb[:, 2] > 190)).sum()
    assert red > 50 and ivory > 50, (red, ivory)


# ------------------------------------------------------------------------ bed
def test_bed_is_quiet_and_the_right_length() -> None:
    bed = SD.synth_bed(3.0)
    assert bed.shape == (3 * SD.RATE, 2)
    peak = float(np.abs(bed).max())
    assert 0.2 < peak <= 0.5


def test_bed_ducks_under_speech_and_opens_in_the_gaps() -> None:
    g = SD.speech_gain(6.0, [(2.0, 3.0)])
    assert float(g[int(2.5 * SD.RATE)]) < 0.45, "bed must sit under the voice"
    assert float(g[int(5.0 * SD.RATE)]) > 0.9, "and open back up between"


def test_ducking_is_smooth_not_stepped() -> None:
    g = SD.speech_gain(4.0, [(1.0, 2.0)])
    step = float(np.abs(np.diff(g)).max())
    assert step < 0.05, "a stepped gain is an audible click in the bed"


def test_finished_bed_sits_at_the_measured_level() -> None:
    track = SD.build_track(8.0, [(1.0, 2.0), (3.0, 4.0)], [])
    rms = float(np.sqrt((track.astype(np.float64) ** 2).mean()))
    assert 0.006 < rms < 0.020, rms


def test_bed_fades_in_and_out() -> None:
    track = SD.build_track(4.0, [], [])
    head = np.abs(track[:200]).max()
    middle = np.abs(track[SD.RATE * 2: SD.RATE * 2 + 200]).max()
    tail = np.abs(track[-100:]).max()
    assert head < middle * 0.2, "fades in"
    assert tail < middle * 0.2, "and out"


def test_hits_land_where_the_punches_are() -> None:
    track = SD.build_track(4.0, [], [1.0])
    quiet = float(np.abs(track[int(1.6 * SD.RATE): int(1.6 * SD.RATE) + 400]).max())
    hit = float(np.abs(track[int(1.0 * SD.RATE): int(1.0 * SD.RATE) + 400]).max())
    assert hit > quiet * 1.5


def test_word_intervals_are_ordered_and_drop_zero_length() -> None:
    got = SD.word_intervals([{"at": 2.0, "end": 2.4}, {"at": 1.0, "end": 1.0},
                             {"at": 0.5, "end": 0.9}])
    assert got == [(0.5, 0.9), (2.0, 2.4)]
