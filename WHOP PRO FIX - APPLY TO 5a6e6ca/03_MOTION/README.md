# 03 — MOTION GRAPHICS FIX

## Diagnosis — why motion still feels like template spam

You built an incredible motion library — `motion/MOTIONS.md` lists 30+ motions (people, bars, line, versus, stack, network, gauge, map, donut, cowfield, roadcar, dominoes, iceberg, bulb, flame, sprout, chess, anchor, balloon, redflag, ghost, wall, compass, plus 12 metaphor shelf scenes). Each with `mode: fullbleed|card`, `at/until`, brand-locked accent, QC validation.

**The system is too powerful for its own good.**

On a 28s Sartain clip, `motion/decide.py` + `assign.py` can fill every 2.5s gap with a new graphic:

```
0.45-3.30s counter (0.45s)
3.30-5.69s bars
5.69-8.42s line
8.42-12.17s versus
...etc
```

`MOTIONS.md` says: *"One idea per screen. Never same motion twice. Cadence: picture inserts ≥6s apart; full-bleed data scenes ≥2.4s apart, chain data scenes 2.4–2.5s start-to-start"*

That's **12 graphics in 30s** if followed literally — every sentence gets a chart. The viewer stops listening and starts watching slides.

**Your `whop` theme makes it worse:**
```json
"transitionOrder": ["flash", "flare", "leak", "bwflash"] // motion/themes/whop.json
```
`flash/flare/leak` are attention-grabbing light wipes. One is cinematic; four in 30s is a TikTok filter ad.

**Post1 needed 0 graphics for the "women match 10%" line** — it's an explanatory sentence, not a data proof. A clean caption at the bottom would let his face sell the claim. Instead the system (when fully triggered) would drop a `people` grid or `bars` there, adding clutter to an already broken caption.

**Speed cost:** Each motion is an SVG → `motion/stage.html` → Chromium headless → 30fps PNG frames → `motion/composite.py` ffmpeg overlay. That's 60-90s per clip even on a fast machine. For Sartain talking-head footage, 80% of that time is rendering graphics that shouldn't be there.

---

## The Pro Fix — less is pro

### Rule 1: Max 1 graphic per 8 seconds (not 2.4s)

In `motion/validate.py`, change:
```python
# BEFORE
FULLBLEED_MIN_GAP = 2.4
# AFTER (PRO)
FULLBLEED_MIN_GAP = 8.0
PICTURE_MIN_GAP = 8.0
DATA_SCENE_MIN_GAP = 8.0
```

And in `motion/decide.py`, after assigning, run a thinning pass:
```python
def thin_to_pro(timeline: list[dict], min_gap=8.0):
    kept = []
    for item in sorted(timeline, key=lambda x: x["at"]):
        if not kept or item["at"] - kept[-1]["at"] >= min_gap:
            kept.append(item)
        else:
            # keep only if this item is EMPHASISE for a number, else drop
            if item.get("job") == "EMPHASISE" and "counter" in item.get("name",""):
                # replace the previous weaker item
                if kept[-1].get("job") != "EMPHASISE":
                    kept[-1] = item
    return kept
```

**Result:** 28s clip → max 3 graphics, each earns attention.

### Rule 2: Data graphics only when transcript has a real number

`motion/assign.py` triggers `people` on speech "N men / people / users". But Sartain says "women match with about 10%" — that's a rate, not a countable crowd. `people` grid of 100 icons is wrong; `counter` with "10%" is right.

Gate every data motion on regex:
```python
DATA_TRIGGERS = {
    "people": r"\b(\d+)\s+(men|women|people|users)\b",
    "bars":   r"\b(\d+[,0-9]*)\b.*\b(\d+[,0-9]*)\b",  # two numbers in one sentence
    "counter": r"\b\d+\s*%|\b\d+\s*percent\b",
}
# Only assign if trigger regex matches the sentence at that timestamp
```

If no trigger → **no graphic**. Caption does the job.

### Rule 3: Kill flash/flare/leak for WHOP talking-head

Hard cuts are pro. Your `AUDIT.md` 1.15 says *"Any graphic >0.8s keeps moving (drift 100→103%, shine ~1.2s)"* — motion is already inside the graphic (drift/shine). You don't need transition FX on top.

New theme `sartain_pro.json`:
```json
"transitionOrder": ["cut"],
"cutTransitions": "hard",
"easing": "soft",
"speed": 1.0
```

Reserve `fade_black 0.25s` **only** for story beats: when timeline jumps between two different anecdotes (e.g., 121s → 142s in milk_budget). That's in `motion/decide.py` already — just gate it to `timeline`/`chapter` items, never to `counter`/`people`.

### Rule 4: Choose by sentence, not by variety (MOTIONS.md p. "Choose by sentence")

Your choosing table is brilliant — *"hear this, show that"* — but `decide.py` also enforces *"never same motion twice"* which forces variety even when one motion is correct. Drop the variety rule for WHOP:

```python
# BEFORE
if motion == last_motion: skip
# AFTER
if motion == last_motion and last_motion_job != "DATA": skip  # allow data to repeat if numbers demand
```

### Rule 5: Full-bleed only for data proof, card for everything else

`MOTIONS.md` says both exist. Default to `card` (panel over speaker's lower third, not covering face) for WHOP — it's talking-head, face must stay. `fullbleed` only for `people`/`bars`/`line` when number is the thumbnail hook (e.g., `68%`).

Implement in `motion/composite.py`: `card` mode uses `boxblur` pad behind plate (you already have blurpad), not transparent overlay over face.

---

## Patch files

- `pro_motion_rules.json` — the 5 rules as data, for `motion/validate.py` to import
- `decide.patch` — thinning + data gate
- `validate.patch` — gap enforcement
