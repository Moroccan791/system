# Results log — Street You Grew Up On

The course is blunt about this: *"Your taste doesn't matter — the audience
decides… study analytics, what kind of clips got views."* Right now we learn
from chat, and chat doesn't survive a reset. So: one row per post, filled in
48 h after it goes up, and a short line on what we'd change.

## What to send (screenshot or copy the numbers)

From TikTok analytics, per post, after 48 h:

- views, likes, comments, shares, saves
- **average watch time** and the retention graph's first cliff (the second it
  drops hardest)
- **% of viewers from the US** — the course's bar is **80%+**; below that the
  account setup is the problem, not the clip
- traffic source split (For You vs profile vs search)

From YouTube Shorts / Reels, if cross-posted: views, average view duration,
"viewed vs swiped away" on Shorts.

## The log

| Post | Date | Views | Avg watch | First cliff | US % | Verdict / what changed next |
|---|---|---|---|---|---|---|
| 4 — terrified to go on stage | | | | | | |
| 6 — oak tree | | | | | | |
| 7 — open that door | | | | | | |

## The mistake list

Every note the user gives, verbatim, with the date it was fixed in the
pipeline. This is the file that stops a note from being re-learned.

| Date | Note (verbatim) | Fixed where |
|---|---|---|
| 2026-10-17 | no visible "ILLUSTRATIVE" word on any graphic | brief.md, no generated raster inserts |
| 2026-10-20 | captions come late | `retighten.py` uses transcript word times |
| 2026-10-20 | emphasis words bigger, in yellow/red/green | `Typesetter.KEY_SCALE` / `key_ink` |
| 2026-10-20 | don't leave "um"/"you know" in | `caption_rules.filler_words` + gate |
| 2026-10-20 | caption lines too long | `caption_rules.wrap_cells` + gate |

## Reading the numbers

- **A clip that underperforms on views but holds watch time** is being shown
  to the wrong people (distribution/topic), not badly edited.
- **A cliff in the first 3 s** is the hook. Compare the hook line against the
  gate's `hook` check — if the gate passed and it still dropped, the line was
  legible but not interesting, which is a selection problem, not an edit one.
- **A cliff at the end** is fine if it's the last beat; a cliff 70-80% in is a
  pacing hole. Check `frozen` and the caption cadence for that second.
- **US % under 80** → `recipes/distribution_playbook.md`, not another render.
