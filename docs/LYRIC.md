# Lyrics: what can actually be set

A lyric file is not just words. It has to be renderable in the chosen face, and
the choice of face is the operator's. This is the short version of what that
means in this repo.

## No face we own has Devanagari

Scanned every `.ttf`/`.otf` under `assets/fonts/` for codepoints in
U+0900–U+097F (Devanagari): **zero glyphs in any face**, including the system
font. So Hindi text set in Couture or Gefika renders as nothing at all — not
tofu, not boxes, nothing. Bangla is the same story.

## So non-English lyrics are romanised

That is the established route here, not a workaround invented under pressure:

| file | script | shipped? |
|---|---|---|
| `bangla.timed.txt` | `AMAR MORAR KARON TUMII` — roman, uppercase | yes, `post2_bangla.mp4` |
| `hindi.txt` | `Deedaar tera milne ke baad hi chhute meri angdaai` — roman | working copy |
| `hindi.deva.txt` | Devanagari | reference only |

Romanised Latin is also what most Hindi reels actually caption in, so this is
not a compromise the audience sees.

## The rules

1. **The operator's wording is the source of truth.** If they send roman, that
   is what is set. If they send Devanagari, romanise it and **show them the
   romanisation before it is cut in** — a transliteration is a decision about
   their words, not a technical detail.
2. **Never reword to make a card fit.** A line that does not fit at the right
   size is a sizing problem, not a licence to edit the lyric.
3. **The lyric is committed** the moment it arrives. `work/` and `footage/` are
   gitignored and a workspace reset takes them; lyrics live in
   `studio/lyrics/`, which is tracked.
4. Line times come from the **track**, measured — never spread proportionally
   across the assumed speech.

## Standing decisions

| video | face | emphasis |
|---|---|---|
| Ghost | Couture | yellow `#FFD125` |
