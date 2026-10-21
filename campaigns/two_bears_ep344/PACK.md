# 2 Bears 1 Cave — Ep. 344 : pack

## Post copy — use as-is

> Tom and Bert on the one thing nobody tells you about [SUBJECT].
> 2 Bears 1 Cave Ep. 344 is out — the full episode is in my bio.
>
> #2BearsWeekly

Rules that are payout conditions, not style:

- The words **2 Bears 1 Cave Ep. 344** must appear in the post.
- **#2BearsWeekly** must be there. Missing it = not paid.
- The episode link must be in the **account bio**, not the post:
  https://youtu.be/3pDAyRLPO58
- Do not story-boost, do not post the same cut twice with no variation, and do
  not put a slur or a Nazi/Hitler reference in the caption — the brief bans
  those in text even where the speech is fine.

## Cover

Picked by `cover.py` — sharpest frame with a large, usable face near the start,
scored on sharpness, face size and exposure. Not a timestamp, not an
expression after a blink.

## Platforms

TikTok, Instagram Reels, YouTube Shorts, X. Same file works for all four
(1080x1920, H.264, -16 LUFS).

## What to check before posting

    .venv/bin/python scripts/whop/qc_gate.py <file> --manifest <post>/cards.json --campaign two_bears_ep344

`topic_safety` must read PASS. `title_safety` must read PASS. Anything else that
warns is a judgement call, and the fillers are the one failure that needs the
raw episode rather than a re-render.
