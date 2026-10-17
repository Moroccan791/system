# Step 1 teardown — your reference edits vs our Street post1

Measured 2026-10-17, frame strips + automated metrics (face boxes, scene cuts,
silence detection, loudness). Frame strips live in `recipes/teardown_sheets/`.
"OURS" below = the current post1 template (v2). The version actually posted
earlier (v1) was the same base/captions minus the hook slate, balloon and music.

## The numbers

| | REF1 | REF2 | REF3 | REF4 | **OURS** |
|---|---|---|---|---|---|
| Length | 17.9s | 12.3s | 30.1s | 27.6s | **33.6s** |
| Visual cuts / changes per 10s | 5.0 | 5.7 | 8.7 | 2.2 | **2.4** |
| Pauses >0.25s left in the speech | **0** | **0** | **0** | **0** | **13 (7.0s total, longest 1.0s)** |
| Face width (median, % of frame) | 44% | 61% | ~40%* | 44% | 46% |
| First frame | face, mid-sentence | face, mid-sentence | face, mid-sentence | face, mid-sentence | face — then a black title card covers it for 1.6s |

*REF3's speaker is smaller in frame; the gap there is made up by giant text.

Loudness is identical everywhere (≈ −14 LUFS) — sound level was never the issue.

## The differences that matter, in the order a viewer's thumb feels them

1. **The open.** All four references are on the speaker's face, mid-line, with
   captions already moving at 0.0s. Ours (v1, as posted) opened mid-sentence on
   a quiet thoughtful line; v2 opens face → black slate → face. A full-screen
   text card with no person in it, in second 1, is a skip trigger. The refs'
   first *cut* lands at 1.0–2.2s; ours sits in one shot for 20 seconds.

2. **Dead air — the biggest measurable gap.** Across 88 seconds of references
   there is not one pause longer than 0.25s. Every breath is cut. Ours kept
   7 seconds of pauses (21% of the runtime), because I edited it like a
   documentary: "clean in, clean out." On a feed, a 0.7s pause with nothing
   happening *is* the swipe moment. This alone can explain most of the 70%.

3. **Caption scale and placement.** Ref captions live at chest/centre height,
   where the eyes already are, and keyword words are *huge* (a third of the
   frame wide in REF3; giant serif heroes in REF2). Words pop one or two at a
   time and *build*. Ours are small sentence-case lines down at the bottom
   (text zone ≈ 0.78 height), arriving a phrase at a time — subtitle energy,
   not headline energy.

4. **Something new every 1–3 seconds.** REF1: counter cards (8 → 10 Years),
   a diagram, house photos pinned on screen, a lifestyle B-roll cutaway.
   REF2: full-screen typography posters, a film clip insert, a numbered list.
   REF3: cash graphics, "$1.4 MILLION" / "$20,000 CASH" stat plates that
   upgrade as he talks. REF4: evidence photos inset over the speaker every
   few seconds, a timer, a map. Ours: one shot, captions, one balloon card
   at 26s, end card. Same visual idea for 20+ seconds at a time.

5. **Camera energy.** Refs are 60fps with whip-pans, speed ramps and
   punch-zooms on beats (REF3's first frame is motion-blurred). Ours is a
   single gentle push-in at 30fps — invisible in practice.

6. **Length.** Refs: 12–30s. Ours: 33.6s of one slow answer.

## The uncomfortable part

Our own engine already has most of the refs' devices — big-word posters,
counters, cards, lists, photo/B-roll inserts, zoom punches. In post1 I used
the calmest slice of them (bottom captions, gentle push, one card) and
measured the result against my internal QC checklist (sync, contrast,
face-zones, loudness) — all of which passed — instead of against these four
videos. The gap is not tooling. It's directing: **cut the air out, open on
the face mid-line, put big words in the middle of the frame, and change the
picture every couple of seconds.**

What this teardown does *not* prove: that copying the style guarantees
views on a fresh account. It proves our clips were losing the first two
seconds on craft, which is the part that's ours to fix.
