"""Carrying source word timings through an edit plan (captions without a 2nd ASR pass)."""
from __future__ import annotations

from clipper.asr.base import Word
from clipper.captions import remap


def _plan(shots):
    return {"shots": [{"start": s, "end": e, "duration": round(e - s, 3)} for s, e in shots]}


def _words(pairs):
    return [Word(text=t, start=s, end=e) for t, s, e in pairs]


def test_a_word_in_the_second_shot_lands_after_the_first():
    plan = _plan([(100.0, 102.0), (1000.0, 1001.0)])       # a cut, not continuous source
    words = _words([("hello", 100.5, 100.9), ("world", 1000.2, 1000.6)])
    out = remap.remap_words(plan, words)
    assert [(w.text, w.start, w.end) for w in out] == [
        ("hello", 0.5, 0.9), ("world", 2.2, 2.6)]


def test_words_in_a_gap_the_edit_dropped_are_left_out():
    plan = _plan([(0.0, 2.0), (10.0, 12.0)])
    words = _words([("kept", 0.5, 0.9), ("dropped", 5.0, 5.4), ("also", 10.5, 10.9)])
    out = remap.remap_words(plan, words)
    assert [w.text for w in out] == ["kept", "also"]
    assert out[1].start == 2.5


def test_word_durations_survive_the_move():
    plan = _plan([(30.0, 32.0)])
    out = remap.remap_words(plan, _words([("stretch", 31.0, 31.7)]))
    assert round(out[0].end - out[0].start, 3) == 0.7


def test_a_word_straddling_a_cut_is_kept_and_clamped():
    plan = _plan([(0.0, 10.0), (10.0, 20.0)])               # contiguous: a plain cut
    words = _words([("cut", 9.8, 10.3)])                    # spoken across the join
    out = remap.remap_words(plan, words)
    assert len(out) == 1
    assert out[0].start == 9.8 and out[0].end <= 10.0       # clamped into the first shot


def test_a_word_spanning_a_dropped_region_is_dropped():
    plan = _plan([(0.0, 10.0), (20.0, 30.0)])               # 10-20s was thrown away
    out = remap.remap_words(plan, _words([("gone", 15.0, 15.4)]))
    assert out == []


def test_a_word_sitting_on_the_second_shot_is_not_lost():
    plan = _plan([(0.0, 10.0), (10.0, 20.0)])
    out = remap.remap_words(plan, _words([("edge", 10.02, 10.4)]))
    assert len(out) == 1


def test_a_sped_up_shot_maps_into_less_time():
    plan = {"shots": [{"start": 0.0, "end": 10.0, "speed": 2.0}]}
    out = remap.remap_words(plan, _words([("fast", 8.0, 9.0)]))
    assert out[0].start == 4.0 and out[0].end == 4.5


def test_clip_duration_is_the_sum_of_the_shots():
    assert remap.clip_duration(_plan([(0.0, 2.0), (50.0, 53.0)])) == 5.0
    assert remap.clip_duration({"shots": [{"start": 0.0, "end": 10.0, "speed": 2.0}]}) == 5.0


def test_no_plan_means_words_come_back_untouched():
    words = _words([("a", 1.0, 1.2)])
    assert remap.remap_words({}, words)[0].start == 1.0


def test_words_are_marked_as_remapped():
    out = remap.remap_words(_plan([(0.0, 5.0)]), _words([("a", 1.0, 1.2)]))
    assert out[0].source == "remap"


def test_words_for_clip_reports_what_it_did(tmp_path):
    import json

    plan_path = tmp_path / "p.plan.json"
    plan_path.write_text(json.dumps(_plan([(0.0, 4.0)])))
    t_path = tmp_path / "t.json"
    t_path.write_text(json.dumps({"words": [
        {"text": "hi", "start": 0.5, "end": 0.9},
        {"text": "gone", "start": 99.0, "end": 99.2}]}))
    words, report = remap.words_for_clip(plan_path, t_path)
    assert report["words_in"] == 2 and report["words_out"] == 1
    assert report["clip_duration"] == 4.0
