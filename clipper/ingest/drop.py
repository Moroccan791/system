"""Stage 0, the other way in: collect footage that was pushed to a git branch.

Uploading through the chat is the normal way in, but it does not always land -
then the files exist on the user's machine and nowhere else. GitHub is reachable
from both sides, so the fallback is:

    python -m clipper drop michael_sartain --branch footage

which fetches that branch, pulls every media file out of it and files each one
under campaigns/<campaign>/{references,raw}. Nothing is merged, the branch you
are working on is untouched, and the dropped branch keeps its own history.

Media is sorted by what the name says first (a "Shorts" download is a reference,
a plain "YouTube" download is raw footage), then by length: short things teach
the style, long things get clipped.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from contextlib import contextmanager
from typing import Callable, Iterable, Iterator, Sequence

from .. import config
from ..ffmpeg import probe
from ..util import log

REFERENCE_HINT = ("short", "shorts", "reel", "tiktok")   # approved examples
RAW_HINT = ("youtube", "video", "podcast", "episode", "livestream", "stream")
REFERENCE_MAX_SECONDS = 240.0     # a reference is a finished short, not an episode


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #
def classify_drop(path: str | Path, duration: float | None = None) -> tuple[str, str]:
    """Where does this file belong? Returns (folder, why)."""
    name = Path(path).name.lower()
    for hint in REFERENCE_HINT:
        if hint in name:
            return "references", f"the name says '{hint}'"
    for hint in RAW_HINT:
        if hint in name:
            return "raw", f"the name says '{hint}'"
    if duration is not None and duration > 0:
        if duration <= REFERENCE_MAX_SECONDS:
            return "references", f"{duration:.0f}s long, short enough to be a reference"
        return "raw", f"{duration:.0f}s long, long enough to clip"
    return "raw", "could not tell, so treated as raw footage"


def plan_moves(
    files: Iterable[str | Path],
    campaign_dir: str | Path,
    *,
    into: str | None = None,
    duration_lookup: Callable[[Path], float | None] | None = None,
    overwrite: bool = False,
) -> list[dict]:
    """Decide, without touching anything, where each file would go.

    ``into`` ("references" or "raw") overrides the guess for every file.
    """
    campaign_dir = Path(campaign_dir)
    lookup = duration_lookup or _duration_or_none
    planned: list[dict] = []
    taken: dict[Path, Path] = {}

    for item in files:
        src = Path(item)
        if not src.is_file():
            continue
        if into:
            folder, why = into, "you said so"
            duration = None
        else:
            duration = lookup(src)
            folder, why = classify_drop(src, duration)
        dest = campaign_dir / folder / src.name

        # two files with the same basename coming from different folders
        clash = taken.get(dest)
        while clash is not None and clash != src:
            dest = dest.with_name(f"{dest.parent.name}_{dest.name}")
            clash = taken.get(dest)

        if dest.exists() and not overwrite:
            same = dest.stat().st_size == src.stat().st_size
            action = "already there" if same else "name taken"
        else:
            action = "copy"

        taken[dest] = src
        planned.append({
            "source": src,
            "dest": dest,
            "folder": folder,
            "why": why,
            "duration": duration,
            "bytes": src.stat().st_size,
            "action": action,
        })
    return planned


def _duration_or_none(path: Path) -> float | None:
    try:
        return float(probe(path).duration) or None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# git plumbing
# --------------------------------------------------------------------------- #
def git(repo: str | Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail[-1] if detail else '?'}")
    return proc


def remote_slug(repo: str | Path, remote: str = "origin") -> str | None:
    """"owner/repo" for the remote, for printing a link the user can click."""
    proc = git(repo, "remote", "get-url", remote, check=False)
    url = (proc.stdout or "").strip()
    if not url:
        return None
    slug = url.rsplit("github.com", 1)[-1].lstrip(":/")
    return slug[:-4] if slug.endswith(".git") else slug


def branch_exists(repo: str | Path, branch: str, remote: str = "origin") -> bool:
    proc = git(repo, "ls-remote", "--heads", remote, branch, check=False)
    return bool((proc.stdout or "").strip())


def fetch_branch(repo: str | Path, branch: str, remote: str = "origin") -> str:
    """Fetch just that branch and return the revision to read from."""
    git(repo, "fetch", "--depth", "1", "--no-tags", remote, branch)
    return "FETCH_HEAD"


def extract(repo: str | Path, rev: str, dest: str | Path) -> Path:
    """Write the files of ``rev`` into ``dest`` (git archive | tar -x)."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    archiver = subprocess.Popen(
        ["git", "-C", str(repo), "archive", "--format=tar", rev],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    untar = subprocess.run(["tar", "-x", "-C", str(dest)], stdin=archiver.stdout)
    archiver.stdout.close()
    stderr = (archiver.stderr.read() or b"").decode(errors="replace").strip()
    archiver.wait()
    if archiver.returncode != 0 or untar.returncode != 0:
        raise RuntimeError(f"could not read {rev}: {stderr or 'tar failed'}")
    return dest


def media_files(root: str | Path) -> list[Path]:
    root = Path(root)
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and p.suffix.lower() in config.MEDIA_EXT)


# --------------------------------------------------------------------------- #
# the whole job
# --------------------------------------------------------------------------- #
@contextmanager
def fetched_files(repo: str | Path, branch: str, remote: str = "origin") -> Iterator[list[Path]]:
    """Fetch the branch and hand over the media in it, alive for the block.

    The scratch directory only lives as long as the ``with`` block, so plans
    built from it have to be carried out inside the block.
    """
    with tempfile.TemporaryDirectory(prefix="clipper-drop-") as scratch:
        rev = fetch_branch(repo, branch, remote)
        extract(repo, rev, scratch)
        yield media_files(scratch)


def copy_planned(planned: Sequence[dict], *, dry_run: bool = False) -> list[dict]:
    """Perform the copies, returning the same items with what actually happened."""
    done = []
    for item in planned:
        if item["action"] == "copy" and not dry_run:
            item["dest"].parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item["source"], item["dest"])
        done.append(item)
    return done


HOW_TO_SEND = """\
Sending footage to me when the chat upload does not land
--------------------------------------------------------
In the browser (no git needed):

  1. open https://github.com/{slug}
  2. click the branch menu, type  {branch}  and pick "Create branch: {branch}"
  3. "Add file" -> "Upload files" -> drop the videos in -> "Commit changes"
  4. tell me "pushed"

The browser takes about 25 MB per file. Bigger ones need git (up to 100 MB) -
from your clone of this repo:

  git checkout -b {branch}
  mkdir -p coming-in && cp <the files> coming-in/
  git add -f coming-in && git commit -m "footage"
  git push -u origin {branch}

Then I run:  python -m clipper drop {campaign} --branch {branch}
"""
