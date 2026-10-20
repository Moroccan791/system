# Street You Grew Up On — shipped posts

One row per delivered post. Every video is 1080×1920, 30 fps, H.264 + AAC 192k,
captions verbatim, `#ad` in the pack, true peak at or under −1.3 dBTP.

| Post | Video | Cover | Pack | Length | Emphasis ink |
|---|---|---|---|---|---|
| 4 — Terrified to go on stage | [`street_post4.mp4`](post4/street_post4.mp4) | [cover](post4/cover.jpg) | [POST.md](post4/POST.md) | 19.8 s | green `#78A974` |
| 6 — Building an oak tree | [`street_post6.mp4`](post6/street_post6.mp4) | [cover](post6/cover.jpg) | [POST.md](post6/POST.md) | 22.9 s | yellow `#FFC83D` |
| 7 — Grateful she could open that door | [`street_post7.mp4`](post7/street_post7.mp4) | [cover](post7/cover.jpg) | [POST.md](post7/POST.md) | 21.8 s | red `#E23B2F` |

## What changed on 2026-10-20

- **post4** — captions put back on the words (the tight pass had spread the
  script proportionally across the speech, so every line drifted late);
  7 trims, bars gone, camera keys, 12 cards.
- **post6 / post7** — bars gone (137 px on post6, 105 px from the second shot
  on post7), camera keys on the spoken words, emphasis words set 16% larger in
  the post's own emphasis ink, covers refreshed. Audio is the shipped mix,
  bit-for-bit in time (measured 0.0 ms shift, correlation ≥ 0.998) with one
  constant gain so the peak lands at −1.3 dBTP instead of +0.7 / +0.3.

Reproduce with:

    .venv/bin/python scripts/whop/tight_posts.py post6 post7

Earlier files (post1 v4–v6.2, post2, post3, post5) are from the pre-brief
pipeline and are listed in their own folders.
