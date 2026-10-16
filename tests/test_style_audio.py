"""Stage 1 audio treatment.

Real speech is not available offline in this sandbox, so the voice-detection
half is exercised through the seams: `speech_intervals` is substituted with
known intervals and the *decision logic* is what gets tested. Loudness and the
spectral measures are tested on real signals produced here.
"""
from __future__ import annotations

import struct
import subprocess
import wave

import numpy as np
import pytest

from clipper import config
from clipper.ffmpeg import ffmpeg_exe
from clipper.style import audio_style as aud


RATE = 16000


def _write_wav(path, samples, rate=RATE):
    data = np.clip(np.asarray(samples, dtype=float), -1.0, 1.0)
    pcm = (data * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(pcm.tobytes())
    return path


def _tone(seconds, freq=220.0, amp=0.3, rate=RATE):
    t = np.arange(int(seconds * rate)) / rate
    return amp * np.sin(2 * np.pi * freq * t)


def _silence(seconds, rate=RATE):
    return np.zeros(int(seconds * rate))


def test_spectral_flatness_separates_tone_from_noise():
    tone = _tone(2.0)
    noise = np.random.default_rng(0).normal(0, 0.2, int(2.0 * RATE))
    flat_tone = aud._spectral_flatness(tone.astype(np.float32), RATE)
    flat_noise = aud._spectral_flatness(noise.astype(np.float32), RATE)
    assert flat_tone.size and flat_noise.size
    assert float(np.mean(flat_tone)) < 0.1 < float(np.mean(flat_noise))


def test_rms_db_handles_silence_and_full_scale():
    # silence clamps to the floor of the dB calculation, not to -inf
    assert aud._rms_db(_silence(0.5)) <= -100.0
    full = np.sin(2 * np.pi * 100 * np.arange(RATE) / RATE).astype(np.float32)
    assert aud._rms_db(full) == pytest.approx(-3.0, abs=0.5)


def test_loudness_is_measured_from_the_file(tmp_path):
    """A file encoded at a known level must report roughly that level."""
    quiet = _write_wav(tmp_path / "quiet.wav", _tone(3.0, amp=0.05))
    loud = _write_wav(tmp_path / "loud.wav", _tone(3.0, amp=0.9))
    lufs_quiet = aud.loudness(str(quiet)).get("integrated_lufs")
    lufs_loud = aud.loudness(str(loud)).get("integrated_lufs")
    assert lufs_quiet is not None and lufs_loud is not None
    assert lufs_loud > lufs_quiet + 20


def test_music_bed_detected_when_gaps_are_loud_and_tonal(tmp_path, monkeypatch):
    """Tone under the whole clip, speech only in the middle -> music bed."""
    samples = _tone(8.0, amp=0.3).astype(np.float32)
    wav = _write_wav(tmp_path / "music.wav", samples)
    monkeypatch.setattr(aud, "speech_intervals", lambda audio, rate: [(2.0, 4.0)])
    out = aud.analyze_audio_style(str(wav))
    assert out["music_bed"] is True
    assert out["speech_ratio"] == pytest.approx(0.25, abs=0.05)
    assert out["target_lufs"] is not None


def test_no_music_bed_when_gaps_are_silent(tmp_path, monkeypatch):
    """Same speech layout, but the background is empty -> no music bed."""
    samples = np.concatenate([_silence(2.0), _tone(2.0, amp=0.3), _silence(1.5),
                              _tone(2.5, amp=0.3)]).astype(np.float32)
    wav = _write_wav(tmp_path / "speechonly.wav", samples)
    monkeypatch.setattr(aud, "speech_intervals", lambda audio, rate: [(2.0, 4.0)])
    out = aud.analyze_audio_style(str(wav))
    assert out["music_bed"] is False


def test_no_speech_intervals_means_unknown(tmp_path, monkeypatch):
    wav = _write_wav(tmp_path / "silentish.wav", _tone(4.0, amp=0.05))
    monkeypatch.setattr(aud, "speech_intervals", lambda audio, rate: [])
    out = aud.analyze_audio_style(str(wav))
    assert out["music_bed"] is None and out["speech_ratio"] == 0.0
    assert out["confidence"] <= 0.2


def test_video_without_audio_is_not_an_error(tmp_path):
    clip = tmp_path / "silent.mp4"
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=black:s=320x568:d=1", "-c:v", "libx264", "-preset",
                    "ultrafast", "-pix_fmt", "yuv420p", str(clip)], check=True)
    out = aud.analyze_audio_style(str(clip))
    assert out["music_bed"] is None
    assert out["confidence"] == 0.0
    assert out["note"] == "no audio track"
