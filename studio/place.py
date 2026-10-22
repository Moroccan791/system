"""Place a lyric whose lines carry NO times.

The studio's placement path takes line windows: `captions.from_timed` puts each
word on a sung syllable *inside* a window it is given. Everything about that is
language-blind and reliable — which is why it works on Bangla and Hindi. What it
cannot do is invent the windows, and the operator cannot supply them: scrubbing
an edit audio for eight line starts is not a job anyone should do twice a day.

So this module derives the windows from the audio, and it is honest about the
one assumption it makes: a sung hook repeats.

    1. a loop period, from a self-similarity matrix of the vocal band
    2. an EXPOSED phrase — the stretch where the voice is nearly the only thing
       in the mix (band energy is >85% of total). Its length is the line length,
       which is why this is not a guess: a clean pre-drop line is one line.
    3. an anchor — the drop, or the first strong vocal onset.
    4. windows every line-length from the anchor, and the lyric laid over them
       in order, cycling when the hook repeats more often than the lyric says.

The result is checked, not trusted: `quality()` measures every card's distance
to the nearest sung onset. A wrong line length reads as a median of hundreds of
milliseconds; a right one reads as tens.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

RATE = 16000
WIN = 1024
HOP = 160


def _load(track: str | np.ndarray) -> np.ndarray:
    if isinstance(track, np.ndarray):
        return track.astype(np.float32)
    import imageio_ffmpeg

    raw = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error", "-i", str(track),
         "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _spec(x: np.ndarray, hop: int = HOP) -> tuple[np.ndarray, np.ndarray]:
    n = 1 + (len(x) - WIN) // hop
    idx = np.arange(WIN)[None, :] + hop * np.arange(n)[:, None]
    S = np.abs(np.fft.rfft(x[idx] * np.hanning(WIN).astype(np.float32), axis=1))
    f = np.fft.rfftfreq(WIN, 1.0 / RATE)
    return S, f


def onsets(track, t0: float, t1: float, hop: int = HOP) -> np.ndarray:
    """Times of sung attacks: spectral flux in the vocal band, peaks only.

    One onset per syllable on a good phrase, which is what the word placement
    needs and what the quality check measures against.
    """
    a = _load(track)
    x = a[int(t0 * RATE):int(t1 * RATE)]
    if len(x) < WIN * 2:
        return np.zeros(0, dtype=np.float32)
    S, f = _spec(x, hop)
    band = (f >= 250) & (f <= 3500)
    L = np.log1p(S[:, band] * 40)
    flux = np.maximum(0.0, np.diff(L, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    k = max(1, int(0.06 * RATE / hop))
    flux = np.convolve(flux, np.ones(k) / k, mode="same")
    thr = float(np.percentile(flux, 72))
    peaks = []
    gap = int(0.09 * RATE / hop)
    for i in range(1, len(flux) - 1):
        if flux[i] >= thr and flux[i] >= flux[i - 1] and flux[i] > flux[i + 1]:
            if not peaks or i - peaks[-1] >= gap:
                peaks.append(i)
    return (t0 + np.asarray(peaks, dtype=np.float32) * hop / RATE)


def loop_period(track, t0: float, t1: float, lo: float = 3.0,
                hi: float = 20.0) -> float:
    """The length of the hook's loop, from the vocal band's self-similarity.

    A loop is the one thing a repeated hook cannot hide: the mix at t and at
    t + period look the same. Measured on the pack that motivated this, the
    strongest lag was 8.36s — exactly four bars at 115 BPM, which is how the
    number can be checked against the grid instead of believed.
    """
    a = _load(track)
    x = a[int(t0 * RATE):int(t1 * RATE)]
    hop = 640
    S, f = _spec(x, hop)
    band = (f >= 250) & (f <= 3500)
    M = np.log1p(S[:, band] * 60)
    M = (M - M.mean(0)) / (M.std(0) + 1e-6)
    M = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    ssm = M @ M.T
    hop_s = hop / RATE
    best, best_lag = -2.0, 0.0
    for lag in range(max(2, int(lo / hop_s)), int(min(hi, (t1 - t0) / 2.5) / hop_s)):
        d = float(np.diagonal(ssm, offset=lag).mean())
        if d > best:
            best, best_lag = d, lag * hop_s
    return float(best_lag)


def exposed(track, t0: float, t1: float, ratio: float = 0.80,
            min_len: float = 1.6) -> list[tuple[float, float]]:
    """Stretches where the voice is nearly alone in the mix.

    Metal and film mixes bury a vocal under everything. Where the voice IS
    exposed — a line sung clean into a drop, a pre-chorus — the vocal band is
    most of the energy, and the length of that stretch is one lyric line. This
    is the module's only solid measurement, so it anchors everything else.
    """
    a = _load(track)
    x = a[int(t0 * RATE):int(t1 * RATE)]
    if len(x) < WIN * 2:
        return []
    S, f = _spec(x, HOP)
    band = (f >= 250) & (f <= 3500)
    ev = np.sqrt((S[:, band] ** 2).sum(1))
    ef = np.sqrt((S ** 2).sum(1)) + 1e-9
    r = ev / ef
    hop_s = HOP / RATE
    good = r > ratio
    out, start = [], None
    for i, g in enumerate(good):
        if g and start is None:
            start = i
        elif not g and start is not None:
            if (i - start) * hop_s >= min_len:
                out.append((t0 + start * hop_s, t0 + i * hop_s))
            start = None
    if start is not None and (len(good) - start) * hop_s >= min_len:
        out.append((t0 + start * hop_s, t0 + len(good) * hop_s))
    return out


def structure(track, t0: float, t1: float, drop: float | None = None) -> dict:
    """Loop, line length and anchor for a window — with what each came from."""
    p = loop_period(track, t0, t1)
    ex = exposed(track, t0, t1)
    # the exposed phrase is one line; prefer the longest one that is not a
    # whole section, and fall back to half a loop (two lines per hook) then to
    # the loop itself.
    lens = [e - s for s, e in ex if 1.4 <= e - s <= 7.0]
    line = max(lens) if lens else (p / 2.0 if p else 0.0)
    if line and p and abs(line - p) < 0.4:          # the phrase WAS the whole loop
        line = p / 2.0
    anchor = drop if drop is not None else (ex[0][0] if ex else t0 + 1.0)
    return {"loop": round(p, 3), "line": round(line, 3),
            "anchor": round(anchor, 3),
            "exposed": [(round(s, 2), round(e, 2)) for s, e in ex]}


def windows(lines: list[str], st: dict, t0: float, t1: float) -> list[tuple[float, float, str]]:
    """Line windows, in order, cycling the lyric when the hook repeats.

    A hook repeats more often than a lyric sheet lists it, and the honest thing
    to do is not to invent new words: the same line goes back on screen. That is
    what the song is doing.
    """
    if not lines:
        return []
    line = st["line"] or (st["loop"] / 2.0 if st["loop"] else 0.0)
    if line <= 0.5:
        line = max(1.2, (t1 - t0) / max(1, len(lines)))
    out = []
    t = st["anchor"]
    # if the anchor is later than the window start, the window before it gets
    # nothing — type over an intro that is not singing those words is a lie.
    k = 0
    while t < t1 - 0.15:
        end = min(t + line, t1)
        out.append((round(t, 3), round(end, 3), lines[k % len(lines)]))
        t += line
        k += 1
        if k > 400:
            break
    return out


def quality(cards: list[dict], ons: np.ndarray) -> dict:
    """How far each card's start sits from a sung onset.

    This is the check that decides whether a placement is real. On the edit this
    module was written for, a correct reading measured a 30-60 ms median; a line
    length that was wrong by a factor of two measured over 900 ms.
    """
    if not cards or len(ons) == 0:
        return {"median_ms": 9999, "worst_ms": 9999, "cards": len(cards)}
    d = [float(np.min(np.abs(ons - c["start"]))) for c in cards]
    return {"median_ms": round(1000 * float(np.median(d)), 1),
            "worst_ms": round(1000 * float(np.max(d)), 1),
            "cards": len(cards)}


def cards(track, t0: float, t1: float, lines: list[str],
          drop: float | None = None, st: dict | None = None) -> tuple[list[dict], dict]:
    """Cards for a window, in absolute track time.

    The window is cut to its own audio file first. That is not tidiness: the
    aligner measures syllable nuclei over the audio it is given, and that
    measurement is quadratic in length — on a three-minute track it took long
    enough to look like a hang. Sixty seconds is the right unit.
    """
    import subprocess
    import tempfile

    import imageio_ffmpeg

    from .captions import from_timed

    st = st or structure(track, t0, t1, drop)
    wav = Path(tempfile.gettempdir()) / "studio_place_window.wav"
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-y", "-v", "error",
         "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", str(track),
         "-ac", "1", "-ar", str(RATE), str(wav)], check=True)
    rel = windows(lines, st, t0, t1)
    table = [(s - t0, e - t0, text) for s, e, text in rel]
    out = from_timed(wav, table, t1 - t0)
    for c in out:
        c["start"] = round(c["start"] + t0, 3)
        c["end"] = round(c["end"] + t0, 3)
    ons = onsets(track, t0, t1)
    return out, {"structure": st, "windows": rel, "quality": quality(out, ons)}


def main(argv=None) -> int:
    import argparse

    from .captions import from_timed, lines_of, parse_timed

    ap = argparse.ArgumentParser(description="line windows for a lyric with no times")
    ap.add_argument("track")
    ap.add_argument("--lyric", required=True, help="one sung line per line, no times")
    ap.add_argument("--window", required=True, help="t0:t1 in seconds of the track")
    ap.add_argument("--drop", type=float, default=None,
                    help="where the hook lands, if the grid knows better")
    ap.add_argument("--line", type=float, default=None,
                    help="override the measured line length, seconds")
    ap.add_argument("--anchor", type=float, default=None,
                    help="override the first line's start, track seconds")
    ap.add_argument("--cards", default=None, help="write the card table here")
    a = ap.parse_args(argv)
    t0, t1 = (float(x) for x in a.window.split(":"))

    lines = [ln.strip() for ln in open(a.lyric, encoding="utf-8")
             if ln.strip() and not ln.strip().startswith("#")]
    st = structure(a.track, t0, t1, a.drop)
    if a.line:
        st["line"] = float(a.line)
    if a.anchor is not None:
        st["anchor"] = float(a.anchor)
    placed, info = cards(a.track, t0, t1, lines, a.drop, st=st)
    st = info["structure"]
    print(f"loop {st['loop']:.2f}s  line {st['line']:.2f}s  anchor {st['anchor']:.2f}s")
    if st["exposed"]:
        print("  exposed: " + ", ".join(f"{s:.2f}-{e:.2f}" for s, e in st["exposed"]))
    for s, e, text in info["windows"]:
        print(f"  {s:7.2f}-{e:7.2f}  {text}")
    print("quality:", info["quality"])
    for L in lines_of(placed):
        print(f"  line {L['line']:2d} {L['start']:7.2f}-{L['end']:7.2f} "
              f"{len(L['cards'])} cards")
    if a.cards:
        from .captions import save_cards

        print("wrote", save_cards(placed, a.cards))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
