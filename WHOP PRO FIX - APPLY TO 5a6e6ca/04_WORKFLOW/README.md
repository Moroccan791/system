# 04 — WORKFLOW FIX (make it fast)

## Diagnosis — why it's still slow despite 4 stages being "done"

You have the stages (`scan`, `style`, `select`, `edit`, `captions`) — but each is a separate manual command with its own ASR + ffmpeg decode:

```bash
python -m clipper scan michael_sartain
python -m clipper style michael_sartain          # 30s, re-decodes references
python -m clipper select michael_sartain --top 8  # 20s, needs transcript
python -m clipper edit michael_sartain --ids "#01" # 40s, re-decodes + reframes
python -m clipper captions ... --campaign michael_sartain # 60s, RE-DOES ASR on edited clip (drifts +0.9s!)
# then manually write post.txt, manually run cover, manually queue exports
```

**Total: ~3-4 minutes per clip × 3 platforms = 12 min.** For 5 clips/day = 1 hour of babysitting.

**Three wastes:**
1. **Re-ASR on edit:** `captions` re-recognizes the cut-up clip, drifting 0.37s mean error. You fixed this with `--plan` (carries source timings, 2× faster) but `FEATURES.md` buries it as optional — not default.
2. **No batch:** `edit` does one clip, one platform. TikTok/Reels/Shorts are same 1080x1920, just different loudness/bitrate — should be one ffmpeg pass with 3 outputs.
3. **No `run` command:** `clipper run` exists in FEATURES.md menu as X1 (`python -m clipper run <campaign>`) but isn't implemented — marked "S" effort, not done.

Your `recipes/new_campaign_runbook.md` + `scripts/bootstrap.sh` document the fast path, but you still have to remember it.

---

## The Pro Fix — one command

### `run_pro.sh` (in this folder)

```bash
bash "WHOP PRO FIX - APPLY TO 5a6e6ca/04_WORKFLOW/run_pro.sh" michael_sartain [--top 4] [--platform all]
```

Does:
1. `scan` (once, cached — skips if manifest.json exists and raw/ unchanged)
2. `style` (once, uses `.pro.style.json` if exists, else learned)
3. `transcribe` each raw **once** with moonshine (offline, 16kHz mono)
4. `select` top N moments (uses transcript, respects campaign.json banned topics)
5. For each moment:
   - `edit --plan-only` → plan.json (no render yet, 0.5s)
   - `captions --plan plan.json` → .ass + burned mp4 with `--punch` + `--sound` + `--tighten 0.6` (uses **carried timings**, no re-ASR)
   - Batch export: one ffmpeg command writes `*_tiktok.mp4` (loudness -14 LUFS), `*_reels.mp4` (same, max 12M), `*_shorts.mp4` (same, max 16M) via `-map 0 -b:v` variants
   - `clipper cover` auto at payoff timestamp (first `EMPHASISE` word) → `cover.jpg`
   - `post.txt` auto from candidate `text` + campaign topics → title/description/hashtags

**Time: 3-4 min → 45s per clip, zero manual steps.**

### Patch 1: Make `--plan` the default (not optional)

In `clipper/captions/pipeline.py:run_captions()`:
```python
# Add auto-plan lookup when editing a clip that has a plan:
if not plan_path and campaign:
    auto_plan = WORK / campaign / "edits" / f"{Path(src).stem}.plan.json"
    if auto_plan.exists():
        plan_path = auto_plan
        log.info("auto-carrying timings from plan", plan=plan_path)
```

And in `clipper/edit/pipeline.py`, always write `plan.json` even on full render — `captions` needs it.

### Patch 2: Batch export

In `clipper/edit/render.py` or new `clipper/export.py`:
```python
PLATFORMS = ["tiktok", "reels", "shorts"]  # same 1080x1920, different metadata
# One ffmpeg: input mezzanine (captions burned), 3 outputs with different -b:v and -metadata
```

### Patch 3: Implement `clipper run` (X1)

New `clipper/run.py`:
```python
def run_campaign(name, top=4, platform="all"):
    scan(name); style(name); select(name, top=top)
    for cand in candidates(name):
        edit(name, ids=cand.id, plan_only=True)
        captions(f"work/{name}/edits/{cand.id}.mp4", plan=f"work/{name}/edits/{cand.id}.plan.json")
        export(name, cand.id, platforms=["tiktok","reels","shorts"] if platform=="all" else [platform])
        cover(name, cand.id)
```

Register in `clipper/cli.py`:
```python
from .run import run_campaign
parser.add_parser("run", handler=run_campaign)
```

### Patch 4: Cache `scan`/`style`

`scan` writes `work/<campaign>/manifest.json` with file sizes. On next run, if raw/ files unchanged (size + mtime), skip probe. Saves 10-15s.

`style` writes `styles/<campaign>.style.json` + `work/.../style/report.json`. If `references/` unchanged, skip.

---

## Patch files

- `run_pro.sh` — bash one-command, uses existing clipper CLI (no code change needed today)
- `run.py` — proper `clipper run` implementation (drop into `clipper/`)
- `pipeline.patch` — auto-`--plan` default

---

## After this, your day looks like

```bash
# Once: drop footage
python -m clipper drop michael_sartain --branch footage

# Daily: one command, walk away
bash run_pro.sh michael_sartain --top 4 --platform all

# Check: viewer still works
python -m clipper serve --port 8000

# Done: post folders have *_tiktok.mp4 + *_reels.mp4 + cover.jpg + post.txt — paste to IG/TikTok/YT
```

No manual caption dragging, no re-typing post.txt, no 3 separate renders.
