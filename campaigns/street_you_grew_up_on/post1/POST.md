# Post 1 — Demi Lovato · v6.2 (fade outro)

> **Review cut, not approved for posting.** The font/colour combination is
> the one saved in `style.json` (Inter Regular captions, Newsreader Book
> Italic keywords, Montserrat Italic diagram, Outfit Semibold outro; teal
> `#14E5C5`). The same per-video chooser is available for every new clip
> (`scripts/whop/style_card.py serve --video post2 …`).

## v6.2 — what changed from v6.1

- **Fade outro.** The speaker stops, the picture fades to black over the
  last 0.5 s, and the end card dissolves in with the fade rather than
  stopping dead. The fade lives in the engine (`motion/stage.html`,
  `TL.fadeOut`), so every clip ends the same way.
- The end card itself still appears hard (QC: no semi-transparent text
  for more than 2 frames) — the resolution is the picture's fade, not a
  slow dissolve of the card.
- Re-render: PASS at level 0 (MOTION QC v2, 15 checks) and PASS on the
  whop invariants (dead air 0, change rate 26.6/10 s, face-first open).
  Sound: −14.05 LUFS integrated, true peak −1.95 dBTP.

## v6.1 — the approved workflow (kept for reference)



> **Review cut, not approved for posting.** The font/colour combination in
> `street_post1_v6.mp4` is a provisional proposal (Inter Regular captions,
> Newsreader Book Italic keywords, Montserrat Italic diagram, Outfit Semibold
> outro; teal `#14E5C5`). Choose the type and ink for **this post** in the
> live per-video style card before the approved render. Earlier post1/v4/v5
> files in this folder are superseded demos, not approval.

- **Video:** [`street_post1_v6_2.mp4`](street_post1_v6_2.mp4) — 21.8 s, 1080×1920,
  30 fps, supplied episode footage only; 48 kHz AAC music/voice master.
- **Earlier cuts:** `street_post1_v6.mp4` (v6), `street_post1_v6_1.mp4`
  (v6.1, the approved workflow) — superseded by v6.2.
- **Review cover:** [`cover_v6.jpg`](cover_v6.jpg) (from the cut, no generated imagery).
- **Source window:** episode 45:59.4–46:30.235. All 64 kept spoken words are
  represented: 60 in word-synced editorial captions; BUSY / SANE / FOCUSED /
  STRUCTURE are speech-synced inside a full-screen motion diagram. The
  award is *crossed out*, not celebrated. The CONNECTION scene cuts cleanly
  off her face and sits under the thesis, followed by a hard-cut outro.
- **QC:** picture PASS level 0; sound PASS at approximately −14.0 LUFS and
  true peak below −1 dBTP. QC is a technical gate, **not** the user's look approval.

## Title
Demi Lovato: I Don't Come Home to an Award

## Description — copy after approval
#ad
Demi Lovato says her craft keeps her busy, sane and focused. But home means her dogs and husband, not an award. What's important in life is connection.

The podcast name is Street You Grew Up On - full episode is available on YT and other podcast platforms

## Hashtags (8)
#DemiLovato #StreetYouGrewUpOn #PodcastClips #DemiLovatoInterview #PodcastMoments #SelfReflection #Connection #MusicAndLife

## Rebuild notes for the editor (nothing needed from the viewer)

- Per-video chooser: `scripts/whop/style_card.py serve --campaign
  street_you_grew_up_on --video post1 --port 8010 --preview
  work/style_card/face.jpg`; user selection is saved in `post1/style.json`.
- Base spec: `scripts/whop/specs/street_post1_v6.json`; re-create
  `work/street/raw/street_full.mp4` from the tracked `origin/footage` episode
  parts if a workspace reset removes it, then run `tight_base.py` on the spec.
- Re-author timeline after changing the style with
  `scripts/whop/build_street_post1_v6.py`; validate; render using
  `--theme street_you_grew_up_on__post1 --music assets/music/chill.wav`.
- Campaign requirements: [`../brief.md`](../brief.md). No visible
  “ILLUSTRATIVE” label, generated photo, marker swipe or pink accent.
