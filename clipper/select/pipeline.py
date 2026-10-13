"""Stage 2 - pick the moments worth cutting out of a long recording.

Reads a raw file (and a transcript if one exists) and writes
`work/<name>/candidates.json`: ranked windows with their reasons, ready for the
edit stage to assemble and the export stage to render. Nothing here depends on
a specific ASR provider or on a transcript existing at all.
"""
from __future__ import annotations

import math
from pathlib import Path

from .. import config
from ..util import jsonio, log
from . import energy as energy_mod
from . import hooks as hooks_mod
from . import score as score_mod


def load_transcript(source) -> list | None:
    """A transcript can be a path, a parsed dict, or already `Word` objects."""
    if source is None:
        return None
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            log.warn("transcript not found, selecting on audio alone", path=str(path))
            return None
        data = jsonio.load(path, None)
    elif isinstance(source, dict):
        data = source
    else:
        return list(source)
    if not data:
        return None
    from ..asr.base import Word

    return [Word.from_dict(w) if isinstance(w, dict) else w for w in (data.get("words") or [])]


def find_transcript(media: Path, campaign: str | None = None) -> Path | None:
    """Where a transcript for `media` would be, wherever it was put."""
    candidates = [
        media.with_suffix(".transcript.json"),
        config.WORK / media.stem / "transcript.json",
    ]
    if campaign:
        candidates.append(config.WORK / campaign / "transcripts" / f"{media.stem}.json")
    for path in candidates:
        if path.exists():
            return path
    return None


def select_candidates(media: str | Path, *, transcript=None, platform: str = "tiktok",
                      min_seconds: float | None = None, max_seconds: float | None = None,
                      top: int = 5, campaign: str | None = None,
                      save: bool = True, work_dir: Path | None = None) -> dict:
    """Score one recording and return its candidate clips."""
    media = Path(media)
    if not media.exists():
        raise FileNotFoundError(media)
    lo, hi = score_mod.TARGET_LENGTHS.get(platform, score_mod.TARGET_LENGTHS["tiktok"])
    min_seconds = float(min_seconds if min_seconds is not None else lo)
    max_seconds = float(max_seconds if max_seconds is not None else hi)
    if max_seconds < min_seconds:
        raise ValueError("max_seconds must be >= min_seconds")

    try:
        curve = energy_mod.energy_curve(media)
    except Exception as exc:                    # no audio track at all
        log.warn("no audio to select from", file=media.name, err=type(exc).__name__)
        return {
            "version": 1, "campaign": campaign,
            "source": {"file": str(media), "name": media.name, "duration": 0.0},
            "mode": "no-audio", "note": "the file has no audio track to analyse",
            "target": {"platform": platform, "min_seconds": min_seconds, "max_seconds": max_seconds},
            "analysis": {"baseline_db": None, "peak_db": None, "hot_spots": [],
                         "sentences": 0, "words": 0},
            "candidates": [],
        }
    spots = energy_mod.hot_spots(curve)

    words = load_transcript(transcript)
    if words is None and transcript is None:
        found = find_transcript(media, campaign)
        if found:
            words = load_transcript(found)
            if words:
                log.info("using transcript", path=str(found))

    units = hooks_mod.sentence_units(words) if words else []
    if units:
        scored = score_mod.score_units(units, curve, spots)
        candidates = score_mod.build_candidates(scored, curve, min_seconds=min_seconds,
                                                max_seconds=max_seconds, top=top, spots=spots)
        mode = "transcript+audio"
    else:
        scored = []
        candidates = score_mod.build_from_energy(curve, spots, min_seconds=min_seconds,
                                                 max_seconds=max_seconds, top=top)
        mode = "audio-only"

    payload = {
        "version": 1,
        "campaign": campaign,
        "source": {"file": str(media), "name": media.name, "duration": curve["duration"]},
        "mode": mode,
        "target": {"platform": platform, "min_seconds": min_seconds, "max_seconds": max_seconds},
        "analysis": {
            "baseline_db": round(curve["baseline_db"], 1),
            "peak_db": round(curve["peak_db"], 1),
            "hot_spots": spots,
            "sentences": len(units),
            "words": len(words) if words else 0,
        },
        "candidates": candidates,
    }
    if save:
        out_dir = Path(work_dir) if work_dir else (config.WORK / (campaign or media.stem))
        payload["written"] = str(write_candidates(out_dir, media, payload))
    return payload


def write_candidates(out_dir: Path, media: Path, payload: dict) -> Path:
    """`work/<campaign>/candidates/<stem>.json` + a readable report."""
    folder = Path(out_dir) / "candidates"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{media.stem}.json"
    jsonio.save(path, payload)
    report = folder / f"{media.stem}.report.md"
    report.write_text(render_report(payload), encoding="utf-8")
    log.info("candidates written", path=str(path), count=len(payload["candidates"]),
             mode=payload["mode"])
    return path


def render_report(payload: dict) -> str:
    lines = [
        f"# candidates - {payload['source']['name']}",
        "",
        f"- mode: `{payload['mode']}`",
        f"- duration: {payload['source']['duration']:.1f}s, "
        f"baseline {payload['analysis']['baseline_db']} dB, peak {payload['analysis']['peak_db']} dB",
        f"- target: {payload['target']['min_seconds']:.0f}-{payload['target']['max_seconds']:.0f}s "
        f"({payload['target']['platform']})",
        f"- loud stretches: {len(payload['analysis']['hot_spots'])}",
        "",
    ]
    for c in payload["candidates"]:
        lines += [
            f"## {c['id']} {fmt_time(c['start'])} - {fmt_time(c['end'])} "
            f"({c['duration']:.1f}s, score {c['score']:.2f})",
            "",
        ]
        if c.get("text"):
            lines += [f"> {c['text']}", ""]
        for reason in c.get("reasons", []):
            lines.append(f"- {reason}")
        lines.append("")
    return "\n".join(lines)


def fmt_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:04.1f}"


def select_campaign(campaign: str, **kwargs) -> list[dict]:
    """Run selection over every raw file of a campaign."""
    from ..ingest.scan import scan_campaign

    manifest = scan_campaign(campaign)
    medias = [r for r in manifest.get("raw", [])]
    if not medias:
        raise RuntimeError(f"campaign '{campaign}' has no files in raw/")
    results = []
    for entry in medias:
        media = Path(entry["path"]) if isinstance(entry, dict) else Path(entry)
        if media.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
            continue
        log.step("select", file=media.name)
        results.append(select_candidates(media, campaign=campaign, **kwargs))
    if not results:
        raise RuntimeError(f"campaign '{campaign}' has no video files in raw/")
    return results


def best_overall(results: list[dict], top: int = 5) -> list[dict]:
    """Flatten several files' candidates, keeping score order."""
    flat = []
    for payload in results:
        for c in payload["candidates"]:
            flat.append({**c, "file": payload["source"]["name"],
                         "duration_total": payload["source"]["duration"]})
    flat.sort(key=lambda c: -c["score"])
    return flat[:top]


def rounded_seconds(value: float) -> float:
    return math.floor(value * 1000) / 1000.0
