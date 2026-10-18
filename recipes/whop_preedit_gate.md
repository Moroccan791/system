# Whop: pre-edit style gate and pilot acceptance

This is an editor instruction, not homework for the viewer. The viewer
judges the content and chooses the typography/colour; the editor handles
footage, transcription, timing, licensing, graphics, music, render and QC.

1. **Plan before editing.** State the clip's purpose, source range, first-second
   claim/open loop, payoff, closing line, intended frame/face-safe zones and
   the spoken beats that merit *actual* motion graphics. Check the relevant
   campaign brief. Do not equate a QC PASS with an editorial acceptance.
2. **For every individual post, offer the chooser before the final edit.**
   `python scripts/whop/style_card.py serve --campaign <slug> --video post<N>
   --preview <clean-speaker-still>`. The agent prepares the still; the user
   does not upload anything. The card previews the real engine. Fonts can be
   selected separately for caption, keyword, serif, diagram and end card;
   text colours, accent and scene ground are selected on the same card.
   `save style` records `campaigns/<slug>/post<N>/style.json` and writes a
   matching `style_theme.json` + `motion/themes/<slug>__post<N>.json`.
   Campaign defaults are a **proposal**, not evidence of user approval.
3. **Only after the choice, build the publishable cut** with that post's theme.
   This is not permission to batch other clips. Verbatim words land on their
   acoustic onsets (engine renders two frames ahead); two lines max, ideally
   2–4 words at a time, one stable eye path. No marker swipes, swiping bars,
   glow/colour wash, words on a face or moving hands, or a graphic dissolving
   over a returning face. A full-screen diagram must change with the speech,
   not just be a static typographic card. Use the supplied footage or licensed
   vector motion, never an unlicensed stock insert.
4. **Delivery gate.** Face is complete in each framed shot, graphics are
   genuinely animated, there are hard cuts into/out of full-screen graphics,
   a quiet music bed, a full spoken ending plus readable endcard. Check the
   actual encoded frames at every transition, not just engine previews.
   Picture QC, sound QC and a campaign-compliant title/description/disclosure/
   7–8 relevant hashtags must all pass. Mark a proposal as *review*, not
   approved or publishable, until the viewer says the edit looks right.

Post1 v6 is a **review cut in a provisional inherited palette**, not a
font/colour decision made by the viewer. Rebuild it from
`scripts/whop/specs/street_post1_v6.json` (source transcript tracked at
`campaigns/street_you_grew_up_on/post1/window_transcript_v6.json`) and
`scripts/whop/build_street_post1_v6.py` when post1's own style is selected.
