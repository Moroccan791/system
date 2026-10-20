# Street You Grew Up On — Demi Lovato Podcast Clipping
Source doc: https://docs.google.com/document/d/153-ug0AMZtrkdz94AQ-e797mefjwZFalPV4tiDJM5Hc/edit?usp=sharing
Fetched 2026-10-17.

## Economics
- Pay: $2.50 CPM · Pool: $3,300 (Part 3 of $20,000 total rewards)
- 60% T1 required for full reward
- Min payout $10 · Max payout $450 per clip
- Paid only after approval on Content Rewards + Vouch verification above 4K views

## Must do
- Use clips from the content library (the supplied footage)
- Strong hook or CTA within the first few seconds
- #ad or #sponsored in description
- Description must include: "The podcast name is Street You Grew Up On - full episode is available on YT and other podcast platforms"
- Own original edit — never a repost of someone else's clip

## Never
- Bots / bought views or engagement (instant removal)
- Anything false or exaggerated about the content or the people in it
- No adult, violent, hateful, political, religious or drug-related content
- No copyrighted music, video or images layered on top without rights
- No misleading titles or thumbnails
- No co-authoring with irrelevant accounts

## Enforcement
- First offence + takedown when asked: warning. Second: removed and banned.
- Refusal to take down: removed immediately. Takedown window 12 hours.

## Production consequences for our edit
- Titles/descriptions must be accurate to what is actually said — no hype beyond the clip.
- Captions verbatim from the supplied footage; no claims added by graphics.
- Motion/music only from our own system assets (no third-party copyrighted layers).
- Every posting pack carries #ad (or #sponsored) + the exact podcast line above.
- USER RULE (2026-10-17): no visible "ILLUSTRATIVE" word on any graphic — it looks ugly. Consequence: for THIS campaign, do not use generated raster inserts at all (our generated b-roll stills/rolls or generated phone captures would require that tag). Inserts come only from the supplied content-library footage; everything else is typography + vector motion graphics, which carry no such label.
- USER RULE (2026-10-17): PILOT FIRST. Produce exactly ONE clip — the strongest moment, fully finished with the new caption style + motion system — as the approval sample. Do NOT batch-produce further clips until the user has seen the pilot and said go. The full ranked moment slate can (and should) still be prepared meanwhile so the batch starts instantly after approval.
- Footage route: 640MB source via GitHub Release `footage-demi-1` (user uploading 2026-10-17).

## Current workflow authorization (2026-10-18)
- The user reviewed the post1 pilot, approved its editorial caption + full-screen graphic workflow as the template, and then explicitly directed a full-episode sweep for additional hook-first 30–40s (or up to 50s) shorts. That later instruction supersedes the earlier wait-after-one-pilot rule for the Whop batch only.
- Current approved scope: finish the selected Demi Lovato posts from the 69-minute episode; do not start faceless, Kelly/batch, or football work.
- Each post gets its own `style.json` before the edit, using the campaign's user-approved font roles and colours unless the user changes them in the style card.
- Captions stay verbatim and engine-synced; use full-bleed, story-specific vector motion graphics plus a low-volume music bed. No marker swipes, hot pink, or captions-only edits.
- Finish each post with the last complete spoken thought, a fade, and the branded end card; ship the video and a posting pack with `#ad`, the exact required description line, and 7–8 hashtags.

## Current workflow authorization (2026-10-18)
- The user reviewed the post1 pilot, approved its editorial caption + full-screen graphic workflow as the template, and then explicitly directed a full-episode sweep for additional hook-first 30–40s (or up to 50s) shorts. That later instruction supersedes the earlier wait-after-one-pilot rule for the Whop batch only.
- Current approved scope: finish the selected Demi Lovato posts from the 69-minute episode; do not start faceless, Kelly/batch, or football work.
- Each post gets its own `style.json` before the edit, using the campaign's user-approved font roles and colours unless the user changes them in the style card.
- Captions stay verbatim and engine-synced; use full-bleed, story-specific vector motion graphics plus a low-volume music bed. No marker swipes, hot pink, or captions-only edits.
- Finish each post with the last complete spoken thought, a fade, and the branded end card; ship the video and a posting pack with `#ad`, the exact required description line, and 7–8 hashtags.

## Current workflow authorization (2026-10-20)
- USER RULE: emphasis words are set a step larger than the words around them
  (1.16x, baseline aligned so the line stays level) and take the post's
  emphasis ink - the user asked for "yellow, red or green" on the words that
  attract the eye. Accent ink stays on plates and the end card; caption ink
  stays the approved ivory. Implemented once in the typesetter
  (`scripts/whop/font_refresh.py`, `Typesetter.KEY_SCALE` / `key_ink`) so every
  post and the next campaign inherit it.
- Tightening pass for a shipped clip with no raw source left: leave the sound
  untouched (no cut, no stretch, no re-mix - the keyboard is already in it),
  rebuild picture only, and apply one constant gain so the true peak lands at
  -1.3 dBTP. See `scripts/whop/tight_posts.py`.

## Course rules adopted (2026-10-20)

