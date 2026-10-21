# 2 Bears 1 Cave — Ep. 344 : results

One row per post. Fill `views` and `watched_3s` once they are in; then

    .venv/bin/python scripts/whop/results_tracker.py campaigns/two_bears_ep344/RESULTS.md

Stricter than last campaign: a post missing the mention, the hashtag or the bio
link is **not paid**, regardless of how it performed. Those are tracked
separately so a good clip with a missing tag is visible as a payout failure
rather than buried in the view count.

| post | hook_score | views | watched_3s | duration | mention | hashtag | bio_link |
|---|---|---|---|---|---|---|---|
| [what_did_you_do](what_did_you_do/POST.md) | 2.0/10 (warn) | | | 44.9 s | yes | yes | yes |
| [awesome_pictures_of_me](awesome_pictures_of_me/POST.md) | 4.5/10 | | | 44.9 s | yes | yes | yes |
| [evil_minded_peasant](evil_minded_peasant/POST.md) | 0.5/10 (warn) | | | 40.6 s | yes | yes | yes |
| [honey_youre_fucked](honey_youre_fucked/POST.md) | 2.0/10 (warn) | | | 23.1 s | yes | yes | yes |

`mention` / `hashtag` are the copy as written in each `POST.md`; `bio_link` is
account-level and set once.

Hook strength is the calibrated scorer from the last campaign, and it is a weak
fit for a comedy anecdote: it rewards a claim in the first two seconds, and a
story that opens on someone asking a question scores low by construction. The
first lines here are, in order, "She goes, are you on YouTube?", "No one in the
gym with me", "In Paris, and we walked into this old beauty shop", "She saw me
on Instagram". They were chosen for whether they make a viewer stay, not for
the score.
