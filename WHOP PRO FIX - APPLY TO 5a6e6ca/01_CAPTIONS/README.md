# 01 — CAPTIONS FIX (the #1 AI-slop)

## Diagnosis — why post1 looks like CapCut auto

Your learner (`python -m clipper style michael_sartain`) did exactly what it was told: measure 3 reference Shorts (Hormozi-style) and copy them.

**What it measured:**
```json
{
  "font_size_ass": 152,          // vs default 96 — 58% bigger
  "primary_color": "#FDFCFD",    // vs #FFFFFF — off-white
  "outline_color": "#275B77",    // vs #000000 — blue outline = cheap
  "outline_width": 7,
  "karaoke": { "enabled": false },
  "animation": { "in": "none" },
  "position": { "cx": 0.5062, "cy": 0.6756 }, // mid-chest, over shirt text
  "max_words_per_cue": 1,         // vs default 4 — ONE WORD
  "max_chars_per_line": 8,        // vs 22 — 8 chars!
  "max_lines": 1
}
```

**What that does to Sartain's sentence** `"So women will like women match with about 10 percent"` (12 words, ~44 chars):

- `max_words 1` → 12 separate cues, each 1 word (or 2 if merged as orphan)
- `max_chars 8` → "women" (5) + "will" (4) = 9 > 8 → line break mid-thought
- Result: frame shows `So women will like women | match with about 10% | Percent.` — 3 lines mashed mid-frame, "Percent." blown up gold as keyword, overlapping `MEN OF ACTION` on shirt
- `font_size 152` + `cy 0.675` → covers face/body, not bottom safe zone
- `animation none` + `karaoke false` → words appear static, no pop, feels dead vs Hormozi which had scale_pop 1.06

**The default in `clipper/config.py` was actually better:**
```python
"font_size_ass": 96, "primary_color": "#FFFFFF", "outline_color": "#000000",
"outline_width": 5, "karaoke": {"enabled": True, "highlight_color": "#FFE14D"},
"position": {"cy": 0.80}, "max_words_per_cue": 4, "max_chars_per_line": 22
```

**Root cause:** `clipper/style/captions_detect.py` measures `max_words` by counting text blobs per cue (`C0h` style) — Hormozi uses 1 word per flash, so it learns 1. It then writes that into the profile, which `clipper/captions/cues.py: group_words(max_words=1, max_chars=8)` obeys literally. No validation that `1 word × 152px` is insane for a 12-word explanatory sentence.

---

## The Pro Fix — what to change

### 1. Override the learned profile (immediate)

Drop `michael_sartain.pro.style.json` (next to this README) into `styles/` and use it:

```bash
python -m clipper captions campaigns/michael_sartain/raw/YTDown...mp4 \
  --style styles/michael_sartain.pro.style.json --platform tiktok --fit cover
```

**What changes (and why):**

| Field | Learned (bad) | Pro (fix) | Why |
|---|---|---|---|
| `font_family` | null → Montserrat fallback medium | **Montserrat-ExtraBold** (ships in assets/fonts/Montserrat-ExtraBold.ttf) | Bold enough to read at 96px on 1080x1920, not thin medium |
| `font_size_ass` | 152 | **96** (cap_height_ratio 0.045) | 96 = 4.5% of 1920 = ~86px cap height = readable bottom caption, not billboard |
| `primary_color` | #FDFCFD | **#FFFFFF** | Pure white, not off-white |
| `outline_color` | #275B77 (blue) | **#000000** | Black outline = universal contrast, not brand tint |
| `outline_width` | 7 | **6** | 5-6 = crisp, 7 = bloated on 96px |
| `shadow` | 0 | **1** (soft) | Lift off busy background (plants) without glow |
| `position.cy` | 0.6756 (mid) | **0.86** | Bottom 14% safe zone, clear of shirt text + TikTok UI (see C7) |
| `karaoke.enabled` | false | **true, #FFE14D** | Yellow highlight sweeps as words spoken = alive, not static |
| `animation.in` | none | **pop, 0.12s, scale 0.82→1.0** | Pop on each cue = modern pro (Hormozi spec, but applied per cue not per word) |
| `max_words_per_cue` | 1 | **3** | 3 words = "So women will" / "like women match" = reads as phrase, not word salad |
| `max_chars_per_line` | 8 | **22** | 22 = ~50% of 1080px at 96px = fits one phrase per line |
| `max_lines` | 1 | **1** | Still 1 line — 2 lines only for deliberate emphasis, not wrapping |
| `casing` | upper | **upper** (keep) | Upper is correct for WHOP — keep |

**Result for same sentence with Pro profile:**
```
Cue 1 (0.0-1.2s): "SO WOMEN WILL"      — bottom, white/black, pop in
Cue 2 (1.2-2.4s): "LIKE WOMEN MATCH"   — same
Cue 3 (2.4-3.6s): "WITH ABOUT 10%"     — "10%" in accent #14E5C5 (number highlight)
```
ONE line, bottom, readable, not overlapping shirt. `Percent.` gone — merged into `10%` cue.

### 2. Fix the grouping logic (code patch)

`clipper/captions/cues.py:group_words()` already has `orphan` absorption, but with `max_words 1` it can't help. Add a floor:

```python
# In clipper/captions/cues.py, top of group_words():
max_words = max(3, max_words)  # never allow 1-word AI slop
max_chars = max(18, max_chars)  # never allow <18 char wrapping
```

And in `clipper/style/captions_detect.py`, after measurement:
```python
# Clamp learned values to sane range before writing profile:
if captions["max_words_per_cue"] < 3:
    captions["max_words_per_cue"] = 3
    captions["notes"] = "clamped from 1 to 3 — 1-word style not appropriate for explanatory content"
if captions["max_chars_per_line"] < 18:
    captions["max_chars_per_line"] = 22
```

### 3. Fix the size learner

`clipper/style/captions_detect.py` computes `font_size_ass` from `cap_height_ratio * 1920`. Your 3 references had ratio 0.0368 → 152px, but they were 720p crops upscaled. Add:

```python
# After cap_height_ratio measurement:
if font_size_ass > 110:
    font_size_ass = 96
    font_size_uncertainty = 0.52  # keep, but note clamp
```

### 4. Preserve the fix across re-learns

Your `styles/` is git-tracked. Commit the `.pro.style.json` and in `clipper/config.py:resolve_style()` add:

```python
# Prefer .pro.style.json if exists, else learned:
pro_path = STYLES / f"{name}.pro.style.json"
if pro_path.exists():
    candidate = pro_path
```

---

## Patch files in this folder

- `michael_sartain.pro.style.json` — drop-in replacement (copy of your learned JSON with the 10 fields above corrected)
- `captions_detect.patch` — diff for the clamping logic
- `cues.patch` — floor enforcement

Apply with `git apply` or copy-paste the snippets above.
