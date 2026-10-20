#!/usr/bin/env python3
"""Make the voice sound recorded, not pulled off the internet.

Every other part of the mix got attention - the bed is synthesised, the
loudness is measured, the true peak is corrected - but the voice itself has
been passed through untouched. On archive footage that means rumble, mud
around 250 Hz, dull consonants and sibilance that the compressor then makes
worse. None of that is visible in a still, and all of it is audible on a phone
speaker, which is where these posts are watched.

The chain, in the order it has to be in:

    highpass 90 Hz x2   rumble and handling noise below the voice; two
                        cascaded stages because ffmpeg caps one at 2 poles and
                        a single stage measured only -4 dB on a 55 Hz tone
    EQ -1.5 dB @ 250    mud that makes a phone speaker sound boxy
    EQ +2.0 dB @ 3.2k   presence: consonants land
    de-ess              BEFORE the compressor, or the compressor lifts the
                        very sibilance you are trying to tame
    compressor          gentle, and only on peaks: measured on post 7, a
                        -20 dB / 2.5:1 setting cut the voice-to-room gap from
                        19.0 dB to 13.5 (the gate wants >= 12), because
                        compression pulls the loud parts down but not the room
                        tone. At -14 dB / 2.0:1 the gap stays ~18 and the
                        peaks are still tamed.
    limiter             a safety net; loudness is still set later by the gate

Deliberately absent: FFT denoise. On archive audio it leaves a watery
"underwater" tail on breaths, which is worse than the hiss it removes.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DEFAULT = {
    "enabled": True,
    "highpass": 90, "highpass_stages": 2,
    "mud_hz": 250, "mud_db": -1.5,
    "presence_hz": 3200, "presence_db": 2.0,
    "air_hz": 9000, "air_db": 0.8,
    "deess": 0.40,
    "comp_threshold": -14, "comp_ratio": 2.0, "comp_attack": 6,
    "comp_release": 140,
    "limiter": 0.95,
}


def ffmpeg() -> str:
    return subprocess.run(
        [sys.executable, "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
        capture_output=True, text=True).stdout.strip()


def chain(cfg: dict | None = None) -> str:
    """The filter chain as ffmpeg syntax. Order is the design, not taste."""
    c = {**DEFAULT, **(cfg or {})}
    parts = [
        # Two stages, because ffmpeg's highpass caps at 2 poles: one stage at
        # 90 Hz measured only -4 dB on a 55 Hz tone, and rumble survived it.
        # Cascading gives 24 dB/oct, which is what actually clears the low end.
        *[f"highpass=f={float(c['highpass']):.0f}:poles=2"
          for _ in range(max(1, int(c["highpass_stages"])))],
        f"equalizer=f={float(c['mud_hz']):.0f}:t=q:w=1.2:g={float(c['mud_db']):.1f}",
        f"equalizer=f={float(c['presence_hz']):.0f}:t=q:w=1.0:g={float(c['presence_db']):.1f}",
        f"equalizer=f={float(c['air_hz']):.0f}:t=q:w=1.5:g={float(c['air_db']):.1f}",
        f"deesser=i={float(c['deess']):.2f}:m=0.5",
        # makeup stays at 1.0: loudness is set later against the whole
        # programme, and makeup here lifts the room tone too - which measured
        # as the bed getting 5 dB louder relative to the voice on post 7
        ("acompressor=threshold={}dB:ratio={}:attack={}:release={}:makeup=1"
         .format(float(c["comp_threshold"]), float(c["comp_ratio"]),
                 float(c["comp_attack"]), float(c["comp_release"]))),
        f"alimiter=limit={float(c['limiter']):.2f}",
    ]
    return ",".join(parts)


def finish(path: Path, cfg: dict | None = None) -> Path:
    """Apply the chain in place, leaving the picture untouched (copy)."""
    c = {**DEFAULT, **(cfg or {})}
    if not c.get("enabled", True):
        return path
    tmp = path.with_name(path.stem + "_voice.mp4")
    subprocess.run(
        [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(path),
         "-map", "0:v:0", "-map", "0:a:0",
         "-c:v", "copy", "-af", chain(c), "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", "-shortest", str(tmp)], check=True)
    tmp.replace(path)
    return path


def bands(path: Path) -> dict:
    """Energy per band, for before/after proof rather than opinion."""
    import numpy as np
    import wave
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(path), "-ac", "1", "-ar", "16000",
                        "-c:a", "pcm_s16le", str(wav)], check=True)
        with wave.open(str(wav)) as w:
            raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if not len(x):
        return {}
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1 / 16000.0)

    def band(lo, hi):
        m = (freqs >= lo) & (freqs < hi)
        return float(np.sqrt((spec[m] ** 2).mean())) if m.any() else 0.0

    power = {f"{int(lo)}-{int(hi)}": band(lo, hi)
             for lo, hi in ((40, 120), (150, 350), (1000, 2600), (2600, 4500), (5500, 9000))}
    rms = float(np.sqrt((x ** 2).mean())) or 1e-9
    peak = float(np.abs(x).max()) or 1e-9
    return {**{k: round(v, 6) for k, v in power.items()},
            "crest_db": round(20 * np.log10(peak / rms), 2)}


def main() -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--copy", help="write the finished file here instead of in place")
    ap.add_argument("--measure", action="store_true", help="print before/after bands")
    args = ap.parse_args()
    src = Path(args.video)
    before = bands(src) if args.measure else None
    if args.copy:
        import shutil
        dst = Path(args.copy)
        shutil.copy2(src, dst)
        finish(dst)
    else:
        dst = finish(src)
    after = bands(dst) if args.measure else None
    print(json.dumps({"file": str(dst), "before": before, "after": after,
                      "chain": chain()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
