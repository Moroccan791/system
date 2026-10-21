# 2 Bears 1 Cave — Ep. 344 : results

One row per post. Fill `views` and `watched_3s` once they are in; then

    .venv/bin/python scripts/whop/results_tracker.py campaigns/two_bears_ep344/RESULTS.md

Stricter than last campaign: a post missing the mention, the hashtag or the bio
link is **not paid**, regardless of how it performed. Those are tracked
separately so a good clip with a missing tag is visible as a payout failure
rather than buried in the view count.

| post | hook_score | views | watched_3s | duration | mention | hashtag | bio_link |
|---|---|---|---|---|---|---|---|
| [what_did_you_do](what_did_you_do/POST.md) | 4.0/10 | | | 44.9 s | yes | yes | yes |
| [awesome_pictures_of_me](awesome_pictures_of_me/POST.md) | 9.0/10 | | | 44.9 s | yes | yes | yes |
| [evil_minded_peasant](evil_minded_peasant/POST.md) | 0.5/10 (warn) | | | 20.8 s | yes | yes | yes |
| [honey_youre_fucked](honey_youre_fucked/POST.md) | 0.5/10 (warn) | | | 24.5 s | yes | yes | yes |

Every file: 1080x1920, 29.97 fps, H.264 + AAC 192k, -16 LUFS, -1.3 to -2.7 dBTP,
gate PASS with no failures. The only rows the gate still prints are `fillers`
(verbatim captions keep the spoken "like") and, on two posts, `hook_strength`.

Hook strength is the scorer calibrated on the last campaign, and it rewards a
claim in the first two seconds; a story that opens on somebody else's line
scores low by construction. The opens here are "Are you on YouTube?", "one in
the gym with me", "Please, leave. I can smell you from here.", "she saw me on
Instagram". The peasant and party clips score 0.5 and were kept anyway: the
score is measuring the shape of a claim, and these are scenes.
