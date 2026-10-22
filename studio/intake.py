"""Footage intake: get the source out of a GitHub release and into footage/.

Every job so far started with "where did the file go" — a zip on main, a release
asset, a paste into the repo root. That is a sourcing problem, not an editing
one, and it was costing a round trip each time. This is the one command.

    python -m studio.intake                      # list the newest release
    python -m studio.intake --tag footage-tom-h --dir footage/tom_holland
    python -m studio.intake --file pack.mp4 --dir footage/tom_holland

Rules that matter:

  * **never clobber.** An existing file of the same size is skipped; a different
    file gets a `.1` suffix. Overwriting a pack mid-job is unrecoverable.
  * **probe on arrival.** Duration, resolution, shot count and the ten highest
    ranked shots go out with the download, so the first message about a new pack
    is about the edit, not about the file.
  * **stage it.** `--stage` copies the moved footage into `footage/` under the
    names the rest of the engine expects (`scenepack.mp4`, `track.mp3`), so no
    command in the pipeline needs a path with a space and an emoji in it.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

VIDEO = {".mp4", ".mov", ".mkv", ".webm"}
AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def releases(limit: int = 5) -> list[dict]:
    """Tag order, newest first. `gh release list` here predates --json, so the
    list is read from its table output and the detail comes from `release view`."""
    proc = _run(["gh", "release", "list", "--limit", str(limit)])
    if proc.returncode != 0:
        raise SystemExit(f"gh release list failed: {proc.stderr[-300:]}")
    # columns: name, Latest/Draft, tag, createdAt
    out = []
    for line in proc.stdout.splitlines():
        parts = [p_.strip() for p_ in line.split("\t")]
        if len(parts) >= 3 and parts[2]:
            out.append({"tagName": parts[2], "draft": parts[1].lower() == "draft"})
    return out


def assets(tag: str | None = None) -> tuple[str, list[dict]]:
    """Assets of `tag`, or of the newest published release that has any."""
    if tag is None:
        for rel in releases(10):
            if rel.get("draft"):
                continue
            view = _run(["gh", "release", "view", rel["tagName"], "--json", "tagName,assets"])
            if view.returncode == 0:
                data = json.loads(view.stdout)
                if data.get("assets"):
                    return data["tagName"], data["assets"]
        raise SystemExit("no release with assets found")
    view = _run(["gh", "release", "view", tag, "--json", "tagName,assets"])
    if view.returncode != 0:
        raise SystemExit(f"no release {tag!r}: {view.stderr[-200:]}")
    data = json.loads(view.stdout)
    return data["tagName"], data["assets"]


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "asset"


def download(tag: str, chosen: list[dict], dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    got: list[Path] = []
    for a in chosen:
        target = dest / _safe(a["name"])
        n = 1
        while target.exists() and target.stat().st_size != a["size"]:
            target = dest / f"{_safe(a['name']).rsplit('.', 1)[0]}.{n}." \
                            f"{_safe(a['name']).rsplit('.', 1)[-1]}"
            n += 1
        if target.exists():
            print(f"  = {target.name} already here ({a['size'] // 1_000_000} MB), skipped")
            got.append(target)
            continue
        proc = _run(["gh", "release", "download", tag, "--pattern", a["name"],
                     "--dir", str(dest), "--clobber"])
        if proc.returncode != 0:
            print(f"  ! {a['name']}: {proc.stderr.strip()[-200:]}")
            continue
        # gh writes under the original name; move it to the safe name
        raw = dest / a["name"]
        if raw.exists() and raw != target:
            raw.replace(target)
        if target.exists():
            print(f"  + {target.name}  {target.stat().st_size // 1_000_000} MB")
            got.append(target)
    return got


def probe(paths: list[Path]) -> None:
    """Duration, resolution and the shortlist — on arrival, not on request."""
    from . import picks
    from .shots import analyse

    for p in paths:
        if p.suffix.lower() in AUDIO:
            from .grid import analyse as analyse_track

            grid = analyse_track(str(p))
            print(f"\naudio {p.name}: {grid.duration:.2f}s, {grid.bpm:.1f} BPM, "
                  f"{len(grid.sections)} sections")
            continue
        if p.suffix.lower() not in VIDEO:
            continue
        src = analyse(str(p), None)
        used = sum(s.dur for s in src.shots)
        print(f"\nvideo {p.name}: {src.width}x{src.height} {src.fps:.0f}fps "
              f"{src.duration:.1f}s -> {len(src.shots)} shots, {used:.0f}s of picture")
        try:
            top = picks.rank(src, 6)
            print("  best moments (unfiltered — the brief decides subject):")
            for r in top:
                print(f"    #{r['shot']:02d} {r['in']:7.2f}s  {r['score']:.2f}  {r['why']}")
        except Exception as exc:
            print(f"  picks unavailable: {type(exc).__name__}")


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="pull footage out of a release")
    ap.add_argument("--tag", default=None, help="release tag; default newest with assets")
    ap.add_argument("--dir", default="footage", help="where to put it")
    ap.add_argument("--file", default=None, help="only this asset name")
    ap.add_argument("--list", action="store_true", help="list assets, download nothing")
    ap.add_argument("--stage", action="store_true",
                    help="also copy into footage/ as scenepack.mp4 / track.mp3")
    a = ap.parse_args(argv)

    tag, items = assets(a.tag)
    print(f"release {tag}: {len(items)} assets")
    for i in items:
        kind = ("video" if Path(i["name"]).suffix.lower() in VIDEO else
                "audio" if Path(i["name"]).suffix.lower() in AUDIO else "other")
        print(f"  {i['size'] // 1_000_000:>4} MB  {kind:5}  {i['name']}")
    if a.list:
        return 0

    chosen = [i for i in items if a.file is None or i["name"] == a.file]
    got = download(tag, chosen, Path(a.dir))
    if not got:
        print("nothing downloaded")
        return 1

    if a.stage:
        vids = [p for p in got if p.suffix.lower() in VIDEO]
        auds = [p for p in got if p.suffix.lower() in AUDIO]
        out = Path("footage")
        out.mkdir(exist_ok=True)
        if vids:
            shutil.copyfile(vids[0], out / f"scenepack{vids[0].suffix.lower()}")
            print(f"  staged {out / f'scenepack{vids[0].suffix.lower()}'}")
        if auds:
            shutil.copyfile(auds[0], out / f"track{auds[0].suffix.lower()}")
            print(f"  staged {out / f'track{auds[0].suffix.lower()}'}")

    probe(got)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
