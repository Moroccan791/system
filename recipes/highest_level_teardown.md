# Highest-level podcast references — teardown (2026-10-16)

The 4 `From Klickpin.com-…mp4` files at the repo root, added in the last
commit of the previous session (`d0478c4 "highest lvl podcast references"`).
Each one is an **editor's portfolio reel**: a small `Raw`/`Before` card and a
large `My Edit`/`Edited`/`After` card playing the *same moment at the same
time* over a neutral backdrop with a CTA ("DM NOW" / `Comment "Raw"`). So
every frame is a synchronised A/B — raw framing/grade on the left, the edit's
framing/grade on the right. The shell is lead-gen for editors; what we steal
is the edit inside the big card.

Evidence: contact sheets + edited-region sheets in `work/refs_analysis/`
(gitignored): `ref{1..4}_sheet.jpg`, `ref{1..4}_edited_sheet.jpg`.

## The four edits at a glance

| # | Editor / subject | Length | Accent system | Signature move |
|---|---|---|---|---|
| 1 | @render.rrush — Ava Juergens, "PersonalBrandLaunch" (21.7 s) | 21.7 s | neon lime on dark | subject-pop grade + full-screen phone/profile proof |
| 2 | PSG Parsai — real-estate walk-and-talk, 3 outfits (24.2 s) | 24.2 s | lime → cyan → pink gradient | light-leak outfit transitions + shout-word captions |
| 3 | PSG Parsai — podcast testimonial read (16.5 s) | 16.5 s | neon green + cyan proof highlights | spoken testimonial → on-screen receipt, phrase-synced |
| 4 | HossainRana — MrBeast podcast interview (30.5 s) | 30.5 s | red (structure) + green (positive) | literal animated metaphors + word-by-word label-bar captions |

All four: 720×1280, dead air = **zero** (no silence ≥ 0.35 s at −45 dB in
any file), loudness compressed (LRA 1.7–5.1 LU; integrated −13.7…−21.2 LUFS,
the quiet ones are portfolio mixes, not deliverables). Edited-region hard
visual changes: R1 ≈ 4, R2 ≈ 4, R3 ≈ 3, R4 = 12 in 30 s — but captions and
overlays change every word, so the *perceived* change rate is every
0.3–2 s everywhere. Nobody's talking head sits unadorned for > ~3 s.

## Per-video breakdown

### R1 — render.rrush (Ava Juergens)
Before: static selfie close-up, warm yellow room light, no captions.
After, in order: neon name super (`AVA JUERGENS`) → cut to **full-body wide**
(a different angle of the same shoot) with the **background darkened +
desaturated and the subject kept bright** (matte-based subject pop), neon
hero line *"I'm the CEO of 'PersonalBrandLaunch'"* + a hand-drawn curved
arrow annotation → **full-screen dark-mode social-profile screenshots** as
proof inserts → back to close-up with micro-overlays while she keeps
talking: checklist chips (✓ Hardworking / ✓ Consistent…), an avatar cluster
("who has … clients"), content-pillar colour bars → centre hero *"The
Editing Test"* → white-flash transition → **stock B-roll** (woman working
at a desk) with **recreated blue chat bubbles typing in one by one**
("This is a remote job / You can expect to…") for ~5 s → speaker close.
Handle watermark `@render.rrush` throughout.

### R2 — PSG real estate
Raw: flat, washed-out outdoor walk-and-talk across 3 outfits/locations.
My Edit: **cinematic grade unifies all three** (teal shadows, contrast,
saturation — the raw looks like log by comparison); two-tier captions —
small white lowercase verbatim line + **huge bold shout word** in gradient
(lime `READY` / `HAD TO`, cyan `POTENTIAL` / `OPPORTUNITY`, cyan→pink
`BECOME`); **orange light-leak/flash transitions exactly on the outfit
changes**, masking the jump cuts and selling "transformation"; a second,
smaller caption tier (white line + red italic keyword, *"low maintenance"*,
*"elevated in all the right ways"*) for detail lines; slow push-in keeps
her centred while walking.

