"""The voice chain: order is the design, and the bands have to actually move.

An audio chain is easy to write and hard to notice. These tests pin the two
things that can go wrong quietly: filters in the wrong order (de-essing after
the compressor just tames sibilance the compressor already lifted), and a
chain that changes the level without changing the tone.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import voice_finish as VF  # noqa: E402


def test_chain_order_is_highpass_eq_deess_comp_limiter() -> None:
    c = VF.chain()
    order = ["highpass", "equalizer", "deesser", "acompressor", "alimiter"]
    pos = [c.index(k) for k in order]
    assert pos == sorted(pos), c
    assert c.count("equalizer") == 3


def test_deess_comes_before_the_compressor() -> None:
    c = VF.chain()
    assert c.index("deesser") < c.index("acompressor")


def test_disabled_chain_leaves_the_file_alone(tmp_path: Path) -> None:
    src = tmp_path / "a.mp4"
    src.write_bytes(b"not really a video")
    assert VF.finish(src, {"enabled": False}) == src
    assert src.read_bytes() == b"not really a video"


def _make_tone(path: Path, *, seconds: float = 1.5) -> None:
    """A synthetic 'voice': 200 Hz mud + 1.2 kHz body + 6 kHz hiss."""
    ff = VF.ffmpeg()
    subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"sine=frequency=200:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=1200:duration={seconds}",
         "-f", "lavfi", "-i", f"anoisesrc=d={seconds}:c=white:a=0.02",
         "-filter_complex",
         "[0:a]volume=0.5[a];[1:a]volume=0.4[b];[2:a]highpass=f=5000,volume=0.5[c];"
         "[a][b][c]amix=inputs=3:normalize=0[out]",
         "-map", "[out]", "-c:a", "pcm_s16le", str(path)], check=True)


def test_chain_changes_tone_not_just_level(tmp_path: Path) -> None:
    src = tmp_path / "tone.wav"
    _make_tone(src)
    before = VF.bands(src)
    out = tmp_path / "out.wav"
    subprocess.run([VF.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(src), "-af", VF.chain(), str(out)], check=True)
    after = VF.bands(out)

    def share(d, band):
        total = sum(v for k, v in d.items() if k != "crest_db")
        return d[band] / total

    # the mud band should lose share and the presence band should gain it
    assert share(after, "150-350") < share(before, "150-350")
    assert share(after, "2600-4500") > share(before, "2600-4500")


def test_highpass_removes_rumble(tmp_path: Path) -> None:
    ff = VF.ffmpeg()
    src = tmp_path / "rumble.wav"
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "sine=frequency=55:duration=1.0",
                    "-f", "lavfi", "-i", "sine=frequency=1500:duration=1.0",
                    "-filter_complex", "[0:a]volume=0.6[a];[1:a]volume=0.4[b];"
                                       "[a][b]amix=inputs=2:normalize=0[out]",
                    "-map", "[out]", str(src)], check=True)
    out = tmp_path / "out.wav"
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(src), "-af", VF.chain(), str(out)], check=True)
    before, after = VF.bands(src), VF.bands(out)
    assert after["40-120"] < before["40-120"] * 0.5
