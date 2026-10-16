#!/usr/bin/env python3
"""Author motion timelines for the 3 Sartain clips from sliced transcripts.

Speech -> poster items (2-4 words, one accent-plate keyword per row,
words lead speech by 2 frames), plus a hand-placed special per clip:
clip1 opening card (the question), clip2 counter (57), clip3 closing
card (the payoff). Words inside a special's window are not captioned
twice. Mirrors motion/timelines/sartain_stage_a.json conventions.

SLICE PROVENANCE (sync-critical, learned from a shipped desync):
word slices MUST be timed against the base edit's own audio -- either
transcribe the base edit itself, or remap source-transcript words
through the edit plan (plan shots: out = out_start + (t - shot.start)).
Never slice as source_time - window_start: if the edit's shots skip
source material, speech lands earlier than that map and every caption
lags. Slices here came from transcribing the rebuilt bases (tracked
candidates, plan-verified contiguous), plus a uniform -100ms onset
compensation (moonshine marks word onsets ~100ms late against the
audio; measured across all three clips).
"""
import json
import subprocess
from pathlib import Path

SYS = Path("/home/user/system")
LEAD = 0.0  # engine draws words 2f early itself (qc.py LEAD_MS)
ZONE = [0.60, 0.82]

STRONG = set("wait cops called viral truth successful fact know every single "
             "should obviously infectious viral need listen smarter ego "
             "successful connection casual everybody".split())


