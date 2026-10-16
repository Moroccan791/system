# The style profile

`styles/<campaign>.style.json` is the contract between stage 1 (learn the style)
and everything downstream (captions, edit assembly, export). It is written by
`python -m clipper style <campaign>` and is meant to be **read, diffed, and
hand-edited**: nothing in it is precious, and anything you set by hand wins,
because the merge in `clipper/config.py` only fills in what is missing.

Every field is optional. A profile of `{"captions": {"primary_color": "#FF3B30"}}`
is valid and only changes that one thing.

## Shape

```json
{
  "version": 1,
  "campaign": "example",
  "source":   { "references": ["ref_01.mp4"], "notes": "...", "sample": {"fps": 6, "width": 480} },
  "pacing":   { "avg_shot_len": 2.0, "median_shot_len": 2.0, "cuts_per_minute": 20.0, "confidence": 0.5 },
  "zoom":     { "dominant": "punch_in", "punch_in_scale": 1.12, "punch_in_duration": 0.33, "confidence": 0.88 },
  "transitions": { "in": "cut", "duration": 0.25, "confidence": 0.0 },
  "captions": {
    "present": true,
    "font_family": null,
    "font_weight": "bold",
    "italic": false,
    "casing": "upper",
    "font_size_ass": 104,
    "font_size_uncertainty": 0.32,
    "cap_height_ratio": 0.025,
    "primary_color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 6,
    "shadow": 0,
    "position": { "anchor": "bottom_center", "cx": 0.5, "cy": 0.72, "margin_v": 420 },
    "karaoke": { "enabled": true, "highlight_color": "#FFE14D", "scale_pop": 1.06 },
    "animation": { "in": "none", "duration": 0.12 },
    "max_lines": 1,
    "max_words_per_cue": 3,
    "max_chars_per_line": 16,
    "confidence": 0.86,
    "evidence": { "cue_count": 4, "frames": ["work/<campaign>/style/evidence/ref_01_1.png"] }
  },
  "audio":    { "music_bed": null, "ducking": null, "target_lufs": -22.0, "speech_ratio": 0.0, "confidence": 0.1 },
  "confidence": 0.586
}
```

## Field notes

* **`pacing`** — average and median shot length, plus cuts per minute. Stage 4
  uses it to decide how often to cut a long clip.
* **`zoom`** — `dominant` is one of `punch_in`, `slow_push`, `pull_out`,
  `static`, `mixed`. `punch_in_scale` is the multiplier the reference reaches
  (1.12 = 12 % bigger) and `punch_in_duration` is how long it takes to get there.
* **`transitions.in`** — how one shot arrives after another in stage 4:
  `cut` (default), `fade` (a crossfade, also `dissolve`/`crossfade`), `fade_black`
  (dip through black), `fade_white` (flash), or **any blend ffmpeg's `xfade` can
  do by name** — `wipeleft`, `slideup`, `circleopen`, `zoomin`, `squeezeh`,
  `pixelize`, `hblur`, `diagtr`, `coverleft`, `revealup` … 58 of them, listed in
  `clipper/edit/plan.py` (`FFMPEG_TRANSITIONS`). An unknown word falls back to a
  hard cut and is reported in the plan's `notes`, never silently ignored.
* **`transitions.duration`** — how long a blend lasts, in seconds (default 0.25,
  capped at 0.8 and never more than half the shortest shot). Extraction does not
  measure this yet (see `FEATURES.md` → *D2*): references with hard cuts leave it
  at `cut`, and you can hand-edit it.
* A blend shows two moments at once, so it costs one `duration` of clip length:
  a 16.35 s moment with seven 0.4 s dissolves renders as 13.55 s. The plan says
  so in `clip.blend_shortening`, and every shot carries `out_start`/`out_end` so
  captions can be mapped onto the rendered timeline.
* **`captions.font_size_ass`** — in ASS pixels at 1080x1920. This is the value
  the caption renderer passes to libass, so it can be compared directly with
  `DEFAULT_STYLE`.
* **`captions.font_family`** — always `null` from extraction. Pixels cannot tell
  you which typeface was used. Set it by hand (the repo ships Montserrat in
  `assets/fonts/`) or leave it and take the default.
* **`captions.font_size_uncertainty`** — the honest error bar on the size,
  explained in the profile's `source.notes`. It comes from the font face being
  unknown: cap-height-per-em ranges from about 0.45 to 0.68 across common faces.
* **`captions.karaoke`** — `enabled` is decided by whether a second accent
  colour appears part-way through a cue and spreads across it (that is what
  karaoke looks like). `highlight_color` is that accent.
* **`captions.casing`** — `"upper"` or `null`. `null` means "as written", which
  is what a detector reports when the case cannot be established.
* **`captions.evidence.frames`** — annotated PNGs of what the extractor saw.
  When a measurement looks wrong, look at these first.
* **`audio.speech_ratio` / `music_bed`** — how much of the reference is speech,
  and whether a music bed runs under it. `null` means "could not tell".
* **`confidence`** — per-section, plus an overall number. Anything below about
  0.5 is worth a look before trusting it.

## Hand-editing

The intended workflow is: extract, open the JSON, fix what you know better
(`font_family`, exact `font_size_ass`, brand colours), and re-run stage 3. The
extractor never overwrites a *different* file: re-running `style` replaces the
campaign's profile, so keep hand edits in a separate file if you want to
re-extract, or copy them back afterwards.

## Regenerating evidence

```bash
python -m clipper style mycampaign --fps 8 --width 640   # denser sampling, sharper evidence
python -m clipper style mycampaign --no-evidence         # skip the PNGs
```
