"""Shared test fixtures.

Tests that need real speech use the wav that ships inside the `moonshine-cpp`
package; when it is missing the test skips instead of failing.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clipper import config  # noqa: E402


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def speech_wav() -> Path:
    """~10 s of real English speech (Ever tried. Ever failed...) at 16 kHz mono."""
    try:
        import moonshine_cpp

        p = Path(moonshine_cpp.__file__).parent / "test-data" / "beckett.wav"
        if p.exists():
            return p
    except Exception:
        pass
    pytest.skip("moonshine test wav not available")


@pytest.fixture(scope="session")
def tmp_work(tmp_path_factory) -> Path:
    """A throwaway work/output dir so tests never touch the real workspace."""
    return tmp_path_factory.mktemp("clipper-work")


@pytest.fixture(scope="session")
def ffmpeg_bin() -> str:
    from clipper.ffmpeg import ffmpeg_exe

    exe = ffmpeg_exe()
    if not shutil.which(exe) and not Path(exe).exists():
        pytest.skip("no ffmpeg")
    return exe


@pytest.fixture(scope="session")
def tone_video(tmp_path_factory) -> Path:
    """5 s 1080x1920 test pattern with a tone - cheap render fixture."""
    from clipper.ffmpeg import ffmpeg_exe

    import subprocess

    out = tmp_path_factory.mktemp("media") / "tone.mp4"
    subprocess.run([
        ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=s=540x960:d=5:r=30", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=48000:duration=5",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-shortest", str(out),
    ], check=True, capture_output=True)
    return out


def pytest_configure(config):  # quieter logs in tests
    import os

    os.environ.setdefault("CLIPPER_LOG", "warn")
