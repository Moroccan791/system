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
from clipper.select import pipeline
from clipper.select.pipeline import select_candidates
from clipper.synth import render_episode, textured_scene, write_video


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


# ---------------------------------------------------------------------------
# campaign rules (clipper/guideline.py) inside selection
# ---------------------------------------------------------------------------
RULES = {
    "campaign": "demo",
    "clip": {"min_seconds": 10, "max_seconds": 25},
    "hook": {"within_seconds": 5},
    # word forms matter: a transcript says "dollars", not "money"
    "topics": {"approved": ["dating", "confidence"],
               "banned": ["money", "dollar", "wealth", "politic"]},
    "entities": {"banned": ["bilzerian"]},
    "phrases": {"banned": ["you live in a country*"]},
    "brand": {"notes": ["a face must be on screen for most of the clip"]},
}


def burst_wav(path, *, seconds=40.0, rate=16000, bursts=((10.0, 16.0), (24.0, 30.0))):
    """Quiet room tone with two loud stretches - the moments worth clipping."""
    import wave

    import numpy as np

    t = np.arange(int(seconds * rate)) / rate
    signal = 0.02 * np.sin(2 * np.pi * 180 * t)
    for start, end in bursts:
        mask = (t >= start) & (t < end)
        signal[mask] += 0.30 * np.sin(2 * np.pi * 320 * t[mask])
    pcm = np.clip(signal, -1, 1)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((pcm * 32767).astype("<i2").tobytes())
    return path


def scripted_transcript(path, spans):
    """spans: (start, end, opening words) - speech that runs the whole span.

    Real podcast speech does not stop for ten seconds in the middle of a story,
    so the filler keeps running until the span ends; otherwise a window cannot
    reach the campaign's minimum length without swallowing the other moment.
    """
    filler = ("and", "then", "we", "kept", "talking", "about", "it", "for", "a", "while")
    words, step = [], 0.34
    for start, end, opening in spans:
        t = start
        for text in (*opening, None):
            if text is None:                      # switch to filler
                i = 0
                while t < end - step:
                    words.append({"text": filler[i % len(filler)], "start": round(t, 3),
                                  "end": round(t + step * 0.8, 3)})
                    t += step
                    i += 1
            else:
                words.append({"text": text, "start": round(t, 3),
                              "end": round(t + step * 0.9, 3)})
                t += step
    path.write_text(json.dumps({"text": " ".join(w["text"] for w in words),
                                "language": "en", "provider": "fixture",
                                "duration": words[-1]["end"] if words else 0,
                                "words": words}), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def ruled_media(tmp_path_factory):
    """One file, two loud moments: one off-campaign (money), one on-campaign (dating)."""
    folder = tmp_path_factory.mktemp("ruled")
    media = folder / "talk.mp4"
    wav = burst_wav(folder / "talk.wav")
    frames = (textured_scene(320, 180, seed=9) for _ in range(40 * 12))
    write_video(str(media), frames, fps=12, audio_path=str(wav))
    # speech runs wider than the loud stretches, the way a podcast does: the
    # moment is where the energy and the hook are, not where the talking stops
    transcript = scripted_transcript(folder / "talk.transcript.json", [
        (8.5, 20.0, ("so", "nobody", "tells", "you", "this", "but", "i", "made",
                     "ninety", "thousand", "dollars", "in", "one", "month")),
        (22.5, 34.0, ("why", "do", "people", "ignore", "the", "dating", "advice",
                      "that", "builds", "confidence", "?")),
    ])
    return {"media": str(media), "transcript": str(transcript)}


def test_rules_drop_the_off_campaign_moment_and_keep_the_other(ruled_media):
    payload = pipeline.select_candidates(
        ruled_media["media"], transcript=ruled_media["transcript"], rules=RULES,
        min_seconds=10, max_seconds=25, top=3, save=False)
    kept_text = " ".join(c.get("text", "") for c in payload["candidates"])
    assert payload["candidates"], "the on-campaign moment should survive"
    assert "dating" in kept_text and "dollars" not in kept_text
    assert payload["rejected"], "the money moment should be reported, not silently lost"
    # the reason names the form that actually matched
    assert any("dollar" in " ".join(c["rejected_for"]) for c in payload["rejected"])
    assert payload["guideline"]["clip"] == {"min_seconds": 10.0, "max_seconds": 25.0}


def test_kept_candidates_carry_their_compliance_verdict(ruled_media):
    payload = pipeline.select_candidates(
        ruled_media["media"], transcript=ruled_media["transcript"], rules=RULES,
        min_seconds=10, max_seconds=25, top=3, save=False)
    candidate = payload["candidates"][0]
    compliance = candidate["compliance"]
    checks = {c["check"]: c for c in compliance["checks"]}
    assert compliance["pass"] is True
    assert checks["length"]["pass"] and checks["topics"]["pass"]
    assert compliance["notes"], "unmeasured brand rules are carried along with the clip"
    assert any("on-campaign" in reason for reason in candidate["reasons"])


def test_keep_banned_shows_them_flagged_instead_of_dropping_them(ruled_media):
    payload = pipeline.select_candidates(
        ruled_media["media"], transcript=ruled_media["transcript"], rules=RULES,
        min_seconds=10, max_seconds=25, top=3, save=False, keep_rejected=True)
    assert payload["rejected"] == []
    flagged = [c for c in payload["candidates"] if not c["compliance"]["pass"]]
    assert flagged, "with --keep-banned the moment stays, marked as failing"


def test_hook_anchor_trims_a_long_lead_in():
    """A clip that meanders for 10 s before its hook breaks the campaign's rule."""
    from clipper.select.pipeline import _hook_anchor

    words = [Word("and", 0.0, 2.0), Word("then", 2.0, 4.0), Word("so", 4.0, 6.0),
             Word("anyway", 6.0, 8.5),
             Word("nobody", 10.0, 10.4), Word("tells", 10.4, 10.8), Word("you", 10.8, 11.0),
             Word("this", 11.0, 11.4), Word("the", 11.4, 11.6), Word("truth", 11.6, 12.0),
             Word("about", 12.0, 12.4), Word("dates", 12.4, 12.9)]
    window = {"start": 0.0, "end": 30.0, "duration": 30.0, "reasons": [], "text": ""}
    trimmed, hook_at = _hook_anchor(window, words, RULES, 10.0)
    assert trimmed["start"] > 8.0, "the lead-in should be trimmed"
    assert trimmed["duration"] < 30.0
    assert hook_at is not None and hook_at <= 5.0, "the hook now lands inside the window"
    assert any("lead-in trimmed" in reason for reason in trimmed["reasons"])


def test_reports_explain_rejections_and_compliance(ruled_media):
    payload = pipeline.select_candidates(
        ruled_media["media"], transcript=ruled_media["transcript"], rules=RULES,
        min_seconds=10, max_seconds=25, top=3, save=False)
    report = pipeline.render_report(payload)
    assert "dropped by the campaign rules" in report
    assert "PASS length" in report or "FAIL length" in report
    assert "note:" in report, "brand rules that cannot be checked automatically are printed"
