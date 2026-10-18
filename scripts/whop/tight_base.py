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
  "splits": [2784.78],                  // camera cuts (keep both halves)
  "crops": [                            // first matching rule wins
    {"until": 2779.3, "crop": [790, 90, 480, 854], "push": 0.055},
    {"until": 2784.78,"crop": [1080, 90, 480, 854], "push": 0.04},
    {"until": 1e9,    "crop": [790, 90, 480, 854], "push": 0.055}
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
        # Drops are source-audio ranges. An ASR onset a few milliseconds
        # before the cut must not leak an orphan caption if virtually the
        # whole word was intentionally removed (e.g. "and." at 2777.62
        # inside a drop beginning 2777.63).
        dur = max(0.001, w["end"] - w["start"])
        return any(a <= w["start"] <= b or
                   max(0.0, min(b, w["end"]) - max(a, w["start"])) >
                   max(0.05, dur * 0.5) for a, b in drops)

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

    # Acoustic cuts can fall INSIDE an ASR word. Never silently omit one:
    # attach a word to the kept audio segment with the largest overlap.
    # If no segment contains audible material for it, fail rather than
    # inventing a caption over absent speech.
    # A word that falls ENTIRELY inside an acoustic silence was never
    # spoken - the ASR invented it. Drop it (it would otherwise be a
    # caption over absent speech).
    def inside_silence(w):
        return any(a - 0.005 <= w["start"] and w["end"] <= b + 0.005
                   for a, b in cuts)
    ghosts = [w for w in words
              if (lo - 0.02 <= (w["start"] + w["end"]) / 2 <= hi + 0.02)
              and not dropped(w) and inside_silence(w)]
    for w in ghosts:
        print(f"dropped unsung word {w['text']!r} at {w['start']:.2f}")
    words = [w for w in words if w not in ghosts]
    candidates = [w for w in words
                  if (lo - 0.02 <= (w["start"] + w["end"]) / 2 <= hi + 0.02)
                  and w["end"] > lo and w["start"] < hi and not dropped(w)]
    assigned = {id(w) for _ab, seg in pairs for w in seg}
    for w in candidates:
        if id(w) in assigned:
            continue
        overlaps = [max(0.0, min(b, w["end"]) - max(a, w["start"]))
                    for (a, b), _seg in pairs]
        best = max(range(len(pairs)), key=lambda j: overlaps[j])
        if overlaps[best] < 0.025:
            raise RuntimeError(f"orphan word with no source audio: {w['text']!r} "
                               f"at {w['start']:.2f}-{w['end']:.2f}")
        pairs[best][1].append(w)
        pairs[best][1].sort(key=lambda x: x["start"])
        print(f"rescued orphan {w['text']!r} into segment {best}")
    if sum(len(seg) for _ab, seg in pairs) != len(candidates):
        raise RuntimeError("source words lost or duplicated before rendering")

    # Visual shot cuts are NOT silence cuts. Split the picture/audio at
    # the camera edit, preserving *both* halves, even when the first
    # half has no ASR midpoint (a word can span the cut). Source audio
    # is continuous; word onsets are remapped exactly once below.
    expanded = []
    for (a, b), seg in pairs:
        cuts_here = [a] + [t for t in spec.get("splits", [])
                           if a + 0.04 < t < b - 0.04] + [b]
        cuts_here.sort()
        if len(cuts_here) == 2:
            expanded.append(((a, b), seg))
            continue
        for j, (sa, sb) in enumerate(zip(cuts_here, cuts_here[1:])):
            ws = [w for w in seg if sa <= (w["start"] + w["end"]) / 2
                  < sb + (0.001 if j == len(cuts_here) - 2 else 0)]
            expanded.append(((sa, sb), ws))
        # a word rescued into this pair (it fell in a gap) keeps its
        # place: the split divides the picture, never the words
        lost = [w for w in seg if not any(w in ws for _r, ws in expanded)]
        for w in lost:
            overlaps = [max(0.0, min(r[1], w["end"]) - max(r[0], w["start"]))
                        for r, _ws in expanded[-len(cuts_here) + 1:]]
            if overlaps:
                j = max(range(len(overlaps)), key=lambda k: overlaps[k])
                expanded[-(len(cuts_here) - 1) + j][1].append(w)
                expanded[-(len(cuts_here) - 1) + j][1].sort(
                    key=lambda x: x["start"])
    if sum(len(seg) for _ab, seg in expanded) != len(candidates):
        raise RuntimeError("a visual split lost a word")
    pairs = expanded

    # Map transcript words through the exact kept source ranges. A word may
    # straddle a removed silence or a visual split: the clip retains the
    # first audible piece before the gap and/or the last piece after it.
    # Mapping its raw onset through only the segment selected by midpoint
    # can place a caption before its word (or reverse word order).
    segment_offsets = []
    mapped_cursor = 0.0
    for (s, e), _seg in pairs:
        segment_offsets.append((s, e, mapped_cursor))
        mapped_cursor += e - s

    def map_word(w):
        pieces = []
        ws, we = float(w["start"]), float(w["end"])
        for s, e, out_at in segment_offsets:
            a, b = max(ws, s), min(we, e)
            if b > a:
                pieces.append((out_at + a - s, out_at + b - s))
        if not pieces:
            raise RuntimeError(f"word {w['text']!r} has no audible kept audio")
        return pieces[0][0], pieces[-1][1]

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
            word_start, word_end = map_word(w)
            slice_words.append({
                "text": w["text"],
                "start": round(word_start, 3),
                "end": round(word_end, 3)})
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
