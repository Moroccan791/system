"""Render an edit plan with ffmpeg.

One filter graph does the whole job: each shot is trimmed, reframed to 9:16,
given its camera move by `zoompan` (which evaluates its zoom expression per
frame, so a punch-in actually ramps), and the shots are concatenated with their
audio following the cuts.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..ffmpeg import ffmpeg_exe, probe
from ..util import log

FOCUS_Y = {"centre": "0.5", "center": "0.5", "top": "0.18", "upper": "0.18",
           "bottom": "0.82", "lower": "0.82"}


def _zoom_expression(move: dict, fps: int) -> str | None:
    """Per-frame zoom for `zoompan`, from the plan's camera move."""
    kind = move.get("type", "static")
    if kind == "static":
        return None
    target = float(move.get("to") or 1.0)
    start = float(move.get("from") or 1.0)
    over = max(0.05, float(move.get("over") or 0.25))
    frames = max(1.0, over * fps)
    ramp = f"min(on/{frames:.3f},1)"
    if kind == "pull_out":
        return f"{start:.4f}-({start:.4f}-{target:.4f})*{ramp}"
    return f"{start:.4f}+({target:.4f}-{start:.4f})*{ramp}"


def build_filtergraph(plan: dict, *, focus: str = "centre", source_fps: float | None = None,
                      with_audio: bool = True) -> str:
    """The `-filter_complex` string for a plan (kept separate so it is testable).

    `zoompan` is told to emit at the *source* frame rate: asked for the output
    rate instead, it hands each input frame on with a mismatched timestamp and
    downstream filters then duplicate frames wildly (a 16 second clip became
    three hours during development). The final `-r` on the encoder does the
    conversion to the platform rate.
    """
    fps = int(plan["target"]["fps"])
    zoom_fps = int(round(source_fps)) if source_fps else fps
    width = int(plan["target"]["width"])
    height = int(plan["target"]["height"])
    focus_y = FOCUS_Y.get(focus, "0.5")
    shots = plan["shots"]
    parts: list[str] = []
    for i, shot in enumerate(shots):
        start, end = shot["start"], shot["end"]
        chain = [
            f"trim=start={start:.3f}:end={end:.3f}",
            "setpts=PTS-STARTPTS",
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}:(iw-{width})/2:(ih-{height})*{focus_y}",
        ]
        expression = _zoom_expression(shot.get("zoom") or {}, zoom_fps)
        if expression:
            chain.append(
                f"zoompan=z='{expression}':x='iw/2-(iw/zoom/2)':"
                f"y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={zoom_fps}")
        else:
            # same rate as the zoompan branch, so concat sees one frame rate
            chain.append(f"fps={zoom_fps}")
        chain.append("setsar=1")
        parts.append(f"[0:v]{','.join(chain)}[v{i}]")
        if with_audio:
            parts.append(f"[0:a]atrim=start={start:.3f}:end={end:.3f},"
                         f"asetpts=PTS-STARTPTS[a{i}]")
    if not with_audio:
        # silent footage is still editable - the clip just has no audio track
        if len(shots) == 1:
            parts.append("[v0]null[v]")
        else:
            parts.append("".join(f"[v{i}]" for i in range(len(shots)))
                         + f"concat=n={len(shots)}:v=1:a=0[v]")
        return ";".join(parts)
    streams = "".join(f"[v{i}][a{i}]" for i in range(len(shots)))
    if len(shots) == 1:
        parts.append("[v0]null[v];[a0]anull[a]")
    else:
        parts.append(f"{streams}concat=n={len(shots)}:v=1:a=1[v][a]")
    return ";".join(parts)


def _clamp_to_source(plan: dict, limit: float) -> dict:
    """A hand-edited or over-long plan can ask for footage the file does not have.

    Trim the tail to what is really there instead of letting ffmpeg pad the end
    with a frozen frame, and say so.
    """
    kept = []
    for shot in plan["shots"]:
        if shot["start"] >= limit - 0.02:
            continue
        end = min(float(shot["end"]), limit)
        kept.append({**shot, "end": round(end, 4), "duration": round(end - shot["start"], 4)})
    if not kept:
        raise RuntimeError(
            f"source is only {limit:.2f}s long, the plan needs footage after "
            f"{plan['shots'][0]['start']:.2f}s")
    log.warn("plan runs past the end of the source, trimmed to what exists",
             planned=f"{plan['clip']['duration']:.2f}s", source=f"{limit:.2f}s",
             shots=f"{len(kept)}/{len(plan['shots'])}")
    clip = {**plan["clip"], "end": kept[-1]["end"],
            "duration": round(sum(s["duration"] for s in kept), 4), "trimmed_to_source": True}
    return {**plan, "shots": kept, "clip": clip}


def render_plan(plan: dict, out_path: str | Path, *, focus: str = "centre",
                crf: int = 18, preset: str = "veryfast", audio_bitrate: str = "256k") -> Path:
    """Cut, zoom and concatenate the moment into a mezzanine clip."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    source = Path(plan["clip"]["source"])
    if not source.exists():
        raise FileNotFoundError(f"source footage is gone: {source}")
    info = probe(source)
    fps = int(plan["target"]["fps"] or 30)
    if info.duration and plan["shots"] and plan["shots"][-1]["end"] > info.duration + 0.05:
        plan = _clamp_to_source(plan, float(info.duration))
    with_audio = bool(info.has_audio)
    if not with_audio:
        log.debug("source has no audio track, rendering video only", file=source.name)
    args = [
        ffmpeg_exe(), "-y", "-v", "error", "-nostdin", "-i", str(source),
        "-filter_complex", build_filtergraph(plan, focus=focus, source_fps=info.fps,
                                             with_audio=with_audio),
        "-map", "[v]", *(["-map", "[a]"] if with_audio else []),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-r", str(fps),
        *(["-c:a", "aac", "-b:a", audio_bitrate] if with_audio else ["-an"]),
        "-movflags", "+faststart",
        str(out_path),
    ]
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"edit render failed:\n{proc.stderr.strip()[-800:]}")
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError("edit render produced no output")
    rendered = probe(out_path)
    planned = float(plan["clip"]["duration"])
    if abs(rendered.duration - planned) > 0.35:
        log.warn("rendered length differs from the plan", planned=f"{planned:.2f}s",
                 rendered=f"{rendered.duration:.2f}s")
    log.info("edit rendered", out=out_path.name,
             shots=len(plan["shots"]),
             dur=f"{rendered.duration:.1f}s",
             size=f"{out_path.stat().st_size / 1024:.0f} KB",
             source_fps=info.fps)
    return out_path
