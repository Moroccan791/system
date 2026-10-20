#!/usr/bin/env python3
"""Gate a Whop render against the campaign's own definition of a good clip.

    .venv/bin/python scripts/whop/qc_gate.py \\
        campaigns/street_you_grew_up_on/post7/street_post7.mp4 \\
        --manifest work/street/post7/tight_cards.json \\
        --campaign street_you_grew_up_on

Why this exists: every rule below was already written down somewhere in this
repo - the clipping course ("1-2 lines, ~14 characters", "trim uh, um, you
know, like", "cut at the emotional peak"), the campaign brief (window, 30-40 s
preference), the editing brain ("nothing frozen for 2-3 s"), our own mix rules
(voice always the loudest). They were applied by hand, post by post, and
therefore missed: post6 and post7 shipped with 24-character caption lines, a
"um" on screen and a "you know" as the last words. A rule that cannot fail a
render is a preference, not a rule.

Exit code is 0 only when nothing failed; `--warn-only` downgrades failures to
warnings for a first look at an old file.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "whop"))

import caption_rules as CR                      # noqa: E402
import hook_lab as HL                          # noqa: E402

PASS, WARN, FAIL = "pass", "warn", "fail"


# --------------------------------------------------------------------- utils
def ffmpeg() -> str:
    return subprocess.run(
        [sys.executable, "-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
        capture_output=True, text=True).stdout.strip()


def measure(path: Path) -> dict:
    """Integrated loudness, LRA and true peak from one ffmpeg pass."""
    err = subprocess.run(
        [ffmpeg(), "-hide_banner", "-i", str(path), "-af",
         "loudnorm=print_format=summary", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    out: dict = {}
    for line in err.splitlines():
        if "Input Integrated" in line:
            out["lufs"] = float(line.split(":")[1].split()[0])
        if "Input True Peak" in line:
            out["dbtp"] = float(line.split(":")[1].split()[0])
        if "Input LRA" in line:
            out["lra"] = float(line.split(":")[1].split()[0])
    return out


def decode16(path: Path) -> np.ndarray:
    raw = subprocess.run(
        [ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", str(path),
         "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").astype(np.float32)


def band_db(x: np.ndarray, rate: int = 16000, lo: float = 250.0,
            hi: float = 3500.0) -> float:
    """80th-percentile level of one stretch, measured inside the voice band.

    Broadband energy cannot answer "is the voice the loudest thing" - a music
    bed lives at 60-200 Hz and in the cymbals, so a broadband comparison
    reads 8 dB when the words are in fact 15 dB clear. The course rule is
    about the element you hear as speech, so the measurement is taken where
    speech lives.
    """
    if x.size == 0:
        return -120.0
    n = 512
    hop = 256
    if x.size < n:
        return -120.0
    win = np.hanning(n).astype(np.float32)
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    keep = (freqs >= lo) & (freqs <= hi)
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop]
    spec = np.fft.rfft(frames * win, axis=1)[:, keep]
    power = (np.abs(spec) ** 2).mean(axis=1) + 1e-12
    return float(10 * np.log10(np.percentile(power, 80)))


def speech_gap_db(audio: np.ndarray, rate: int = 16000) -> tuple[float, float]:
    """How far the voice sits above the music-only stretches, in dB.

    The course rule is "voice is always the loudest element". Integrated
    loudness cannot see that - a clip can hit -16 LUFS with a bed that buries
    the words. This splits the file with the VAD we already trust, measures
    the loudest 80th percentile inside speech and inside non-speech, and
    returns the difference.
    """
    from clipper.align.vad import speech_intervals

    iv = speech_intervals(audio, rate, min_speech=0.12)
    if not iv:
        return 0.0, 0.0
    n = len(audio)
    mask = np.zeros(n, dtype=bool)
    for a, b in iv:
        mask[int(a * rate):int(b * rate)] = True

    return band_db(audio[mask], rate), band_db(audio[~mask], rate)


# -------------------------------------------------------------------- checks
def add(rows: list[dict], name: str, status: str, detail: str) -> None:
    rows.append({"name": name, "status": status, "detail": detail})


def check_captions(rows: list[dict], cards: list[dict], rules: dict) -> None:
    conf = rules.get("captions", {})
    report = CR.card_report(cards)
    max_chars = int(conf.get("max_chars", CR.HARD_LINE_CHARS))
    target = int(conf.get("target_chars", CR.TARGET_LINE_CHARS))
    max_lines = int(conf.get("max_lines", CR.MAX_LINES))
    hard = [t for t, n in report["over_hard"] if n > max_chars]
    over = [t for t, n in report["over_target"] if n > target]
    share = len(over) / max(report["lines"], 1)
    # "~14 in most cases" is a shape, not a per-line ceiling: a couple of 15s
    # around a median of 10 is the rule working. A quarter of the lines over
    # budget is the rule failing, so that is where it warns.
    status = FAIL if hard or report["max_lines_per_card"] > max_lines else (
        WARN if share > 0.25 else PASS)
    add(rows, "caption_lines",
        status,
        f"{report['cards']} cards, {report['lines']} lines, median "
        f"{report['median_chars']} chars, max {report['max_chars']}"
        + (f" | over {target}: " + "; ".join(f"'{t}' ({len(t)})" for t in over) if over else "")
        + (f" | over {max_chars}: " + "; ".join(f"'{t}' ({len(t)})" for t in hard) if hard else ""))


def check_fillers(rows: list[dict], words: list[str], rules: dict) -> None:
    if not rules.get("captions", {}).get("forbid_fillers", True):
        add(rows, "fillers", WARN, "not enforced by this campaign")
        return
    found = CR.filler_words(words)
    add(rows, "fillers", FAIL if found else PASS,
        f"{len(found)} in the kept speech" + (": " + ", ".join(found) if found else ""))


def check_duration(rows: list[dict], duration: float, rules: dict) -> None:
    clip = rules.get("clip", {})
    lo = float(clip.get("hard_min_seconds", 0))
    hi = float(clip.get("hard_max_seconds", 1e9))
    plo = float(clip.get("preferred_min_seconds", lo))
    phi = float(clip.get("preferred_max_seconds", hi))
    if duration < lo or duration > hi:
        add(rows, "duration", FAIL, f"{duration:.1f}s outside the platform window {lo:.0f}-{hi:.0f}s")
    elif duration < plo or duration > phi:
        add(rows, "duration", WARN,
            f"{duration:.1f}s is outside the preferred {plo:.0f}-{phi:.0f}s band "
            f"(answer it in the pack)")
    else:
        add(rows, "duration", PASS, f"{duration:.1f}s inside {plo:.0f}-{phi:.0f}s")


def check_hook(rows: list[dict], words: list[dict], rules: dict) -> None:
    conf = rules.get("hook", {})
    within = float(conf.get("within_seconds", 2.0))
    banned = {w.lower() for w in conf.get("ban_first_words", [])}
    first = [w for w in words if float(w.get("at", 0)) <= within]
    if not first:
        add(rows, "hook", FAIL, f"no words in the first {within:.0f}s")
        return
    lead = CR.bare(str(first[0].get("w") or first[0].get("text") or ""))
    line = " ".join(str(w.get("w") or w.get("text")) for w in first)
    if lead in banned:
        add(rows, "hook", FAIL, f"opens on lead-in '{lead}' - first words: {line!r}")
    else:
        add(rows, "hook", PASS, f"first {within:.0f}s: {line!r}")


def check_hook_strength(rows: list[dict], words: list[dict], rules: dict) -> None:
    """How strong is the thing a viewer meets in the first two seconds.

    `check_hook` above only asks whether the opening is legible and not a
    lead-in. This asks whether it is worth stopping for: the rubric is
    calibrated on the campaign's own reference clips (defiance 8.0, number
    6.0, setup-first 0.6), and it is a warning on purpose - picking the moment
    is an editorial call, but a render that opens on "I'm trying to build"
    should say so out loud rather than quietly ship.
    """
    heard = [w for w in words if float(w.get("at", 0)) < HL.WINDOW]
    if not heard:
        add(rows, "hook_strength", WARN, "no words inside the hook window")
        return
    text = " ".join(str(w.get("w") or w.get("text")) for w in heard)
    score, why = HL.classify(text, [{"text": str(w.get("w") or w.get("text")),
                                     "start": float(w.get("at", 0)),
                                     "end": float(w.get("end", 0))} for w in heard])
    floor = float(rules.get("hook", {}).get("min_strength", 4.0))
    add(rows, "hook_strength", PASS if score >= floor else WARN,
        f"{score:.1f}/10 (floor {floor:.0f}) - {'; '.join(why) or 'nothing concrete'} "
        f"| {text!r}")


def check_audio(rows: list[dict], path: Path, audio: np.ndarray, rules: dict) -> None:
    conf = rules.get("audio", {})
    info = measure(path)
    lufs, dbtp = info.get("lufs"), info.get("dbtp")
    lo = float(conf.get("min_lufs", -23))
    hi = float(conf.get("max_lufs", -11))
    ceiling = float(conf.get("max_true_peak_dbtp", -1.3))
    if lufs is None:
        add(rows, "loudness", WARN, "could not measure")
    else:
        add(rows, "loudness", PASS if lo <= lufs <= hi else FAIL,
            f"{lufs:.1f} LUFS (window {lo:.0f}..{hi:.0f})")
    if dbtp is None:
        add(rows, "true_peak", WARN, "could not measure")
    else:
        add(rows, "true_peak", PASS if dbtp <= ceiling + 0.05 else FAIL,
            f"{dbtp:+.1f} dBTP (ceiling {ceiling:+.1f})")
    voice, bed = speech_gap_db(audio)
    need = float(conf.get("voice_over_bed_db", 12.0))
    gap = voice - bed
    if bed <= -119:
        add(rows, "voice_over_bed", PASS, "no non-speech stretch to measure")
    else:
        add(rows, "voice_over_bed", PASS if gap >= need else FAIL,
            f"voice sits {gap:.1f} dB over the bed (needs {need:.0f}; "
            f"speech {voice:.1f} dB, bed {bed:.1f} dB)")


def check_picture(rows: list[dict], path: Path, cards: list[dict], rules: dict,
                  manifest_endcard: float | None = None) -> None:
    conf = rules.get("picture", {})
    band = conf.get("caption_band", [1480, 1805])
    max_bar = int(conf.get("max_top_bar_rows", 12))

    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # 1. black bars - footage only. The end card and the vector plates are
    # designed to be near-black edge to edge; judging them as letterboxing
    # would fail every clip we have.
    endcard = float(manifest_endcard or 1e9)
    worst, worst_t = 0, 0.0
    for i in range(0, total, max(1, int(fps // 2))):
        if i / fps >= endcard:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if float(cv2.resize(gray, (108, 192)).std()) < 42.0:
            continue                        # vector plate, not footage
        dark = gray.mean(axis=1) < 14
        rows_dark, k = 0, 0
        while k < len(dark) and dark[k]:
            rows_dark += 1
            k += 1
        if rows_dark > worst:
            worst, worst_t = rows_dark, i / fps
    add(rows, "black_bars", PASS if worst <= max_bar else FAIL,
        f"worst top bar {worst} px at {worst_t:.1f}s (limit {max_bar})")

    # 2. a caption must not sit on a face
    model = ROOT / "assets" / "models" / "face_detection_yunet_2023mar.onnx"
    bad = []
    if model.exists() and cards:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = cap.read()
        if ok:
            h, w = frame.shape[:2]
            det = cv2.FaceDetectorYN.create(str(model), "", (w, h), 0.5, 0.3, 50)
            for card in cards:
                t = (float(card["show_from"]) + float(card["show_until"])) / 2
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                ok, frame = cap.read()
                if not ok:
                    continue
                _, faces = det.detect(frame)
                if faces is None:
                    continue
                for f in faces:
                    x, y, fw, fh = (float(v) for v in f[:4])
                    score = float(f[-1])
                    # A jaw and a jacket collar read as a face at ~0.54 while
                    # real faces here score 0.69+, and a caption is only over
                    # a face when a real share of the box sits in the band.
                    if score < 0.62:
                        continue
                    overlap = max(0.0, (y + fh) - band[0]) / max(fh, 1.0)
                    if overlap > 0.35 and fw > 90:
                        bad.append(round(t, 2))
                        break
    if model.exists():
        add(rows, "caption_face", PASS if not bad else FAIL,
            "no face behind a caption" if not bad else f"face under caption at {bad}")
    else:
        add(rows, "caption_face", WARN, "YuNet model missing")

    # 3. nothing frozen
    frozen_max = float(conf.get("max_frozen_seconds", 3.0))
    prev, longest, last_change = None, 0.0, 0.0
    for i in range(0, total, max(1, int(fps // 3))):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (96, 170)).astype(np.float32)
        t = i / fps
        if prev is not None and float(np.mean(np.abs(small - prev))) > 4.0:
            longest = max(longest, t - last_change)
            last_change = t
        prev = small
    longest = max(longest, total / fps - last_change)
    add(rows, "frozen", PASS if longest <= frozen_max else FAIL,
        f"longest unchanged stretch {longest:.1f}s (limit {frozen_max:.0f}s)")
    cap.release()


def check_ending(rows: list[dict], manifest: dict, duration: float, rules: dict) -> None:
    words = manifest.get("words_kept") or []
    last = max((float(w.get("end") or 0) for w in words), default=duration)
    tail = duration - last
    limit = float(rules.get("ending", {}).get("max_tail_seconds", 2.0))
    status = PASS if tail <= limit else WARN
    add(rows, "ending_tail", status,
        f"{tail:.2f}s after the last spoken word"
        + (" - cut closer to the peak, or record the CTA card as the reason"
           if tail > limit else ""))


# ---------------------------------------------------------------------- main
def gate(video: Path, manifest: dict, rules: dict) -> dict:
    rows: list[dict] = []
    duration = float(manifest.get("duration") or 0)
    cards = manifest.get("cards") or []
    words = manifest.get("words_kept") or []
    audio = decode16(video)
    if not duration:
        duration = len(audio) / 16000.0
    check_captions(rows, cards, rules)
    check_fillers(rows, [str(w.get("w") or w.get("text")) for w in words], rules)
    check_hook(rows, words, rules)
    check_hook_strength(rows, words, rules)
    check_duration(rows, duration, rules)
    check_audio(rows, video, audio, rules)
    check_picture(rows, video, cards, rules, manifest.get("endcard"))
    check_ending(rows, manifest, duration, rules)
    ok = all(r["status"] != FAIL for r in rows)
    return {"video": str(video), "ok": ok, "checks": rows}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("--manifest", required=True, help="cards/words JSON written by the render")
    ap.add_argument("--campaign", default="street_you_grew_up_on")
    ap.add_argument("--out", help="write the report here (default: <video>.qc.json)")
    ap.add_argument("--warn-only", action="store_true")
    args = ap.parse_args()

    video = Path(args.video)
    manifest = json.loads(Path(args.manifest).read_text())
    rules = json.loads((ROOT / "campaigns" / args.campaign / "campaign_rules.json").read_text())
    report = gate(video, manifest, rules)
    if args.warn_only:
        for row in report["checks"]:
            if row["status"] == FAIL:
                row["status"] = WARN
        report["ok"] = True

    mark = {PASS: "PASS", WARN: "WARN", FAIL: "FAIL"}
    print(f"\nCAMPAIGN GATE — {video.name} — {'PASS' if report['ok'] else 'FAIL'}")
    for row in report["checks"]:
        print(f"[{mark[row['status']]}] {row['name']}: {row['detail']}")
    out = Path(args.out) if args.out else video.with_suffix(".qc.json")
    out.write_text(json.dumps(report, indent=1) + "\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
