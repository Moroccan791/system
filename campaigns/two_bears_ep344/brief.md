# 2 Bears 1 Cave — Ep. 344

Campaign: Whop Bounties weekly return campaign.
Source: **2 Bears 1 Cave, Ep. 344** (Tom Segura + Bert Kreischer).
This brief is stricter than the last one: most of its "do not clip" list is a
*legal and payout* surface, not a taste preference.

## The required three (missing any = not paid)

1. The post must mention **"2 Bears 1 Cave Ep. 344"**.
2. The post must carry **#2BearsWeekly**.
3. The **episode link must be in the account bio**: https://youtu.be/3pDAyRLPO58

Platforms: TikTok, Instagram Reels, YouTube Shorts, X.

## Payout

- $1.00 per 1,000 qualified views, **$200 cap per video** (~200K views).
- Monthly pool $5,000, first-come review.
- Account must show **60%+ US / English-speaking audience**.
- Manual review plus bot screening before payment.

## Rejection reasons (verbatim from the brief)

- No 2 Bears 1 Cave footage or context in the clip.
- Missing #2BearsWeekly.
- Footage from anywhere other than Ep. 344.
- Missing the episode link in the bio.
- **Slop reposting**: the identical clip spammed with minimal variation.
- **Story boosting**: pumping views through story shares/boosts.
- Fake-looking views or likes.
- Any content from the DO NOT CLIP list.

## DO NOT CLIP — topics

| Category | Rule |
|---|---|
| Slurs | None of any kind. Not ironic, not callbacks, **not bleeped**, never in text. |
| Sexual explicitness | Graphic anatomy or act, incest riffs, anything involving minors even as a joke. |
| Suicide / self-harm | Including hyperbolic "kill myself" phrasing. |
| Drug use | No how-to, dosage, sourcing, or glamorising. Alcohol and tobacco excepted. |
| Real-person accusations | Crime, abuse, cheating, health/mental-health claims about named people. |
| Named-brand disses | Fast food, airlines, sponsors' competitors. Costs money, not views. |
| Guns / violence | Specifics, or anything reading as a threat. |
| Politics / elections | Fine in-episode, bad as a standalone clip (comment sections + ad rates). |
| **Hitler / Nazi / Holocaust** | No clips built on it, including ironic or accent-based, including one-line riffs. **Never in titles, captions or on-screen text.** |

## DO NOT CLIP — moments

- **Ad reads and sponsor bits** — clipping a paid read as organic content is an
  attribution problem.
- **The baby bit.** Kids + anything sexual in the same frame: automatic no,
  no clip, no quote, no caption.
- **Divorce / marriage jokes** as the premise — lands differently now.
- Guests' unresolved legal or personal drama.
- YMH staff or network-talent bits that read mean out of context.
- Network/business talk: revenue, deals, contracts. Never clip.
- Clips that only land if you heard the previous ten minutes.

## What this means for the pipeline

Two hard rules on top of everything built so far:

1. **A banned moment invalidates the whole window.** Not "cut around it" — a
   clip that needs the taboo line for its punchline is the clip that gets the
   channel restricted. `topic_guard.py` blocks any candidate whose span
   overlaps a banned hit, and `qc_gate.py` re-checks the finished cut.
2. **Text is held to a stricter standard than speech.** For slurs and for
   Nazi/Hitler references the brief forbids the words in titles, captions and
   on-screen text outright, so the text check is a hard block even where the
   same word in speech is only a warning.

Known limitation, stated plainly: the guard reads the **transcript**. A
bleeped slur leaves no word behind, and this campaign bans bleeped slurs. Any
clip containing bleeps must be reviewed by ear before it ships; the guard
cannot see them.
