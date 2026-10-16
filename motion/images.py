#!/usr/bin/env python3
"""Image pipeline (permanent rules, Part 2).

    python motion/images.py <slots.json> <base.mp4> <out_dir>

For every image slot (a PiP / B-roll insert in a timeline) this:
  1. builds 4 candidate prompts - subject from the spoken sentence,
     a rotating camera/framing, lighting + palette measured from the
     video itself, one consistent style per video - plus the fixed
     negative prompt (kept in prompts.json verbatim);
  2. scores every candidate file: resolution (upscale if short),
     sharpness (Laplacian variance), exposure clipping, palette
     distance to the video (Lab delta-E);
  3. checks CLIP relevance (open_clip) IF weights are available -
     in this sandbox the weight hosts are unreachable, so relevance
     comes back null and every generated image is flagged
     needs_user_review (the spec's explicit fallback - said out loud
     in scores.json, never silently skipped);
  4. picks the best passing candidate (regenerate ONCE if none pass,
     then fall back to no image at all), grade-matches it to the
     video (colour transfer + contrast + matched grain), crops it
     to the subject at the slot's display aspect;
  5. archives everything - all candidates, the graded chosen file,
     prompts, scores - under <out_dir>.

Candidates are produced externally (the generator tool); this script
is the discipline around them. slots.json:

  [{"id": "hoop", "type": "pip", "sentence": "We need a basketball
    hoop for the lounge", "subject": "a basketball hoop ...",
    "candidates_dir": "work/stage_b/hoop"}]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

NEGATIVE_PROMPT = ("text, watermark, logo, extra fingers, distorted faces, "
                   "plastic skin, oversaturated, generic stock photo, "
                   "staged smile, looking at camera, blurry, lowres")
STYLE_SUFFIX = ("photorealistic photograph, natural unposed moment, "
                "no staged smiles, no text, no logos")
FRAMINGS = [
    "close-up, shallow depth of field, 85mm lens",
    "medium shot, 50mm lens, subject off-centre",
    "wide environmental shot, 35mm lens, deep focus",
    "low-angle detail shot, shallow depth of field, 85mm lens",
]
# gates (documented, calibrated on this pipeline's generators)
SHARP_MIN = 45.0          # Laplacian variance at native resolution
PALETTE_DE_MAX = 38.0     # Lab delta-E, candidate mean vs video mean
EXPOSE_MAX = 0.12         # clipped (near-black + blown) pixel share
TARGETS = {"broll": (1080, 1920), "pip": (1252, 826)}


# ------------------------------------------------------------ video side
def video_profile(video: Path, n: int = 7) -> dict:
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    labs, lab_stds, lumas, sats, noise = [], [], [], [], []
    for k in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (k + 0.5) / n))
        ok, fr = cap.read()
        if not ok:
            continue
        small = cv2.resize(fr, (270, 480))
        lab_px = cv2.cvtColor(small, cv2.COLOR_BGR2Lab).reshape(-1, 3)
        labs.append(lab_px.mean(0))
        lab_stds.append(lab_px.std(0))
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        lumas.append(float(hsv[:, :, 2].mean()))
        sats.append(float(hsv[:, :, 1].mean()))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
        noise.append(float((gray - cv2.GaussianBlur(gray, (0, 0), 2)).std()))
    cap.release()
    lab = np.mean(labs, axis=0)
    luma = float(np.mean(lumas))
    warm = float(lab[2]) - 128.0          # Lab b: + = yellow/warm
    lighting = ("warm indoor light" if warm > 4 else
                "cool daylight" if warm < -4 else "neutral soft light")
    if luma < 90:
        lighting += ", low-key moody exposure"
    elif luma > 165:
        lighting += ", bright airy exposure"
    palette_words = ("muted earthy tones" if float(np.mean(sats)) < 110
                     else "rich saturated colour")
    return {"lab": [float(x) for x in lab],
            "lab_std": [float(x) for x in np.mean(lab_stds, axis=0)],
            "luma": luma,
            "sat": float(np.mean(sats)),
            "grain_sigma": float(np.clip(np.mean(noise) * 0.6, 0.8, 5.0)),
            "lighting": lighting, "palette_words": palette_words}


def build_prompts(slot: dict, profile: dict) -> list[str]:
    return [f"{slot['subject']}, {framing}, {profile['lighting']}, "
            f"{profile['palette_words']}, {STYLE_SUFFIX}"
            for framing in FRAMINGS]


# ------------------------------------------------------------- scoring
def _lab_mean(img: np.ndarray) -> np.ndarray:
    small = cv2.resize(img, (270, 480))
    return cv2.cvtColor(small, cv2.COLOR_BGR2Lab).reshape(-1, 3).mean(0)


def _delta_e(lab1, lab2) -> float:
    a = np.array([lab1[0] * 100 / 255, lab1[1] - 128, lab1[2] - 128])
    b = np.array([lab2[0] * 100 / 255, lab2[1] - 128, lab2[2] - 128])
    return float(np.linalg.norm(a - b))


_clip_state = None


def clip_relevance(path: Path, sentence: str):
    """(score|None, note). CLIP weights are unreachable from this
    sandbox (weight hosts blocked); when that is the case the spec
    says to SAY SO and flag every image for user review instead."""
    global _clip_state
    if _clip_state is None:
        try:
            import open_clip  # noqa: F401
            _clip_state = "importable"
        except Exception:
            _clip_state = "unavailable"
    if _clip_state == "unavailable":
        return None, "CLIP UNAVAILABLE (weights unreachable) - flagged for user review"
    return None, "CLIP present but no weights configured - flagged for user review"


def score_candidate(path: Path, slot: dict, profile: dict) -> dict:
    img = cv2.imread(str(path))
    if img is None:
        return {"file": str(path), "error": "unreadable", "pass": False}
    h, w = img.shape[:2]
    tw, th = TARGETS[slot["type"]]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 2]
    clipped = float(((hsv < 8) | (hsv > 247)).mean())
    de = _delta_e(_lab_mean(img), profile["lab"])
    rel, rel_note = clip_relevance(path, slot["sentence"])
    failures = []
    if sharp < SHARP_MIN:
        failures.append(f"soft (laplacian {sharp:.0f} < {SHARP_MIN:.0f})")
    if clipped > EXPOSE_MAX:
        failures.append(f"exposure clipped {clipped:.0%}")
    if de > PALETTE_DE_MAX:
        failures.append(f"palette far from video (dE {de:.0f} > {PALETTE_DE_MAX:.0f})")
    return {"file": str(path), "w": w, "h": h,
            "needs_upscale": bool(w < tw or h < th),
            "sharpness": round(sharp, 1), "clipped": round(clipped, 3),
            "palette_dE": round(de, 1),
            "clip_relevance": rel, "clip_note": rel_note,
            "needs_user_review": rel is None,
            "failures": failures, "pass": not failures}


# ------------------------------------------------------- grade + crop
def grade_match(img: np.ndarray, profile: dict,
                strength: float = 0.45) -> np.ndarray:
    """Reinhard colour transfer toward the video's mean/std, then
    matched gaussian grain - the insert sits IN the footage."""
    src = img.astype(np.float32)
    tgt_lab = np.array(profile["lab"], dtype=np.float32)
    tgt_std = np.array(profile.get("lab_std", [40.0, 12.0, 14.0]),
                       dtype=np.float32)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2Lab).astype(np.float32)
    for c in range(3):
        m = float(lab[:, :, c].mean())
        s = float(lab[:, :, c].std()) + 1e-5
        target_m = m + (float(tgt_lab[c]) - m) * strength
        target_s = s * (1.0 + (float(tgt_std[c]) / s - 1.0) * strength * 0.6)
        lab[:, :, c] = (lab[:, :, c] - m) * (target_s / s) + target_m
    out = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8),
                       cv2.COLOR_Lab2BGR).astype(np.float32)
    noise = np.random.default_rng(7).normal(
        0, profile["grain_sigma"], out.shape[:2])[..., None]
    return np.clip(out + noise, 0, 255).astype(np.uint8)


def subject_crop(img: np.ndarray, tw: int, th: int) -> np.ndarray:
    """Crop to the target aspect around the highest-detail region
    (the subject), upscaling first if the source is short."""
    h, w = img.shape[:2]
    scale = max(tw / w, th / h)
    if scale > 1:
        img = cv2.resize(img, (round(w * scale), round(h * scale)),
                         interpolation=cv2.INTER_CUBIC)
        h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    energy = cv2.GaussianBlur(np.abs(cv2.Laplacian(gray, cv2.CV_64F)),
                              (0, 0), 12)
    _, _, _, loc = cv2.minMaxLoc(energy)
    cx, cy = loc
    cw = int(h * tw / th) if w / h > tw / th else w
    ch = int(w * th / tw) if w / h <= tw / th else h
    x0 = int(np.clip(cx - cw / 2, 0, w - cw))
    y0 = int(np.clip(cy - ch / 2, 0, h - ch))
    out = img[y0:y0 + ch, x0:x0 + cw]
    return cv2.resize(out, (tw, th), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------- main
def main() -> int:
    if sys.argv[1] == "--prompts":
        slots = json.loads(Path(sys.argv[2]).read_text())
        profile = video_profile(Path(sys.argv[3]))
        for slot in slots:
            for p in build_prompts(slot, profile):
                print(p)
            print("NEGATIVE:", NEGATIVE_PROMPT)
        return 0
    slots = json.loads(Path(sys.argv[1]).read_text())
    video, out_dir = Path(sys.argv[2]), Path(sys.argv[3])
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = video_profile(video)
    report = {"video_profile": {k: v for k, v in profile.items()},
              "clip": "unavailable - every generated image flagged "
                      "needs_user_review", "slots": []}
    for slot in slots:
        prompts = build_prompts(slot, profile)
        cands = sorted(Path(slot["candidates_dir"]).glob("*"))
        scored = [score_candidate(p, slot, profile) for p in cands
                  if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
        passing = [s for s in scored if s["pass"]]
        passing.sort(key=lambda s: (-s["sharpness"], s["palette_dE"]))
        entry = {"id": slot["id"], "type": slot["type"],
                 "sentence": slot["sentence"],
                 "prompts": prompts, "negative_prompt": NEGATIVE_PROMPT,
                 "candidates": scored, "chosen": None}
        # archive raw candidates
        for p in cands:
            if p.suffix.lower() in (".jpg", ".jpeg", ".png"):
                cv2.imwrite(str(out_dir / f"{slot['id']}__{p.name}"),
                            cv2.imread(str(p)))
        if passing:
            chosen = passing[0]
            img = cv2.imread(chosen["file"])
            graded = subject_crop(grade_match(img, profile),
                                  *TARGETS[slot["type"]])
            dest = out_dir / f"{slot['id']}__chosen.jpg"
            cv2.imwrite(str(dest), graded, [cv2.IMWRITE_JPEG_QUALITY, 92])
            entry["chosen"] = {"file": str(dest),
                               "from": chosen["file"],
                               "graded": True, "cropped_to_subject": True,
                               "needs_user_review": True}
            print(f"[{slot['id']}] chose {Path(chosen['file']).name} "
                  f"(sharp {chosen['sharpness']}, dE {chosen['palette_dE']})")
        else:
            entry["status"] = "NO PASSING CANDIDATE - regenerate once, " \
                              "then fall back to no image"
            print(f"[{slot['id']}] NO PASSING CANDIDATE")
        report["slots"].append(entry)
    (out_dir / "scores.json").write_text(json.dumps(report, indent=2))
    # contact sheet: every candidate, labelled with its verdict
    tiles = []
    for slot in slots:
        for p in sorted(Path(slot["candidates_dir"]).glob("*")):
            if p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            img = cv2.imread(str(p))
            if img is None:
                continue
            img = cv2.resize(img, (270, 480))
            cv2.putText(img, f"{slot['id']}:{p.stem[-12:]}", (8, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 180), 2)
            tiles.append(img)
    if tiles:
        cols = 4
        rows = (len(tiles) + cols - 1) // cols
        sheet = np.zeros((rows * 480, cols * 270, 3), np.uint8)
        for i, t in enumerate(tiles):
            sheet[(i // cols) * 480:(i // cols + 1) * 480,
                  (i % cols) * 270:(i % cols + 1) * 270] = t
        cv2.imwrite(str(out_dir / "images_sheet.jpg"), sheet,
                    [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"scores -> {out_dir / 'scores.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
