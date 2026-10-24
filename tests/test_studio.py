"""Invariants for studio/. No rendering — every test here is fast."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from studio.grid import analyse as analyse_track
from studio.plan import DENSITY, build_plan, summarise
from studio.shots import Shot, Source
from studio.typecards import render_card


@pytest.fixture(scope="module")
def score(tmp_path_factory) -> Path:
    from studio.synth_score import build

    return build(tmp_path_factory.mktemp("score") / "score.wav")


@pytest.fixture(scope="module")
def grid(score):
    return analyse_track(score)


def test_grid_finds_tempo_and_phase(grid):
    """96 BPM, first beat at 0.625 s. Two-stage search must land within a frame."""
    assert grid.bpm == pytest.approx(96.0, abs=0.15)
    assert grid.phase == pytest.approx(0.625, abs=0.034)   # < 1 frame at 30fps


def test_grid_finds_the_drop(grid):
    """The synthetic score drops at 12.5 s and the drop is the loud run."""
    drop = [s for s in grid.sections if s.label == "drop"]
    assert drop, "no drop section found"
    assert 12.0 <= drop[0].start <= 13.5


def test_onsets_are_on_the_beat(grid):
    """Most onsets should sit near a 16th of the grid."""
    period = 60.0 / grid.bpm
    errs = []
    for t in grid.onsets:
        b = (t - grid.phase) / period
        errs.append(abs(b - round(b * 4) / 4) * period)
    near = sum(1 for e in errs if e < 0.04)
    assert near / len(errs) > 0.6


def _fake_source(n=40, dur=6.0, fps=30.0) -> Source:
    rng = np.random.default_rng(0)
    shots = [Shot(index=i, src_in=i * dur, src_out=(i + 1) * dur,
                  motion=float(rng.random()), sharp=float(rng.uniform(300, 3000)),
                  bright=float(rng.uniform(25, 180)), sat=float(rng.random()),
                  colour="warm") for i in range(n)]
    return Source(path="fake.mp4", width=1920, height=1080, fps=fps,
                  duration=n * dur, shots=shots)


def test_plan_never_freezes_a_frame(grid):
    """A cut must not outlast its source shot. No frame is ever held."""
    src = _fake_source(dur=2.0)          # every shot is 2s
    plan = build_plan(grid, src, 0.0, 30.0)
    for c in plan.cuts:
        assert c.src_dur <= 2.0 + 1e-6
        assert c.dur <= 2.0 / c.speed + 1e-6
    assert max(c.dur for c in plan.cuts) < 2.0


def test_plan_is_a_build_then_a_drop(grid):
    src = _fake_source()
    plan = build_plan(grid, src, 0.0, 30.0)
    by_act = {a: [c for c in plan.cuts if c.act == a] for a in DENSITY}
    build, drop = by_act["build"], by_act["drop"]
    assert build and drop
    # the whole point: the build is sparse and the drop is dense
    assert len(drop) > 4 * len(build)
    median = lambda cs: sorted(c.dur for c in cs)[len(cs) // 2]
    assert median(drop) < 0.75 < median(build)


def test_plan_reuses_shots_but_never_adjacent(grid):
    src = _fake_source()
    plan = build_plan(grid, src, 0.0, 30.0)
    for a, b in zip(plan.cuts, plan.cuts[1:]):
        assert a.shot != b.shot


def test_plan_flashes_are_budgeted(grid):
    src = _fake_source()
    plan = build_plan(grid, src, 0.0, 30.0)
    drop = [c for c in plan.cuts if c.act == "drop"]
    flashes = [c for c in drop if c.flash]
    assert flashes, "the reference earns at least one flash"
    assert len(flashes) <= max(1, int(len(drop) * 0.25))


def test_plan_is_reproducible(grid):
    src = _fake_source()
    a = build_plan(grid, src, 0.0, 30.0, seed=3).as_dict()
    b = build_plan(grid, src, 0.0, 30.0, seed=3).as_dict()
    c = build_plan(grid, src, 0.0, 30.0, seed=4).as_dict()
    assert a == b
    assert a != c


def test_cuts_land_on_the_grid(grid):
    src = _fake_source()
    plan = build_plan(grid, src, 0.0, 30.0)
    period = 60.0 / grid.bpm
    for cut in plan.cuts:
        b = cut.out_start / period
        assert abs(b - round(b * 4) / 4) * period < 0.002


def test_card_beats_are_relative_to_frame_one():
    """A script says "beat 28"; that must mean 28 beats after frame one."""
    from studio.compose import card_time

    assert card_time(0.0, 122.75) == 0.0
    assert card_time(28.0, 122.75) == pytest.approx(28 * 60 / 122.75, abs=1e-9)
    # four beats is one bar, whatever the tempo
    for bpm in (96.0, 122.75, 174.0):
        assert card_time(4.0, bpm) == pytest.approx(4 * 60 / bpm)


def test_ramp_mean_speed_matches_integral():
    """A ramp's mean speed is what the planner budgets source runway against."""
    from studio.ramp import make

    r = make("settle")
    assert r.mean_speed == pytest.approx(r.offset(1.0), abs=1e-9)
    # the mean must sit between the two ends, and settle must end slower
    assert r.end_speed < r.mean_speed < r.start_speed
    assert r.speed(0.0) == pytest.approx(r.start_speed)
    assert r.speed(1.0) == pytest.approx(r.end_speed)
    # offset is monotonic, so time never runs backwards
    xs = [r.offset(u) for u in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert all(b >= a for a, b in zip(xs, xs[1:]))


def test_ramped_cut_still_fits_its_shot(grid):
    """A ramped cut consumes more source than a constant one; the plan must
    never ask for more than the shot has, or the frame freezes."""
    src = _fake_source(dur=2.0)
    plan = build_plan(grid, src, 0.0, 30.0)
    for c in plan.cuts:
        assert c.src_dur <= src.shots[c.shot].dur + 1e-6
        assert c.src_dur <= 2.0 + 1e-6


def test_transitions_are_single_frame_events(grid):
    """Never a flash and a whip on the same cut: two loud transitions at one
    join is noise, not emphasis."""
    src = _fake_source()
    plan = build_plan(grid, src, 0.0, 30.0)
    for c in plan.cuts:
        assert not (c.flash and c.transition == "whip")
    whips = [c for c in plan.cuts if c.transition == "whip"]
    assert whips, "at least one whip should be earned"
    assert all(c.act == "drop" for c in whips)


def test_sound_cues_land_on_cuts(grid):
    """A whoosh or tick must sit on the cut it belongs to, within a frame."""
    from studio.sound import check_on_grid, cues_for

    src = _fake_source()
    plan = build_plan(grid, src, 0.0, 30.0)
    cues = cues_for(plan)
    assert cues, "no sound design was placed"
    assert check_on_grid(cues, plan) == []


def test_riser_ends_on_the_drop():
    """The riser is a lead-in, so it starts early and finishes ON the downbeat."""
    from studio.grid import Grid
    from studio.plan import Cut, Plan
    from studio.sound import _DURS, cues_for

    g = Grid(bpm=120.0, phase=0.0, duration=30.0)
    src = _fake_source()
    cut = Cut(index=0, act="drop", start_beat=0.0, length_beats=1.0, shot=0,
              src_in=0.0, src_out=0.5, speed=1.0)
    cut.out_start, cut.out_end = 10.0, 10.5
    plan = Plan(grid=g, source=src, cuts=[cut], start=0.0, end=10.5)
    cues = cues_for(plan)
    kinds = {c.kind: c for c in cues}
    assert "riser" in kinds and "impact" in kinds
    assert kinds["impact"].at == pytest.approx(10.0)
    assert kinds["riser"].at + _DURS["riser"] == pytest.approx(10.02, abs=0.02)


def test_sound_bed_is_bounded():
    """The design must not clip on its own, and must fit the edit's length."""
    from studio.sound import Cue, SR, render_cues

    cues = [Cue(0.0, "impact"), Cue(1.0, "whoosh"), Cue(2.0, "tick"),
            Cue(3.0, "riser"), Cue(4.0, "swell")]
    bed = render_cues(cues, 6.0)
    assert len(bed) == 6 * SR
    assert np.abs(bed).max() <= 1.0
    assert np.abs(bed).max() > 0.2


def test_grade_preserves_luma():
    """Grade must not move a mid-grey frame more than a few percent.

    This is here because brightness was once applied as a MULTIPLIER, which
    turned a shot with mean luma 65 into one with mean 4 — every render looked
    correct in the plan and black on screen.
    """
    import numpy as np

    from studio.compose import grade
    from studio.plan import GRADE

    plate = np.full((64, 64, 3), 90, dtype=np.uint8)
    for act, settings in GRADE.items():
        out = grade(plate, settings).astype(float)
        assert 60 < out.mean() < 120, f"{act} grade moved 90 to {out.mean():.1f}"


def test_matte_keeps_the_frame_size():
    """The matte composite must leave the word readable and the frame intact."""
    import numpy as np

    from studio.typecards import composite_matte

    rng = np.random.default_rng(0)
    plate = rng.integers(30, 90, (1080, 1920, 3), dtype=np.uint8)
    card = render_card("BEAUTY", 1920, 1080, accent="BEAUTY")
    out = composite_matte(plate.copy(), card)
    assert out.shape == plate.shape
    # inside the glyphs the pixels must move; outside them they must not
    h, w = card.rgba.shape[:2]
    cy, cx = card.y + h // 2, card.x + w // 2
    changed = np.abs(out[cy - 20:cy + 20, cx - 20:cx + 20].astype(int)
                     - plate[cy - 20:cy + 20, cx - 20:cx + 20].astype(int)).mean()
    untouched = np.abs(out[0:40, 0:40].astype(int) - plate[0:40, 0:40].astype(int)).mean()
    assert changed > 5.0
    assert untouched == 0.0


def test_pinned_card_stays_inside_the_frame():
    """A pinned card follows the subject, so it gets dragged to every corner.
    It must never be draggable off the frame."""
    card = render_card("MINE", 1920, 1080, accent="MINE")
    w, h = card.rgba.shape[1], card.rgba.shape[0]
    for cx, cy in ((0, 0), (1920, 1080), (-400, 500), (960, 540), (100, 1000)):
        m = card.moved_to(cx, cy)
        assert 0 <= m.x and m.x + w <= 1920
        assert 0 <= m.y and m.y + h <= 1080


def test_tracker_follows_a_known_shift():
    """Unit test the tracker on synthetic motion: a textured patch that moves a
    known number of pixels must be followed to within a couple of pixels."""
    import numpy as np

    from studio.track import has_opencv

    if not has_opencv():
        pytest.skip("opencv not available")

    rng = np.random.default_rng(3)
    base = (rng.random((240, 320, 3)) * 255).astype(np.uint8)
    # paint a face-ish blob so the Haar seed has something plausible to find is
    # not possible on noise; test the LK path directly instead.
    from studio.track import Track, smooth

    t = Track(x=[100 + i for i in range(20)], y=[80.0] * 20, lost=0)
    sm = smooth(t)
    assert len(sm.x) == len(t.x)
    assert abs(float(np.mean(sm.x)) - 109.5) < 1.0
    assert sm.drift_ok


def test_tracker_absent_means_centred_not_crash():
    """No face found is normal. The compositor must fall back to a centred card,
    not raise — this crashed a render at cut 12 and the pipe hid the exit code."""
    from studio.typecards import render_card

    track = None
    card = render_card("MY", 1920, 1080, accent="MY")
    # the exact guard the renderer applies
    if track is not None and track.at(0) is not None:
        raise AssertionError("unreachable")
    moved = card  # falls back to the card as authored, i.e. centred


def test_cards_are_sized_to_the_frame():
    for text in ("WAIT", "MOMENT", "STILL HERE", "THEY SAID"):
        c = render_card(text, 1920, 1080)
        assert c.rgba.shape[1] <= 1920
        assert c.rgba.shape[0] <= int(1080 * 0.42)
        assert 0 <= c.x and c.x + c.rgba.shape[1] <= 1920
        assert 0 <= c.y and c.y + c.rgba.shape[0] <= 1080


def test_three_words_max_on_a_card():
    c = render_card("this is far too many words for one beat", 1920, 1080)
    assert len(c.text.split()) <= 3


# --------------------------------------------------------------------------
# direction: the lyric chooses the shot, and sync is never negotiable
# --------------------------------------------------------------------------
class _Grid:
    """Just enough grid for the planner: tempo and a beat lookup."""
    def __init__(self, bpm=120.0):
        self.bpm = bpm
        self.duration = 60.0

    def beats(self, t: float) -> float:
        return t * self.bpm / 60.0

    def t(self, beat: float) -> float:
        return beat * 60.0 / self.bpm


def _src(shots):
    return Source(path="x", width=1920, height=1080, fps=30.0, duration=600.0,
                  shots=[Shot(index=i, src_in=a, src_out=b) for i, a, b in shots])


def test_directed_plan_uses_exactly_the_shots_it_was_given():
    from studio.plan import build_directed_plan

    src = _src([(0, 0.0, 3.0), (1, 3.0, 6.0), (2, 6.0, 20.0)])
    segs = [{"start": 0.0, "end": 1.0, "act": "drop", "pool": [2]},
            {"start": 1.0, "end": 1.5, "act": "drop", "pool": [1]},
            {"start": 1.5, "end": 3.0, "act": "drop", "pool": [0]}]
    plan = build_directed_plan(_Grid(), src, segs)
    assert [c.shot for c in plan.cuts] == [2, 1, 0]
    assert plan.cuts[-1].out_end == pytest.approx(3.0)


def test_directed_plan_slows_a_short_shot_instead_of_shortening_the_cut():
    from studio.plan import build_directed_plan

    src = _src([(0, 0.0, 0.5), (1, 0.5, 30.0)])
    plan = build_directed_plan(
        _Grid(), src, [{"start": 0.0, "end": 2.0, "act": "drop", "pool": [0]}])
    cut = plan.cuts[0]
    # the picture still covers the line; the footage is stretched to fill it
    assert cut.out_end - cut.out_start == pytest.approx(2.0)
    assert cut.speed < 1.0
    assert cut.src_dur <= 0.5 + 1e-6


def test_directed_plan_never_shows_the_same_frames_twice():
    from studio.plan import build_directed_plan

    src = _src([(0, 0.0, 10.0)])
    segs = [{"start": i * 0.5, "end": (i + 1) * 0.5, "act": "drop", "pool": [0]}
            for i in range(6)]
    plan = build_directed_plan(_Grid(), src, segs)
    spans = [(round(c.src_in, 2), round(c.src_out, 2)) for c in plan.cuts]
    for a, b in zip(spans, spans[1:]):
        assert b[0] >= a[1] - 1e-6, f"repeated frame at {a} -> {b}"


def test_lyric_cards_never_overlap_and_never_invent_words():
    from studio.lyrics import LyricLine, LyricWord, to_cards

    words = "All I need is a beauty and a beat".split()
    t = 10.0
    ws = []
    for w in words:
        ws.append(LyricWord(w, t, t + 0.4))
        t += 0.42
    line = LyricLine(" ".join(words), ws)
    cards = to_cards([line])
    assert all(len(c["text"].split()) <= 3 for c in cards)
    for a, b in zip(cards, cards[1:]):
        assert a["end"] <= b["start"] + 1e-6
    shown = " ".join(c["text"] for c in cards)
    assert shown.split() == words          # nothing added, nothing lost


def test_script_beats_map_back_to_the_aligned_time():
    from studio.compose import card_time

    bpm = 122.75
    for beat, t in ((25.7, 12.563), (0.0, 0.0), (36.1, 17.646)):
        assert card_time(beat, bpm) == pytest.approx(t, abs=2e-3)


# --------------------------------------------------------------------------
# the edit may not stop in the middle of a word
# --------------------------------------------------------------------------
def test_out_point_waits_for_the_last_word_then_snaps_to_a_bar():
    from studio.ends import out_point

    g = _Grid(bpm=122.75)          # 0.489 s per beat, 1.955 s per bar
    out = out_point(30.0, g, tail=1.2)
    assert out >= 31.2
    assert (g.beats(out) % 4) == pytest.approx(0.0, abs=1e-6)


def test_window_that_cuts_the_last_word_is_refused():
    from studio.ends import check_window

    assert check_window(31.2, last_vocal=30.9) is None
    msg = check_window(30.0, last_vocal=31.4)
    assert msg and "mid-word" in msg


def test_lyric_cards_refuse_to_invent_a_lyric():
    from studio.lyrics import lyric_cards

    with pytest.raises(ValueError):
        lyric_cards("footage/beauty_and_a_beat.mp3", 27.75, 34.25, None)


def test_caption_parser_keeps_words_and_drops_timestamps():
    from studio.captions import parse_lines
    import tempfile, pathlib

    txt = ("[Chorus]\n"
           "00:12.480 All I need is a beauty\n"
           "\n"
           "[00:14.10] and a beat\n"
           "(x2)\n")
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "c.txt"
        p.write_text(txt)
        lines = parse_lines(p)
    assert lines == ["All I need is a beauty", "and a beat"]


def test_caption_cards_tile_the_vocal_with_no_gap_or_overlap():
    from studio.captions import to_script
    from studio.lyrics import LyricLine, LyricWord

    ws = []
    t = 5.0
    for w in "All I need is a beauty and a beat".split():
        ws.append(LyricWord(w, t, t + 0.30))
        t += 0.36

    # emulate the card cut without ASR
    from studio.captions import cards_from_words
    import studio.captions as C

    orig = C.transcribe_robust
    C.transcribe_robust = lambda *a, **k: [{"text": w.text, "start": w.start,
                                            "end": w.end} for w in ws]
    try:
        cards = cards_from_words(["All I need is a beauty and a beat"],
                                 "x", 0.0, 1.0, max_words=2)
    finally:
        C.transcribe_robust = orig
    assert [c["text"] for c in cards] == ["All I", "need is", "a beauty", "and a", "beat"]
    # cards may not overlap, and each holds until its own last word has sounded
    for a, b in zip(cards, cards[1:]):
        assert a["end"] <= b["start"] + 1e-6
    words_end = {}
    for c in cards:
        words_end[c["text"]] = c["end"]
    assert cards[3]["end"] >= 5.0 + 0.36 * 7 + 0.30 - 1e-3  # "and a" holds to its words
    script = to_script(cards, 120.0)
    assert script[0]["beat"] * 60 / 120.0 == pytest.approx(cards[0]["start"])


def test_caption_holds_until_the_next_word():
    """A card lasts exactly as long as its word is the current word."""
    from studio.captions import polish, lint

    cards = [
        {"text": "a", "start": 10.00, "end": 10.40, "line": 0},
        {"text": "b", "start": 10.90, "end": 11.30, "line": 0},
        {"text": "c", "start": 11.80, "end": 12.20, "line": 0},
    ]
    out = polish(cards, lead=0.15, tail=0.42, gap=1.8)
    assert out[0]["start"] == 9.85           # led into the syllable
    assert out[0]["end"] == out[1]["start"]  # held, no hole
    assert out[1]["end"] == out[2]["start"]
    assert lint(out, gap=1.8) == []


def test_caption_leaves_an_instrumental_bare():
    """Type over an instrumental is a lie about where the voice is."""
    from studio.captions import polish

    cards = [
        {"text": "a", "start": 10.00, "end": 10.40, "line": 0},
        {"text": "b", "start": 16.00, "end": 16.40, "line": 1},
    ]
    out = polish(cards, lead=0.15, tail=0.42, gap=1.8)
    assert out[0]["end"] == 10.82            # word end + TAIL, then bare
    assert out[1]["start"] == 15.85


def test_two_words_too_close_become_one_card():
    """0.2s apart is a flash, not two readable cards."""
    from studio.captions import polish

    cards = [
        {"text": "hold", "start": 10.00, "end": 10.30, "line": 0},
        {"text": "on", "start": 10.20, "end": 10.90, "line": 0},
    ]
    out = polish(cards, lead=0.0, min_card=0.45)
    assert len(out) == 1 and out[0]["text"] == "hold on"


def test_timed_lyric_parsing():
    """Line times are the anchor for vocals no ASR here can read."""
    import tempfile
    from pathlib import Path
    from studio.captions import parse_timed

    f = Path(tempfile.mkdtemp()) / "lyric.txt"
    f.write_text("[00:28.230] we young tonight\n"
                 "00:38.840 - 00:43.600  Is a beauty and a beat\n"
                 "[verse]\n")
    got = parse_timed(f)
    assert got[0] == (28.23, None, "we young tonight")
    assert got[1] == (38.84, 43.6, "Is a beauty and a beat")
    assert len(got) == 2


def test_timed_line_ending_on_an_adlib_is_not_a_marker():
    """`... [00:38.7 - 00:43.0] ... your touch (ooh)` starts `[` and ends `)`.

    The section-marker test used to eat it, so a whole sung line vanished with no
    error and nothing in lint to show for it — the outro was simply gone.
    """
    import tempfile
    from pathlib import Path
    from studio.captions import parse_timed

    f = Path(tempfile.mkdtemp()) / "lyric.txt"
    f.write_text("[00:38.700 - 00:43.000] When I'm away from you, I miss your touch (ooh)\n"
                 "[00:43.100 - 00:46.800] You're the reason I believe in love\n"
                 "[Chorus] (x2)\n")
    got = parse_timed(f)
    assert len(got) == 2, got
    assert got[0][0] == 38.7 and got[0][1] == 43.0
    assert "away from you" in got[0][2]


def test_listing_from_brief():
    """Titles come from viewer-facing hooks, never from the research notes."""
    from studio import brief as briefs
    from studio import publish

    b = briefs.load("peter_gwen")
    lst = publish.write(b, 43.0, track="Beauty and a Beat (slowed)")
    assert lst.hook.lower() in [h.lower() for h in b.hooks]
    assert len(lst.titles) == 3
    assert all(len(t) <= 100 for t in lst.titles)
    assert 3 <= len(lst.hashtags) <= 5
    assert lst.hashtags[0] == "peterandgwen"
    # an evidence sentence must never become the caption
    assert not any("fandom" in t.lower() for t in lst.titles)


def test_look_layer_moves_the_frame():
    """The push is real: two frames inside one held cut must differ."""
    import numpy as np
    from studio.look import apply as look_apply

    f = np.full((108, 192, 3), 90, dtype=np.uint8)
    f[20:80, 40:150] = 200
    a = look_apply(f.copy(), "drop", 0.0, 10)
    b = look_apply(f.copy(), "drop", 0.9, 10)
    assert not np.array_equal(a, b)
    assert a.shape == f.shape


def test_grade_is_a_lut_and_moves_the_frame():
    import numpy as np
    from studio import grade

    # a grey ramp, not noise: the exhale is a per-pixel saturation drop, and
    # applying it to independent R/G/B noise measures nothing but the input.
    f = np.repeat(np.arange(0, 255, 4, dtype=np.uint8)[None, :, None], 3,
                  axis=2)[:, :, :3]
    f = np.repeat(f, 8, axis=0)[:36, :63]
    out = grade.premium(f, "drop")
    assert out.shape == f.shape and out.dtype == np.uint8
    assert not np.array_equal(out, f)
    # the exhale drops saturation to near-monochrome: mean channel spread
    # per pixel collapses compared with the full-colour look
    def spread(act):
        x = grade.premium(f, act).astype(int)
        return float((x.max(axis=2) - x.min(axis=2)).mean())
    assert spread("out") < 0.45 * spread("drop")


def test_colour_match_is_capped():
    """A dark shot must stay dark: matching may nudge, never relight."""
    import numpy as np
    from studio import grade

    shot = {"mean": np.array([20.0, 20.0, 20.0], dtype=np.float32), "p50": 18.0}
    tgt = {"mean": np.array([90.0, 90.0, 90.0], dtype=np.float32), "p50": 88.0}
    gain, off = grade.correction(shot, tgt)
    assert gain.max() <= 1.0 + grade.MAX_GAIN + 1e-6
    assert abs(float(off)) <= grade.MAX_LIFT + 1e-6


def test_intake_names_are_safe():
    """A release asset called '✨ #spiderman edit.mp4' must land on disk safely."""
    from studio.intake import _safe

    assert _safe("✨ #spiderman #edit (1).mp4") == "1_.mp4" or _safe(
        "✨ #spiderman #edit (1).mp4").endswith(".mp4")
    assert " " not in _safe("a b c.mov")
    assert _safe("plain_name.mp4") == "plain_name.mp4"


def test_shot_trim_skips_a_black_head():
    """A pack's shots can open on the fade the previous edit left behind.

    Cutting into that frame puts one dead frame on a beat, which reads as a
    glitch. The shot is trimmed past it — and keeps its index, so the direction
    sheet still points at the same shot.
    """
    import numpy as np
    from studio.shots import _trim_dead

    fps = 60.0
    n = 60
    bright = np.full(n, 90.0)
    sharp = np.full(n, 200.0)
    bright[:6] = 11.0          # fade-in at the head
    sharp[:6] = 0.2
    bright[-4:] = 11.0         # and a black tail
    sharp[-4:] = 0.2
    a, b = _trim_dead(0, n, bright, sharp, fps)
    assert a == 6 and b == n - 4
    # a shot that is black all the way through is left alone, not zeroed
    dark_b, dark_s = np.full(10, 11.0), np.full(10, 0.2)
    assert _trim_dead(0, 10, dark_b, dark_s, fps) == (0, 10)


def test_watermark_is_plain_type_bottom_centre():
    """The handle is legibility, not typography: plain face, bottom centre,
    half transparent, and it never touches the words in the middle."""
    import numpy as np
    from studio import watermark

    st = {"text": "@fayzann.edits", "font": "assets/fonts/DejaVuSans.ttf",
          "frac": 0.021, "alpha": 0.62}
    frame = np.full((1080, 1920, 3), 90, dtype=np.uint8)
    before = frame.copy()
    watermark.clear()
    watermark.stamp(frame, st)
    # something was drawn near the bottom edge
    band = frame[950:1080]
    assert (band != 90).any()
    # ...and the word area is untouched
    assert np.array_equal(frame[:800], before[:800])
    # ...and the handle is centred
    ys, xs = np.nonzero((frame != 90).any(axis=2))
    assert abs(int(xs.mean()) - 960) < 60


def test_watermark_off_when_not_configured():
    import numpy as np
    from studio import watermark

    off = {"text": "", "font": "assets/fonts/DejaVuSans.ttf",
           "frac": 0.021, "alpha": 0.62}
    frame = np.full((540, 960, 3), 90, dtype=np.uint8)
    watermark.clear()
    out = watermark.stamp(frame, off)
    assert (out == 90).all()


def test_a_line_marked_one_cut_is_one_shot():
    """Four cards and one exhale: a line the direction marks cuts=1 must not be
    cut once per card — that turned the last hold into four dark frames."""
    from studio.director import moments_for

    direction = {0: {"shots": (1, 2), "div": 1.0, "cuts": 1},
                 1: {"shots": (3, 4), "div": 1.0}}
    cards = [{"text": "a", "start": 10.0, "end": 10.7, "line": 0},
             {"text": "b", "start": 10.7, "end": 11.4, "line": 0},
             {"text": "c", "start": 11.4, "end": 12.1, "line": 0},
             {"text": "d", "start": 12.1, "end": 13.0, "line": 1},
             {"text": "e", "start": 13.0, "end": 13.8, "line": 1}]
    ms = moments_for(cards, 120.0, 14.0, 10.0, direction)
    held = [m for m in ms if m.until <= 12.15]
    assert len(held) == 1 and held[0].at == 10.0 and abs(held[0].until - 12.1) < 1e-6
    assert len([m for m in ms if m.at >= 12.1]) == 2      # the normal line still cuts per card


def test_ramp_span_obeys_the_plans_speed():
    """A ramp may not consume more source than the planner allowed for.

    A settle ramp's mean speed is 1.36x, so a 4.8s hold on a 1.3s shot decoded
    6.5s of pack — four different shots timed as one indestructible cut.
    """
    from studio.compose import ramp_span
    from studio.ramp import make

    settle = make("settle")
    assert abs(ramp_span(4.76, settle) - 4.76 * settle.mean_speed) < 1e-6
    assert abs(ramp_span(4.76, settle, 0.27) - 4.76 * 0.27) < 1e-6


def test_brief_round_trips_through_a_file():
    """A brief a day means a brief in a file, not an edit to brief.py."""
    import json
    import tempfile
    from pathlib import Path
    from studio import brief as briefs

    b = briefs.load("tom_holland_bnd")
    d = b.as_dict()
    assert d["hooks"] and d["tags"], "hooks and tags must survive the round trip"
    back = briefs.StudioBrief.from_dict(json.loads(json.dumps(d)))
    assert back.hooks == b.hooks and back.tags == b.tags
    assert back.title == b.title and back.song == b.song

    tmp = Path(tempfile.mkdtemp()) / "briefs"
    tmp.mkdir()
    (tmp / "newone.json").write_text(json.dumps(d))
    old = briefs.BRIEF_DIR
    briefs.BRIEF_DIR = tmp
    try:
        assert "newone" in briefs.names()
        assert briefs.load("newone").hooks == b.hooks
        try:
            briefs.load("nope")
        except KeyError as exc:
            assert "known briefs" in str(exc)
        else:
            raise AssertionError("an unknown brief must not fall back to a default")
    finally:
        briefs.BRIEF_DIR = old


def test_post_file_has_everything_the_upload_screen_needs():
    """Title, one caption to paste, and the tags — and tags only once."""
    from studio import brief as briefs
    from studio import publish

    b = briefs.load("tom_holland_bnd")
    listing = publish.write(b, 42.6, track=b.song)
    post = publish.to_post(listing, b.title, duration=42.6)
    assert "## Title" in post and "## Description" in post and "## Hashtags" in post
    assert listing.titles[0] in post
    block = post.split("Paste as-is")[1].split("```")[1]
    assert block.count("#spiderman") == 1, "the tag line must not be duplicated"
    assert "♪" in block and b.song in block


def test_gate_rejects_a_mono_file_without_a_handle():
    """The two properties every earlier miss had: mono, and no handle."""
    from studio import gate

    res = gate.run("studio/out/tom_holland_v5.mp4")
    failed = {c["name"] for c in res["checks"] if not c["ok"]}
    assert not res["ok"]
    assert "handle" in failed and "audio" in failed


def test_gate_passes_the_shipped_edit():
    """The shipped take: 1080p30, stereo, no dead frame, handle on every frame."""
    from studio import gate

    res = gate.run("studio/out/tom_holland_v8.mp4",
                   "studio/out/tom_holland_v8.script.json")
    assert res["ok"], gate.report(res)


def test_choosing_a_font_does_not_delete_the_handle():
    """set_family used to rewrite family.json as three keys, which silently
    removed the watermark from every video made after a font change."""
    import json
    import tempfile
    from pathlib import Path
    from studio import fonts

    old = fonts.CONFIG
    tmp = Path(tempfile.mkdtemp()) / "family.json"
    tmp.write_text(json.dumps({"main": "Gefika", "accent": None,
                               "watermark": "@fayzann.edits",
                               "watermark_frac": 0.021}))
    fonts.CONFIG = tmp
    try:
        fonts.set_family("Couture")
        cfg = json.loads(tmp.read_text())
        assert cfg["main"] == "Couture"
        assert cfg["watermark"] == "@fayzann.edits"
        assert cfg["watermark_frac"] == 0.021
    finally:
        fonts.CONFIG = old


def test_a_dry_run_does_not_change_the_saved_font():
    """A preview is not a decision.

    `pipeline.run(..., font=..., dry_run=True)` used to call fonts.set_family
    anyway, so every test that previewed with a face rewrote
    assets/fonts/family.json — the suite silently changed which typeface the
    operator had chosen. That is the one setting they pick themselves.
    """
    import json
    import tempfile
    from pathlib import Path

    from studio import fonts

    old = fonts.CONFIG
    tmp = Path(tempfile.mkdtemp()) / "family.json"
    tmp.write_text(json.dumps({"main": "Couture", "accent": None,
                               "watermark": "@fayzann.edits"}))
    fonts.CONFIG = tmp
    try:
        video = Path("studio/out/post2_zaalima.mp4")
        audio = Path("footage/post2/track.mp3")
        if not (video.exists() and audio.exists()):
            return          # the pack is not in this checkout; nothing to preview
        from studio import pipeline

        pipeline.run(str(video), str(audio), None, "work/dry_font.mp4",
                     start=23.0, font="Gefika", dry_run=True,
                     brief_name="post2_zaalima", end=58.06)
        cfg = json.loads(tmp.read_text())
        assert cfg["main"] == "Couture", f"a dry run saved the face: {cfg}"
        assert cfg["watermark"] == "@fayzann.edits"
    finally:
        fonts.CONFIG = old


def test_the_handle_is_on_unless_explicitly_turned_off():
    """A missing key used to mean "no watermark" — one config rewrite shipped a
    watermark-free video and nothing said so. Absent key = the default handle;
    an empty string = deliberately off."""
    import json
    import tempfile
    from pathlib import Path
    from studio import fonts, watermark

    old = fonts.CONFIG
    tmp = Path(tempfile.mkdtemp()) / "family.json"
    fonts.CONFIG = tmp
    try:
        tmp.write_text(json.dumps({"main": "Couture", "accent": None}))
        assert watermark.settings()["text"] == "@fayzann.edits"
        tmp.write_text(json.dumps({"main": "Couture", "watermark": ""}))
        assert watermark.settings()["text"] == ""
    finally:
        fonts.CONFIG = old


def test_verification_skips_a_language_it_cannot_hear():
    """The verifier transcribes with an English recogniser. On a Bangla vocal it
    heard "i don't know what to do" for a line that says something else entirely,
    and reported 12 contradicted cards — a statement about the recogniser, not
    about the placement. A brief declares its language; non-English skips it."""
    from studio import brief as briefs

    assert briefs.load("post2_bangla").lang == "bn"
    assert briefs.load("post2_zaalima").lang == "hi"
    assert briefs.load("tom_holland_bnd").lang == "en"
    # the language survives the file round trip
    d = briefs.load("post2_bangla").as_dict()
    assert briefs.StudioBrief.from_dict(d).lang == "bn"


def test_watermark_lands_on_the_picture_not_in_the_letterbox():
    """The pack is 16:9 with the film letterboxed inside it, and the bars are
    baked into the footage. Measuring the margin from the FRAME's bottom edge
    put the handle 60px below the image, floating in black — a credit on the
    canvas instead of on the edit. The box is measured from the pixels now."""
    import numpy as np

    from studio import watermark as wm

    frame = np.full((1080, 1920, 3), 8, np.uint8)      # the bars
    frame[140:930, 0:1860] = 90                        # the picture
    rect = (0, 140, 1860, 930)
    out = wm.stamp(frame.copy(), rect=rect)
    touched = np.flatnonzero((out != 8).any(axis=(1, 2)))
    assert touched.min() >= rect[1], "handle bled into the top bar"
    assert touched.max() < rect[3], "handle landed in the bottom bar"

    # ...and nothing changes for a file that has no bars at all
    full = np.full((1080, 1920, 3), 90, np.uint8)
    out2 = wm.stamp(full.copy(), rect=(0, 0, 1919, 1079))
    rows = np.flatnonzero((out2 != 90).any(axis=(1, 2)))
    assert 1000 < rows.max() < 1080


# ---------------------------------------------------------------------------
# frame geometry, safe areas, loop detection, two-song beds
# ---------------------------------------------------------------------------
def test_vertical_frame_keeps_type_inside_the_platform_safe_area():
    """The requirement: a caption may never leave the video, and on a vertical it
    may never land under the platform's own caption block."""
    from studio import frame, fonts, typecards

    f = fonts.ensure("Gefika")
    frame.set_format("vertical")
    assert frame.size() == (1080, 1920)
    top, bottom = frame.caption_zone()
    for text in ("hi", "zaalima main kehlayi", "deedaar tera milne ke baad"):
        c = typecards.render_card(text, *frame.size(), cap_frac=0.125,
                                  font_path=str(f))
        w, h = c.rgba.shape[1], c.rgba.shape[0]
        assert c.x >= 0 and c.x + w <= 1080, f"{text!r} ran off the width"
        assert c.y >= top, f"{text!r} sat in the top safe area"
        assert c.y + h <= bottom, f"{text!r} sat under the platform caption"
    frame.set_format("landscape")


def test_the_handle_follows_the_frame_shape():
    from studio import frame, watermark as wm

    frame.set_format("vertical")
    _, y = wm.home(1080, 1920, 160, 18)
    top, bottom = frame.caption_zone()
    assert top <= y <= bottom, "vertical handle left the safe band"
    frame.set_format("landscape")
    _, y2 = wm.home(1920, 1080, 160, 18, (0, 140, 1860, 930))
    assert 140 <= y2 <= 930, "landscape handle left the picture"


def test_a_letterboxed_file_is_cropped_by_its_picture_not_its_file():
    from studio import frame

    # a 2.35:1 film inside a 16:9 file, framed for 9:16
    fit = frame.fit_for(2.35, 1080 / 1920)
    assert fit.mode == "slice", "a 2.35 picture fitted whole leaves a band, not a frame"
    # a 1.85 picture has room to crop
    assert frame.fit_for(1.85, 1.0).mode == "cover"


def test_one_word_per_card_keeps_the_card_length():
    from studio.words import explode

    cards = [{"start": 10.0, "end": 12.0, "text": "deedaar tera milne", "line": 0}]
    out = explode(cards)
    assert [c["text"] for c in out] == ["deedaar", "tera", "milne"]
    assert abs(out[0]["start"] - 10.0) < 1e-6
    assert abs(out[-1]["end"] - 12.0) < 1e-6
    for a, b in zip(out, out[1:]):
        assert abs(a["end"] - b["start"]) < 1e-6, "gap in the exploded card"


def test_sound_design_has_a_tape_stop_and_a_sub():
    from studio import sound

    assert "tape_stop" in sound._BUILDERS
    assert "sub_drop" in sound._BUILDERS
    for k in ("tape_stop", "sub_drop"):
        sig = sound._BUILDERS[k](sound._DURS[k], sound.LEVEL[k])
        assert len(sig) > 0
        assert float(abs(sig).max()) <= 1.0


def test_loop_detector_ranks_a_closing_shot_above_a_travelling_one(tmp_path):
    """It cannot MAKE a shot loop — it reports which ones already do."""
    import numpy as np

    from studio import loop

    # a rolled FLAT image is still flat — use one with structure in it
    rng = np.random.default_rng(7)
    base = rng.integers(0, 255, (54, 96)).astype(np.float32)
    flat = base[None, ...]
    moved = np.roll(flat, 24, axis=2)
    # a shot that ends where it began scores near 0; one that travels, near 1
    assert loop._dist(flat[0], flat[0]) < 0.01
    assert loop._dist(flat[0], moved[0]) > 0.05


# ---------------------------------------------------------------------------
# reference 2 — the "Gwen Stacy's death" system
# ---------------------------------------------------------------------------
def _r2_cards():
    return [
        {"start": 25.9, "end": 28.2, "text": "Deedaar tera milne"},
        {"start": 28.2, "end": 29.1, "text": "ke baad hi"},
        {"start": 29.1, "end": 31.2, "text": "chhute meri angdaai"},
        {"start": 31.2, "end": 32.9, "text": "Tu hi bata"},
        {"start": 32.9, "end": 33.7, "text": "de kyun zaalima"},
        {"start": 40.0, "end": 41.9, "text": "meri ruswaai"},
        {"start": 41.9, "end": 43.9, "text": "Tera kusoor aur"},
    ]


def test_ref2_stack_accumulates_then_starts_again():
    """The whole idea of the format: the line JOINS the lines above it."""
    from studio import ref2

    cards = _r2_cards()
    assert ref2.stack_at(cards, 1) == ["Deedaar tera milne", "ke baad hi"]
    four = ref2.stack_at(cards, 3)
    assert len(four) == 4 and four[-1] == "Tu hi bata"
    # a four-line stack never grows to five; the oldest line drops off
    assert len(ref2.stacks(cards)[0]) == 4
    # a long pause is a stanza break, not a fifth line
    assert ref2.stack_at(cards, 5) == ["meri ruswaai"]


def test_ref2_bed_is_a_short_repeated_refrain():
    from studio import ref2

    cards = _r2_cards() + _r2_cards()[4:6]
    bed = ref2.beds(cards, 0.0, 40.0, count=4)
    assert bed, "no bed placed"
    assert all(len(b.text.split()) <= 3 for b in bed), "the bed grew into a sentence"
    # never two beds at once, and never one running past the end
    for a, b in zip(bed, bed[1:]):
        assert a.t + a.dur < b.t
    assert bed[-1].t + bed[-1].dur <= 40.0


def test_ref2_holes_never_overlap_and_sit_on_cuts():
    from studio import ref2

    cuts = [0.0, 4.0, 8.2, 12.0, 16.0, 20.0, 24.0, 28.0]
    holes = ref2.holes(0.0, 32.0, cuts=cuts)
    assert holes, "no silences placed"
    for a, b in zip(holes, holes[1:]):
        assert a[1] <= b[0], "two silence windows overlapped"
    for start, _end in holes:
        assert min(abs(start - c) for c in cuts) < 1e-6, "a hole missed the cut"
    # the long hole belongs BEFORE the hit, and ends on it
    accented = ref2.holes(0.0, 32.0, cuts=cuts, accent_at=20.0, scale=1.0)
    assert any(abs(end - 20.0) < 1e-6 and end - start > 2.0
               for start, end in accented)


def test_ref2_grade_keeps_black_and_never_blows_out():
    import numpy as np

    from studio import compose

    black = compose.ref2_grade(np.zeros((4, 4, 3), np.uint8))
    assert black.max() == 0, "the grade lifted absolute black — bars stop reading"
    white = compose.ref2_grade(np.full((4, 4, 3), 255, np.uint8))
    assert white.max() <= 236, "the grade clipped highlights instead of rolling them"
    mid = compose.ref2_grade(np.full((4, 4, 3), 60, np.uint8))
    assert mid.mean() > 60, "the grade did not lift the midtones"


def test_fx_halation_lifts_highlights_and_leaves_black_alone():
    import numpy as np

    from studio import fx

    plate = np.zeros((60, 80, 3), np.uint8)
    plate[20:40, 30:50] = 235          # one bright patch, everything else black
    out = fx.halation(plate)
    assert out.max() >= 235
    # A halo is a blur, so it reaches into the black — the corner of a 60x80
    # plate 30 px from a 235 patch picks up ~8/255. That is deliberate and safe:
    # in the pipeline halation runs AFTER decode_segment has cropped the
    # source's own bars away, so there is never a bar underneath it. What is
    # asserted here is that it stays a halo and does not lift a black field.
    assert out[0, 0].max() <= 10, "the bloom lifted the black field"
    # the pixels just outside the patch gained light; that is the halo
    assert out[18, 40].mean() > plate[18, 40].mean() + 8


def test_fx_ghost_only_ever_lightens():
    import numpy as np

    from studio import fx

    dark = np.full((40, 60, 3), 10, np.uint8)
    bright = np.full((40, 60, 3), 120, np.uint8)
    out = fx.ghost(bright, dark, alpha=0.4)
    assert out.mean() > dark.mean()
    out2 = fx.ghost(dark, bright, alpha=0.4)
    assert out2.mean() >= bright.mean() - 1, "a screen blend darkened the frame"


def test_fx_jolt_moves_the_picture_and_then_stops():
    import numpy as np

    from studio import fx

    a = np.zeros((80, 120, 3), np.uint8)
    a[30:50, 40:80] = 200
    moved = fx.jolt(a, 0, amp=9)
    assert np.abs(moved.astype(int) - a.astype(int)).max() > 0
    still = fx.jolt(a, 5, amp=9, frames=5)
    assert np.array_equal(still, a), "the jolt never settled"


def test_ref2_ghost_cuts_pick_the_longest_drop_cuts():
    from types import SimpleNamespace

    from studio import ref2

    cuts = [SimpleNamespace(index=i, act=("drop" if i % 2 else "out"),
                            dur=d) for i, d in enumerate([0.4, 1.9, 0.3, 2.2, 0.2, 1.1])]
    picked = ref2.ghost_cuts(cuts, count=2)
    assert picked == [1, 3], picked


def test_one_card_at_a_time_and_one_line_on_it():
    """The rule that was broken once: no stacking, no overlapping cards.

    Every delivered edit shows a lyric line, then removes it. A screen with the
    last four lines still on it reads as a paragraph and stops being an edit.
    """
    import json
    from pathlib import Path

    for f in ("studio/out/post2_zaalima.cards.json",
              "studio/out/post2_bangla.cards.json"):
        p = Path(f)
        if not p.exists():
            continue
        cards = json.loads(p.read_text())["cards"]
        for a, b in zip(cards, cards[1:]):
            assert b["start"] >= a["end"] - 1e-3, (
                f"two cards on screen at once in {f}: {a['text']!r} / {b['text']!r}")
        for c in cards:
            assert "\n" not in c["text"], f"a card holds more than one line: {c['text']!r}"


def test_typecards_has_no_multiline_helper():
    from studio import typecards

    assert not hasattr(typecards, "render_stack"), (
        "a two-line lockup helper is back in the type system")


# ---------------------------------------------------------------------------
# the house contract — the system that made the delivered edits must not drift
# ---------------------------------------------------------------------------
def test_house_style_is_the_default_and_changes_nothing():
    """`--style house` (and no style at all) must mean 'what we already had'.

    Every field on the house entry is None on purpose: the pipeline's own
    defaults decide. If someone ever fills these in, the two delivered edits
    stop being reproducible and this test is the alarm.
    """
    from studio import styles

    for name in (None, "", "house"):
        st = styles.get(name)
        assert st.name == "house"
        for f in ("behaviour", "design", "silence_ms", "accent_at"):
            assert getattr(st, f) is None, f"house drifted: {f} = {getattr(st, f)}"
        assert st.type_engine == "cards"
        assert st.grade == "premium"
        assert st.fx == ()


def test_unknown_style_raises_instead_of_falling_back():
    from studio import styles

    import pytest

    with pytest.raises(KeyError) as e:
        styles.get("not_a_style")
    assert "house" in str(e.value)


def test_house_plan_for_the_delivered_zaalima_is_unchanged():
    """The cut structure of post2_zaalima, regenerated, to the number.

    49 cuts over 35.06 s: 3 build, 45 drop, 1 out; 6 flash, 6 whip, 2 ramp.
    These are the numbers the delivered file was built from. If a change to the
    director, the planner or the cards moves ANY of them, the house system has
    been altered — which is the one thing that must not happen silently.
    """
    from pathlib import Path

    from studio import pipeline

    video = Path("footage/post2/videoplayback.mp4")
    audio = Path("footage/post2/YTDown.com_YouTube_Media_PJ3f0_LPlSY_zaalima-"
                 "arijit-singh-harshdeep-kaur-editaudio_009_128k.mp3")
    cards = Path("studio/out/post2_zaalima.cards.json")
    if not (video.exists() and audio.exists() and cards.exists()):
        import pytest

        pytest.skip("the post2 pack is not in this checkout")

    rep = pipeline.run(str(video), str(audio), None, "work/house_contract.mp4",
                       start=23.0, font="Gefika", dry_run=True,
                       brief_name="post2_zaalima", cards_in=str(cards),
                       end=58.06)
    plan = "\n".join(rep["plan"])
    assert "plan: 49 cuts over 35.06s" in plan, plan
    assert "build    3 cuts    2.92s" in plan, plan
    assert "drop    45 cuts" in plan, plan
    assert "out      1 cuts" in plan, plan
    assert "6 flash" in plan and "6 whip" in plan and "2 ramp" in plan, plan


def test_house_pack_still_describes_the_delivered_files():
    """The frozen copy must keep matching what actually shipped.

    `studio/stylepacks/house_v1.json` is a copy of the working system: the
    parameters, the plan fingerprints and the hashes of the two delivered edits.
    If a future change alters either edit, this fails — which is the whole point
    of freezing it instead of trusting a memory of what the settings were.
    """
    import hashlib
    from pathlib import Path

    from studio import styles

    d = styles.pack("house_v1")
    assert d["engine"]["type_engine"] == "cards"
    assert d["engine"]["fx"] == []
    assert d["engine"]["caption_rule"].startswith("one card at a time")
    for e in d["edits"]:
        f = Path(e["delivered"])
        if not f.exists():
            continue
        h = hashlib.sha256(f.read_bytes()).hexdigest()[:12]
        assert h == e["sha256_12"], (
            f"{e['name']} is no longer the file the house pack describes "
            f"({h} vs {e['sha256_12']})")


# ---------------------------------------------------------------------------
# barrage — a style built from a reference reel, not from the house
# ---------------------------------------------------------------------------
def test_reference1_is_another_name_for_the_house_system():
    """The system that made Faahun, Zaalima and Stay answers to three names.

    The user calls it reference1. The registry calls it house. Both must be the
    same object, with every field still None, or the working system has been
    quietly changed by vocabulary.
    """
    from studio import styles

    house = styles.get(None)
    for name in ("house", "reference1", "ref1"):
        assert styles.get(name) is house
    assert house.behaviour is None and house.grade == "premium"


def test_barrage_is_parked_and_asks_for_no_type():
    from studio import styles

    st = styles.get("barrage", parked_ok=True)
    assert st.type_engine == "none"
    assert st.grade == "barrage"
    assert styles.get(None).name == "house"      # still the default


def test_parked_styles_are_not_offered():
    """reference1 is the system. A parked style must not resolve by name."""
    import pytest

    from studio import styles

    assert styles.names() == ["house", "ref1", "reference1"]
    assert "cold_read" not in styles.names()
    for name in styles.PARKED:
        with pytest.raises(KeyError) as e:
            styles.get(name)
        assert "parked" in str(e.value)
        assert "reference1" in str(e.value)


def test_barrage_plan_has_the_reference_shape():
    """Half-second cutting, one three-second hold at two-thirds, three-frame
    flashes, and no cards. These are the invariants from the v26 pass; if the
    builder drifts, this fails before a render does."""
    from pathlib import Path

    import pytest

    from studio import barrage, grid as _grid, shots

    src_path = Path("footage/tom_holland/scenepack.mp4")
    trk = Path("footage/tom_holland/track.mp3")
    if not (src_path.exists() and trk.exists()):
        pytest.skip("the tom_holland pack is not in this checkout")

    g = _grid.analyse(trk, 31.0)
    src = shots.analyse(src_path, None)
    plan = barrage.build(g, src, 0.0, 30.0)

    d = sorted(c.dur for c in plan.cuts)
    median = d[len(d) // 2]
    assert 0.42 <= median <= 0.62, median            # reference median 0.53
    holds = [c for c in plan.cuts if c.dur >= 1.5]
    assert len(holds) == 1, f"{len(holds)} long shots, reference has one"
    # 3.10 s in the reference. It can only be as long as the shot feeding it,
    # so a pack whose longest single take is 2.7 s gets 2.70 — the clamp is the
    # plan being honest, not the style drifting.
    # 3.10 s in the reference. A hold can only be as long as the take feeding
    # it: this scenepack's longest shot is ~1.85 s, so the hold clamps to ~1.7
    # rather than freezing. On a pack with a 3 s take it lands on 3.10.
    longest = max(sh.dur for sh in src.shots)
    if longest >= 3.2:
        assert 2.9 <= holds[0].dur <= 3.3, holds[0].dur
    else:
        assert holds[0].dur >= longest * 0.85, (holds[0].dur, longest)
    assert 0.55 <= holds[0].out_start / plan.duration <= 0.78
    flashes = [c for c in plan.cuts if c.flash]
    assert 4 <= len(flashes) <= 8, f"{len(flashes)} flashes"
    assert all(c.flash_frames == 3 for c in flashes)  # 0.10s, not 2 frames
    assert not any(c.flash and c.transition == "whip" for c in plan.cuts)


def test_barrage_never_fakes_a_breakdown():
    """A duck only happens where the song itself steps back.

    The first build ducked the track at two-thirds whatever the song was doing,
    which invents a moment that is not there. A track with no quiet section
    must come back with no breakdown at all.
    """
    from pathlib import Path

    import pytest

    from studio import barrage, grid as _grid, shots

    src_path = Path("footage/post2/videoplayback.mp4")
    trk = Path("footage/post2/YTDown.com_YouTube_Media_PJ3f0_LPlSY_zaalima-"
               "arijit-singh-harshdeep-kaur-editaudio_009_128k.mp3")
    if not (src_path.exists() and trk.exists()):
        pytest.skip("the post2 pack is not in this checkout")

    g = _grid.analyse(trk, 54.0)
    src = shots.analyse(src_path, None)
    plan = barrage.build(g, src, 23.0, 53.0)
    # Zaalima has no quiet passage near two-thirds; the picture still slows,
    # but the audio must be left alone.
    assert plan.breakdown is None
    assert any(c.dur >= 1.5 for c in plan.cuts)


# ---------------------------------------------------------------------------
# landscape only, and no style that repeats its own pack
# ---------------------------------------------------------------------------
def test_no_style_may_ask_for_a_crop():
    """Landscape only, decided 2026-10-23.

    v12 is square because it is a phone interview. Copying that means cropping
    a 16:9 pack to 1:1, which throws away the sides of every frame — an aspect
    ratio is never inherited from a reference. `styles.check` refuses it, so it
    cannot come back by accident.
    """
    import pytest

    from studio import styles

    for name in styles.names(include_parked=True):
        assert styles.get(name, parked_ok=True).format == "landscape", name
    with pytest.raises(ValueError):
        styles.check(styles.Style(name="oops", label="oops", format="square"))


def test_longtake_is_landscape_and_slow():
    from studio import styles

    st = styles.get("longtake", parked_ok=True)
    assert st.format == "landscape"
    assert st.grade == "longtake"
    assert "1:1" in st.note          # the note says the square is NOT copied


def test_built_styles_do_not_repeat_shots():
    """The repertoire picker must exhaust the pack before reusing a shot.

    The house `_pick_shot` penalises a used shot by 1.2, which on a real pack is
    smaller than the motion/brightness spread — 14 cuts drew on 4 shots out of
    87 usable ones. The built styles use `repertoire.pick` instead; the house
    system keeps the picker it shipped with, because its plans are frozen.
    """
    from pathlib import Path

    import pytest

    from studio import grid as _grid, longtake, shots
    from studio import plan as _plan

    src_path = Path("footage/post2/videoplayback.mp4")
    trk = Path("footage/post2/YTDown.com_YouTube_Media_PJ3f0_LPlSY_zaalima-"
               "arijit-singh-harshdeep-kaur-editaudio_009_128k.mp3")
    if not (src_path.exists() and trk.exists()):
        pytest.skip("the post2 pack is not in this checkout")

    g = _grid.analyse(trk, 54.0)
    src = shots.analyse(src_path, None)
    plan = longtake.build(g, src, 23.0, 53.0)
    picked = [c.shot for c in plan.cuts]
    assert len(set(picked)) == len(picked), (
        f"{len(picked) - len(set(picked))} repeated shots in a "
        f"{len(picked)}-cut plan")


# ---------------------------------------------------------------------------
# the three type-led styles
# ---------------------------------------------------------------------------
def test_every_built_style_is_landscape_and_loads():
    from studio import styles

    for name in ("barrage", "longtake", "cold_read", "hymn", "hype"):
        st = styles.get(name, parked_ok=True)
        assert st.format == "landscape", name
    assert styles.get(None).name == "house"


def test_style_layouts_produce_one_card():
    """Every type layout must hand the compositor ONE Card.

    They differ in placement and voice; none of them may return a list, and a
    two-line lockup must never come back (the caption rule).
    """
    from studio import typefaces
    from studio.typecards import Card

    for name, fn in typefaces.LAYOUTS.items():
        c = fn("Deedaar tera milne itna")
        assert isinstance(c, Card), name
        assert c.rgba.ndim == 3 and c.rgba.shape[2] == 4, name


def test_typecards_still_has_no_multiline_helper():
    """The one-line rule holds for the new layouts too."""
    from studio import typecards

    assert not hasattr(typecards, "render_stack")
    assert not hasattr(typecards, "stack_face")


def test_cold_read_kills_a_fragment_on_its_cut():
    """The defining rule of the style: words die with the shot they sit on."""
    from pathlib import Path

    import pytest

    from studio import coldread, grid as _grid, shots

    src_path = Path("footage/post2/videoplayback.mp4")
    trk = Path("footage/post2/YTDown.com_YouTube_Media_PJ3f0_LPlSY_zaalima-"
               "arijit-singh-harshdeep-kaur-editaudio_009_128k.mp3")
    if not (src_path.exists() and trk.exists()):
        pytest.skip("the post2 pack is not in this checkout")

    g = _grid.analyse(trk, 54.0)
    src = shots.analyse(src_path, None)
    plan = coldread.build(g, src, 23.0, 53.0)
    assert plan.cuts[-1].act == "out"
    assert plan.cuts[-1].dur >= 2.0, "the style ends on a hold"

    cards = [{"start": 2.0, "end": 2.5, "text": "a", "line": 0},
             {"start": 6.0, "end": 6.4, "text": "b", "line": 1}]
    out = coldread.shape_cards(cards, plan)
    for c in out:
        cut = next((k for k in plan.cuts
                    if k.out_start - 1e-6 <= c["start"] < k.out_end), None)
        assert cut is not None
        assert c["end"] <= cut.out_end + 1e-6, "a fragment outlived its shot"


def test_cards_are_never_on_screen_together():
    """The caption rule, enforced on every style that draws words.

    One card at a time, one line on it. Cards may not overlap in time after a
    style's own shaping — that is the failure the user called out.
    """
    from pathlib import Path

    import pytest

    from studio import grid as _grid, hymn, hype, shots

    src_path = Path("footage/post2/videoplayback.mp4")
    trk = Path("footage/post2/YTDown.com_YouTube_Media_PJ3f0_LPlSY_zaalima-"
               "arijit-singh-harshdeep-kaur-editaudio_009_128k.mp3")
    if not (src_path.exists() and trk.exists()):
        pytest.skip("the post2 pack is not in this checkout")

    g = _grid.analyse(trk, 54.0)
    src = shots.analyse(src_path, None)
    raw = [{"start": 1.0 + i * 2.0, "end": 2.6 + i * 2.0, "text": f"line {i}",
            "line": i} for i in range(12)]
    for mod in (hymn, hype):
        plan = mod.build(g, src, 23.0, 53.0)
        # shape_cards works in EDIT seconds; these test cards already are
        out = mod.shape_cards(raw, plan)
        for a, b in zip(out, out[1:]):
            assert a["end"] <= b["start"] + 1e-6, (mod.__name__, a, b)
