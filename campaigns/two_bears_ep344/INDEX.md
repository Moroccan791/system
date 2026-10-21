# 2 Bears 1 Cave — Ep. 344

Four posts, cut from the 66-minute episode. Every one of them passed the
campaign gate (`topic_safety` and `title_safety` PASS); the rows that still read
WARN are listed per post and are judgement calls, not defects.

| Post | Video | Length | Loudness | True peak | What it is |
|---|---|---|---|---|---|
| [What did you do?](what_did_you_do/POST.md) | [`what_did_you_do.mp4`](what_did_you_do/what_did_you_do.mp4) | 40.6 s | −13.9 LUFS | −1.5 dBTP | The plane seatmate who finds the hit piece about him and asks what he did |
| [I took some awesome pictures of me](awesome_pictures_of_me/POST.md) | [`awesome_pictures_of_me.mp4`](awesome_pictures_of_me/awesome_pictures_of_me.mp4) | 43.3 s | −14.0 LUFS | −2.1 dBTP | 54 years old, alone in the gym, caught by the maintenance guy |
| [Please, leave. I can smell you from here](evil_minded_peasant/POST.md) | [`evil_minded_peasant.mp4`](evil_minded_peasant/evil_minded_peasant.mp4) | 21.7 s | −14.0 LUFS | −2.8 dBTP | A Paris perfume shop reverses every word the second it recognises him |
| [Honey, you're fucked](honey_youre_fucked/POST.md) | [`honey_youre_fucked.mp4`](honey_youre_fucked/honey_youre_fucked.mp4) | 24.3 s | −14.1 LUFS | −1.7 dBTP | The one-line verdict on caring what people say |

Every file: 1080×1920, 29.97 fps, H.264 + AAC 192k, −14 LUFS, true peak under the
−1.3 dBTP ceiling. Re-cut with white captions and green `#2ECC71` emphasis;
18+ words ship starred (`F*ck!`, `f*cking`).

## What is in every one of them

The house kit, all of it, checked per post:

- **Full-bleed 9:16** — the vertical window is cut from inside the show's own
  picture frame and tracks the speaker. It is clamped left of x=1610, where the
  broadcaster's burned-in "2 BEARS, / 1 CAVE" bug sits, so the bug can never
  enter the crop even when the speaker is right of frame.
- **Kinetic open** — the opening sentence lands word by word, white, with the
  first content word already green, animating from frame 1.
- **Emphasis ink** — white captions, green `#2ECC71` on the words that carry
  the line, and those words are larger (118 px key / 250 px hero against 96 px
  connective), so the colour is a size cue too, not a tint.
- **Slow push** across the clip; **whip** on any real cut, with a whoosh.
- **End card** — 2 BEARS / 1 CAVE · EP. 344 / FULL EPISODE IN BIO, on the last
  1.5 s, so the clip ends on a card instead of mid-expression.
- **Keyboard typing** on the caption reveal grid — one burst per word, silent
  before the first word and across the end card.
- **18+ words starred** — `F*ck!`, `f*cking`, `f*cked`. Masked in the builder
  after the caption is matched to the transcript, so the word still lands on
  its syllable; guarded by `screen_text` in `motion/qc.py`.
- Grade, voice chain, bed carved out of the speech band, −14 LUFS.

## Why only four

The episode is mostly not clippable under this brief. In order, the first
nineteen minutes are the Shane Gillis / SNL monologue controversy (a named
person's conduct, and the conversation repeatedly quotes a slur in order to
discuss it); 18–22 minutes are the live-streamed execution story (violence,
politics, a disabled man as the punchline); 27–32 minutes are Trump, the press
secretary and George W. Bush (politics as a standalone clip, which the brief
bans); and 62 minutes in there is a sexual comparison that the sexual-content
rule blocks. Those windows are named here so it is obvious they were seen and
rejected, not missed.

What is left is what somebody says about himself: the plane, the gym, the
perfume shop, the party. All four are self-contained, need no earlier context,
and put the button on a line he does not write for himself.

## Posting

[`POST-NOW.md`](POST-NOW.md) has the download links, the copy to paste, the
posting order and the bio check. There is no post URL to give back from this
session: TikTok, Instagram, YouTube and X are not available as connectors here,
so nothing was published - the files and the copy are ready to upload.

## Payout conditions

Every post carries **2 Bears 1 Cave Ep. 344** and **#2BearsWeekly** in the copy
written in its `POST.md`. The episode link goes in the **bio**, once, at account
level: https://youtu.be/3pDAyRLPO58

## Reproduce

    .venv/bin/python scripts/whop/make_2bears.py --picks work/two_bears/picks.json

## What is deliberately not done

- The show's own burned-in subtitles sit in the bottom ~180 px of the panel, so
  the panel is cropped 12% at the bottom before it is placed. Nothing else is
  cropped; nobody is cut out of frame.
- The recogniser's own errors were repaired before the captions were set, not
  after: `caption_corrections.json` lists all six, each one a run of words
  nobody said ("are you dead machine?" -> "are you Bert Kreischer?"). Nothing
  was added or reworded; times do not move.
- Captions are the spoken words only. Fillers are reported by the gate and kept,
  because verbatim is a harder rule than tidy.
- The grade moves the picture 0.9 code values from the reference implementation
  at 3.4× the speed, with skin damped rather than tinted.
