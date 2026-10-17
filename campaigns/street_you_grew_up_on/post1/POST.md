# Post 1 — PILOT — “I Don't Come Home to an Award” (Demi Lovato)

- **Video:** `street_post1.mp4` (33.6 s, 1080×1920, 30 fps) — motion-graphics edit with the new marker-caption system: sentence-case captions, pink marker swipe on structural words, green on the payoff words (“joy”, “connection”), word-by-word sync. Branded end card “STREET YOU GREW UP ON”. **Motion QC v2 PASS at level 0**, loudness normalised to **−14.3 LUFS / −0.7 dBTP**.
- **Cover:** `cover.jpg` — “I DON'T COME HOME / TO AN AWARD” (direct quote, nothing exaggerated).
- **Source:** full episode 45:59.6–46:33.2. Self-contained answer, clean in/out, real closing line (“All of this can go away. What's important in life is connection.”) + fade into the end card. No banned-topic content, no profanity.
- **Hook (0 s):** “I'm able to hold space because my craft keeps me busy, it keeps me sane…” — captions animating from frame 1.

## Title
Demi Lovato: “I Don't Come Home to an Award”

## Description (copy-paste exactly)
#ad
Demi Lovato on what actually keeps her grounded: “I don't come home to an award. I come to my dogs and my husband — and that's what brings me joy. All of this can go away. What's important in life is connection.”

The podcast name is Street You Grew Up On - full episode is available on YT and other podcast platforms

## Hashtags (8)
#DemiLovato #StreetYouGrewUpOn #podcast #podcastclips #celebrityinterview #interview #popmusic #inspiration

## Production notes (for the batch)
- Vertical base built per reframe shot (3 shots): close-up crops on Demi Lovato + one centred two-shot for “my dogs and my husband”. Rule for every base: `fps=30` BEFORE `zoompan`, then verify frame count = duration × 30 (an earlier build ran 1.7 s fast against its audio and every automated gate missed it).
- Engine fix shipped with this pilot: `motion/stage.html` had junk lines after `</html>` that rendered as source-code fragments in the top-left corner of every frame. Removed + regression test added (`test_stage_html_has_nothing_after_closing_tag`).
- decide.py put the filler “YOU KNOW” in a generated list panel; replaced by hand with the spoken caption. Check every auto-panel for filler before shipping.
