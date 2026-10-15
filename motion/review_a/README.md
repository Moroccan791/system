# Stage A review pack — regeneration recipe (reset-proof)

Videos: `milk_grade_stageA.mp4` (10s), `milk_budget_stageA.mp4` (28.8s),
`sartain_stageA.mp4` (12.6s) — all QC v2 12/12 PASS (`*_qc.txt`).
Audit: `../AUDIT.md`. If the sandbox resets, everything regenerates:

## Sources (from `origin/main`, media is never re-committed)

```bash
git show "origin/main:campaign 2/MilkPEP_milkXP_Episode3_YT_16x9.mp4" > work/src/milk_ep3.mp4
git show "origin/main:campaigns/michael_sartain/raw/YTDown.com_YouTube_Media_XrdXKjTOQBg_Women-Are-Shocked-By-The-Reality-Of-Dating-For-Men_002_720p.mp4" > work/src/sartain.mp4
```

## Bases (1080x1920 @30fps)

- grade: ep3 `-ss 550.95 -to 560.95`, `crop=607:1080:680:0,scale=1080:1920,fps=30`
- budget: ep3 `121.60–136.04` crop `607:1080:820:0` + `142.81–157.17`
  crop `607:1080:1026:0`, each scaled, concat `-c copy` (865→866 fr ok)
- Sartain: `-ss 30 -t 12.6`, `crop=405:720:671:0,scale=1080:1920,fps=30`

## Transcripts

`python -m clipper transcribe <base> --asr moonshine` — on the EPISODE
transcribe a 30s+ slice and offset (short files drift ~200ms).
Cleanup applied: ASR "Nay" → "an A" in the grade transcript.
Timelines in `../timelines/` are already synced to these transcripts.

## Render (per job)

```bash
.venv/bin/python motion/transitions.py work/<job>/base.mp4 motion/timelines/<t>.json work/<job>/timeline_fx.json
.venv/bin/python motion/validate.py work/<job>/timeline_fx.json
(cd motion && node render.mjs ../work/<job>/timeline_fx.json ../work/<job>/frames)
.venv/bin/python motion/composite.py work/<job>/base.mp4 work/<job>/frames work/<job>/timeline_fx.json work/<job>/final.mp4
.venv/bin/python motion/qc.py work/<job>/timeline_fx.json work/<job>/transcript.json work/<job>/final.mp4 work/<job>/frames
.venv/bin/python motion/composite.py --sheet work/<job>/final.mp4 work/<job>/timeline_fx.json work/<job>/pack
```

Timelines: `../timelines/milk_grade_10s.json`,
`../timelines/milk_budget_stage2.json`, `../timelines/sartain_stage_a.json`.
