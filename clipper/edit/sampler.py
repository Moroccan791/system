"""Render a sampler: one clip that shows what each blend between shots looks like.

Choosing a transition from a list of names is guesswork, so this builds the same
pair of shots repeatedly and blends them with a different transition each time,
labelled, concatenated into one file you can scrub through.

    python -m clipper blends                # a curated set that looks different
    python -m clipper blends --all          # every blend this ffmpeg build has
    python -m clipper blends --list         # just print the names

The blends are not ours: they are the transition names built into ffmpeg's
`xfade` filter, read out of the binary at run time (`clipper.edit.plan`).
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..captions.ass import build_ass
from ..captions.cues import Cue
from ..asr.base import Word
from ..ffmpeg import ffmpeg_exe, probe
from ..synth import textured_scene, write_video
from ..util import log
from .plan import FFMPEG_TRANSITIONS, build_plan, resolve_transition
from .render import XFADE_NAMES, render_plan

# one per visual family, so the default sampler stays short but covers the looks
CURATED = ("fade", "fade_black", "fade_white", "fadegrays" if "fadegrays" in FFMPEG_TRANSITIONS else "fadeslow",
           "wipeleft", "wiperight", "wipeup", "slideleft", "slideup", "circleopen", "circleclose",
           "horzopen", "radial", "diagtl", "hlslice", "hblur", "zoomin", "squeezeh", "pixelize",
           "smoothleft", "coverleft", "revealup", "distance", "fadeslow")

SCENE_A = ((210, 150, 110), (240, 190, 140), (255, 235, 205), (225, 180, 130))   # warm
SCENE_B = ((120, 150, 210), (150, 185, 240), (240, 245, 255), (140, 175, 225))   # cool


def available_blends() -> list[str]:
    """Every blend this ffmpeg build can do (58 on the 7.0.2-static build here)."""
    return list(FFMPEG_TRANSITIONS)


def _pair_clip(work_dir: Path, *, seconds: float, size: tuple[int, int], fps: int,
               source: str | None = None, pair=None) -> Path:
    """Two visibly different shots, one after the other, in a single file.

    A blend is only judgeable if the two shots differ where they meet, so the
    synthesized pair uses two palettes and `--source` mode cuts two moments out
    of your own footage.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / "pair.mp4"
    if source and pair:
        (a_start, a_end), (b_start, b_end) = pair
        parts = []
        for i, (start, end) in enumerate(((a_start, a_end), (b_start, b_end)), start=1):
            piece = work_dir / f"pair_{i}.mp4"
            args = [ffmpeg_exe(), "-y", "-v", "error", "-nostdin",
                    "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(piece)]
            proc = subprocess.run(args, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"could not cut the sampler source:\n{proc.stderr[-500:]}")
            parts.append(piece)
        _concat(parts, out)
        return out
    width, height = size
    frames: list = []
    for palette, seed in ((SCENE_A, 3), (SCENE_B, 17)):
        base = textured_scene(width, height, seed=seed, palette=palette)
        frames.extend([base] * int(round(seconds * fps)))
    write_video(str(out), frames, fps=fps,
                audio_source=f"sine=frequency=220:duration={2 * seconds:.2f}")
    return out


def _concat(parts: list[Path], out: Path) -> Path:
    listing = out.with_suffix(".txt")
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    proc = subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-nostdin", "-f", "concat",
                           "-safe", "0", "-i", str(listing), "-c", "copy", str(out)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"sampler concat failed:\n{proc.stderr[-500:]}")
    return out


def _label_ass(blends: list[str], segment: float, size: tuple[int, int], path: Path) -> Path:
    """One caption per segment naming the blend - libass, since drawtext is absent."""
    style = {"captions": {"font_size_ass": 58, "casing": "upper", "outline_width": 6,
                          "karaoke": {"enabled": False}, "animation": {"in": "none"},
                          "position": {"anchor": "bottom_center", "cx": 0.5, "cy": 0.84},
                          "max_lines": 1, "max_words_per_cue": 4}}
    cues = [Cue(index=i + 1, start=i * segment, end=(i + 1) * segment - 0.05,
                words=[Word(name, i * segment, (i + 1) * segment)],
                lines=[[name]])
            for i, name in enumerate(blends)]
    path.write_text(build_ass(cues, style, width=size[0], height=size[1]), encoding="utf-8")
    return path


