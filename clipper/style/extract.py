"""Stage 1 - turn the reference clips of a campaign into a style profile.

    python -m clipper style mycampaign

Writes:
    styles/<campaign>.style.json          the profile (consumed by stages 3-5)
    work/<campaign>/style/report.json     raw measurements per reference
    work/<campaign>/style/evidence/*.png  annotated frames for eyeballing

Aggregation across several references uses the median for numbers and the most
common value for enums, weighted by clip duration - one long reference should
not be outvoted by three tiny ones.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from .. import config
from ..ingest.scan import scan_campaign
from ..util import jsonio, log
from . import audio_style, captions_detect, profile as profile_mod, zoom as zoom_mod
from .frames import sample_video
from .shots import detect_cuts

DEFAULT_SAMPLE_FPS = 6.0
DEFAULT_SAMPLE_WIDTH = 480


def _median(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(float(np.median(vals)), 4) if vals else None


def _mode(values: list) -> object | None:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    counts: dict = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    return max(counts, key=lambda k: counts[k])


def analyze_reference(path: str | Path, *, fps: float = DEFAULT_SAMPLE_FPS,
                      width: int = DEFAULT_SAMPLE_WIDTH,
                      max_seconds: float | None = None,
                      evidence_dir: Path | None = None, evidence_limit: int = 3,
                      cap_height_em: float | None = None,
                      calibrate_dir: Path | None = None) -> dict:
    """All four analyses for one reference clip."""
    path = Path(path)
    t0 = time.time()
    frames = list(sample_video(str(path), fps=fps, width=width, max_seconds=max_seconds))
    if not frames:
        raise ValueError(f"no frames sampled from {path}")
    duration = frames[-1].t + 1.0 / fps

    with log.step("shots", file=path.name):
        shots = detect_cuts(frames)
    with log.step("zoom", file=path.name):
        zres = analyze_zoom_safe(frames, shots.cuts)
    with log.step("captions", file=path.name):
        if cap_height_em is None:
            cap_height_em = captions_detect.calibrate_cap_height(
                calibrate_dir, sampled_width=width)
        caps = captions_detect.analyze_captions(frames, cap_height_em=cap_height_em)
    with log.step("audio", file=path.name):
        try:
            aud = audio_style.analyze_audio_style(str(path))
        except Exception as exc:
            log.warn("audio analysis failed", err=type(exc).__name__)
            aud = {"confidence": 0.0}

    evidence: list[str] = []
    if evidence_dir is not None and caps.get("present") and evidence_limit:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        saved = 0
        for frame in frames:
            if saved >= evidence_limit:
                break
            bands = captions_detect.detect_bands(frame.bgr)
            if not bands:
                continue
            canvas = captions_detect.draw_evidence(frame, bands)
            out = evidence_dir / f"{path.stem}_caption_{saved}.png"
            _write_png(out, canvas)
            evidence.append(str(out))
            saved += 1
    if evidence:
        caps["evidence"]["frames"] = evidence

    shots_stats = shots.stats()
    return {
        "path": str(path),
        "duration": round(duration, 3),
        "elapsed": round(time.time() - t0, 2),
        "pacing": {**shots_stats,
                   "cut_times": shots.cuts[:40],
                   "confidence": _pacing_confidence(shots_stats, duration)},
        "zoom": zres.to_dict(),
        "captions": caps,
        "audio": aud,
        "sample": {"fps": fps, "width": width, "frames": len(frames),
                   "cap_height_em": round(float(cap_height_em or 0), 4)},
    }


def analyze_zoom_safe(frames, cuts):
    try:
        return zoom_mod.analyze_zoom(frames, cuts)
    except Exception as exc:  # zoom is nice to have; never kill the profile
        log.warn("zoom analysis failed", err=type(exc).__name__)
        return zoom_mod.ZoomResult()


def _pacing_confidence(stats: dict, duration: float) -> float:
    if not stats.get("shot_count"):
        return 0.0
    shots = stats["shot_count"]
    conf = 0.25 + 0.5 * min(1.0, shots / 6.0)
    if duration < 3.0:
        conf *= 0.6
    return round(min(0.9, conf), 3)


def _write_png(path: Path, bgr: np.ndarray) -> None:
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), bgr)


def aggregate(references: list[dict]) -> dict:
    """Combine per-reference measurements into one campaign style profile."""
    usable = [r for r in references if r.get("duration")]
    if not usable:
        return {"captions": {"present": False, "confidence": 0.0}, "confidence": 0.0}

    weights = np.array([r["duration"] for r in usable], dtype=float)
    weights = weights / weights.sum()

    # ---- pacing -----------------------------------------------------------
    avg_len = _median([r["pacing"].get("avg_shot_len") for r in usable])
    cpm = _median([r["pacing"].get("cuts_per_minute") for r in usable])
    pacing = {
        "avg_shot_len": avg_len,
        "median_shot_len": _median([r["pacing"].get("median_shot_len") for r in usable]),
        "cuts_per_minute": cpm,
        "confidence": round(float(np.average(
            [r["pacing"].get("confidence") or 0.0 for r in usable], weights=weights)), 3),
    }

    # ---- zoom -------------------------------------------------------------
    zoom_sections = [r["zoom"] for r in usable if r.get("zoom")]
    zoom = {
        "dominant": _mode([z.get("dominant") for z in zoom_sections]) or "unknown",
        "punch_in_scale": _median([z.get("punch_in_scale") for z in zoom_sections]),
        "punch_in_duration": _median([z.get("punch_in_duration") for z in zoom_sections]),
        "confidence": round(float(np.mean([z.get("confidence") or 0.0 for z in zoom_sections]))
                            if zoom_sections else 0.0, 3),
    }

    # ---- captions ---------------------------------------------------------
    cap_refs = [r["captions"] for r in usable if r.get("captions", {}).get("present")]
    if cap_refs:
        present = True
        font_size = _median([c.get("font_size_ass") for c in cap_refs])
        outline_w = _median([c.get("outline_width") for c in cap_refs])
        primary = _weighted_color([( c.get("primary_color"), r["duration"])
                                  for c, r in zip(cap_refs, usable) if c.get("primary_color")])
        outline = _weighted_color([(c.get("outline_color"), r["duration"])
                                   for c, r in zip(cap_refs, usable) if c.get("outline_color")])
        karaoke_refs = [c for c in cap_refs if c.get("karaoke", {}).get("enabled")]
        highlight = _weighted_color([(c["karaoke"].get("highlight_color"), r["duration"])
                                     for c, r in zip(cap_refs, usable)
                                     if c.get("karaoke", {}).get("highlight_color")])
        captions = {
            "present": True,
            "font_family": None,       # not inferable from pixels; documented
            "font_size_ass": int(font_size) if font_size else None,
            "font_size_uncertainty": _median([c.get("font_size_uncertainty") for c in cap_refs]),
            "cap_height_ratio": _median([c.get("cap_height_ratio") for c in cap_refs]),
            "primary_color": primary,
            "outline_color": outline,
            "outline_width": int(outline_w) if outline_w is not None else None,
            "casing": _mode([c.get("casing") for c in cap_refs]),
            "position": {
                "anchor": "bottom_center",
                "cx": _median([c.get("position", {}).get("cx") for c in cap_refs]),
                "cy": _median([c.get("position", {}).get("cy") for c in cap_refs]),
            },
            "karaoke": {"enabled": bool(karaoke_refs),
                        "highlight_color": highlight},
            "animation": {"in": _mode([c.get("animation", {}).get("in") for c in cap_refs]) or "none"},
            "max_lines": int(_median([c.get("max_lines") for c in cap_refs]) or 1),
            "max_words_per_cue": int(_median([c.get("max_words_per_cue") for c in cap_refs]) or 4),
            "max_chars_per_line": int(_median([c.get("max_chars_per_line") for c in cap_refs]) or 22),
            "confidence": round(float(np.average([c.get("confidence") or 0.0 for c in cap_refs],
                                                 weights=weights[:len(cap_refs)])), 3),
            "evidence": {
                "cue_count": int(sum(c.get("evidence", {}).get("cue_count", 0) for c in cap_refs)),
                "frames": [f for c in cap_refs for f in c.get("evidence", {}).get("frames", [])],
            },
        }
    else:
        captions = {"present": False, "confidence": 0.0, "evidence": {"cue_count": 0, "frames": []}}

    # ---- audio ------------------------------------------------------------
    audio_refs = [r.get("audio") for r in usable if r.get("audio")]
    audio = {
        "music_bed": _mode([a.get("music_bed") for a in audio_refs]),
        "ducking": _mode([a.get("ducking") for a in audio_refs]),
        "target_lufs": _median([a.get("target_lufs") for a in audio_refs]),
        "speech_ratio": _median([a.get("speech_ratio") for a in audio_refs]),
        "confidence": round(float(np.mean([a.get("confidence") or 0.0 for a in audio_refs]))
                            if audio_refs else 0.0, 3),
    }

    return {"captions": captions, "pacing": pacing, "zoom": zoom, "audio": audio}


def _weighted_color(pairs: list[tuple[str | None, float]]) -> str | None:
    """Most common colour, weighted by clip duration (hex strings)."""
    counts: dict[str, float] = {}
    for color, weight in pairs:
        if not color:
            continue
        counts[color.upper()] = counts.get(color.upper(), 0.0) + float(weight)
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def extract_style(campaign: str | Path, *, fps: float = DEFAULT_SAMPLE_FPS,
                  width: int = DEFAULT_SAMPLE_WIDTH, max_seconds: float | None = None,
                  save_evidence: bool = True, write: bool = True) -> dict:
    """Full stage 1 for one campaign."""
    t0 = time.time()
    manifest = scan_campaign(campaign)
    name = manifest["campaign"]
    refs = manifest["references"]
    if not refs:
        raise RuntimeError(
            f"no reference clips in {manifest['root']}/references - stage 1 needs examples"
        )
    work_dir = config.WORK / name / "style"
    evidence_dir = work_dir / "evidence" if save_evidence else None

    analyses: list[dict] = []
    for ref in refs:
        path = ref.get("abs") or ref.get("path")
        try:
            analyses.append(analyze_reference(path, fps=fps, width=width,
                                              max_seconds=max_seconds,
                                              evidence_dir=evidence_dir,
                                              calibrate_dir=work_dir))
        except Exception as exc:
            log.warn("reference failed", file=Path(path).name, err=f"{type(exc).__name__}: {exc}")

    if not analyses:
        raise RuntimeError("no reference could be analysed")

    agg = aggregate(analyses)
    profile = profile_mod.apply_defaults({
        "campaign": name,
        "source": {
            "references": [Path(a["path"]).name for a in analyses],
            "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "sample": {"fps": fps, "width": width},
            "notes": "",
        },
        **agg,
    })
    profile["confidence"] = profile_mod.overall_confidence(profile)
    notes = profile_mod.notes_for(profile)
    profile["source"]["notes"] = "; ".join(notes) if notes else "ok"

    if write:
        out = config.STYLES / f"{name}.style.json"
        jsonio.save(out, profile)
        jsonio.save(work_dir / "report.json", {
            "campaign": name,
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "elapsed": round(time.time() - t0, 2),
            "profile": str(out),
            "references": analyses,
            "aggregate": agg,
            "notes": notes,
        })
        log.info("style written", path=str(out), confidence=profile["confidence"],
                 took=f"{time.time() - t0:.1f}s")
    for note in notes:
        log.warn(note)
    profile["_analyses"] = analyses
    return profile
