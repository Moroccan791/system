#!/usr/bin/env python3
"""Tight-cut vertical base builder (Whop editor, brain rule #1/#3).

Takes a horizontal source + word-level transcript and produces a vertical
1080x1920 base where every pause longer than --max-gap is CUT (jump cuts on
word boundaries), filler ranges listed in the spec are dropped, each kept
segment is reframed with its spec crop and given a gentle push-in.

Also writes the remapped transcript (slice) whose word times match the base,
which is what produce.py/QC consume.

Spec JSON:
{
  "source": "path/to/episode.mp4",
  "words": "path/to/transcript.json",   // clipper format {"words":[...]}
  "offset": 2752.0,                     // transcript t=0 in source seconds
  "span": [2759.6, 2790.4],             // keep words inside (source seconds)
  "drops": [[2769.2, 2770.05]],         // source-second ranges to delete
  "crops": [                            // first matching rule wins
    {"until": 2779.3, "crop": [790, 0, 480, 1080], "push": 0.055},
    {"until": 2784.6, "crop": [650, 0, 608, 1080], "push": 0.03},
    {"until": 1e9,    "crop": [790, 0, 480, 1080], "push": 0.055}
  ],
  "out_base": "base.mp4",
  "out_slice": "slice.json"
}
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from clipper.ffmpeg import ffmpeg_exe  # noqa: E402

MAX_GAP = 0.15   # brain: no pause > ~0.25s survives (incl. decay tails)
PAD_L, PAD_R = 0.04, 0.03


def main(spec_path: str) -> int:
    spec = json.loads(Path(spec_path).read_text())
    off = float(spec.get("offset", 0.0))
    words = json.loads(Path(spec["words"]).read_text())["words"]
    words = [{"text": w["text"], "start": w["start"] + off,
              "end": w["end"] + off} for w in words]
    lo, hi = spec["span"]
    drops = spec.get("drops", [])

    def dropped(w):
        return any(a <= w["start"] <= b for a, b in drops)

    # Cut on ACOUSTICS, not ASR timestamps: find true silences in the source
    # span and delete every one longer than MAX_GAP (keeping a few frames of
    # each edge so word attacks/tails are not clipped).
    ff0 = ffmpeg_exe()
    probe = subprocess.run(
        [ff0, "-ss", f"{lo - 1:.2f}", "-t", f"{hi - lo + 2:.2f}", "-i",
         spec["source"], "-vn", "-af",
         "silencedetect=noise=-35dB:d=0.08", "-f", "null", "-"],
        capture_output=True, text=True)
    sils: list[tuple[float, float]] = []
    cur = None
    for line in probe.stderr.splitlines():
        if "silence_start:" in line:
            cur = float(line.split("silence_start:")[1].strip()) + lo - 1
        elif "silence_end:" in line and cur is not None:
            end = float(line.split("silence_end:")[1].split("|")[0].strip()) + lo - 1
            sils.append((cur, end)); cur = None
    cuts = [(a + 0.03, b - 0.02) for a, b in sils if b - a > 0.12]
    cuts += [(a, b) for a, b in drops]
    ranges: list[tuple[float, float]] = [(lo, hi)]
    for a, b in sorted(cuts):
        nxt = []
        for s0, e0 in ranges:
            if b <= s0 or a >= e0:
                nxt.append((s0, e0)); continue
            if a > s0: nxt.append((s0, a))
            if b < e0: nxt.append((b, e0))
        ranges = nxt
    ranges = [(a, b) for a, b in ranges if b - a > 0.09]
    print(f"acoustic cuts: {len(cuts)} -> {len(ranges)} ranges")

    pairs: list[tuple[tuple[float, float], list[dict]]] = []
    for a, b in ranges:
        seg = [w for w in words
               if a - 0.02 <= (w["start"] + w["end"]) / 2 <= b + 0.02
               and not dropped(w)]
        if seg:
            pairs.append(((a, b), seg))
    if not pairs:
        print("no words in span"); return 1

    def crop_for(mid: float):
        for rule in spec["crops"]:
            if mid <= rule["until"]:
                return (rule["crop"], float(rule.get("push", 0.05)),
                        float(rule.get("anchor", 0.30)))
        r = spec["crops"][-1]
        return (r["crop"], float(r.get("push", 0.05)),
                float(r.get("anchor", 0.30)))

    ff = ffmpeg_exe()
    fc: list[str] = []
    labels: list[str] = []
    slice_words: list[dict] = []
    cursor = 0.0
    for i, ((s, e), seg) in enumerate(pairs):
        dur = e - s
        frames = max(1, round(dur * 30))
        (cx, cy, cw, ch), push, anchor = crop_for((s + e) / 2)
        # Push-in via animated crop on an oversize canvas (frame-exact;
        # zoompan is banned here: it resamples to 25fps internally,
        # drops frames and poisons concat sync - measured 2026-10-17)
        sw = int(1080 * (1 + push)) // 2 * 2
        sh = int(1920 * (1 + push)) // 2 * 2
        fn = max(frames - 1, 1)
        fc.append(
            f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS,"
            f"fps=30,crop={cw}:{ch}:{cx}:{cy},"
            f"scale={sw}:{sh}:flags=lanczos,"
            f"crop=w='{sw}-{sw - 1080}*n/{fn}':h='{sh}-{sh - 1920}*n/{fn}':"
            f"x='(in_w-out_w)/2':y='(in_h-out_h)*{anchor}',"
            f"scale=1080:1920,trim=end_frame={frames},"
            f"setsar=1[v{i}]")
        fc.append(
            f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels += [f"[v{i}]", f"[a{i}]"]
        for w in seg:
            slice_words.append({
                "text": w["text"],
                "start": round(cursor + (w["start"] - s), 3),
                "end": round(cursor + (w["end"] - s), 3)})
        cursor += dur  # audio-exact clock
        print(f"seg {i}: src {s:.2f}-{e:.2f} ({dur:.2f}s) "
              f"crop {cw}x{ch}@{cx} words {len(seg)}")
    tail = float(spec.get("tail_seconds", 0.0))
    if tail > 0:
        i = len(pairs)
        ft = max(1, round(tail * 30))
        (cx, cy, cw, ch), _, _ = crop_for(hi)
        fc.append(
            f"[0:v]trim=start={hi - 0.06:.3f}:end={hi - 0.02:.3f},"
            f"setpts=PTS-STARTPTS,fps=30,crop={cw}:{ch}:{cx}:{cy},"
            f"scale=1080:1920:flags=lanczos,"
            f"tpad=stop_mode=clone:stop_duration={tail:.3f},"
            f"trim=end_frame={ft},"
            f"setsar=1[v{i}]")
        fc.append(
            f"anullsrc=r=44100:cl=stereo,atrim=0:{tail:.3f},"
            f"asetpts=PTS-STARTPTS[a{i}]")
        labels += [f"[v{i}]", f"[a{i}]"]
        cursor += tail
    total = cursor
    fc.append("".join(labels) + f"concat=n={len(labels) // 2}:v=1:a=1[v][a]")
    out = Path(spec["out_base"])
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ff, "-y", "-v", "error", "-i", spec["source"],
           "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-crf", "16", "-preset", "veryfast",
           "-c:a", "aac", "-b:a", "192k", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-3000:]); return 1
    Path(spec["out_slice"]).write_text(json.dumps(
        {"text": " ".join(w["text"] for w in slice_words),
         "words": slice_words}, indent=1))
    print(f"base {out} duration {total:.2f}s, {len(slice_words)} words, "
          f"{len(pairs)} segments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
