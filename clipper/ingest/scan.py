"""Stage 0 - look at a campaign folder and write down what is inside.

A campaign folder is exactly what Whop gives you:

    campaigns/<name>/references/*.mp4   examples the creator approved
    campaigns/<name>/raw/*.mp4          the long-form footage

`scan` probes every file (resolution, fps, duration, audio) and writes
work/<name>/manifest.json. Later stages read that instead of re-probing.
"""
from __future__ import annotations

from pathlib import Path

from .. import config
from ..ffmpeg import probe
from ..util import jsonio, log


def find_campaign_dirs() -> list[Path]:
    """Every folder that looks like a campaign, in samples/ and campaigns/."""
    out: list[Path] = []
    for base in (config.CAMPAIGNS, config.SAMPLES):
        if not base.exists():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and any((child / sub).is_dir() for sub in ("references", "raw")):
                out.append(child)
    return out


def _media_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.rglob("*")
                  if p.is_file() and p.suffix.lower() in config.MEDIA_EXT)


def scan_campaign(campaign: str | Path) -> dict:
    path = Path(campaign)
    if not path.is_absolute():
        for base in (config.CAMPAIGNS, config.SAMPLES):
            if (base / path).is_dir():
                path = base / path
                break
    if not path.is_dir():
        raise FileNotFoundError(f"campaign folder not found: {campaign}")
    name = path.name

    def describe(files: list[Path], kind: str) -> list[dict]:
        rows = []
        for f in files:
            try:
                info = probe(f)
                rows.append({"path": str(f.relative_to(path)), "abs": str(f), "kind": kind,
                             **info.to_dict()})
            except Exception as exc:
                log.warn("probe failed", file=str(f.relative_to(path)), err=type(exc).__name__)
                rows.append({"path": str(f.relative_to(path)), "abs": str(f), "kind": kind,
                             "error": str(exc)})
        return rows

    refs = describe(_media_files(path / "references"), "reference")
    raw = describe(_media_files(path / "raw"), "raw")
    manifest = {
        "campaign": name,
        "root": str(path),
        "references": refs,
        "raw": raw,
        "counts": {"references": len(refs), "raw": len(raw)},
        "warnings": [
            *( ["no /references folder"] if not (path / "references").is_dir() else [] ),
            *( ["no /raw folder"] if not (path / "raw").is_dir() else [] ),
            *( ["no reference videos found"] if not refs else [] ),
            *( ["no raw footage found"] if not raw else [] ),
        ],
    }
    jsonio.save(config.WORK / name / "manifest.json", manifest)
    log.info("scanned campaign", campaign=name, references=len(refs), raw=len(raw))
    for w in manifest["warnings"]:
        log.warn(w)
    return manifest
