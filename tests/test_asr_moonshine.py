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