- The campaign's "Clipping 101" is now enforced by
  `scripts/whop/caption_rules.py` + `scripts/whop/qc_gate.py`, with the
  numbers in `campaign_rules.json`: 1-2 caption lines, ~14 chars (17 ceiling),
  no fillers left in the kept speech, hook inside 2 s, voice at least 12 dB
  over the bed, no black bars, no caption over a face, nothing frozen over 3 s,
  25-40 s preferred (12-60 s hard).
- Ending has two modes: the branded CTA card, or `--end=peak`, which cuts on
  the last spoken word because the course says to cut at the emotional peak.
  Whichever is used must be recorded in the post's pack.
- Results loop: `RESULTS.md` in this folder, one row per post 48 h after it
  goes up (views, watch time, first cliff, US%). Distribution:
  `recipes/distribution_playbook.md`.

## Ending decision (2026-10-20)

- USER DECISION: the **branded card ending** ("FOLLOW FOR MORE" + fade) is
  the default, chosen after watching both cuts of post7 side by side
  (`street_post7_new_card.mp4` vs `street_post7_new_peak.mp4`). `--end=peak`
  stays available and is the exception, not the default.
- Consequence for selection: because the clip lands on a card rather than on
  the peak, the **last spoken line has to be the payoff itself** - no clip
  should end on a trailing "you know" or a filler, since that is the beat the
  viewer is left with before the card.

## Hook selection (2026-10-20)

- USER NOTE: "make sure we get the best hooks to keep users retention - that's
  the best way to keep views."
- Implemented as `scripts/whop/hook_lab.py`: every plausible entry point is
  scored 0-10 on what a viewer sees in the first 2 s, calibrated on this
  campaign's reference clips - defiance 8.0 (opens on its strongest line),
  number 6.0 (same), setup-first 0.6 (reaches its number at 6.2 s; the clip
  starts too early). The score is a gate warning on every render
  (`hook_strength`, floor 4.0).
- Rule of thumb the calibration produced: **open on the line that would work
  as a caption on its own.** If the opening only makes sense with the
  sentence that follows, trim into it.
- USER CORRECTION (2026-10-20): "why do u need me to pick the hook" - so
  selection is **ours to make**. `scripts/whop/auto_pick.py` chooses the clip
  and its opening (hook 45% / payoff 25% / density 20% / length 10%, filler
  penalty, no mid-sentence cuts) and reports the pick with its reasoning. The
  user sees a finished decision they can veto; they are never asked to choose
  between candidates.

## Grade (2026-10-20)

- USER NOTE: "could we add colour grading, viewers really like that."
- Implemented in `tight_posts.py:grade_frame` and applied to footage only -
  never to vector plates, the end card, or the caption, whose colours are
  approved in the style card. Defaults: S-curve 0.26, saturation 1.05,
  warmth 0.010, cool 0.008, vignette 0.10, lift 0.008, skin guard 0.55.
  Measured on post 7: caption ink identical to the shipped master
  (230/238/244 BGR), frame mean -6%, skin within 2 points.
- Tuned on a face, not a colour chart: the first pass (warmth 0.022) turned
  her skin orange, so the warm lift is now small, capped, and skipped where
  pixels are already saturated. Measured on a post7 frame: skin BGR 90/92/109
  -> 88/91/109 (unchanged), frame contrast +1.5, saturation +24.
- Per-campaign overrides live in `campaign_rules.json` under `grade`.

## Motion (2026-10-20)

- Punches: 3.5% zoom bump on each emphasised word (the words the caption
  engine already sets in key ink at 1.16x), 70 ms in, 200 ms hold, 380 ms out,
  at least 0.9 s apart, max 9. Post 7 fires 5. This is the layer that makes
  the cut feel like someone is reacting to the words rather than a slow push.
- A/B framing: a 1.6% scale change, but only at a real silence between cards
  (not at every card boundary - the cards tile the speech, so that would
  twitch every 1.3 s). Post 7 has no internal silences, so it gets none; the
  tool exists for raws that do.
- Both are asserted by `tests/test_punch.py`.

## Hook title + sound (2026-10-20)

- **Hook title.** The opening line is set large in the top third for its first
  beat (post 7: 0-1.12 s, "I WILL NEVER" with NEVER in the emphasis ink), then
  the band starts on the next card so the same words are never on screen
  twice. Same words, no new claim. Reason: autoplay is muted and the band sits
  in the bottom third where platform chrome covers it.
- Bug found by this: the band is only erased when one of our cards is up, so
  the archive's own burned-in subtitles were showing through underneath the
  title (post 7, 0-0.4 s). The band is now cleaned during the title too.
- **Sound.** `sound_design.py` synthesises an A-minor pad + a sub pulse on the
  beat, ducked under the voice from the transcript's own word times, plus a
  sub hit on each punch. Everything is generated here - no licensed master, so
  no Content ID claim, no mute, no territory block, nothing to expire.
- Bed level is measured, not assumed: the first pass landed at -24.9 dBFS in
  the quiet moments (audible "thinking pad"), so it was cut to 0.012 and now
  sits near -30 dBFS with 18.6 dB of clearance under the voice, against the
  gate's 12 dB requirement.
- **Gate fix.** `black_bars` used a fixed brightness cut, so the grade (which
  darkens by 6%) pushed a textured dark wall under it and failed post 7 at
  4.0 s. A bar is now dark *and flat* (row std < 2.5): content rows measure
  ~30, a real bar ~0.

