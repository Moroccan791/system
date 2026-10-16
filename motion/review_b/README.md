# Stage B review pack — Part 2: image quality

One test video affected: `milk_budget_stageB.mp4` (28.8 s, MILK XP Ep. 3
budget scene). Stage-1 and Sartain videos have no generated-image slots
(Sartain's timeline contains no PiP/B-roll), so their Stage-A renders
stand unchanged — nothing they depend on was modified in Stage B.

## What changed vs Stage A

The two illustrative images in the stage-2 timeline were re-sourced
through the new `motion/images.py` pipeline instead of one-off picks:

| slot | timeline | sentence | chosen candidate |
|---|---|---|---|
| `hoop` (PiP, 58% w) | 7.1–9.35 s | "We need a basketball hoop for the lounge" | `hoop/cand3_wide.jpg` |
| `led` (B-roll, full-bleed) | 15.95–17.65 s | "Crazy LED lights set the vibe" | `led/cand2_medium.jpg` |

Pipeline per slot: prompt = sentence subject + rotating camera framing
(consecutive slots never share a look) + the base video's measured
lighting ("warm indoor light") and palette ("muted earthy tones") +
fixed photoreal style suffix and negative prompt (no text, no logos, no
staged/stock look). 4 candidates per slot, gated on resolution (upscale
flagged — all 8 candidates arrived 768×1376), Laplacian sharpness ≥ 45,
highlight/shadow clipping ≤ 12%, palette ΔE ≤ 38 against the video.
Best passing candidate wins (sharpness, then palette), then the video's
own grade is matched back onto it (Reinhard Lab transfer at 45%
strength + gaussian grain at the video's measured σ) and it is
subject-cropped (peak-detail anchor) to the slot's target size.

All 8 candidates, the scores, and the graded chosen files are in
`images/` (`images_sheet.jpg` is the contact sheet).

## ⚠ CLIP relevance — unavailable, declared

The spec asks for CLIP image↔sentence relevance scoring (≥7/10). CLIP
weights cannot be downloaded in this sandbox (both
`huggingface.co` and `openaipublic.azureedge.net` are egress-blocked;
only github/npm/pypi are reachable), so no relevance score is faked:
`scores.json` records `clip_relevance: null` with the note
"CLIP UNAVAILABLE", and **every generated image is flagged
`needs_user_review: true`**. The numeric gates above still ran; the
relevance call is yours. (Agent pre-screen by eye: both chosen frames
show exactly the spoken subject — a wall-mounted hoop in a lounge; a
lounge lit by LED strips.)

## Result

`milk_budget_stageB_qc.txt`: **QC v2 PASS 12/12**, same single standing
WARN as Stage A (counter accent digits 3.2:1, carried by the 3 px dark
stroke). The `images` check reports both slots as generated +
ILLUSTRATIVE-labelled (badge burned into the render by the engine).

## Regenerate

```bash
# candidates: 4 images per slot dir via the image generator, framed as
# printed by:  python motion/images.py --prompts <slots.json> <base.mp4>
.venv/bin/python motion/images.py work/stage_b/slots.json \
    work/stage2_test/base.mp4 motion/review_b/images
cp motion/review_b/images/hoop__chosen.jpg motion/test_assets/hoop_b.jpg
cp motion/review_b/images/led__chosen.jpg  motion/test_assets/led_lounge_b.jpg
.venv/bin/python motion/transitions.py work/stage2_test/base.mp4 \
    motion/timelines/milk_budget_stage2.json work/stage2_test/timeline_fx.json
.venv/bin/python motion/validate.py work/stage2_test/timeline_fx.json
LD_LIBRARY_PATH=/tmp/al2023/lib node motion/render.mjs \
    work/stage2_test/timeline_fx.json work/stage2_test/frames
.venv/bin/python motion/composite.py work/stage2_test/base.mp4 \
    work/stage2_test/frames work/stage2_test/timeline_fx.json \
    work/stage2_test/final.mp4
.venv/bin/python motion/qc.py work/stage2_test/timeline_fx.json \
    work/stage2_test/transcript.json work/stage2_test/final.mp4 \
    work/stage2_test/frames
```
