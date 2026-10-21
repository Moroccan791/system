"""The pause dip is small, slow, and only over real pauses."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import render_clip  # noqa: E402


def _wav(tmp_path: Path, seconds: float = 4.0, rate: int = 48000) -> Path:
    t = np.arange(int(seconds * rate)) / rate
    x = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    stereo = np.repeat(x[:, None], 2, axis=1)
    from sound_design import write_wav
    return write_wav(tmp_path / "tone.wav", stereo, rate)


def _rms(path: Path, a: float, b: float, rate: int = 48000) -> float:
    import imageio_ffmpeg
    raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error",
                          "-i", str(path), "-vn",
                          "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, dtype="<f4")
    seg = x[int(a * rate):int(b * rate)]
    return float(np.sqrt((seg ** 2).mean()))


def test_a_pause_dips_two_db_and_speech_does_not(tmp_path, monkeypatch) -> None:
    import imageio_ffmpeg
    monkeypatch.setattr(render_clip, "ffmpeg",
                        lambda: imageio_ffmpeg.get_ffmpeg_exe())
    src = _wav(tmp_path)
    mp4 = tmp_path / "tone.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y",
                    "-i", str(src), "-c:a", "aac", "-b:a", "192k", str(mp4)],
                   check=True)
    speech = [(0.5, 1.5), (2.5, 3.5)]
    render_clip._duck_pauses(mp4, speech, 4.0)
    speech_db = 20 * np.log10(_rms(mp4, 0.6, 1.4))
    pause_db = 20 * np.log10(_rms(mp4, 1.8, 2.3))
    assert abs(speech_db - (-14.0)) < 3.0, speech_db
    assert 1.4 <= speech_db - pause_db <= 2.6, (speech_db, pause_db)


def test_a_short_gap_is_left_alone(tmp_path, monkeypatch) -> None:
    import imageio_ffmpeg
    monkeypatch.setattr(render_clip, "ffmpeg",
                        lambda: imageio_ffmpeg.get_ffmpeg_exe())
    src = _wav(tmp_path)
    mp4 = tmp_path / "tone.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y",
                    "-i", str(src), "-c:a", "aac", "-b:a", "192k", str(mp4)],
                   check=True)
    render_clip._duck_pauses(mp4, [(0.2, 1.9), (2.1, 3.9)], 4.0)
    before = 20 * np.log10(_rms(mp4, 1.93, 2.07))
    assert before > -18.0, "a 0.2 s gap is a breath, not a pause"