### R3 — PSG podcast testimonial
Raw: one medium podcast shot. My Edit: punch-in closer, warmer skin,
richer background. Word captions with the operative word in neon green
(*"Instagram"*, *"ALL THE TIME"*, *"PROVING IT"*). The core of the edit is
a **proof stack that lands with the speech**: an animated mint UI/counter
card → rounded photo insert (two women) → the testimonial card itself
(*"Sarah Johnson, Student — I've been posting consistently on Instagram
for 36 days straight, with 936 followers"*) with **the exact clause
highlighted in cyan as she reads it**, held ~5 s → a second card,
*"Automated sales $7,000"*, the number in green. Punch-ins alternate
wide/close on emphasis lines. She says it; the receipt is on screen,
highlighted, at the same time.

### R4 — HossainRana / MrBeast (the closest to our Sartain work)
Raw: static medium angles. Edited: tight punch-in per speaker, warm
cinematic grade + vignette, cuts on speaker change. **Word-by-word
captions**, 1–3 words, centre-low, white bold; operative words get
semantic colour — **red label-bar** for structure (*"3 Questions"*,
*"Step one"*, *"thing"*, *"question?"*), **green** for positive/key
(*"original?"*, *"you know"*, *"improving"*, *"possible"*), oversized
stacked type for the lines that must land (*"look five times / never
going to forget"*, *"apply to ideas"* + a 💡 sticker on the word).
**Literal metaphors, animated**: *"driving down the road"* → a grey road
band with a red car driving across the bottom of frame; *"purple cow"* →
full-screen field of white cows, **one turns purple**; a thinking-man
insert + 🤔; further inserts (young MrBeast, soccer) framed as
**rounded-corner cards on a black canvas** — cutaway without losing the
podcast world. 12 hard visual changes / 30 s + a caption change per word.

## The shared grammar ("highest level" = these seven)

1. **Claim → receipt, instantly.** No abstract statement survives
   unvisualised: proof screenshot, testimonial card, stock B-roll or a
   literal metaphor appears with the sentence, not after it.
2. **Two-tier captions.** A quiet verbatim line + one shout word (huge,
   accented/gradient/label-barred). Captions are a design layer, not
   subtitles. Colour is *semantic* (R4: red = structure, green = key).
3. **Baseline table stakes:** punch-in reframe + cinematic grade on
   everything (R1 goes further: selective background dim/desat).
4. **Transitions only where meaning changes** (outfit, topic, speaker) —
   light leak/flash, never decoration.
5. **Zero dead air.** Silences cut, loudness squeezed, visual change
   every ≤ ~2 s (our QC pacing rule already demands this).
6. **One accent system per video**, locked (R2 bends it into a gradient
   ramp; R4 into a two-colour semantic pair).
7. **The reel itself is an ad** (Before/After cards + CTA). Not part of
   the edit grammar — ignore for client deliverables.

## Caption deep-dive (the gap inside the gap)

Zoomed crops in `work/refs_analysis/caps/`. Their captions are not
subtitles with a highlight — they are a *typography performance*, and
this is the single most visible difference from our output:

| Element | Theirs (R4/R2/R1) | Ours today |
|---|---|---|
| Base look | Rounded ExtraBold, **sentence case**, clean white ink straight on the picture, thin outline + soft shadow | Sharp ExtraBold, often ALL-CAPS (Anton/Archivo packs), 2–3px stroke — reads as "subtitle" |
| Highlight | **Marker bar**: an accent bar wipes in behind the *lower half* of the word, white ink on top (`"3 Questions"`) | Full ink-on-accent **plate** behind the whole word (Stage-A rule) — heavier, boxier |
| Colour logic | **Two semantic accents**: red = structure/negation, green = payoff/key; R2 gradients (cyan→pink `BECOME`, lime `READY`) | One accent per video; neon/serif variants only |
| Size hierarchy | *Inside one line*: connectives ~40% grey, normal words 100%, the operative word 160–220% — the eye is dragged word to word | Poster stacks rows (small connective row / huge keyword row); karaoke is one size for every word |
| Reveal | 1–3 words at a time, each **popping with overshoot**; in R2 the shout word *stays* while the small verbatim line cycles above it | Block (2–4 words) or karaoke row replaces as a unit; heroes are separate items |
| Mixed voices | Sans + **serif-italic accent word in the same line** (R2's red italic detail tier: *"low maintenance"*) | Serif word exists in poster (`wd.kind`) but not as a flowing inline tier |
| Finish | Neon bloom glow (R1 lime), gradient ink, emoji sticker glued to the word (💡 on *"ideas."*) | Glow only on neon *scene* words; captions get stroke + shadow, no gradient ink, no on-word sticker |
| Placement | Tight under the chin / on the chest — the eye never leaves the face | Fixed lower-centre (ASS) or measured poster zones; correct, but further from the face |

Our nearest frame for comparison (`caps/ours_post7.jpg`): black ink on
hot-pink plates, very legible — but it's a *label*. Theirs
(`caps/r4_3.0.jpg`) is ink, a marker swipe and air. Same information,
half the visual weight, twice the "edited" feel. We do have the right
raw ingredients (Poppins ExtraBold is already vendored; poster has
small-connective + hero sizing; Stage-A plates prove the renderer can
paint behind words) — what's missing is the *combination* as a caption
style: **marker-bar + semantic second accent + gradient ink + inline
size hierarchy + per-word pop**, packaged as a selectable
`captionStyle` (working name: `marker`), with `decide.py` tagging word
roles (structure vs payoff) instead of a single keyword.

## What we already have (honest overlap ≈ two-thirds)

Word-level captions with accent operative word, poster/hero/karaoke
packs, camera punches on payoff words, face-tracked reframe, 51 vector
scenes (chat, people, bars, counter, quote…), PiP/B-roll, claim cards,
proof *stickers*, themes + 8 font packs, flash/flare/leak FX, sound
design, QC pacing (visual change ≤ 2.5 s), images.py still sourcing.
Nothing in these four reels needs a renderer we don't own — the stage
(HTML/CSS → PNG → ffmpeg) can express all of it.

## What we lack (the actual gaps, in build order)

1. **Real proof assets as timeline items.** Screenshots / screen
   recordings (profiles, comments, testimonials, revenue cards) with
   **word-synced phrase highlighting** and count-up numbers *inside the
   card* (R3). Today: `decide.py` only *reports* PiP candidates, media
   choice is manual, cards are static vector/still. **Biggest gap** —
   this niche (coaches/creators) sells on receipts.
2. **Literal-metaphor + stock-video B-roll.** Animated concrete
   metaphors (purple cow, road/car — R4) and motion stock with
   recreated chat bubbles over it (R1). Today: abstract/data vector
   scenes + generated *stills*; no stock video, no bubbles-over-video
   composite, no "show the analogy" rule in `decide.py`.
3. **Subject-pop selective grade + named cinematic grades.** Matte-based
   background dim/desaturate (R1) and LUT-style look presets that unify
   mixed locations (R2). Today: global grade only (denoise/sharpen,
   neutral); the matte exists but only feeds behind-text.
4. **Eye-catching captions (see deep-dive above).** Marker-bar
   highlight, semantic second accent, gradient ink, inline size
   hierarchy, per-word pop — as one `marker` captionStyle. Today: one
   accent, full plates, single-size karaoke; the ingredients exist,
   the combination doesn't. **Co-#1 with proof** — it's on screen
   100% of every video, while proof items come and go.
5. **Phone-frame screen inserts.** Full-bleed device mock with a
   scrolling profile capture (R1). Today: PiP stills only.
6. Small: emoji sticker stuck *on* a caption word (💡/🤔 — icons exist,
   not caption-attached), hand-drawn arrow annotations (arrow scene is
   close).

Not gaps: the Before/After portfolio shell (that's their sales page,
not a client deliverable), and transition variety (we have leak/flash —
theirs is an editorial rule about *placement*, which our
never-twice/meaning-change rules can adopt for free).

**Verdict:** the "highest level" is not fancier motion graphics — it's
*asset-driven* editing: real receipts, literal pictures, synced
highlights, at the pacing we already QC for. Our system is
generated/vector-driven; closing gap #1 (proof) and #2 (metaphor/stock
video) is what moves our output into this tier.

---

## Built — 2026-10-16 (all six gaps closed)

| Gap | Shipped as |
|---|---|
| 1. Real proof assets | `proof` timeline item: testimonial card, phrases highlighted on their spoken onsets, count-up value inside the card. `motion/proof.py` token-matches asset phrases to the transcript; unmatched phrases are reported, never guessed. produce.py auto-zones it under the measured face; fallback level 1 downgrades it to a poster rather than dropping it. |
| 2. Literal metaphors + motion B-roll | `cowfield` (one purple cow) + `roadcar` vector scenes, fired by literal triggers in `assign.py`, metaphor dwell 1.0–1.8s. `broll` plays real video frame-synced (`render.mjs` `syncVideos()`) with `messages[]` chat bubbles on spoken beats. |
| 3. Subject pop + grades | `composite.py --grade {teal,warm,punchy}`; `subject_pop` desaturates/darkens only the background, split by the `matte.py` person matte (hard error without a mask). `produce.py --grade` threads it through. |
| 4. Marker captions | `captionStyle: "marker"` (theme `marker-bold`): sentence-case white ink, marker bar behind the key word's lower half, `mark` (structure, accent) vs `pay` (payoff, `accent2`) roles tagged by `decide.py`, `grad` gradient shout words, inline size hierarchy, serif mix, emoji sticker glued to the word. A marker poster with no marked word fails validation. |
| 5. Phone inserts | `phone` item: full-bleed device mock, capture scrolls under the glass, ILLUSTRATIVE when generated. |
| 6. Small devices | `doodle` hand-drawn arrow (draws on, then points) + emoji-on-word in #4. |

Evidence: `motion/timelines/highest_demo.json` exercised in
`motion/demo_highest/` (sheet + strips + `qc_report.txt`) — one 32s
clip using every device above, composited with `--grade teal`,
**MOTION QC v2: PASS**. `tests/test_highest_level.py` covers marker
roles/sizes, proof timing, metaphor dwell, grade rules, the fallback
downgrade and the QC event model. The subject_pop chain was verified
separately on a 6s slice (MediaPipe matte → selective grade: room
quiets, speaker untouched).
