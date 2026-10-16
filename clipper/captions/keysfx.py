"""Synthesized keyboard-click bank for typed on-screen text.

The samples are generated, not recorded: each variant is a filtered-noise
tick plus a low sine 'thock', which reads as a soft mechanical keystroke.
Five slightly different variants (plus a two-part "enter" key) are picked at
random per keystroke so typed headlines never sound looped. Everything here
is original code output - CC0, no samples to license (see
assets/sfx/LICENSES.md). Regenerate with:  python -m clipper.captions.keysfx
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from .. import config

SAMPLE_RATE = 48000
BANK_DIR = config.ROOT / "assets" / "sfx" / "keys"

# (seed offsets, body pitch Hz, decay ms) - small differences, same family
_VARIANTS = [
    (11, 235.0, 46),
    (23, 262.0, 40),
    (37, 218.0, 54),
    (41, 248.0, 43),
    (53, 276.0, 38),
]


def _rng(seed: int):
    state = [seed * 2654435761 % 2**32]

    def nxt() -> float:  # xorshift32 -> [-1, 1), deterministic per variant
        x = state[0]
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        state[0] = x
        return x / 2**31 - 1.0

    return nxt


def _envelope(n: int, attack_ms: float, decay_ms: float) -> list[float]:
    a = max(1, int(SAMPLE_RATE * attack_ms / 1000))
    d = max(1, int(SAMPLE_RATE * decay_ms / 1000))
    env = []
    for i in range(n):
        if i < a:
            env.append(i / a)
        else:
            env.append(math.exp(-(i - a) / d * 4.5))
    return env


def _keystroke(seed: int, pitch: float, decay_ms: float,
               dur_ms: float = 80.0) -> bytes:
    rnd = _rng(seed)
    n = int(SAMPLE_RATE * dur_ms / 1000)
    env = _envelope(n, 0.8, decay_ms)
    # band-passed noise tick: difference of two one-pole lowpasses
    slow = [0.0] * n
    fast = [0.0] * n
    lp1 = lp2 = 0.0
    for i in range(n):
        w = rnd()
        lp1 += 0.85 * (w - lp1)
        lp2 += 0.30 * (w - lp2)
        slow[i] = lp2
        fast[i] = lp1 - lp2
    samples = bytearray()
    for i in range(n):
        t = i / SAMPLE_RATE
        thock = math.sin(2 * math.pi * pitch * t) * math.exp(-t * 90)
        click = fast[i] * 0.9 + slow[i] * 0.25
        v = (click * 0.75 + thock * 0.45) * env[i]
        v = max(-0.95, min(0.95, v))
        samples += struct.pack("<h", int(v * 32767))
    return bytes(samples)


def _enter() -> bytes:
    """Softer, lower two-part key: press + release, ~115 ms total."""
    press = _keystroke(71, 196.0, 34, dur_ms=70)
    release = _keystroke(97, 165.0, 28, dur_ms=55)
    gap = b"\x00\x00" * int(SAMPLE_RATE * 0.045)
    return press[: int(SAMPLE_RATE * 0.055) * 2] + gap + release


def _write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)


def synthesize_bank(out_dir: Path | None = None) -> list[Path]:
    """Write key1..key5.wav + enter.wav into `out_dir` (default assets bank)."""
    out_dir = Path(out_dir) if out_dir else BANK_DIR
    written = []
    for i, (seed, pitch, decay) in enumerate(_VARIANTS, start=1):
        p = out_dir / f"key{i}.wav"
        _write_wav(p, _keystroke(seed, pitch, decay))
        written.append(p)
    enter_path = out_dir / "enter.wav"
    _write_wav(enter_path, _enter())
    written.append(enter_path)
    return written


def bank_files() -> dict[str, list[str] | str]:
    """Paths the pipeline mixes with, or {} when the bank is missing."""
    keys = [BANK_DIR / f"key{i}.wav" for i in range(1, 6)]
    enter = BANK_DIR / "enter.wav"
    if all(p.exists() for p in keys) and enter.exists():
        return {"keys": [str(p) for p in keys], "enter": str(enter)}
    return {}


if __name__ == "__main__":  # pragma: no cover
    for p in synthesize_bank():
        print(p)
