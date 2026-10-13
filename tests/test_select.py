"""Stage 2: moment selection.

The episode used here is synthetic but not arbitrary: `synth.render_episode`
places loud stretches at known times and `samples.episode_transcript` puts hook
sentences inside them, so "did it find the moments" has a numeric answer.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from clipper import config
from clipper.asr.base import Word
from clipper.select import energy as energy_mod
from clipper.select import hooks as hooks_mod
from clipper.select import score as score_mod
from clipper.select.pipeline import select_candidates
from clipper.synth import render_episode


@pytest.fixture(scope="module")
def episode(tmp_path_factory):
    path = tmp_path_factory.mktemp("episode") / "episode.mp4"
    info = render_episode(str(path))
    info["path"] = str(path)
    return info


@pytest.fixture(scope="module")
def curve(episode):
    return energy_mod.energy_curve(episode["path"])


@pytest.fixture()
def scripted(episode):
    from clipper.samples import episode_transcript

    data = episode_transcript(episode)
    return [Word.from_dict(w) for w in data["words"]]


# ---------------------------------------------------------------------------
# energy
# ---------------------------------------------------------------------------
def test_energy_curve_finds_the_loud_stretches(episode, curve):
    spots = energy_mod.hot_spots(curve)
    assert len(spots) == len(episode["hot_windows"])
    for spot, (start, end) in zip(spots, episode["hot_windows"]):
        assert spot["start"] == pytest.approx(start, abs=0.7)
        assert spot["end"] == pytest.approx(end, abs=0.7)
        assert spot["peak_above_db"] > 6.0, "hot stretches must stand above the baseline"


def test_quiet_points_land_between_the_bursts(curve):
    quiet = energy_mod.quiet_points(curve)
    assert quiet, "a clip with silence in it must expose quiet points"
    # the stretch between the first and second hot window is calm
    assert any(13.0 <= q <= 20.0 for q in quiet)


def test_snap_to_pause_moves_a_cut_into_the_gap(curve):
    moved = energy_mod.snap_to_pause(13.6, curve)
    assert 12.5 <= moved <= 20.5
    assert moved != 13.6


def test_activity_is_bounded(curve):
    activity = energy_mod.activity(curve)
    assert activity.size and float(activity.min()) >= 0.0 and float(activity.max()) <= 1.0


# ---------------------------------------------------------------------------
# hooks
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,floor", [
    ("nobody tells you this but i lost ninety thousand dollars in three months", 0.6),
    ("there are three reasons your ads fail and the first one is brutal", 0.5),
    ("why do people ignore the best offer they will ever see ?", 0.4),
])
def test_hooks_score_high(text, floor):
    score, reasons = hooks_mod.score_text(text)
    assert score >= floor, f"{text!r} scored {score} ({reasons})"
    assert reasons


@pytest.mark.parametrize("text", [
    "so anyway that is kind of how the week went",
    "and then we sort of moved on to the next thing",
])
def test_filler_scores_low(text):
    score, _ = hooks_mod.score_text(text)
    assert score < 0.3


def test_filler_phrases_are_penalised():
    plain, _ = hooks_mod.score_text("i made a mistake")
    padded, reasons = hooks_mod.score_text("i mean you know i made a mistake kind of")
    assert padded < plain
    assert any("filler" in r for r in reasons)


def test_sentences_split_on_pauses_and_punctuation():
    words = [
        Word("hello", 0.0, 0.3), Word("there", 0.35, 0.6), Word("friend.", 0.65, 0.95),
        Word("this", 3.0, 3.3), Word("is", 3.35, 3.6), Word("later", 3.65, 4.0),
    ]
    units = hooks_mod.sentence_units(words)
    assert len(units) == 2
    assert units[0]["text"].endswith("friend.")
    assert units[1]["start"] == pytest.approx(3.0)


def test_a_monologue_without_punctuation_still_units():
    words = [Word(f"w{i}", i * 0.3, i * 0.3 + 0.25) for i in range(30)]
    units = hooks_mod.sentence_units(words, max_words=10)
    assert len(units) >= 3


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
def test_scored_units_flag_the_hooks(scripted, curve):
    spots = energy_mod.hot_spots(curve)
    scored = score_mod.score_units(hooks_mod.sentence_units(scripted), curve, spots)
    hooks = [u for u in scored if u["burst_id"] is not None]
    filler = [u for u in scored if u["burst_id"] is None]
    assert hooks and filler
    assert min(u["score"] for u in hooks) > max(u["score"] for u in filler)


def test_candidates_carry_exactly_one_moment(episode, scripted, curve):
    spots = energy_mod.hot_spots(curve)
    scored = score_mod.score_units(hooks_mod.sentence_units(scripted), curve, spots)
    candidates = score_mod.build_candidates(scored, curve, min_seconds=12, max_seconds=22,
                                            top=5, spots=spots)
    assert len(candidates) == len(spots) == 3
    for candidate in candidates:
        inside = [i for i, spot in enumerate(spots)
                  if candidate["start"] <= spot["peak_time"] <= candidate["end"]]
        assert len(inside) == 1, f"{candidate['id']} covers {len(inside)} moments"


def test_candidates_respect_the_target_length(episode, scripted, curve):
    spots = energy_mod.hot_spots(curve)
    scored = score_mod.score_units(hooks_mod.sentence_units(scripted), curve, spots)
    floor = score_mod.length_floor(12.0)
    for candidate in score_mod.build_candidates(scored, curve, min_seconds=12,
                                                max_seconds=22, top=5, spots=spots):
        assert floor <= candidate["duration"] <= 22.0


def test_candidates_do_not_overlap(episode, scripted, curve):
    spots = energy_mod.hot_spots(curve)
    scored = score_mod.score_units(hooks_mod.sentence_units(scripted), curve, spots)
    candidates = score_mod.build_candidates(scored, curve, min_seconds=12, max_seconds=22,
                                            top=5, spots=spots)
    spans = sorted((c["start"], c["end"]) for c in candidates)
    for (_, end), (start, _) in zip(spans, spans[1:]):
        assert end <= start + 1e-6


def test_better_moment_wins_a_contested_slot(scripted, curve):
    """Two seeds, one clearly better: the better one keeps its full length."""
    spots = energy_mod.hot_spots(curve)
    scored = score_mod.score_units(hooks_mod.sentence_units(scripted), curve, spots)
    candidates = score_mod.build_candidates(scored, curve, min_seconds=12, max_seconds=22,
                                            top=1, spots=spots)
    assert len(candidates) == 1
    best = max(scored, key=lambda u: u["score"])
    assert candidates[0]["start"] <= best["start"] and best["end"] <= candidates[0]["end"]


def test_audio_only_selection_finds_every_moment(episode, curve):
    spots = energy_mod.hot_spots(curve)
    candidates = score_mod.build_from_energy(curve, spots, min_seconds=12, max_seconds=22,
                                             top=5)
    assert len(candidates) == 3
    for start, end in episode["hot_windows"]:
        assert any(c["start"] <= start + 0.8 and end - 0.8 <= c["end"] for c in candidates)


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------
def test_select_writes_json_and_a_report(episode, tmp_path):
    payload = select_candidates(episode["path"], transcript=None, platform="tiktok",
                                min_seconds=12, max_seconds=22, top=3,
                                work_dir=tmp_path / "work")
    assert payload["mode"] == "audio-only"
    written = tmp_path / "work" / "candidates" / "episode.json"
    assert written.exists()
    reloaded = json.loads(written.read_text())
    assert len(reloaded["candidates"]) == 3
    assert (tmp_path / "work" / "candidates" / "episode.report.md").exists()
    for candidate in reloaded["candidates"]:
        assert candidate["reasons"] and candidate["duration"] > 0


def test_select_uses_a_transcript_when_given_one(episode, scripted, tmp_path):
    payload = select_candidates(episode["path"], transcript=scripted, platform="tiktok",
                                min_seconds=12, max_seconds=22, top=3,
                                work_dir=tmp_path / "work")
    assert payload["mode"] == "transcript+audio"
    assert payload["analysis"]["words"] == len(scripted)
    texts = " ".join(c["text"] or "" for c in payload["candidates"])
    assert "ninety thousand dollars" in texts
    assert "three reasons" in texts


def test_select_reads_a_transcript_from_disk(episode, scripted, tmp_path):
    tpath = tmp_path / "episode.transcript.json"
    tpath.write_text(json.dumps({"words": [{"text": w.text, "start": w.start, "end": w.end}
                                           for w in scripted], "language": "en"}))
    payload = select_candidates(episode["path"], transcript=tpath, min_seconds=12,
                                max_seconds=22, top=2, work_dir=tmp_path / "work")
    assert payload["mode"] == "transcript+audio"


def test_sidecar_transcript_is_discovered(episode, scripted, tmp_path):
    media = tmp_path / "show.mp4"
    media.write_bytes(open(episode["path"], "rb").read())
    media.with_suffix(".transcript.json").write_text(json.dumps({
        "words": [{"text": w.text, "start": w.start, "end": w.end} for w in scripted]}))
    payload = select_candidates(media, min_seconds=12, max_seconds=22, top=2,
                                work_dir=tmp_path / "work")
    assert payload["mode"] == "transcript+audio"


def test_min_longer_than_max_is_rejected(episode):
    with pytest.raises(ValueError):
        select_candidates(episode["path"], min_seconds=30, max_seconds=10, save=False)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        select_candidates(tmp_path / "nope.mp4", save=False)


def test_video_without_audio_is_not_a_crash(tmp_path):
    """A silent screen recording should report nothing, not explode."""
    import subprocess

    from clipper.ffmpeg import ffmpeg_exe

    clip = tmp_path / "silent.mp4"
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=black:s=320x568:d=2", "-c:v", "libx264", "-preset",
                    "ultrafast", "-pix_fmt", "yuv420p", str(clip)], check=True)
    payload = select_candidates(clip, save=False)
    assert payload["candidates"] == []
    assert "audio" in (payload.get("note", "") + payload["mode"])


def test_report_is_readable(episode, scripted):
    from clipper.select.pipeline import render_report

    payload = select_candidates(episode["path"], transcript=scripted, min_seconds=12,
                                max_seconds=22, top=2, save=False)
    report = render_report(payload)
    assert report.startswith("# candidates")
    assert "loud stretches" in report
