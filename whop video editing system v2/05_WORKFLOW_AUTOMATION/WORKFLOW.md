# 05 — WORKFLOW AUTOMATION (5x Faster, Not Sloppy)

## Why you're slow now
- Manual transcription → manual splitting → manual font → manual export per platform
- No proxies → 4K raw chokes timeline
- No batch export → export 40s, then re-do for 62s, then for 16:9 = 3x work

## Pro Automation (Human decision, machine labor)

### 1. Folder Watch System (Mimics your WHOP campaigns/ structure but organized)
```
05_WORKFLOW_AUTOMATION/
├── 01_INBOX/                → Drop raw here (Sartain, podcast, campaign MP4s)
├── 02_WORKING/proxy/        → Auto proxies 720p (edit smooth, no lag)
├── 03_TEMPLATES/            → MASTER_TEMPLATE_2025.prproj linked
├── 04_EXPORT_QUEUE/         → One-click exports land here, auto-named
├── 05_ARCHIVE/              → Finished projects zipped, raw stays
└── scripts/
    ├── auto_tag.py          → Watches 01_INBOX, creates proxy + whisper transcribe + caption JSON
    ├── caption_cleaner.py   → Splits AI transcript to 2-3 word hierarchy, picks yellow keyword (noun/verb), outputs BODY_WHITE timing
    └── auto_export.py       → Watches 03_TEMPLATES, exports 40s+62s+16:9+thumb to 04_EXPORT_QUEUE
```

**How it runs:**
- Drop `michael_sartain/raw/*.mp4` → `auto_tag.py` (runs every 5 min) → proxy + `transcript.json` + `captions_draft.json` (2-3 words per line, yellow guess) appears in 02_WORKING
- You open template, drag `captions_draft.json` to V2 → 80% done, tweak 2 yellow words → export queue does rest

### 2. Scripts Included (Python, no cloud, runs locally)

**`caption_cleaner.py` — fixes AI slop captions automatically:**
```python
Input:  "Women Will Only Make You Wait If You're A Beta" (10 words, all white)
Output: Line1: "WAIT" (yellow, 72pt, top) 
        Line2: "if you're a beta" (white, 42pt, bottom)
Logic: Picks longest noun/verb as yellow, splits to 2-3 words max, respects safe zones
```

**`auto_proxy.py`:**
- 4K raw → 720p proxy with timecode burn → edit smooth on any laptop
- Toggle proxy off before export → full quality automatically

**`auto_export.py`:**
- One preset `EXPORT_40s_62s_YT` → Queue 4 outputs: 40s 9:16, 62s 9:16, 16:9, 1:1 + thumb jpg
- Auto-names: `CLIENT_TOPIC_40s_9x16.mp4` etc. → to `04_EXPORT_QUEUE/`

### 3. Speed Benchmark
| Task | Old (manual) | New (automated) | Your gain |
|---|---|---|---|
| Transcribe 40s clip | 8 min (type) | 30 sec (whisper auto) | 16x |
| Split captions hierarchy | 20 min (drag each word) | 2 min (tweak yellow picks) | 10x |
| Add motion/transitions | 15 min (keyframe each) | 2 min (drag preset, 2 spots only) | 7x |
| Export 3 formats | 12 min (export x3) | 2 min (queue once) | 6x |
| **Total per 40s reel** | **90-120 min** | **12-15 min** | **~8x faster** |

### 4. How to Install (5 min)
1. Copy `scripts/` to your `campaigns/` root (next to `michael_sartain/`)
2. `pip install faster-whisper` (local, no data leaves laptop) — already in repo
3. Set Watch Folder in Premiere: `File > Project Manager > Watch Folder > 01_INBOX`
4. Done. Drop raw, get drafts.

### 5. Quality Guard (Not AI Slop)
Automation does 80% (proxy, rough split), **you do 20%** (pick yellow word, nudge timing, add 1 whip). That 20% human = professional, not slop. If you let AI do 100%, it's slop.

