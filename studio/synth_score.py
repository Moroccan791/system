"""A synthetic test score, so the engine can be verified without a licensed track.

The three beds in assets/music are 14-second loops with a flat RMS curve — they
are campaign background, and they have no build and no drop, which is exactly
what this system needs to be tested against. So this generates a score with a
real structure:

    0 - 12.5s   build   kick on 1 and 3, hats on 8ths, filter sweeping open
    12.5s       riser   noise sweep into the downbeat
    12.5 - 25s  drop    four-on-the-floor, hats on 16ths, bass on the kick
    25 - 30s    out     kick gone, pad only

It is a metronome with a groove, not music. Its job is to have a grid you can
check the cut plan against with your own ears.
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 44100
BPM = 96.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
BUILD_BARS = 5        # 12.5 s
DROP_BARS = 5         # 12.5 s
OUT_BARS = 2          # 5.0 s
TOTAL = (BUILD_BARS + DROP_BARS + OUT_BARS) * BAR


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / max(decay, 1e-4))


def _kick(dur=0.42, f0=130.0, f1=48.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.045)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR)
    click = np.random.default_rng(7).normal(0, 1, n) * np.exp(-t / 0.004) * 0.3
    return (body * _env(n, 0.002, 0.16) + click) * 0.9


def _hat(dur=0.05) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.default_rng(11).normal(0, 1, n)
    # crude high-pass by differencing
    return np.diff(np.concatenate([[0.0], noise])) * _env(n, 0.0005, 0.012) * 0.5


def _bass(freq=55.0, dur=0.30) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    saw = 2 * ((t * freq) % 1.0) - 1
    return saw * _env(n, 0.004, 0.10) * 0.35


def _riser(dur=2.5) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.default_rng(3).normal(0, 1, n)
    # one-pole low-pass with a rising cutoff
    out = np.zeros(n)
    acc = 0.0
    for i in range(n):
        k = 0.001 + 0.06 * (i / n) ** 2
        acc += k * (noise[i] - acc)
        out[i] = acc
    return out * (t / dur) ** 2 * 1.6


def build(out_path: str | Path) -> Path:
    n = int(TOTAL * SR)
    mix = np.zeros(n)
    rng = np.random.default_rng(5)

    def place(sig: np.ndarray, at: float, gain=1.0):
        i = int(at * SR)
        j = min(n, i + len(sig))
        if i < n:
            mix[i:j] += sig[: j - i] * gain

    drop_at = BUILD_BARS * BAR
    out_at = (BUILD_BARS + DROP_BARS) * BAR

    beat = 0
    total_beats = int(TOTAL / BEAT)
    while beat * BEAT < TOTAL:
        t = beat * BEAT
        in_build = t < drop_at
        in_drop = drop_at <= t < out_at
        bar_beat = beat % 4

        if in_build:
            if bar_beat in (0, 2):
                place(_kick(), t, 0.85)
            place(_hat(), t, 0.25)
            place(_hat(), t + BEAT / 2, 0.18)
            if bar_beat == 0:
                place(_bass(55.0, 0.6), t, 0.5)
        elif in_drop:
            place(_kick(), t, 1.0)
            place(_hat(), t, 0.42)
            place(_hat(), t + BEAT / 4, 0.22)
            place(_hat(), t + BEAT / 2, 0.34)
            place(_hat(), t + 3 * BEAT / 4, 0.22)
            place(_bass(55.0, 0.26), t, 0.75)
            place(_bass(65.4, 0.26), t + BEAT / 2, 0.55)
        beat += 1

    place(_riser(BAR), drop_at - BAR, 0.9)

    # pad under the out section
    t = np.arange(int((TOTAL - out_at) * SR)) / SR
    pad = (np.sin(2 * np.pi * 110 * t) + 0.5 * np.sin(2 * np.pi * 164.8 * t))
    place(pad * 0.12 * np.minimum(1.0, t / 1.5), out_at, 1.0)

    # gentle limiter and normalise
    mix /= max(1e-9, np.abs(mix).max())
    mix = np.tanh(mix * 1.6) * 0.85
    stereo = np.stack([mix, np.roll(mix, 37)], axis=1)

    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(str(p), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return p


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "work/studio/test_score.wav"
    print(build(out))
