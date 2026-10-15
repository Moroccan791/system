#!/usr/bin/env python3
"""Decision rules: transcript -> draft motion timeline.

    python motion/decide.py <transcript.json> <out.json> [--accent #9BE82E]

The renderer is deterministic; this is where the editorial grammar of
the format lives. Each utterance of speech is classified by the first
matching rule (the order is the priority):

  1. PROCESS   sequence markers (first/then/next/finally) or repeated
               "NN% category" allocations  -> step stack, steps light
               up as they are spoken
  2. LIST      two or more short comma phrases ("food, shelter and
               transportation", "needs, wants, and savings")
               -> accumulating plates, one per phrase as spoken; a
               money headline in front also earns a COUNTER
  3. COUNTER   a money / percent / count number that carries the
               sentence -> big counting number with a label
  4. CARD      a short strong claim (never / always / nobody / ...)
               -> full-screen text card
  5. POSTER    everything else -> word-stacked captions; the keyword
               pops in the accent, an emotional keyword goes neon
               (hot) or serif-italic (soft)

Concrete picturable nouns (TV, car, roof...) are reported as PiP /
B-roll candidates with their timestamps — media choice stays a human
call (client footage first; generated stills must be marked
illustrative), so they are never auto-inserted.

The output passes motion/validate.py; QC (word sync, pacing) still
runs after the render as usual.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

STOP = set("the a an and or but of to in on for with that this it is are was were be "
           "you your we i they he she them us our their my me him her so just like "
           "gonna want wants got get going go do does did have has had can cant "
           "that's it's im ive dont".split())
NEON_HOT = set("crazy insane secret stop never free rich broke fear hate fire "
               "obsessed impossible unstoppable dangerous wrong money million".split())
SERIF_SOFT = set("love remember story home family heart dream believe hope "
                 "feel feels feeling miss beautiful".split())
CONCRETE = set("tv television console basketball hoop car house roof phone "
               "laptop computer website couch poster posters lights sign dog "
               "watch shoes sneakers gaming camera book pool garden kitchen "
               "bedroom office store shop".split())
CLAIM_MARKERS = set("never always nobody everyone everybody nothing everything "
                    "stop truth cannot can't wont won't impossible nobody's "
                    "everyone's".split())
SEQ_MARKERS = {"first", "second", "third", "fourth", "then", "next", "finally", "step"}
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
             "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
             "forty": 40, "fifty": 50, "hundred": 100, "thousand": 1000,
             "million": 1000000}

NUM_RE = re.compile(r"^\$?([\d,]+(?:\.\d+)?)(%|k|m)?$")


def norm(tok: str) -> str:
    return re.sub(r"[^a-z0-9'$%]", "", tok.lower())


def parse_number(words, i):
    """(value, prefix, suffix, span, strong) if words[i] starts a number.

    strong = carries digits / $ / % / a scale word. A bare number-word
    ("one of those") is weak and never headlines a counter on its own.
    """
    # match on the raw token: norm() would glue "50-30-20" into "503020"
    raw = words[i]["text"].lower().strip(".,!?")
    tok = norm(words[i]["text"])
    m = NUM_RE.match(raw)
    if m and any(c.isdigit() for c in raw):
        value = float(m.group(1).replace(",", ""))
        unit = m.group(2) or ""
        if unit == "k":
            value, unit = value * 1000, ""
        if unit == "m":
            value, unit = value * 1000000, ""
        return value, ("$" if raw.startswith("$") else ""), \
            ("%" if raw.endswith("%") or unit == "%" else ""), 1, True
    if tok in NUM_WORDS:
        nxt = norm(words[i + 1]["text"]) if i + 1 < len(words) else ""
        if nxt in ("thousand", "million", "hundred"):
            return float(NUM_WORDS[tok] * NUM_WORDS[nxt]), "", "", 2, True
        if i > 0 and norm(words[i - 1]["text"]) in ("a", "an") and tok == "thousand":
            return 1000.0, "", "", 1, True
        return float(NUM_WORDS[tok]), "", "", 1, False
    if tok in ("thousand", "million") and i > 0 and norm(words[i - 1]["text"]) in ("a", "an"):
        return float(NUM_WORDS[tok]), "", "", 1, True
    return None


def utterances(words):
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        end_punct = re.search(r"[.?!]$", w["text"].strip())
        gap = (words[i + 1]["start"] - w.get("end", w["start"])) if i + 1 < len(words) else 9
        if end_punct or gap > 0.7:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [u for u in out if u]


def comma_phrases(u):
    """Split an utterance at commas: (intro_words, [(phrase_words)]) or None.

    Handles the spoken shapes: "the top three needs are food, shelter
    and transportation" (first item rides in the intro group) and
    trailing clauses ("..., and that's why...") which are NOT items.
    """
    groups, cur = [], []
    for w in u:
        cur.append(w)
        if w["text"].rstrip().endswith(","):
            groups.append(cur)
            cur = []
    loose_tail = bool(cur)          # trailing words after the last comma
    if cur:
        groups.append(cur)
    if len(groups) < 2:
        return None

    # the first item often rides in the intro group: "...needs are food,"
    first = groups[0]
    mark = next((i for i, w in enumerate(first)
                 if norm(w["text"]) in ("are", "is")), None)
    if mark is not None and mark < len(first) - 1:
        intro, first_phrase = first[:mark + 1], first[mark + 1:]
    elif len(first) <= 3 and len(groups) >= 3:
        intro, first_phrase = [], first   # "A TV, a console, and a ball"
    else:
        intro, first_phrase = first, []

    raw = ([first_phrase] if first_phrase else []) + groups[1:]
    phrases = []
    for gi, g in enumerate(raw):
        is_loose_tail = loose_tail and gi == len(raw) - 1
        toks = [norm(w["text"]) for w in g]
        if is_loose_tail and "and" not in toks:
            break                    # trailing speech, not a list item
        # "shelter and transportation" is two items
        parts, part = [], []
        for w in g:
            if norm(w["text"]) == "and" and part:
                parts.append(part)
                part = []
            else:
                part.append(w)
        if part:
            parts.append(part)
        stop = False
        for p in parts:
            clean = [w for w in p if norm(w["text"]) not in ("and", "")]
            if not clean:
                continue
            if len(clean) > 3:
                stop = True          # a new clause begins; list is over
                break
            phrases.append(clean)
        if stop:
            break
    if len(phrases) < 2:
        return None
    texts = [" ".join(norm(w["text"]) for w in g) for g in phrases]
    if max(texts.count(t) for t in texts) > len(texts) / 2:
        return None                  # "go, go, go" is a chant, not a list
    if len(intro) > 6 and not any(norm(w["text"]) in ("are", "is") for w in intro):
        return None
    return intro, phrases


def key_word(u):
    best, best_score = None, -1
    for w in u:
        t = norm(w["text"])
        if t in STOP or not t:
            continue
        score = len(t) + (3 if t in NEON_HOT or t in SERIF_SOFT else 0)
        if score > best_score:
            best, best_score = w, score
    return best


def poster_items(u, log):
    items, chunk = [], []
    def flush():
        if not chunk:
            return
        rows, row = [], []
        for w in chunk:
            row.append(w)
            if len(row) >= 4:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows = rows[:2] + ([[w for r in rows[2:] for w in r]] if len(rows) > 2 else [])
        kw = key_word(chunk)
        out_rows = []
        for r in rows:
            out = []
            for w in r:
                t = norm(w["text"])
                entry = {"w": w["text"], "at": round(w["start"], 3)}
                if w is kw:
                    if t in NEON_HOT:
                        entry.update({"w": w["text"].upper(), "kind": "neon"})
                    elif t in SERIF_SOFT:
                        entry.update({"w": w["text"], "kind": "serif"})
                    else:
                        entry.update({"w": w["text"].upper(), "kind": "key"})
                out.append(entry)
            out_rows.append(out)
        items.append({"type": "poster", "at": round(chunk[0]["start"], 3),
                      "until": round(chunk[-1]["start"] + 0.55, 3), "rows": out_rows})
        log.append(f"  poster  @{chunk[0]['start']:6.2f}  "
                   f"{' '.join(w['text'] for w in chunk)[:58]!r}")
        chunk.clear()
    for w in u:
        chunk.append(w)
        if len(chunk) >= 8 or w["text"].rstrip().endswith(","):
            flush()
    flush()
    return items


def counter_item(u, i, parsed, log):
    value, prefix, suffix, span = parsed[0], parsed[1], parsed[2], parsed[3]
    at = u[i]["start"]
    label_words = [norm(w["text"]) for w in u[i + span:i + span + 4]]
    label_words = [x for x in label_words
                   if x and x not in ("and", "we", "were", "was", "are", "is",
                                      "it", "that", "this", "of", "you", "a")]
    label = " ".join(label_words[:3]).upper() or "TOTAL"
    item = {"type": "counter", "at": round(at, 3), "value": value,
            "countDur": 0.8, "until": round(at + 1.9, 3), "label": label}
    if prefix:
        item["prefix"] = prefix
    if suffix:
        item["suffix"] = suffix
    if value != int(value):
        item["decimals"] = 1
    log.append(f"  counter @{at:6.2f}  {prefix}{value:g}{suffix} '{label}'")
    return item


def classify(u, log):
    text = " ".join(w["text"] for w in u)
    toks = [norm(w["text"]) for w in u]
    nums = [(i, p) for i in range(len(u)) if (p := parse_number(u, i))]

    # 1. PROCESS: sequence markers, or percent allocations
    seq = [i for i, t in enumerate(toks) if t in SEQ_MARKERS]
    pct_steps = []
    for i, w in enumerate(u):
        p = parse_number(u, i)
        if p and p[2] == "%":
            cat = [norm(x["text"]) for x in u[i + p[3]:i + p[3] + 2]]
            cat = [c for c in cat
                   if c and c not in ("of", "that", "on", "the", "a", "an",
                                      "and", "to", "in", "for")][:1]
            if cat:
                pct_steps.append((w, p, cat[0].upper()))
    phr = comma_phrases(u)
    if len(seq) >= 2 or len(pct_steps) >= 2:
        if pct_steps:
            steps = [{"text": name,
                      "sub": f"{p[1]}{p[0]:g}{p[2]}",
                      "at": round(w["start"], 3)} for w, p, name in pct_steps]
            title = "THE SPLIT"
        else:
            steps, cur = [], None
            for i, w in enumerate(u):
                if toks[i] in SEQ_MARKERS:
                    if cur:
                        steps.append(cur)
                    cur = {"text": "", "at": round(w["start"], 3), "_w": []}
                elif cur is not None:
                    cur["_w"].append(w["text"])
            if cur:
                steps.append(cur)
            for s in steps:
                s["text"] = " ".join(s.pop("_w"))[:24].upper() or "STEP"
            steps = [s for s in steps if s["text"] != "STEP"] or steps
            title = "THE PROCESS"
        if len(steps) >= 2:
            log.append(f"  process @{steps[0]['at']:6.2f}  {len(steps)} steps: "
                       f"{' / '.join(s['text'] for s in steps)}")
            return [{"type": "process", "at": steps[0]["at"], "title": title,
                     "steps": steps, "until": round(steps[-1]["at"] + 1.8, 3)}]

    # 2. LIST: comma phrases (a money headline first also gets a counter)
    if phr:
        intro, phrases = phr
        plates = [{"text": " ".join(x for x in
                                     (norm(w["text"]) for w in g)
                                     if x not in ("a", "an", "the")).upper(),
                   "at": round(g[0]["start"], 3)} for g in phrases]
        plates = [p for p in plates if p["text"]][:5]
        if len({p["text"] for p in plates}) < 2:
            plates = []   # "go, go, go" is a chant, not a list
        if plates:
            title = " ".join(norm(w["text"]) for w in intro
                             if norm(w["text"]) not in ("are", "is")).upper()[:28]
            items = []
            money = [(i, p) for i, p in nums
                     if p[4] and (p[1] == "$" or (p[0] >= 100 and not p[2]))]
            if money and money[0][0] < len(intro) + 1:
                items.append(counter_item(u, money[0][0], money[0][1], log))
            log.append(f"  list    @{plates[0]['at']:6.2f}  "
                       f"{' / '.join(p['text'] for p in plates)}")
            items.append({"type": "list", "at": plates[0]["at"],
                          "title": title or "THE LIST", "items": plates,
                          "until": round(plates[-1]["at"] + 1.6, 3)})
            return items

    # 3. COUNTER: a headline number carries the sentence
    strong = [(i, p) for i, p in nums if p[4]]
    if strong and len(u) <= 14:
        i, p = strong[0]
        items = []
        if i >= 3:
            items += poster_items(u[:i], log)
        items.append(counter_item(u, i, p, log))
        return items

    # 4. CARD: short strong claim
    if len(u) <= 9 and any(t in CLAIM_MARKERS for t in toks):
        half = (len(u) + 1) // 2
        kw = key_word(u)
        def line(ws):
            return [{"w": w["text"].upper() if w is kw else w["text"],
                     "at": round(w["start"], 3),
                     **({"kind": "key"} if w is kw else {})} for w in ws]
        log.append(f"  card    @{u[0]['start']:6.2f}  {text[:58]!r}")
        return [{"type": "card", "at": round(u[0]["start"], 3),
                 "until": round(u[-1]["start"] + 0.9, 3), "bg": "dark",
                 "lines": [line(u[:half]), line(u[half:])]}]

    # 5. POSTER
    return poster_items(u, log)


def flat_words(item):
    return [w for row in (item.get("rows") or item.get("lines") or []) for w in row]


def make_poster(words, until):
    rows, row = [], []
    for w in words:
        row.append(w)
        if len(row) >= 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return {"type": "poster", "at": words[0]["at"],
            "until": round(until, 3), "rows": rows}


def repair(items, duration):
    """Same-type neighbours may abut but never overlap (validator rule,
    and the engine's blur-swap hand-off is built for abutting stacks).
    An overlap is fixed by clamping until to the next start; if that
    would cut the previous stack's last word, merge and re-split at
    the widest word gap instead. Finally clamp everything to the
    timeline duration."""
    items.sort(key=lambda i: i["at"])
    out = []
    for it in items:
        # a repeated line ("we spent 50%... we spent 50%...") earns one
        # counter, not three; and a counter never starts inside the
        # previous counter's beat
        if it["type"] == "counter" and out and out[-1]["type"] == "counter" \
                and (out[-1].get("value") == it.get("value") and it["at"] - out[-1]["at"] < 6
                     or it["at"] < out[-1]["until"]):
            continue
        if out and it["type"] == out[-1]["type"] and it["at"] < out[-1]["until"]:
            prev = out[-1]
            if prev["type"] == "poster":
                pw, cw = flat_words(prev), flat_words(it)
                if it["at"] >= pw[-1]["at"] + 0.2:
                    prev["until"] = it["at"]
                    out.append(it)
                    continue
                words = pw + cw
                if len(words) <= 8:
                    out[-1] = make_poster(words, max(it["until"], words[-1]["at"] + 0.55))
                    continue
                lo, hi = max(4, len(words) - 8), min(8, len(words) - 4)
                k = max(range(lo, hi + 1),
                        key=lambda j: words[j]["at"] - words[j - 1]["at"])
                # abut if the gap allows, else the minimum dwell (the
                # <=0.2 s handoff the validator permits)
                first_until = max(words[k]["at"], round(words[k - 1]["at"] + 0.21, 3))
                out[-1] = make_poster(words[:k], first_until)
                out.append(make_poster(words[k:], it["until"]))
                continue
            floor = prev["at"]
            if prev["type"] == "counter":
                floor = prev["at"] + float(prev.get("countDur") or 0.9) + 0.35
            elif prev["type"] in ("list", "process"):
                subs = prev.get("items") or prev.get("steps") or []
                if subs:
                    floor = subs[-1]["at"] + 0.85
            prev["until"] = round(max(it["at"], floor), 3)
        out.append(it)
    for it in out:
        if it.get("until") and it["until"] > duration:
            floor = 0.0
            if it["type"] in ("poster", "card"):
                ws = flat_words(it)
                if ws:
                    floor = max(w["at"] for w in ws) + 0.21
            it["until"] = round(max(min(it["until"], duration), floor), 3)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("out")
    ap.add_argument("--accent", default="#9BE82E")
    ap.add_argument("--duration", type=float, default=0)
    args = ap.parse_args()

    data = json.loads(Path(args.transcript).read_text())
    words = [{"text": str(w.get("text") or w.get("word") or ""),
              "start": float(w["start"]),
              "end": float(w.get("end") or w["start"] + 0.3)}
             for w in data.get("words", [])]
    words = [w for w in words if w["text"].strip()]
    if not words:
        print("no words in transcript", file=sys.stderr)
        return 1

    # merge one/two-word fragments into the following utterance -
    # ASR punctuation is not sentence structure
    utts = []
    for u in utterances(words):
        if utts and len(u) <= 2 and u[0]["start"] - utts[-1][-1].get("end", 0) < 1.2:
            utts[-1] += u
        else:
            utts.append(list(u))

    items, log, suggestions = [], [], {}
    for u in utts:
        items += classify(u, log)
        for w in u:
            t = norm(w["text"])
            if t in CONCRETE and t not in suggestions:
                suggestions[t] = w["start"]
    duration = args.duration or round(words[-1]["end"] + 0.8, 3)
    items = repair(items, duration)
    # if the requested duration clips a poster's minimum dwell, the
    # timeline grows to fit the speech (a warning, not a silent cut)
    needed = max((max(w["at"] for w in flat_words(i)) + 0.21
                  for i in items if i["type"] in ("poster", "card")), default=0)
    if needed > duration:
        print(f"  ! duration {duration:.1f}s clips a word's dwell; "
              f"extended to {needed:.1f}s")
        duration = round(needed, 3)
    tl = {"version": 1, "fps": 30, "width": 1080, "height": 1920,
          "duration": duration, "brand": {"accent": args.accent}, "items": items}
    Path(args.out).write_text(json.dumps(tl, indent=2))

    # pacing sanity (the QC enforces 2.5 s; warn here so it is fixed at
    # authoring time, not after a render)
    events = sorted({i["at"] for i in items} |
                    {w["at"] for i in items for r in (i.get("rows") or i.get("lines") or [])
                     for w in r} |
                    {s["at"] for i in items for s in (i.get("items") or i.get("steps") or [])})
    print(f"decide: {len(items)} items -> {args.out}")
    for line in log:
        print(line)
    for a, b in zip(events, events[1:]):
        if b - a > 2.5:
            print(f"  ! pacing gap {b - a:.1f}s at {a:.1f}s - add a beat (chip/fx) or extend a hold")
    for noun, at in sorted(suggestions.items(), key=lambda kv: kv[1]):
        print(f"  ? PiP/B-roll candidate: '{noun}' @{at:.1f}s "
              f"(client media, or generated + illustrative)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
