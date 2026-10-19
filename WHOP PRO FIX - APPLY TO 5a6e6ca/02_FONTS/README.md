# 02 — FONTS FIX

## Diagnosis — why fonts feel unprofessional

You ship 12 font files in `assets/fonts/` (Montserrat, Anton, Archivo Black, Bebas, Inter, Poppins, Outfit, Playfair, Space Grotesk, DejaVuSerif) — amazing library. **But none are actually used.**

`styles/michael_sartain.style.json` has `"font_family": null`. `clipper/config.py` notes: *"font family cannot be identified from pixels — keeping the default; set captions.font_family by hand"*.

So every render falls back to:
- `clipper/config.py` default: `font_family: "Montserrat"` (regular weight)
- `clipper/captions/ass.py` line 48: `font_name = cap.get("font_family") or "Arial"` — if null, Arial.

**Result:** Medium-weight Montserrat (or Arial on some containers) for everything — captions, numbers, quotes. No hierarchy, no pairing, no brand. Looks like Google Docs.

Your `motion/themes/whop.json` has `"fontMode": "sans"` and `"captionStyle": "editorial"` but those only affect the motion HTML layer (`motion/stage.html`), not the clipper caption burn. Motion's `motion/fonts.py` lists packs, but clipper doesn't read them.

**The pro gap:** Pro editors use 2-3 fonts max, each with a job:
- Display (hero numbers: `68%`, `10%`) — heavy, tight
- Body (captions: `SO WOMEN WILL`) — bold, readable at small size
- Accent (quotes: `she literally said…`) — serif italic

You have the files, but no assignment.

---

## The Pro Fix — lock to 3 packs

### Pack A: WHOP Sartain (your current campaign)

| Role | Font file (already in repo) | ASS name | Use | Size rule |
|---|---|---|---|---|
| **Body / Captions** | `Montserrat-ExtraBold.ttf` | `Montserrat Extra Bold` | All caption cues: `SO WOMEN WILL` | 96px, white/black, pop |
| **Display / Numbers** | `Anton.woff2` → convert to TTF or use `ArchivoBlack.woff2` (`Archivo Black`) | `Archivo Black` | Hero numbers only: `68%`, `10%`, `57` — rendered as `poster` motion, not caption | 140px, accent #14E5C5 on ink plate |
| **Serif / Quotes** | `PlayfairDisplay-BoldItalic.woff2` | `Playfair Display` | Quote cards: `"she texted..."` → `serif` motion | 88px italic, #FFFFFF on dark plate |
| **Fallback** | `Inter-Regular.woff2` | `Inter` | Small connective `of`, `with`, `about` if you add editorial hierarchy later | 72px |

### Pack B: MilkXP (playful)

| Role | File | Use |
|---|---|---|
| Body | `Montserrat-ExtraBold.ttf` | Same captions |
| Display | `LuckiestGuy.woff2` (`Luckiest Guy`) | Funny numbers |
| Serif | `Newsreader-BookItalic.woff2` | Rare |

### How to lock it (2 changes)

**1. Fix `assets/fonts/` WOFF2 → TTF for ffmpeg/libass**

libass via ffmpeg `subtitles` filter with `fontsdir` only reliably loads `.ttf/.otf`, not `.woff2`. Your folder has 9 woff2 + 4 ttf. Convert once:

```bash
# On your machine (one time):
for f in assets/fonts/*.woff2; do
  woff2_decompress "$f"  # or use fonttools: pip install fonttools brotli && ttfs=$(python -m fontTools.ttLib.woff2 decompress ...)
done
# Result: Anton.ttf, ArchivoBlack.ttf etc. beside the woff2
```

Or simply tell clipper to use the TTFs you already have: `Montserrat-ExtraBold.ttf` + `DejaVuSerif-Bold.ttf` as interim. The patch below does that.

**2. Set `font_family` in every style profile (not null)**

Edit `styles/michael_sartain.style.json`:
```json
"captions": { "font_family": "Montserrat Extra Bold", ... }
```

And create `motion/themes/sartain_pro.json` (drop-in):
```json
{
  "name": "sartain_pro",
  "accent": "#14E5C5",
  "ink": "#0B0E11",
  "paper": "#FFFFFF",
  "fontPack": "sartain",
  "captionStyle": "editorial",
  "transitionOrder": ["cut", "fade_black"],
  "fonts": {
    "body": "Montserrat Extra Bold",
    "display": "Archivo Black",
    "serif": "Playfair Display"
  }
}
```

Wire it in `clipper/captions/render.py:subtitles_filter()` — it already passes `fontsdir=config.FONTS`, so once TTFs exist, libass will find them. Verify with:
```bash
python -m clipper doctor  # checks fonts
fc-match "Montserrat Extra Bold"  # should resolve to assets/fonts/Montserrat-ExtraBold.ttf
```

### The old `whop video editing system v2/03_FONTS_TRANSITIONS` advice was generic

It said "Display + Body + Mono pairing" — correct principle, but didn't point at your actual 12 files or the `null` bug. This fix does.

---

## Patch files

- `font_lock.json` — theme snippet to copy into `motion/themes/`
- `woff2_to_ttf.sh` — one-time conversion script
