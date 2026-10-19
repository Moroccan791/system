# 04 — TEMPLATES & PRESETS (Speed System)

## The Goal: 40s video in 12 minutes, not 2 hours

### Template Structure (One Template = Every Output)
We give you ONE Premiere Pro project + ONE CapCut project that outputs everything:

```
MASTER_TEMPLATE_2025.prproj / capcut_template.cap
├── Sequence 01: 9:16_40s (IG Reels)
├── Sequence 02: 9:16_62s (TikTok/YT, automatically extends 40s with 2 beats)
├── Sequence 03: 16:9_YT (horizontal, same captions reflow to bottom)
├── Sequence 04: 1:1_SQUARE (feed post, auto crop)
└── Sequence 05: PODCAST_H_REELS (3 clips + auto lower third)
```

**Inside each Sequence:**
- Track V1: B-roll / Main footage (with 103% push preset)
- Track V2: Captions (HOOK_YELLOW / BODY_WHITE / PUNCH_BIG mogrts linked to text)
- Track V3: MG (Lower Third / Callout / End Card)
- Track A1: VO / Main audio (ducked)
- Track A2: Drone music (C-minor, auto-duck -6dB)
- Track A3: SFX (click/whoosh, linked to caption markers)

**Change text in ONE place (Essential Graphics panel) → updates all sequences.**

### Presets Included

| Preset File | What it does | Import to |
|---|---|---|
| `CAPTION_HOOK_YELLOW.mogrt` | Big yellow hook, slide-up 10f | Premiere Essential Graphics |
| `CAPTION_BODY_WHITE.mogrt` | White body + yellow emphasis logic | Premiere |
| `CAPTION_PUNCH.mogrt` | 110pt hold 2s, heavy shadow | Premiere |
| `LOWER_THIRD_SARTAIN.mogrt` | Guest name + title, slide 12f | Premiere |
| `TRANS_WHIP_10f.prfpset` | 10f directional blur, presets left/right | Premiere Effects > Presets |
| `COLOR_MOODY_LUT.cube` | Muted purple/black crush, matches butterfly/Pi palette | Lumetri |
| `EXPORT_40s_62s_YT.epr` | One-click export queue: 9:16 40s + 62s + 16:9 + thumbnail | Media Encoder |

**CapCut Equivalent:** Same names with `.capcut_template` in `capcut/` subfolder — drag to Timeline > Save as Favorite.

### How to Make a New Video (12 min Total)

**Step 1 — Ingest (1 min):**
- Drop raw podcast/Sartain clip or AI art into `05_WORKFLOW_AUTOMATION/01_INBOX/`
- Run `auto_tag.py` → auto-creates proxy 720p + transcribes + splits to 2-3 word caption files

**Step 2 — Template (2 min):**
- Open `MASTER_TEMPLATE_2025.prproj` → Duplicate `9:16_40s` sequence → Rename `CLIENT_4000Weeks_40s`
- Drag proxy to V1 (auto-scales) → Drag caption file to V2 (auto-populates with BODY_WHITE, yellow on nouns)

**Step 3 — Polish (7 min):**
- Fix 2-3 yellow emphasis words (the only manual part) → nudge timing ±3 frames if pop off-beat
- Add 1 Whip on calendar reveal + 1 Camera Push on "4000 weeks" → drag preset, done
- Check lower third for guest name (if podcast)

**Step 4 — Export (2 min):**
- File → Export Queue → `EXPORT_40s_62s_YT` → hits 4 outputs + thumbnail in one go to `07_publish/`
- Auto-upload draft to Drive/WHOP preview via `auto_upload.py`

**Old way:** 90-120 min (manual captions, manual scale, manual export 3 times)
**New way:** 12 min (template does 80%)

### Where to Download
- All `.mogrt` and `.prfpset` are linked in `05_WORKFLOW_AUTOMATION/assets/links.txt` (Google Drive, 45MB total)
- Or generate locally: we include After Effects `.aep` to edit colors/fonts yourself — change yellow #FFD60A → your brand color in 1 file, all templates update

### Speed Guarantee
If a 40s edit still takes >20 min after template, you're customizing too much. Use hard cuts, 2 transitions max, 1 yellow word per sentence. Done is pro.

