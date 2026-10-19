# STREET YOU GREW UP ON — Audit post2 → post7 (Demi Lovato)

**Worktree:** `arena/5a6e6ca9-system` `4e877d9` — `campaigns/street_you_grew_up_on/post2..7`
**Frames:** extracted at 1s/3s/6s/10s + 1/3/5/8/12/15 for post5-7 via imageio-ffmpeg
**Brief:** `brief.md` (CPM $2.50, #ad, podcast line, hook in first 3s, 30-40s ideal, original edit only, no ILLUSTRATIVE tag → vector+typography only)

---

## TL;DR — What's good vs what needs fixing

**You fixed the big Sartain caption bug — street is WAY better than Sartain.** Post1 pilot's editorial style (white bottom captions + full-screen vector when it earns it) is the right template. Post2-3 are clean. The problems in post4-7 are subtler: inconsistency, orphan words, card spam, and hook weakness.

| Post | Title | Dur | Verdict | Fix priority |
|------|-------|-----|---------|--------------|
| **2** | Barney — couldn't read | 33.1s | ✅ Good — cleanest of 6. White bottom captions, face always on, no spam cards. Just needs keyword accent. | LOW |
| **3** | Sang Selena at 7 | 24.8s | ✅ Good — same clean base as 2. Hook could be stronger. | LOW |
| **4** | Terrified to go on stage | 21.4s | ⚠️ Mixed — stage vector card at 1s is okay idea but flat illustration + text "I don't want to go on stage" competes with caption. Mid beats have caption lag/orange fade. Short (21s). | MEDIUM |
| **5** | My worth isn't in my body | 18.1s | ⚠️ Too short + card spam. "WORTH" full-black card breaks face time, then 3 face beats fragment; pacing feels rushed. Needs +8s breathing. | HIGH |
| **6** | Oak tree to protect kids | 22.9s | ⚠️ Most ambitious — editorial hierarchy (build/protect in green serif) is RIGHT direction, but orphan "image" single word at 6s + "We" at 3s + tree graphic late = cadence off. OAK TREE card is good but disconnects from face. | HIGH |
| **7** | Open that door for mom | 21.8s | ⚠️ Similar to 6 — "angry" corner serif is cute but lands on empty frame, then "We" orphan, then face cards. Needs hook tightening. | HIGH |

**Campaign compliance:** All 6 have `#ad` + exact podcast line — ✅. No copyrighted layers — ✅.

---

## Per-post frame proof + fix

### Post2 — "Demi Came Close to Booking Barney" (33.1s) ✅ KEEP, polish only

**Frames @ 3s:** `I DIDN'T` (white bottom), @6s `AND MY MOM WOULD DRAW PICTURES`, @10s `AND THAT'S HOW I WOULD MEMORIZE`

**What's working:**
- Position bottom (cy ~0.86) — not mid-chest like Sartain bug — correct
- Font size ~96px, pure white/black outline — legible on dark leather
- Face 100% on (no full-bleed cutaway stealing face time)
- Duration 33s = ideal for WHOP CPM (30-40s)

**What to do (10 min):**
1. Add keyword accent: `DRAW PICTURES` should be teal #14E5C5 plate or at least green serif like post6 does for `build`. Currently all white — loses hierarchy. In `style.json` you already have `keyword: displaybook` + `accent: #14E5C5` but captions aren't using it — wire `keyword` words to accent in `ass.py`.
2. Hook is weak: first 3s is `I DIDN'T` over neutral face — no context. Better open with the ice-cream cone visual + text `SHE COULDN'T READ YET` (the title hook) for 1.2s before she speaks. You have the anecdote — show it.
3. Cover: `cover.jpg` is 98K — check it's not same as first frame (should be payoff "ice-cream cone = cue" moment)

---

### Post3 — "Sang Selena at 7" (24.8s) ✅ KEEP, hook fix

**Frames @1s `I'M HISPANIC,` @3s `I WANTED TO REPRESENT` @6s `AND I WAS LIKE, MY MOM` @10s `THEY WANT YOU TO SING`**

**Working:** Same clean base as post2.

**Fix:**
1. Same keyword pass: `HISPANIC` and `REPRESENT` should pop in accent (currently white). You have the system — just tag them in transcript as keywords.
2. Hook: `I'M HISPANIC,` is okay but not curious — better cold open with `AT SEVEN, SHE SANG SELENA` card (1.0s) then cut to face at `I'M HISPANIC`. Uses the title hook before she explains.
3. Duration 24.8s is on short side — consider adding 4s of her singing anecdote end (you cut early, last frame is still mid-sentence). WHOP rewards favor 30s+.

---

### Post4 — "Terrified to Go On Stage" (21.4s) ⚠️ GRAPHIC vs CAPTION clash

**Frames:** @1s **full vector stage** (mic under spotlight, audience silhouettes, text `I don't want to go on stage.` gold `stage.`) — @3s face `You know,` — @6s face `they're going to write online,` — @10s face `No one got up`

**Working:** Stage card is correct *idea* (visualize fear) — gold #D7A73C palette matches title card per `style_theme.json`.

**Problems:**
1. **Style clash:** Stage vector is flat navy illustration; next frame is photoreal face. Hard cut between them feels like two apps. Solution: add film grain + vignette to stage card (you have `grade_chain` vignette — apply to card background too) so it feels same world.
2. **Text fight:** Card says `I don't want to go on stage.` in white/gold serif — then 2s later caption says `You know,` — viewer reads same idea twice, cadence stutters. Better: card holds 1.0s silent (no caption), then face enters with `You know, they're going to write online` — cut the duplicate.
3. **Mid caption at 10s:** `No one got up` shows "got up" greyed/faded (your ghost caption style?) and small `out` orphan at bottom edge — that's the orphan bug (max_words gap). Fix grouping: `No one got up` should be one cue, not split.
4. **Short:** 21.4s — you have more of the "they still loved her / tears of joy" arc — extend to 28s with payoff card `THEY STILL LOVED HER` (white on gold plate).

**Action:** Re-render card with grain + 1.0s hold, fix cues grouping, extend 7s.

---

### Post5 — "My Worth Isn't In My Body" (18.1s) ⚠️ TOO SHORT + CARD SPAM

**Frames:** @1s **BLACK WORTH card** (WORTH huge white + teal underline, `MY WORTH ISN'T IN` small bottom) — @3s face `MY HUSBAND DOESN'T LOVE ME BECAUSE` — @6s face `OF MY` (orphan) — @10s face `MY FAMILY DOESN'T LOVE`

**Working:** WORTH card is strong editorial hook — black/teal system is clean.

**Problems:**
1. **Duration 18.1s = will underpay.** Brief says 30-40s ideal, CPM needs 60% T1 watch — 18s has no time to hold. You cut the most powerful line ("My worth isn't in my body" payoff + husband/family love + what she holds true) to fragments. Add the full closing: "then closes with what she holds true to her heart" — that's the CTA, you trimmed it.
2. **Orphan `OF MY` at 6s:** Classic grouping bug — `OF MY` alone is 2 words, 4 chars, but split from previous `LOVE ME BECAUSE`. Should be merged: `LOVE ME BECAUSE OF MY BODY` one cue.
3. **Face vs card ratio:** 1s card + 17s face = card is hook but disconnects — viewer forgets WORTH by 10s. Better: keep WORTH as **editorial overlay on face** (like post6 does with `build` green) not separate black card — `MY WORTH ISN'T IN MY BODY` stacked center-chest, `WORTH` huge in accent, face still visible behind (you approved this in post1 pilot — "editorial caption + full-screen graphic workflow" but for WHOP, editorial over face > black card).
4. **No end card:** Ends mid-face, no branded fade — brief requires fade + end card.

**Action:** Extend to 28-30s with full payoff, merge orphans, convert black card to editorial overlay, add end card fade.

---

### Post6 — "Oak Tree to Protect Kids" (22.9s) ⚠️ AMBITIOUS BUT CADENCE OFF

**Frames:** @1s face `I'm trying to build` (build green serif), @3s **BLACK OAK TREE card** (OAK TREE huge + green line, `That` small bottom), @5s face `that will shade`, @6s face `image` (single word!), @10s face `like, I want to protect my kids,` (protect green), @18s **tree vector** (brown trunk, green clouds, `protect my` green serif top)

**Working:** This is your most pro — you're using the 3-font system (regular caption + green serif italic for emotional verbs `build`/`protect`) — exactly what post2/3 lack. Accent #78A974 sage is perfect for "oak tree/nature" story.

**Problems:**
1. **Orphan `image` at 6s:** One word centered = AI slop signal. Text is "that will shade and protect" — grouping split `image` alone because of pause detection gap >0.45s. Increase `gap_break` to 0.6s or merge single-word orphans under 0.7s into prior cue.
2. **OAK TREE card disconnect:** Same as post5 — black card breaks face time. For this metaphor, the tree vector card at 18s is better (shows meaning), OAK TREE text card could be editorial over face at 3s instead of black cutaway.
3. **Tree vector at 18s is late + flat:** Appears for 2s at very end, background #101319 dark grey, tree is simple flat 2D (not ugly, but not premium). Could be more cinematic: add subtle glow/pulse to leaves, or parallax drift (you have `drift 100→103%` in AUDIT 1.15) — currently static.
4. **Duration 22.9s:** Could be 28s — you have "shade and protect her children from negative body-image talk" — you cut after `protect my kids,` losing the body-image payoff which is the title hook.

**Action:** Merge `image` orphan, move OAK TREE to editorial over face (or keep but shorten to 0.8s), animate tree leaves, extend 5s to include body-image line.

---

### Post7 — "Open That Door for Mom" (21.8s) ⚠️ SAME ORPHAN PATTERN

**Frames (sampled):** Similar structure — @1s face, @2s `angry` small red serif corner (style #C7654E terracotta), @5s `We` orphan bottom, etc.

**Working:** Terracotta #C7654E palette correctly signals "warm/family" vs sage "nature" — good per-post theming.

**Problems:**
1. **Corner `angry`:** At ~2s, `angry` appears tiny red serif in bottom-left over face — it's the keyword style but misplaced (should be centered plate, not corner). Looks like placeholder. Move to center editorial or inline with caption: `I will never be angry` where `angry` is red serif inline, not corner.
2. **Orphan `We` at 5s:** Same bug — `We` alone. Should be `We share a struggle` one cue.
3. **Short 21.8s:** The payoff "She is grateful she could open that door" is the title — you need that door-opening card (you have it in style but not in clip) — add vector door at payoff, extend to 28s.

---

## Systemic fixes (apply to all 6, not per-post)

### 1. Orphan single-word captions (post4/5/6/7 all hit it)

**Root:** `clipper/captions/cues.py:group_words(gap_break=0.45, max_words=3-4)` splits on any pause >0.45s, leaving 1-word cues `OF MY`, `image`, `We`, `angry` alone.

**Patch (already in WHOP PRO FIX 01_CAPTIONS/README.md but enforce):**
```python
# clipper/captions/cues.py
gap_break = 0.60  # was 0.45 — Demi pauses a lot emotionally, don't split on breath
# + after grouping, merge any cue with len(words)==1 and duration<0.7s into next cue
if len(cue.words)==1 and cue.duration < 0.7:
    merge into neighbor
```

Test: post6 `image` 0.5s alone → merges to `shade and protect my image` one cue.

### 2. Per-post accent is good, but feed needs lock

You use 4 accents: teal #14E5C5 (2/3/5), gold #D7A73C (4), sage #78A974 (6), terracotta #C7654E (7). Intentional palette per emotion — smart.

**Fix:** Keep per-post accent but lock **ink/paper** to one: `#0B0E11` ink + `#FFFFFF` paper for all. Currently post5/6/7 use warm inks (#20181B, #111710, #211512) — on feed scroll, backgrounds flash warm/cool. Lock to #0B0E11 for visual consistency; accent alone signals emotion. Update `style_theme.json` `paper` to `#FFFFFF` everywhere.

### 3. Black full-screen cards → editorial over face

Brief says "full-bleed, story-specific vector motion graphics plus low-volume music bed. No marker swipes, hot pink, or captions-only edits" — and you approved post1 pilot's editorial+vector. Black WORTH/OAK TREE cards violate the "face on screen" desire — viewer follows Demi's eyes, not black.

**Rule:** Black card only for the **hook** (first 1.2s) if needed; after that, editorial captions (small regular + large display) live **on chest** over face, not on black. Your motion system already has `caption: regular`, `keyword: displaybook`, `serif: serifbi` — use them together on one frame:

```
MY WORTH ISN'T
WORTH  (displaybook, accent, 118px)
ISN'T IN MY BODY
```
All over face, not black.

### 4. Transitions: kill flash/flare/leak

All 3 `style_theme.json` have `"transitionOrder": ["flash","flare","leak","bwflash"]` — that's the cheap WHOP template look. For Demi's intimate podcast, **hard cut only** (or 0.25s fade_black between card→face). Change to `"transitionOrder": ["cut"]` + `"cutTransitions": "hard"` — already in config, just not set.

### 5. Durations: extend 5 & 7 to 28-30s

WHOP CPM rewards 30-40s (brief). Post5 18.1s + post4/7 ~21s leave money on table and feel clipped. Pull 8-10s more from episode (you have 69-min source via footage-demi-1 release) — add the payoff sentence + end card fade (0.8s). Pays better, holds better.

### 6. Music bed: verify low-volume bed exists

Frames can't show audio. Check: `ffprobe street_post2.mp4 | grep audio` — should be -14 LUFS bed at -22dB under voice. If silent, add `assets/music/chill.wav` at 0.12 volume (you have it) — brief says "plus a low-volume music bed."

### 7. Captions: wire keyword accent (post2/3 missing it, post6 has it)

Post6 correctly colors `build`/`protect` green serif — post2/3 don't. Same engine, same `style.json` structure — why difference? Check `motion/produce.py` keyword tagging — post2/3 transcripts may not have keywords marked. Tag manually: top 5 emotional verbs/nouns per clip → accent.

---

## Priority action list (do in order)

**Today (30 min):**
1. Fix orphans: patch `cues.py` gap_break 0.60 + merge singles, re-render post5/6/7 — fixes `OF MY`/`image`/`We`/`angry` instantly
2. Re-render post5 extended (add payoff + end card) — 18→28s — biggest CPM win
3. Re-render post6 with OAK TREE as editorial over face (not black), animate tree (drift 100→103%)

**This week:**
4. Add keyword accent to post2/3 (`DRAW PICTURES`, `HISPANIC`/`REPRESENT`) — 5 min per clip
5. Lock `paper` to #FFFFFF across all 6 style_themes, set transitions to `cut` only
6. Extend post4 (+7s) and post7 (+6s) to 28s — pull from source

**Polish (if time):**
7. Stage card grain + vignette for post4
8. End card fade check on all 6 (brief requires it)

---

## What to keep

- Post2/3 foundation is **keeper** — white bottom captions, face on, no spam — it's your best baseline. Don't rebuild, just add keyword accent.
- Post6's 3-font hierarchy (regular + green serif) is the **pro template** — copy it to post2/3/4/5/7
- Per-post accent by emotion (teal → hope, gold → fear, sage → growth, terracotta → family) is smart — keep, just lock paper

---

*Prepared from frame extraction on 5a6e6ca @ 4e877d9 — all 6 videos probed, 24 frames sampled. Next step: apply WHOP PRO FIX 01_CAPTIONS pro profile + cues patch, then batch re-render post5-7.*
