"""Real speech recognition, end to end, on the wav that ships with moonshine-cpp.

These tests are slow-ish (a few seconds) but they are the honest ones: real
audio in, real transcript out, timings checked against the audio.
"""
from __future__ import annotations

import numpy as np
import pytest

from clipper.asr import get_provider
from clipper.ffmpeg import decode_audio, probe

pytestmark = pytest.mark.integration


def test_provider_is_available():
    prov = get_provider("moonshine")
    if not prov.available():
        pytest.skip("moonshine-cpp not installed")
    assert prov.available() is True


def test_transcribes_real_speech(speech_wav):
    audio = decode_audio(speech_wav, rate=16000)
    prov = get_provider("moonshine")
    transcript = prov.transcribe(audio, 16000)

    text = transcript.text.lower()
    assert transcript.words, "no words recognised"
    # the clip says: "ever tried ever failed, no matter try again fail again fail better"
    for expected in ("ever", "failed", "try", "again", "better"):
        assert expected in text, f"missing '{expected}' in {text!r}"


def test_words_have_sane_timings(speech_wav):
    audio = decode_audio(speech_wav, rate=16000)
    duration = len(audio) / 16000
    transcript = get_provider("moonshine").transcribe(audio, 16000)

    assert transcript.words
    for w in transcript.words:
        assert 0.0 <= w.start < w.end <= duration + 0.25, f"{w.text} {w.start}-{w.end} of {duration}"
    starts = [w.start for w in transcript.words]
    assert starts == sorted(starts), "word timings must be monotonic"
    # speech is continuous here: no long silent gaps in the middle of the words
    span = transcript.words[-1].end - transcript.words[0].start
    assert span < duration


def test_word_count_matches_text(speech_wav):
    audio = decode_audio(speech_wav, rate=16000)
    transcript = get_provider("moonshine").transcribe(audio, 16000)
    assert len(transcript.words) == len(transcript.text.split())


def test_fixture_provider_deterministic():
    from clipper.asr.fixture import FixtureProvider

    prov = FixtureProvider(script=["alpha", "beta", "gamma"])
    t1 = prov.transcribe(np.zeros(16000, dtype=np.float32), 16000)
    t2 = prov.transcribe(np.zeros(16000, dtype=np.float32), 16000)
    assert t1.to_dict() == t2.to_dict()
    assert [w.text for w in t1.words] == ["alpha", "beta", "gamma"]
    assert t1.words[1].start == pytest.approx(t1.words[0].end + 0.06, abs=1e-3)


def test_a_dead_worker_falls_back_instead_of_losing_the_chunk(tmp_path, monkeypatch):
    """The model is native code and can kill its process: the chunk must survive."""
    import clipper.asr.moonshine as mod

    prov = mod.MoonshineProvider()
    calls = {"worker": 0}

    def dead_worker(self, wav):
        calls["worker"] += 1
        raise RuntimeError("worker produced no output (rc=-11)")

    class FakeModel:
        def transcribe_wav(self, path):
            return "  rescued  "

    monkeypatch.setattr(mod.MoonshineProvider, "_worker_text", dead_worker)
    monkeypatch.setattr(prov, "_resolve_model_dir", lambda: None)
    text = prov._chunk_text(tmp_path / "chunk.wav", FakeModel())
    assert text == "rescued" and calls["worker"] == 1


def test_no_isolation_means_no_subprocess(tmp_path, monkeypatch):
    import clipper.asr.moonshine as mod

    prov = mod.MoonshineProvider(isolate_chunks=False)

    def boom(self, wav):
        raise AssertionError("must not start a worker")

    class FakeModel:
        def transcribe_wav(self, path):
            return "direct"

    monkeypatch.setattr(mod.MoonshineProvider, "_worker_text", boom)
    assert prov._chunk_text(tmp_path / "chunk.wav", FakeModel()) == "direct"


def test_an_unbroken_stretch_of_speech_is_split_too():
    """A voice with no pause must not slip past the chunk cap and OOM the model."""
    from clipper.asr.moonshine import split_interval_chunks

    chunks = split_interval_chunks([(0.0, 40.0)], 8.0)
    assert len(chunks) == 5
    assert all(e - s <= 8.001 for s, e in chunks)
    assert chunks[0][0] == 0.0 and chunks[-1][1] == 40.0


def test_split_chunks_cover_everything_without_overlapping():
    from clipper.asr.moonshine import split_interval_chunks

    chunks = split_interval_chunks([(0.0, 3.0), (10.0, 31.0)], 8.0)
    assert chunks[0] == (0.0, 3.0)                 # a short stretch is untouched
    inside = [(s, e) for s, e in chunks if s >= 10.0]
    # the pieces of one unbroken stretch tile it exactly: 10 -> 31 with no holes
    assert inside[0][0] == 10.0 and inside[-1][1] == 31.0
    assert all(inside[i][1] == inside[i + 1][0] for i in range(len(inside) - 1))
    assert sum(e - s for s, e in chunks) == 24.0


def test_short_chunks_are_left_alone():
    from clipper.asr.moonshine import split_interval_chunks

    assert split_interval_chunks([(1.0, 2.0), (5.0, 12.0)], 8.0) == [(1.0, 2.0), (5.0, 12.0)]
