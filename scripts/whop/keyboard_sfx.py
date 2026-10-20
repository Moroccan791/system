"""Recorded keyboard typing for the caption type-on.

The user supplied a recorded keyboard run (a Mixkit free-use typing file,
vendored as `assets/sfx/keyboard_typing.wav`). The old house typing sound was
synthesized (`clipper/captions/keysfx.py`) and mixed at 0.07-0.10 under the
music bed, where a -16 dB measurement says it was effectively inaudible.

This module cuts the individual keystrokes out of that recording and lays
them on the caption reveal grid:

* every caption types on: one short burst of real keys lands on each word's
  reveal time, so the last key of a burst hits the frame the word appears;
* the track is strictly gated to caption windows - before the first caption,
  after the last one, through the OAK TREE plate's held lines and over the
  end card there is exact digital silence, never a bed of clicks.

Everything is deterministic per post (seeded), so re-renders match.
"""
from __future__ import annotations

import subprocess
import sys
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
KEY_WAV = ROOT / "assets" / "sfx" / "keyboard_typing.wav"
SR = 48000

_BANK: list[np.ndarray] | None = None


def _ff() -> str:
    return subprocess.run(
        [sys.executable, "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
        capture_output=True, text=True).stdout.strip()


def _decode(path: Path, sr: int = SR) -> np.ndarray:
    raw = subprocess.run(
        [_ff(), "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").astype(np.float32)


def _highpass(x: np.ndarray, ms: float = 3.0, sr: int = SR) -> np.ndarray:
    """Rough high-pass: subtract a 3 ms moving average.

    Kills the room rumble under a key without an IIR loop (scipy is not a
    dependency of this script) and leaves the attack edge intact.
    """
    w = max(3, int(sr * ms / 1000.0))
    kern = np.ones(w, dtype=np.float32) / w
    low = np.convolve(x, kern, mode="same").astype(np.float32)
    return (x - low).astype(np.float32)


def _onsets(x: np.ndarray, sr: int = SR) -> int:
    """Sample indices of keystroke attacks in a fast, smoothed envelope."""
    env = np.abs(x)
    w = max(1, int(sr * 0.002))
    env = np.convolve(env, np.ones(w) / w, mode="same")
    thr = np.percentile(env, 96)
    hits: list[int] = []
    gap = int(sr * 0.04)
    i = 0
    while i < len(env):
        if env[i] > thr:
            j = min(i + gap, len(env))
            hits.append(i + int(np.argmax(env[i:j])))
            i += gap
        else:
            i += 1
    return np.array(hits, dtype=int)


def key_bank() -> list[np.ndarray]:
    """Clean isolated keystrokes cut from the supplied recording.

    A key is kept only if the next one is >=160 ms away (so no second click
    bleeds into the tail) and the 60-120 ms tail is quiet relative to the
    attack. Each is normalised to peak 1.0 with short fades so it can be
    layered without a click of its own.
    """
    global _BANK
    if _BANK is not None:
        return _BANK
    x = _highpass(_decode(KEY_WAV))
    hits = _onsets(x)
    pre = int(SR * 0.008)
    win = int(SR * 0.120)
    rows = []
    for p in hits:
        others = hits[hits != p]
        if len(others) == 0:
            continue
        near = float(np.min(np.abs(others - p)) / SR)
        if near < 0.16 or p - pre < 0 or p + pre + win >= len(x):
            continue
        seg = x[p - pre:p + pre + win].copy()
        head = float(np.sqrt(np.mean(seg[:int(SR * 0.025)] ** 2))) + 1e-9
        tail = float(np.sqrt(np.mean(seg[int(SR * 0.060):] ** 2)))
        second = float(np.abs(seg[int(SR * 0.045):]).max()) / (
            float(np.abs(seg[:int(SR * 0.020)]).max()) + 1e-9)
        rows.append((tail / head + second, seg))
    rows.sort(key=lambda r: r[0])
    bank = []
    for _, seg in rows[:12]:
        seg = seg / max(float(np.abs(seg).max()), 1e-9)
        # gentle saturation: a recorded key is a very spiky transient, and a
        # spike this tall would either clip the program mix or force the keys
        # so quiet they vanish under the music bed. Compressing the crest
        # puts the energy into the body of the click, which is what reads as
        # "loud" on a phone speaker.
        seg = np.tanh(seg * 1.5) / np.tanh(1.5)
        seg = seg / max(float(np.abs(seg).max()), 1e-9)
        fi, fo = int(SR * 0.003), int(SR * 0.030)
        seg[:fi] *= np.linspace(0, 1, fi, dtype=np.float32)
        seg[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32) ** 1.5
        bank.append(seg.astype(np.float32))
    if len(bank) < 4:
        raise SystemExit(f"keyboard bank too small ({len(bank)}) - check {KEY_WAV}")
    _BANK = bank
    return bank


def _rate(seg: np.ndarray, rate: float) -> np.ndarray:
    """Cheap linear resample - rate>1 is shorter/higher, <1 longer/lower."""
    n = max(8, int(round(len(seg) / rate)))
    x = np.linspace(0.0, len(seg) - 1.0, n)
    return np.interp(x, np.arange(len(seg)), seg).astype(np.float32)


def typing_events(caps: list[dict], endcard: float,
                  seed: str) -> list[tuple[float, int, float, float]]:
    """(time, bank index, gain, rate) for every keystroke of the type-on.

    One burst per word, ending on that word's reveal time: 1 key for a short
    word, up to 3 for a long one, 45-70 ms apart. Bursts never run into each
    other and never leave the caption's own on-screen window.
    """
    bank = key_bank()
    rng = np.random.default_rng(zlib.crc32(seed.encode()))
    events: list[tuple[float, int, float, float]] = []
    for cap in caps:
        cells = [c for line in cap["lines"] for c in line]
        if not cells:
            continue
        lo = max(0.0, cap["show_from"])
        hi = min(cap["show_until"], endcard) - 0.05
        cursor = lo
        for cell in cells:
            at = float(cell["at"])
            if at < lo or at > hi:
                continue
            word = "".join(ch for ch in cell["w"] if ch.isalnum() or ch in "'")
            # characters typed, capped so a burst stays a burst
            n = min(4, max(1, int(np.ceil(len(word) / 2.2))))
            gap = float(rng.uniform(0.050, 0.074))
            start = at - gap * (n - 1)
            if start < cursor:
                # not enough room before this reveal: drop keys, not timing
                n = max(1, int((at - cursor) / gap) + 1)
                start = max(cursor, at - gap * (n - 1))
            if at - start < 0.012:
                start = max(0.015, cursor)
                n = 1
            for k in range(n):
                t = start + gap * k
                idx = int(rng.integers(len(bank)))
                gain = float(rng.uniform(0.80, 1.05))
                rate = float(rng.uniform(0.94, 1.06))
                events.append((round(t, 4), idx, gain, rate))
            cursor = at + 0.030      # keep 30 ms of air after a burst
    events.sort(key=lambda e: e[0])
    return events


def typing_track(caps: list[dict], duration: float, endcard: float,
                 seed: str) -> tuple[np.ndarray, list[dict]]:
    """The keyboard track alone, plus the event log used to place it."""
    bank = key_bank()
    n = int(round(duration * SR)) + SR // 2
    track = np.zeros(n, dtype=np.float32)
    events = typing_events(caps, endcard, seed)
    log = []
    for t, idx, gain, rate in events:
        seg = _rate(bank[idx], rate) * gain
        i = int(round(t * SR))
        if i < 0 or i >= n:
            continue
        j = min(n, i + len(seg))
        track[i:j] += seg[:j - i]
        log.append({"t": t, "key": idx, "gain": round(gain, 3), "rate": round(rate, 3)})
    return track, log


def mix_into(bed: np.ndarray, track: np.ndarray, peak: float = 0.85,
             knee: float = 0.95, headroom: float = 0.89
             ) -> tuple[np.ndarray, float]:
    """Add the keyboard over the shipped mix and keep the result legal.

    The keyboard is scaled so its loudest key peaks at `peak`; where a key
    lands on an already-hot music passage the sum is soft-clipped above
    `knee` (a smooth tanh knee, so a click never turns into a square edge),
    and the whole program is left at `headroom` to keep AAC inter-sample
    overs from breaking up on playback.
    """
    top = float(np.abs(track).max()) if len(track) else 0.0
    if top <= 0:
        return bed, 0.0
    gain = peak / top
    n = max(len(bed), len(track))
    out = np.zeros(n, dtype=np.float32)
    out[:len(bed)] = bed
    out[:len(track)] += track * gain
    a = np.abs(out)
    over = a > knee
    if over.any():
        out[over] = (np.sign(out[over])
                     * (knee + (1 - knee) * np.tanh((a[over] - knee) / (1 - knee))))
    out *= headroom
    return out, gain
