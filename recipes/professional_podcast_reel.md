# The professional podcast-reel recipe

Distilled from two watch-throughs of the tutorials the user sent (every word
transcribed, frames studied): "Viral Podcast Reels in Premiere Pro" (6:56) and
"Viral Podcast Reel Editing — Minimal Text Animation" (25:02). Transcripts:
`work/viral_podcast_reels_fast/transcript.json`,
`work/viral_podcast_reel_editing/transcript.json`.

Both tutorials independently teach the *same* style. What follows is the
grammar, ranked by how much it matters.

## 1. Sentence-block captions, revealed word by word

- The caption is a **sentence block that stays on screen**; each word **appears
  exactly when it is spoken** and remains until the sentence clears. The unit
  is the beat, not the single word.
- **Hierarchy inside the block**: the operative word is big; connective words
  are small. Both tutorials say it directly — *"one word will be slightly
  bigger and the other words will remain smaller. This creates a clean, modern
  visual flow."* (Slight on the word subtitles; 4-5× on the big-word blocks.)
- Fast tutorial's fonts: **Montserrat Bold**; long tutorial: **SF Pro Display**.
  Either way: heavy sans, white.
- Drop shadow on the text, **duplicated so it reads as pop**, not as a blur.
- Reference positions from the frames: centered horizontally, optical center —
  lower third on tight shots; over b-roll, stacked flush-left big/small blocks.

## 2. One motion recipe, everywhere

- Every word does the **same** animation: rise ~15-20px from below + fade in,
  **ease-out curve** ("start fast and end slowly"), ~200-250ms. Alternate
  variant per line max: slide from the left with the same easing. The
  professionalism is the *consistency*: "Copy, paste, adjust — that's exactly
  how clean edits are made."
- Subtle scale-pop emphasis on payoff words is acceptable; bounce/glow/shake
  is not. **Minimal is the north star** (their words).

## 3. The cinematic finish (cheap and visible)

- **Bottom fade bar**: a black rectangle masked with a heavy feather along the
  caption zone, blended upward — "this is where our captions will appear". It
  makes captions legible on any footage and reads instantly as intentional.
- **Vignette**: black video + feathered rectangular mask darkening the frame
  edges (fast tutorial masks with feather ~280-300). Small, but this is most
  of what people call "the cinematic look".
- Slight grade: mild contrast/saturation lift. No LUTs, no teal-orange.

## 4. Story-matched b-roll / stills — rare, never decorative

- When speech names a thing ("tired at night", "crisis", "love"), cut to or
  overlay a **matching image/clip for 1.5-3 s**: sleeping man for "tired", a
  doorway still for "crisis", a couple for "love". Sources they used:
  Pinterest vertical clips and Freepik stills, hand-picked.
- Rule: *exactly when the word lands, gone when the beat ends.* Never constant,
  never generic. "Not always, no overedits."
- Over b-roll, big stacked text blocks ride the dark footage (see the
  "You are / **Stressed** / from / **Doing** too" frame).

## 5. What both tutorials deliberately do NOT use

- No jump-cut zoom-spam, no RNG emojis on every line, no rainbow keyword
  cycling, no loud transitions. Sound design is restraint: at most one riser/whoosh.
- The only color accents: a single red/colored emphasis variant for a hot
  word, and the amber stacked hook header ("Bulla / don't") pinned top-corner
  while the hook plays.

## What this means for us (mapped to code)

| Rule | Feature | Status |
|---|---|---|
| sentence block + per-word reveal | ASS karaoke (`\k`) per sentence, words hidden until spoken | building |
| big emphasis word inside the block | inline `{\fs}` override on the sentence's operative word | building |
| rise+fade ease-out motion | per-sentence `\move` 15px over ~250ms + `\fad` | building |
| bottom fade bar | ASS `\p1` gradient strips event spanning the clip | building |
| vignette + mild grade | style profile `grade` section → `vignette`/`eq` in the burn | building |
| story-matched inserts | plan/captions `inserts`, files from `broll/` by keyword | mechanism building; user supplies assets |
| hook header (amber stacked) | after the above — needs a per-clip placement pass | next |
| one-whoosh sound design | needs an SFX asset library; user supplies | deferred |
| emoji/icon over payoff | needs an icon set on disk | deferred |


## Reviewer amendments (first real viewer, 2026-10-14)

1. **Never paste an image across the speaker's face.** The tutorial pattern is a
   full-frame *cutaway*: picture replaces picture for the beat. `--insert` now
   defaults to `full`; overlays are the deliberate exception.
2. **A clip must know where it starts and ends.** Selection is story-arc shaped
   (`clipper arcs`): question hook, payoff inside, end at the first real silence
   plus a short reaction tail. Anything else is reported, not padded.
3. **Assets are the tool's problem, not the user's.** SFX and icons live in
   `assets/` (synthesized / openly licensed, fetched from GitHub in-sandbox).