def render_sampler(out_path: str | Path, *, blends: list[str] | None = None,
                   seconds: float = 1.4, size: tuple[int, int] = (540, 960), fps: int = 24,
                   source: str | None = None, pair=None, label: bool = True,
                   work_dir: str | Path | None = None) -> Path:
    """Render every blend in `blends` (default: a curated set) into one file."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    names = list(blends or CURATED)
    # both spellings work: the words people use ("fade_black", "dissolve") and
    # ffmpeg's own names ("fadeblack")
    for name in names:
        canonical = resolve_transition(name)
        if canonical is None or canonical == "cut":
            raise ValueError(f"not a blend this ffmpeg has: {name}")
        if XFADE_NAMES.get(canonical, canonical) not in FFMPEG_TRANSITIONS:
            raise ValueError(f"not a blend this ffmpeg has: {name}")
    # the per-blend segments are scaffolding, not results: they go to a temp
    # directory (and are cleaned up) so they do not clutter work/ or the viewer
    scratch = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="clipper-sampler-"))
    scratch.mkdir(parents=True, exist_ok=True)
    keep = work_dir is not None
    blend_len = round(min(0.5, seconds * 0.4), 3)

    try:
        return _render(out_path, names, pair_path_builder=lambda: _pair_clip(
            scratch, seconds=seconds, size=size, fps=fps, source=source, pair=pair),
            scratch=scratch, seconds=seconds, size=size, fps=fps, blend_len=blend_len,
            label=label)
    finally:
        if not keep:
            shutil.rmtree(scratch, ignore_errors=True)


def _render(out_path: Path, names: list[str], *, pair_path_builder, scratch: Path,
            seconds: float, size: tuple[int, int], fps: int, blend_len: float,
            label: bool) -> Path:
    """Render each blend over the same pair of shots, then label and join them."""
    pair_path: Path = pair_path_builder()
    pieces: list[Path] = []
    for name in names:
        style = {"pacing": {"avg_shot_len": seconds},
                 "zoom": {"dominant": "static"},
                 "transitions": {"in": name, "duration": blend_len}}
        candidate = {"id": f"#{name}", "start": 0.0, "end": round(2 * seconds, 3),
                     "score": 1.0, "file": str(pair_path), "source_name": "pair"}
        built = build_plan(candidate, style=style, shot_len=seconds)
        built["target"] = {"platform": "sampler", "width": size[0], "height": size[1],
                           "fps": fps}
        built["style"]["transition"] = name
        piece = scratch / f"{name}.mp4"
        render_plan(built, piece, crf=23, preset="veryfast")
        pieces.append(piece)
        log.step("blend", blend=name, of=len(names))

    joined = scratch / "joined.mp4"
    _concat(pieces, joined)
    if not label:
        _copy(joined, out_path)
        return out_path
    ass_path = _label_ass(names, seconds, size, scratch / "labels.ass")
    fonts = Path(__file__).resolve().parents[2] / "assets" / "fonts"
    args = [ffmpeg_exe(), "-y", "-v", "error", "-nostdin", "-i", str(joined),
            "-vf", f"subtitles={ass_path}:fontsdir={fonts}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-movflags", "+faststart", str(out_path)]
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"sampler labels failed:\n{proc.stderr[-500:]}")
    info = probe(out_path)
    log.info("blend sampler rendered", out=out_path.name, blends=len(names),
             seconds=f"{info.duration:.1f}s", size=f"{info.width}x{info.height}")
    return out_path


def _copy(src: Path, dst: Path) -> None:
    proc = subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-nostdin", "-i", str(src),
                           "-c", "copy", str(dst)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"sampler copy failed:\n{proc.stderr[-500:]}")