def probe_dur(p):
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run([ff, "-i", str(p)], capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if "Duration" in line:
            t = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = t.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise SystemExit(f"no duration for {p}")


def key_word(words):
    for w in words:
        if any(c.isdigit() for c in w["text"]):
            return w
    cands = [w for w in words if w["text"].strip(".,?!").lower() in STRONG]
    if cands:
        return max(cands, key=lambda w: len(w["text"]))
    alpha = [w for w in words if len(w["text"].strip(".,?!")) >= 5]
    return (alpha[-1] if alpha else words[-1])


def chunk_words(words):
    """Group into poster items. Break on time gaps (a special's window
    must never be spanned). Fast speech keeps absorbing into the same
    item (up to 8 words / 2.6s) -- 5-word items at machine-gun pace
    flip every ~1s and their 8f exits blur into the next stack."""
    items, cur = [], []
    for w in words:
        if cur and w["start"] - cur[-1]["end"] > 0.45:
            items.append(cur); cur = []
        cur.append(w)
        ends_sentence = w["text"].strip().endswith((".", "?", "!"))
        span = cur[-1]["end"] - cur[0]["start"]
        if ((ends_sentence and len(cur) >= 3 and span >= 1.2)
                or (len(cur) >= 5 and span >= 1.35)
                or len(cur) >= 8 or span > 2.6):
            items.append(cur); cur = []
    if cur:
        items.append(cur)
    return [c for c in items if c]


def poster(cur, zone=ZONE):
    n = len(cur)
    rows = []
    groups = [cur] if n <= 3 else [cur[: (n + 1) // 2], cur[(n + 1) // 2:]]
    for g in groups:
        kw = key_word(g)
        row = []
        for w in g:
            o = {"w": w["text"], "at": round(max(0.03, w["start"] - LEAD), 3)}
            if w is kw:
                o["kind"] = "key"
            row.append(o)
        rows.append(row)
    at = rows[0][0]["at"]
    return {"type": "poster", "at": at, "until": 0, "zone": zone, "rows": rows,
            "_last_end": cur[-1]["end"],
            "_last_at": round(max(0.03, cur[-1]["start"] - LEAD), 3)}


def build(words, duration, specials, zone=ZONE):
    """specials: list of item dicts with at/until; posters fill the gaps."""
    items = [{"type": "fx", "kind": "opening", "at": 0.0, "dur": 0.27}]
    covered = sorted((s["at"], s["until"]) for s in specials)
    free = [w for w in words
            if not any(a - 0.05 <= w["start"] < u for a, u in covered)]
    posters = [poster(c, zone) for c in chunk_words(free)]
    all_items = sorted(posters + specials, key=lambda i: i["at"])
    for i, it in enumerate(all_items):
        if it["type"] == "poster":
            nxt = all_items[i + 1]["at"] if i + 1 < len(all_items) else duration
            # validator: until >= last word + 0.2 beat, same-type overlap
            # <= 0.25s, dwell <= 3.0s
            until = it["_last_at"] + 0.30
            # the engine's 8f exit runs PAST until: end the item early
            # enough that the exit completes as the next item's first
            # word pops (nxt - 0.28) -- two stacks never co-dissolve
            until = min(until, nxt - 0.28, it["at"] + 2.95, round(duration, 2))
            until = max(until, it["_last_at"] + 0.21)
            it["until"] = round(until, 3)
            del it["_last_end"], it["_last_at"]
    items += all_items
    dur_out = round(duration, 2)
    max_until = max(i.get("until") or i["at"] for i in items)
    if max_until > dur_out:  # last word's exit beat outlives the base tail
        dur_out = round(max_until + 0.01, 2)
    return {"version": 1, "fps": 30, "width": 1080, "height": 1920,
            "duration": dur_out,
            "brand": {"accent": "#FF3355", "ink": "#0D0F12", "paper": "#FFFFFF"},
            "items": items}


def W(t, s):
    return {"w": t, "at": round(s, 3)}


def card_from(words_slice, key_texts):
    """Card lines = the spoken words themselves, one entry per word.
    Rows break on sentence ends AND wrap at 5 words (or after a comma
    with >=3 words in the row) -- a full long sentence on one row
    overflows the 1080 frame (caught visually on the payoff card)."""
    lines, cur = [], []
    for w in words_slice:
        o = {"w": w["text"], "at": round(max(0.0, w["start"] - LEAD), 3)}
        if w["text"].strip(".,?!").lower() in key_texts:
            o["kind"] = "key"
        # char guard: a 5-word row with a long plated keyword still
        # overflows (clip3 payoff card) -- wrap before exceeding ~30 ch
        if cur and sum(len(x["w"]) + 1 for x in cur) + len(w["text"]) > 30:
            lines.append(cur); cur = []
        cur.append(o)
        t = w["text"].strip()
        if t.endswith((".", "?", "!")) or len(cur) >= 5 or (t.endswith(",") and len(cur) >= 3):
            lines.append(cur); cur = []
    if cur:
        lines.append(cur)
    return lines


def main():
    jobs = []
    # clip1: card = the two-sentence question (or just sentence 1 if the
    # pair outlives the 3s card cap)
    s1 = json.load(open(SYS / "work/sartain_new/clip1_words.json"))
    w1 = s1["words"]
    waits = [i for i, w in enumerate(w1)
             if w["text"].strip(".,").lower() == "wait"]
    end_i = waits[1] if len(waits) > 1 else waits[0]
    q_words = w1[: end_i + 1]
    q_until = q_words[-1]["end"] + 0.25
    if q_until - q_words[0]["start"] > 2.95:
        end_i = waits[0]
        q_words = w1[: end_i + 1]
        q_until = q_words[-1]["end"] + 0.25
    card1 = {"type": "card", "at": round(max(0.0, q_words[0]["start"]), 3),
             "until": round(q_until, 3), "bg": "dark",
             "lines": card_from(q_words, {"wait"})}
    jobs.append(("clip1", "women-make-you-wait-beta_M1",
                 "work/sartain_new/clip1_words.json", [card1], [0.70, 0.86]))
    # clip2: counter on 57
    s2 = json.load(open(SYS / "work/sartain_new/clip2_words.json"))
    w57 = next(w for w in s2["words"] if "57" in w["text"])
    c_at = round(w57["start"] - 0.9, 3)
    counter = {"type": "counter", "at": c_at, "zone": [0.60, 0.82],
               "value": 57, "label": "MEN IN THE GROUP CHAT",
               "countDur": 0.9, "until": round(c_at + 2.7, 3)}
    jobs.append(("clip2", "cornell-7-story_M2",
                 "work/sartain_new/clip2_words.json", [counter], [0.68, 0.86]))
    # clip3: closing card on the payoff sentence
    s3 = json.load(open(SYS / "work/sartain_new/clip3_words.json"))
    i0 = next(i for i, w in enumerate(s3["words"])
              if w["text"].strip().lower() == "if")
    i1 = next(i for i, w in enumerate(s3["words"])
              if w["text"].strip(".,").lower() == "successful")
    p_words = s3["words"][i0: i1 + 1]
    card3 = {"type": "card",
             "at": round(max(0.0, p_words[0]["start"] - 0.02), 3),
             "until": round(p_words[-1]["end"] + 0.3, 3), "bg": "dark",
             "lines": card_from(p_words, {"viral", "successful"})}
    jobs.append(("clip3", "men-cant-accept-her-past_M3",
                 "work/sartain_new/clip3_words.json", [card3], [0.66, 0.86]))
    for name, stem, slice_path, specials, zone in jobs:
        sl = json.load(open(SYS / slice_path))
        base = SYS / f"work/michael_sartain/edits/{stem}.mp4"
        dur = probe_dur(base)
        tl = build(sl["words"], dur, specials, zone)
        out = SYS / f"work/sartain_new/{name}_timeline.json"
        out.write_text(json.dumps(tl, indent=1))
        kinds = {}
        for i in tl["items"]:
            kinds[i["type"]] = kinds.get(i["type"], 0) + 1
        print(name, "dur", tl["duration"], kinds, "->", out.name)


if __name__ == "__main__":
    main()
