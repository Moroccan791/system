"""The beat grid — the clock everything else in studio/ hangs off.

Why this file exists: in the whop campaign chain a timeline is authored in
seconds, because words have timestamps. An overedit is authored in *beats*,
because the music is the score and the picture is played against it. Change the
track and every cut should still land. That is only possible if cuts are stored
as `beat 12.5`, never as `t=4.13`.

So: analyse the track once, derive
  - tempo (BPM) and the phase of the grid,
  - the 16th-note onset grid the cuts will quantise to,
  - the sections (build / drop / out) from the track's own energy,
and expose `Grid.t(beats)` to turn a musical position into seconds.

Sections are DETECTED, not assumed. A track that builds for 20s and drops is
the common shape, but the planner must read what this track actually does.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SR = 22050
HOP = 256
WIN = 1024


def _ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def load_audio(path: str | Path) -> np.ndarray:
    """Decode anything ffmpeg reads to mono float32 at SR."""
    raw = subprocess.run(
        [_ffmpeg(), "-nostdin", "-v", "error", "-i", str(path),
         "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def _stft_mag(x: np.ndarray) -> np.ndarray:
    n = 1 + (len(x) - WIN) // HOP
    if n <= 0:
        return np.zeros((1, WIN // 2 + 1), dtype=np.float32)
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    frames = x[idx] * np.hanning(WIN).astype(np.float32)
    return np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32)


def onset_envelope(x: np.ndarray) -> np.ndarray:
    """Spectral flux on a log-magnitude spectrogram, normalised to 0..1."""
    mag = _stft_mag(x)
    log = np.log1p(mag * 20.0)
    flux = np.maximum(0.0, np.diff(log, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    # local mean subtraction kills the loudness envelope, leaving attacks
    k = 16
    pad = np.pad(flux, (k // 2, k // 2), mode="edge")
    local = np.convolve(pad, np.ones(k) / k, mode="valid")[: len(flux)]
    env = np.maximum(0.0, flux - local)
    if env.max() <= 0:
        return np.zeros_like(env)
    return (env / env.max()).astype(np.float32)


def low_band_envelope(x: np.ndarray, cutoff_hz: float = 160.0) -> np.ndarray:
    """Onset envelope restricted to the kick/低 band.

    The full-band flux peaks a few frames late (it is dominated by broadband
    transients with a slower attack than the kick's pitch drop), which puts the
    whole grid ~60ms behind the beat. Phase is therefore taken from the low
    band, where the attack is sharp; tempo still comes from the full spectrum.
    """
    mag = _stft_mag(x)
    freqs = np.fft.rfftfreq(WIN, 1.0 / SR)
    hi = int(np.searchsorted(freqs, cutoff_hz))
    hi = max(2, hi)
    band = np.log1p(mag[:, :hi] * 40.0)
    flux = np.maximum(0.0, np.diff(band, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    k = 8
    pad = np.pad(flux, (k // 2, k // 2), mode="edge")
    local = np.convolve(pad, np.ones(k) / k, mode="valid")[: len(flux)]
    env = np.maximum(0.0, flux - local)
    if env.max() <= 0:
        return np.zeros_like(env)
    return (env / env.max()).astype(np.float32)


def onset_times(env: np.ndarray, thresh_q: float = 0.90, min_gap: float = 0.11):
    """Peak-pick the envelope. Returns seconds."""
    if len(env) < 3:
        return []
    thr = np.percentile(env, thresh_q * 100)
    peaks = [i for i in range(1, len(env) - 1)
             if env[i] > thr and env[i] >= env[i - 1] and env[i] >= env[i + 1]]
    # frames are windowed, so the time of frame i is the centre of its window
    t = (np.arange(len(env)) * HOP + WIN / 2) / SR
    out = []
    for p in peaks:
        if not out or t[p] - out[-1] > min_gap:
            out.append(float(t[p]))
    return out


def estimate_tempo(env: np.ndarray, lo: float = 70.0, hi: float = 190.0,
                   phase_env: np.ndarray | None = None):
    """Find the tempo whose grid actually has hits on it, then refine it.

    Two stages, because a coarse comb search lands within ~0.2% of the tempo and
    0.2% is 60ms of drift over a 31-second edit — enough to see. Stage two does a
    joint fine search over tempo and phase against the low band, where the kick
    attack is sharp.
    """
    fps = SR / HOP
    if env.max() <= 0 or len(env) < int(fps * 2):
        return 120.0, 0.0, 0.0
    penv = phase_env if (phase_env is not None and phase_env.max() > 0) else env

    best = (0.0, 120.0, 0.0)
    for period_frames in np.arange(fps * 60 / hi, fps * 60 / lo, 0.25):
        n_beats = int((len(env) - 1) / period_frames)
        if n_beats < 4:
            continue
        k = np.arange(n_beats)
        for phase in np.arange(0, period_frames, max(1.0, period_frames / 12)):
            pos = np.round(phase + k * period_frames).astype(int)
            pos = pos[pos < len(env)]
            if len(pos) < 4:
                continue
            score = float(env[pos].mean())
            score *= min(1.0, len(pos) / 16.0) ** 0.25
            if score > best[0]:
                best = (score, 60.0 * fps / period_frames, float(phase))
    _score, bpm0, _ph = best

    # --- stage two: joint fine search around the coarse winner -----------------
    def score_grid(bpm: float, phase_s: float) -> float:
        period = 60.0 / bpm * fps
        phase_f = phase_s * fps
        n_beats = int((len(penv) - phase_f) / period)
        if n_beats < 6:
            return -1.0
        pos = np.round(phase_f + np.arange(n_beats) * period).astype(int)
        pos = pos[(pos >= 0) & (pos < len(penv))]
        if len(pos) < 6:
            return -1.0
        # weight late beats equally: a grid that drifts scores worse here
        return float(penv[pos].mean())

    best_bpm, best_phase, best_s = bpm0, 0.0, -1.0
    for bpm in np.arange(bpm0 * 0.985, bpm0 * 1.015, 0.01):
        period = 60.0 / bpm * fps
        for phase_f in np.arange(0.0, period, 1.0):
            sc = score_grid(bpm, phase_f / fps)
            if sc > best_s:
                best_s, best_bpm, best_phase = sc, float(bpm), float(phase_f / fps)

    # express the phase as the first beat inside the track
    period_s = 60.0 / best_bpm
    while best_phase >= period_s:
        best_phase -= period_s
    while best_phase < 0:
        best_phase += period_s
    return float(best_bpm), float(best_phase), float(best_s)


@dataclass
class Section:
    start: float
    end: float
    level: int          # 0 quiet, 1 mid, 2 loud
    label: str          # build / drop / out / body

    def as_dict(self):
        return {"start": round(self.start, 3), "end": round(self.end, 3),
                "level": self.level, "label": self.label}


@dataclass
class Grid:
    bpm: float
    phase: float                 # seconds, position of beat 0
    duration: float
    onsets: list[float] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    rms_db: list[float] = field(default_factory=list)

    # --- the only conversion the rest of the system is allowed to use ---
    def t(self, beats: float) -> float:
        return self.phase + beats * 60.0 / self.bpm

    def beats(self, seconds: float) -> float:
        return (seconds - self.phase) * self.bpm / 60.0

    def snap(self, beats: float, division: int = 4) -> float:
        """Quantise a beat position to a musical division (4 = 16th notes)."""
        return round(beats * division / division * division) / division

    def section_at(self, seconds: float) -> Section | None:
        for s in self.sections:
            if s.start <= seconds < s.end:
                return s
        return self.sections[-1] if self.sections else None

    def as_dict(self):
        return {
            "bpm": round(self.bpm, 2),
            "phase": round(self.phase, 4),
            "duration": round(self.duration, 3),
            "onsets": [round(o, 3) for o in self.onsets],
            "sections": [s.as_dict() for s in self.sections],
            "rms_db": [round(v, 1) for v in self.rms_db],
        }


def _attack_lag(penv: np.ndarray, depth: float = 0.25, max_back: int = 10) -> float:
    """How many seconds the envelope peaks AFTER the transient starts.

    A beat is the start of the attack, not its maximum. On a kick with a pitch
    drop the low-band energy keeps rising for ~30ms after the hit, so phase taken
    from peaks is systematically late by about a frame. Measure that lag and
    subtract it.
    """
    fps = SR / HOP
    if penv.max() <= 0 or len(penv) < 8:
        return 0.0
    thr = np.percentile(penv, 92)
    peaks = [i for i in range(1, len(penv) - 1)
             if penv[i] >= thr and penv[i] >= penv[i - 1] and penv[i] >= penv[i + 1]]
    lags = []
    for pk in peaks[:120]:
        j = pk
        target = penv[pk] * depth
        while j > 0 and pk - j < max_back and penv[j - 1] >= target:
            j -= 1
        lags.append((pk - j) / fps)
    return float(np.median(lags)) if lags else 0.0


def _sections(x: np.ndarray, duration: float) -> tuple[list[Section], list[float]]:
    """Level-change segmentation on a smoothed RMS curve.

    Smoothing is deliberately long (2s): a sparse build has near-silent bars
    between kicks, and a short window reads those gaps as sections. We want the
    section to describe the *texture* of a stretch, not its individual hits.
    """
    win = int(SR * 0.5)
    hop = int(SR * 0.25)
    if len(x) < win:
        return [Section(0.0, duration, 1, "mid")], [0.0]
    frames = np.lib.stride_tricks.sliding_window_view(x, win)[::hop]
    rms = np.sqrt((frames ** 2).mean(axis=1))
    db = 20 * np.log10(rms + 1e-9)
    t = np.arange(len(db)) * hop / SR

    k = 9                       # ~2s of smoothing
    pad = np.pad(db, (k // 2, k // 2), mode="edge")
    sm = np.convolve(pad, np.ones(k) / k, mode="valid")[: len(db)]

    lo, hi = np.percentile(sm, 40), np.percentile(sm, 75)
    if hi - lo < 1.5:           # flat track: one section, no invented structure
        return [Section(0.0, duration, 1, "mid")], [float(v) for v in db]
    level = np.digitize(sm, [lo, hi])

    # run-length encode
    runs = [[int(level[0]), 0, len(level)]]
    for i in range(1, len(level)):
        if level[i] != runs[-1][0]:
            runs[-1][2] = i
            runs.append([int(level[i]), i, len(level)])

    # repeatedly absorb the shortest run into its longer neighbour
    min_frames = max(4, int(2.0 / 0.25))
    while len(runs) > 1:
        lens = [r[2] - r[1] for r in runs]
        i = int(np.argmin(lens))
        if lens[i] >= min_frames:
            break
        if i == 0:
            runs[1][1] = 0
        elif i == len(runs) - 1:
            runs[i - 1][2] = runs[i][2]
        else:
            if lens[i - 1] >= lens[i + 1]:
                runs[i - 1][2] = runs[i][2]
            else:
                runs[i + 1][1] = runs[i][1]
        del runs[i]

    # collapse neighbours that ended up on the same level
    merged = [runs[0]]
    for r in runs[1:]:
        if r[0] == merged[-1][0]:
            merged[-1][2] = r[2]
        else:
            merged.append(r)
    runs = merged

    sections = []
    for lv, a, b in runs:
        s_start = float(t[a])
        s_end = float(min(duration, t[min(b, len(t) - 1)]))
        if s_end > s_start:
            sections.append(Section(s_start, s_end, lv, ""))
    if not sections:
        return [Section(0.0, duration, 1, "mid")], [float(v) for v in db]
    sections[0].start = 0.0
    sections[-1].end = duration

    loud_i = max(range(len(sections)), key=lambda i: sections[i].level)
    has_drop = (sections[loud_i].level == 2
                and (sections[loud_i].end - sections[loud_i].start) >= 2.0)
    names = {0: "quiet", 1: "mid", 2: "loud"}
    for i, s_ in enumerate(sections):
        if has_drop and i == loud_i:
            s_.label = "drop"
        elif has_drop and i < loud_i:
            s_.label = "build"
        else:
            s_.label = names.get(s_.level, "mid")
    return sections, [float(v) for v in db]


def analyse(track: str | Path, max_seconds: float | None = None) -> Grid:
    x = load_audio(track)
    if max_seconds:
        x = x[: int(max_seconds * SR)]
    duration = len(x) / SR
    env = onset_envelope(x)
    penv = low_band_envelope(x)
    bpm, phase, _score = estimate_tempo(env, phase_env=penv)
    phase = phase - _attack_lag(penv) + (WIN / 2) / SR
    period_s = 60.0 / bpm
    while phase < 0:
        phase += period_s
    while phase >= period_s:
        phase -= period_s
    onsets = onset_times(env)
    sections, db = _sections(x, duration)
    return Grid(bpm=bpm, phase=phase, duration=duration, onsets=onsets,
                sections=sections, rms_db=db)


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="beat grid for a music track")
    ap.add_argument("track")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-seconds", type=float, default=None)
    a = ap.parse_args(argv)
    g = analyse(a.track, a.max_seconds)
    d = g.as_dict()
    text = json.dumps(d, indent=1)
    if a.out:
        Path(a.out).write_text(text + "\n")
    print(f"{a.track}: {g.bpm:.1f} BPM, beat0 {g.phase:.3f}s, "
          f"{len(g.onsets)} onsets, {len(g.sections)} sections")
    for s in g.sections:
        print(f"  {s.label:6s} level {s.level}  {s.start:6.2f} - {s.end:6.2f}"
              f"  ({s.end - s.start:.2f}s)")
    if not a.out:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
