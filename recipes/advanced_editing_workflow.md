# Advanced editing workflow: plan the promise, then build the cut

This is the production contract for future Whop clips. It is a judgment-led
workflow informed by `editing_brain.md` (retention, habituation, open loops,
and dual coding), not a checklist of effects to copy. Passing QC is necessary,
not the quality bar. Review the finished cut at full speed, with sound, and
with the source open beside it.

## 1. Review the whole episode before selecting a moment

1. Read/watch the complete source and its transcript. Identify the strongest
   *spoken* claim, confession, result, tension, or punchline—not merely the
   easiest section to style.
2. Use `scripts/whop/review_hooks.py` only to shortlist verbatim openings for
   human review. It is a heuristic, not a retention predictor. Do not write a
   stronger line for the speaker, move an unrelated payoff forward, or imply
   that a current video has validated a new hook.
3. Choose a self-contained thought: one purpose, claim in the first seconds,
   meaningful escalation, the important line intact, and a real closing line
   that pays off the opening. Default to 25–40 seconds; extend toward 50 only
   when the thought genuinely needs the extra time.
4. Keep the end of the speaker's footage and the end-card transition clean.
   Close the thought, then cut to the approved end card; do not leave a frozen
   face or a stray speaker tail under it.

## 2. Get the per-video style card approved before editing

Open the style-card page for the exact video. Present a role specimen (caption,
keyword, list, end-card, and any serif role), a palette preview, and a timeline
preview. The user chooses the fonts and font colours before the edit begins.

- Font matching is vibe-first, but source only properly licensed OFL or
  Fontshare equivalents from their official source. Never copy or redistribute
  a paid-tool font. Show the actual font files/weights on the specimen sheet
  and wait for approval.
- The user chooses the big-word accent for each project. Do not impose
  `#FF3355`, a campaign-wide accent, or a repeated blue/teal look. Give each
  video a distinct palette and preserve the approved choice through render.
- Approval is specific to campaign + video. Editing/production stays blocked
  until that exact card is approved; changing it invalidates the receipt.

## 3. Build the cut before decorating it

- Start inside the real spoken moment. Keep the source line verbatim; captions
  must match what was said, not what would read better as copy.
- Tighten long pauses with `motion/prep.py` defaults (compress pauses over
  0.30s while retaining a 0.18s breath); the Whop acoustic base builder uses
  the same defaults. Override conservatively for reflective delivery so a
  meaningful breath survives. Listen after the cut: preserve natural cadence
  and never remove a word or an important reaction merely to hit a duration target.
- Reframe only with the face fully in frame. Use a deliberate punch, pullback,
  or crop change to direct attention to a beat—not constant arbitrary zoom.
- Keep the speaker visible for the full spoken thought unless a deliberate
  hard-cut graphic or full-frame cutaway is doing a clear storytelling job.
  B-roll is full-frame only, one or two inserts maximum, generated or supplied
  for the campaign; never paste it over a face.
- Do not add a title slate before the opening line. The spoken opening, face,
  and first caption are the hook; a slate does not earn spoken-hook credit.

## 4. Make a graphic earn its screen time

A graphic must clarify, prove, or intensify the exact line being spoken. Use
context-gated, authored motion graphics—not a random burst because a keyword
was detected. Examples include a counter for a spoken number, a diagram for a
spoken relationship, or a metaphor scene only when the speaker actually uses
that metaphor. Prefer one strong visual idea per beat over a stack of
competing decorations.

- A full-screen vector scene is a hard cut and must be supported by the words;
  it should feel like a purposeful visual sentence, then return to the speaker
  before the next thought. Keep faces unobstructed on speaker shots.
- Motion needs a clear arc (assemble, resolve, release), readable silhouettes,
  controlled easing, and a landing. A poster with a scale pulse alone is not a
  motion graphic.
- Keep movement and visual changes purposeful. Avoid an unchanged state for
  more than roughly 2.5 seconds, but do not create meaningless cuts just to
  satisfy a counter. The viewer should always understand what changed and why.

## 5. Caption polish: flat editorial type

- Captions stay verbatim, legible, and editorial: clear role hierarchy, clean
  line breaks, stable placement in the eye path, and enough contrast against
  the footage. Keep the speaker's face clear.
- Use the approved per-video keyword accent. No marker-swipe captions, no
  coloured bar wiping behind a keyword, no moving highlight strip, and no
  heavy condensed caps with an offset-shadow treatment.
- Word-by-word timing and typing sound are on by default; keep the sound and
  low-volume music subordinate to the voice. The caption animation must not
  turn into a repetitive effect that distracts from the sentence.

## 6. Finish, QC, and deliver

The thought closes before the end card. The only end-card wording is
**FOLLOW FOR MORE**. Apply a proper fade/outro with no frozen image or face-bleed
tail. Each clip is delivered in its `post<N>/` directory with the video and a
posting pack containing a title, description, and 7–8 hashtags. Preserve the
required campaign description in that pack.

QC should include at least:

- verbatim-caption and cut-boundary review against the source;
- full-speed viewing with sound and a muted/mobile-legibility pass;
- face-safe framing, graphic context, readable motion, and clean hard cuts;
- low-volume music and present-but-not-dominant typing sound;
- a real ending, approved CTA, no frozen tail, and no unintended frames;
- review by a human on attractiveness and pacing, not only validator output.

## Post5 visual-feature demo scope

Use the existing “My worth isn't in my body.” hook and transcript exactly as
currently authored. The demo is to show the approved style, editorial
captions, and context-gated `WORTH` motion scene—not to test a stronger hook.
Do not claim stronger-hook improvement from this or any existing video. The
demo is not shipping approval. Existing post2–post7 finals remain untouched.
