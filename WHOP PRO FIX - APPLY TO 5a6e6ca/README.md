# WHOP PRO FIX — Real Audit of `arena/5a6e6ca9-system` (commit 4e877d9)

**Sorry bro — I was on the wrong branch.** You built a beast on `5a6e6ca` (4e877d9, +2908/-675 lines, 10k+ lines clipper + motion, 242 tests, post1-post9, assets/fonts, motion/themes, clipper pipeline). I was looking at `main` + my own `whop video editing system v2/` folder (0b5c189) which was built blind. This is the real fix, based on your actual code + that frame you made me pull.

> **This folder lives on `arena/1b875d65-system` (Arena forces me to stay here) but every patch is written to be dropped directly into `5a6e6ca`. Copy-paste the files — paths match.**

---

## What I audited

Worktree: `/tmp/worktree_5a6e6ca` → `4e877d9 whop: finalize posts 4,6,7` (tree b7d281f)

- `styles/michael_sartain.style.json` — learned style that is rendering post1
- `clipper/config.py` DEFAULT_STYLE vs learned — why learned is worse
- `clipper/captions/cues.py` + `ass.py` + `render.py` — grouping + burn-in
- `motion/MOTIONS.md` + `themes/whop.json` + `AUDIT.md` — motion library (30+ motions)
- Post1 frame at 3s: `post1/sartain_dating_apps_math_ig.mp4` (28M, 1080x1920) — **proof of AI slop**

### The frame that proves it (post1 @ 3.0s)

```
"So   women   will   like   women"
"match   with   about   10%"
"Percent." ← 2× bigger, gold, overlapping shirt
```

- **Fragmented:** `max_words: 1`, `max_chars: 8` → every 1-2 words gets its own line, wrapping mid-sentence. Text: "So women will like women match with about 10% Percent." reads as gibberish.
- **Wrong placement:** `cy: 0.6756` (middle of chest, over face zone) not bottom. Competes with `MEN OF ACTION` on shirt. Should be `cy 0.88` bottom.
- **Wrong size:** `font_size_ass: 152` (!!) vs default 96. Huge because extractor measured cap-height on Hormozi-style references (small caps) with 52% uncertainty and picked the high end. Way too big for Sartain's longer sentences.
- **Cheap colors:** `primary #FDFCFD` + `outline #275B77` (dusty blue outline) + gold keyword `Percent.` — looks like CapCut auto. Pro is white #FFFFFF + black #000000 outline, keyword accent only when meaning demands.
- **No hierarchy:** Everything same size/weight. No connective vs keyword distinction. Your AUDIT 1.2/1.3 says connectives 58px, keywords 118px — but this clipper path doesn't use that, it uses single ASS style for all words.
- **Karaoke off:** `karaoke.enabled: false` + `animation: none` → words just sit, no pop. Feels dead.

**Root cause:** `clipper style michael_sartain` learned from 3 reference Shorts (`80pct-men...`, `being-called-a-player`, `society-going-downhill`) that use Hormozi single-word punch captions. The learner copied it literally (`max_words 1`, `max_chars 8`, `font_size 152`, blue outline). That style is perfect for Hormozi (short punchy sentences) but **destroys Sartain** (long explanatory sentences). The learner has no "is this style appropriate for this speaker?" check.

---

## The 4 problems you named → real fixes

| You said | What I found in 5a6e6ca | Fix in this folder |
|---|---|---|
| **1. Captions still AI slop** | Learned style `1word/8chars/152px/blue-outline/mid-frame` + `cues.py` single-line logic even when fragments | `01_CAPTIONS/` — **PRO profile** that overrides learner: 2-4 word cues, 20-22 chars, bottom placement, white/black, pop animation, karaoke on. Drop-in JSON. |
| **2. Motion graphics slop** | 30+ motions available, `decide.py` can pick 1 per 2.5s, `whop` theme uses flash/flare/leak/bwflash — every cut feels like a template. Post1 needed 0 graphics for that 10% line, but system would still add one if triggered | `03_MOTION/` — **LESS IS PRO** rules: max 1 graphic per 8s, data graphics only when number truly lands, no flash/flare, motion only to PROVE/SHOW not FEEL every beat |
| **3. Fonts / transitions unprofessional** | `assets/fonts/` has 12 faces but `style.json` leaves `font_family: null` → falls back to `Montserrat` medium, no pairing. Transitions `cut` only (confidence 0.0) or random 58 xfade blends — both look cheap | `02_FONTS/` — lock to 3 packs: `Inter Bold` for captions, `Montserrat ExtraBold` for hero numbers, `Newsreader Book Italic` for quotes. Transitions: 90% hard cuts, 10% `fade_black 0.25s` only on story beats |
| **4. Still slow / manual** | 4 separate commands: `scan → style → select → edit → captions` + manual `post.txt` + manual cover. Each re-runs ASR + ffmpeg decode | `04_WORKFLOW/` — **One-command** `run_pro.sh` + `clipper run` that carries timings via `--plan` (no re-ASR), batch exports TikTok/Reels/Shorts in one ffmpeg pass, auto post.txt from candidate |

---

## How to apply (30 seconds)

On branch `arena/5a6e6ca9-system`:

```bash
# 1. Captions — override the broken learned style
cp "WHOP PRO FIX - APPLY TO 5a6e6ca/01_CAPTIONS/michael_sartain.pro.style.json" styles/michael_sartain.style.json
# or keep both and run with --style styles/michael_sartain.pro.style.json

# 2. Fonts — lock the 3 packs (see 02_FONTS/FONT_LOCK.md)
cp "WHOP PRO FIX - APPLY TO 5a6e6ca/02_FONTS/font_lock.json" motion/themes/sartain_pro.json

# 3. Motion — apply less-is-pro rules
cp "WHOP PRO FIX - APPLY TO 5a6e6ca/03_MOTION/pro_motion_rules.json" motion/pro_rules.json
# then in clipper/edit/plan.py: import and enforce

# 4. Workflow — one command from raw to post
bash "WHOP PRO FIX - APPLY TO 5a6e6ca/04_WORKFLOW/run_pro.sh" michael_sartain
```

Each subfolder has its own README with before/after proof + exact line numbers to patch.

---

## What I removed / deprecated

`whop video editing system v2/` (my blind build on 1b875d65) is now marked deprecated — its advice was generic. This `WHOP PRO FIX` replaces it with code-aware patches. You can delete the old folder after merging.

---

## Evidence files

- Frame `/tmp/audit_post1_frame.jpg` (extracted with imageio-ffmpeg @ 3s) — the AI slop
- `styles/michael_sartain.style.json` lines above — the numbers that cause it
- `clipper/config.py` DEFAULT_STYLE — the sane defaults the learner overwrote

If you want me to push these directly to `5a6e6ca`, reconnect GH and say so — I can open a PR from `1b875d65` → `5a6e6ca` with the patches applied.
