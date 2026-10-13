"""ffmpeg wrapper: probing, decoding, encoding and the fallbacks."""
from __future__ import annotations

import numpy as np
import pytest

from clipper import ffmpeg as ff


def test_ffmpeg_binary_resolves():
    assert ff.ffmpeg_exe()


def test_libass_available():
    # burning captions needs the subtitles filter (libass)
    assert ff.has_filter("subtitles"), "this ffmpeg has no libass - captions cannot be burned"


def test_probe_reads_resolution_and_duration(tone_video):
    info = ff.probe(tone_video)
    assert info.has_video and info.has_audio
    assert (info.width, info.height) == (540, 960)
    assert 4.5 < info.duration < 5.6
    assert info.fps and 29 < info.fps < 31


def test_parse_ffmpeg_input_fallback():
    stderr = """
Input #0, mov,mp4,m4a, from 'x.mp4':
  Duration: 00:01:02.50, start: 0.000000, bitrate: 900 kb/s
  Stream #0:0: Video: h264 (High), yuv420p, 1080x1920, 30 fps, 30 tbr
  Stream #0:1: Audio: aac (LC), 44100 Hz, stereo, fltp
"""
    info = ff.parse_ffmpeg_input(stderr)
    assert info.duration == pytest.approx(62.5)
    assert (info.width, info.height) == (1080, 1920)
    assert info.fps == 30 and info.has_audio and info.audio_channels == 2


def test_decode_audio_mono_float(tone_video):
    audio = ff.decode_audio(tone_video, rate=16000)
    assert audio.dtype == np.float32
    assert abs(len(audio) / 16000 - 5.0) < 0.3
    assert float(np.abs(audio).max()) > 0.01


def test_iter_frames_yields_expected_shape(tone_video):
    frames = list(ff.iter_frames(tone_video, size=(64, 114), fps=5))
    assert len(frames) >= 20
    assert frames[0].shape == (114, 64, 3)


def test_write_wav_roundtrip(tmp_path):
    audio = (np.sin(np.linspace(0, 40, 16000)) * 0.5).astype(np.float32)
    p = ff.write_wav(tmp_path / "t.wav", audio, 16000)
    assert p.exists() and p.stat().st_size > 30_000
    back = ff.decode_audio(p, rate=16000)
    assert abs(len(back) - len(audio)) < 100


def test_render_produces_playable_file(tmp_path, tone_video):
    out = ff.render(tone_video, tmp_path / "out.mp4", preset={"crf": 30, "preset": "ultrafast",
                                                             "acodec": "aac", "abitrate": "96k"},
                    duration=1.0)
    info = ff.probe(out)
    assert info.has_video and 0.8 < info.duration < 1.4
