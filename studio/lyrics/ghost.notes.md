# Ghost — the brief

The words are the operator's, copied exactly. Any difference between this file
and `ghost.txt` is a mistake in this file, not in the lyric.

## Decisions, made by the operator

| what | choice | when |
|---|---|---|
| system | **reference1** (the house system) | 2026-10-24 |
| face | **Couture** | 2026-10-24 |
| emphasis | **yellow** on the emphatic words | 2026-10-24 |
| accent colour | `#FFD125` — already in `family.json`, unchanged |  |

## Shape of the song

11 lines in three breaths:

    verse    2 lines   I miss your touch / I know you crossed a bridge
    turn     2 lines   Since the love / I want you to know
    chorus   7 lines   That if I can't be close ... more than life (×3)

The chorus repeats **"I miss you more than life" three times** — a 4-line body,
then the hook twice. That repetition is the spine of the edit: the three
deliveries are the same sentence at three different pressures, so they should not
be set the same way. First one lands on the drop, the second is the held one, the
third is the one that costs something.

## Where the yellow goes

Not every line needs it, or the colour stops meaning anything. The words that
carry the meaning with the most weight:

| line | emphasised |
|---|---|
| I miss your touch on nights when I'm **hollow** | hollow |
| I know you crossed a bridge that I can't **follow** | follow |
| Since the love that you left is all that I **get** | get |
| I want you to **know** | know |
| That if I can't be close to **you** | you |
| I'll settle for the **ghost** of you | ghost |
| I miss you **more than life** | more than life |
| And if you can't be next to **me** | me |
| Your memory is **ecstasy** | ecstasy |
| I miss you **more than life** | more than life |

`hollow` / `follow` are the rhyme, and setting both is what makes the couplet
read as one thought. `ghost` is the title of the song in one word. `ecstasy`
is the only abstract word in the chorus, so it is the one that can take colour.

## Still needed

- the video (scenepack)
- the audio (the cut to music)
- the line times, once there is audio to measure — taken from the track, not
  guessed, the way every other edit in this house has been timed

## delivery (v9, 2026-10-26)
- **no sound design.** reference1 renders now default to `sfx=False`; the v8
  cut had 21 cues (9 whoosh, 8 tick, riser, impact, sub-drop, swell) mixed
  under the vocal. `--sfx` brings them back if ever wanted.
- 1920x1080, crf 22, ~8 Mb/s. v8 was 1280x720 at 620 kb/s — softer than the
  source pack itself (which is 1.2 Mb/s).
- the 1080p OOM is fixed at the cause: `compose.decode_segment` held each cut
  twice (bytes + copies); it now reads into one bytearray and returns views.
