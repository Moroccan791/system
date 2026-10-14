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

# what the plan calls a blend -> what ffmpeg's xfade calls it
XFADE_NAMES = {"fade": "fade", "fade_black": "fadeblack", "fade_white": "fadewhite"}


def _zoom_expression(move: dict, fps: int) -> str | None:
    """Per-frame zoom for `zoompan`, from the plan's camera move.

    Both ends are clamped at 1.0: `zoompan` crops `iw/zoom`, so a value under
    1.0 asks for more picture than the frame holds and ffmpeg fills the
    difference with padding. A pull-back is therefore expressed as starting
    above 1.0 and settling at it, not as ending below it.
    """
    kind = move.get("type", "static")
    if kind == "static":
        return None
    target = max(1.0, float(move.get("to") or 1.0))
    start = max(1.0, float(move.get("from") or 1.0))
    if abs(target - start) < 1e-4:
        return None
    over = max(0.05, float(move.get("over") or 0.25))
    frames = max(1.0, over * fps)
    ramp = f"min(on/{frames:.3f},1)"
    if kind == "pull_out":
        return f"{start:.4f}-({start:.4f}-{target:.4f})*{ramp}"
    return f"{start:.4f}+({target:.4f}-{start:.4f})*{ramp}"


def _blends(shots: list[dict], source_duration: float | None = None) -> list[tuple[int, str, float]]:
    """The blends in a plan as (index of the outgoing shot, name, seconds)."""
    found: list[tuple[int, str, float]] = []
    for i, shot in enumerate(shots):
        # the transition *into* a shot is stored on that shot
        name = str(shot.get("transition") or "cut").strip().lower()
        seconds = float(shot.get("transition_duration") or 0.0)
        if name == "cut" or seconds <= 0:
            continue
        found.append((i - 1, name, seconds))
    return found


def crop_offset(focus: str = "centre", focus_x: float | None = None) -> tuple[str, str]:
    """Where the 9:16 window sits on a landscape frame.

    `focus` picks the band vertically (centre / top / bottom); `focus_x` picks the
    horizontal position as a fraction of the slack, 0.0 = hard left, 0.5 =
    centred, 1.0 = hard right. Side-on studio shots put the speaker off centre,
    so sometimes 0.35 is the difference between a clip of someone and a clip of
    a chair.
    """
    focus_y = FOCUS_Y.get(focus, "0.5")
    if focus_x is None:
        x = "(iw-ow)/2"
    else:
        clamped = min(max(float(focus_x), 0.0), 1.0)
        x = f"(iw-ow)*{clamped:.4f}"
    return x, focus_y


def build_filtergraph(plan: dict, *, focus: str = "centre", source_fps: float | None = None,
                      with_audio: bool = True,
                      source_duration: float | None = None,
                      focus_x: float | None = None) -> str:
    """The `-filter_complex` string for a plan (kept separate so it is testable).

    Hard cuts are concatenated; blends are done with `xfade`, and the outgoing
    shot's tail is extended by the blend's length so the clip still lasts exactly
    as long as the plan says. (A crossfade overlaps two shots, so without the
    extension every blend would shorten the clip.)

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
    offset_x, focus_y = crop_offset(focus, focus_x)
    shots = plan["shots"]
    blends = _blends(shots, source_duration)
    parts: list[str] = []
    for i, shot in enumerate(shots):
        start, end = shot["start"], shot["end"]
        trim_end = round(min(end, source_duration) if source_duration else end, 3)
        chain = [
            f"trim=start={start:.3f}:end={trim_end:.3f}",
            "setpts=PTS-STARTPTS",
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}:{offset_x}:(ih-{height})*{focus_y}",
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
            parts.append(f"[0:a]atrim=start={start:.3f}:end={trim_end:.3f},"
                         f"asetpts=PTS-STARTPTS[a{i}]")
    if blends:
        parts.append(_blend_chain(shots, blends))
        return ";".join(parts)
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
    from . import plan as plan_mod

    shortening = round(sum(float(s.get("transition_duration") or 0.0) for s in kept[1:]
                           if str(s.get("transition") or "cut") != "cut"), 3)
    clip = {**plan["clip"], "end": kept[-1]["end"],
            "duration": round(sum(s["duration"] for s in kept) - shortening, 4),
            "blend_shortening": shortening, "trimmed_to_source": True}
    kept = [{**s, "index": i + 1} for i, s in enumerate(kept)]
    plan_mod._timeline(kept)
    return {**plan, "shots": kept, "clip": clip}


def _blend_chain(shots: list[dict], blends: list[tuple[int, str, float]]) -> str:
    """xfade/acrossfade the shots together.

    A dissolve shows the last `d` of the outgoing shot on top of the first `d`
    of the incoming shot, so both are still on screen at the same time: the clip
    ends up `d` shorter, which is what a real dissolve does too (the plan says so
    in `blend_shortening`, and every shot carries its `out_start`/`out_end`).

    Verified against ffmpeg's actual behaviour rather than its docs: `xfade`
    plays the main input up to `offset`, blends for `duration`, then continues
    with the second input - and ends when the *second* input ends, so the
    running length grows by (planned length - blend) per shot. `acrossfade`
    shortens by the same amount, which is why the audio stays in step.
    """
    last = len(blends) - 1
    video_label, audio_label = "v0", "a0"
    parts: list[str] = []
    cursor = float(shots[0]["duration"])
    for k, (index, name, seconds) in enumerate(blends):
        offset = round(cursor - seconds, 3)
        v_out = "v" if k == last else f"vx{k}"
        a_out = "a" if k == last else f"ax{k}"
        parts.append(
            f"[{video_label}][v{index + 1}]xfade=transition={XFADE_NAMES.get(name, name)}"
            f":duration={seconds:.3f}:offset={offset:.3f}[{v_out}]")
        parts.append(f"[{audio_label}][a{index + 1}]acrossfade=d={seconds:.3f}:"
                     f"c1=tri:c2=tri[{a_out}]")
        cursor = round(offset + float(shots[index + 1]["duration"]), 3)
        video_label, audio_label = v_out, a_out
    if video_label != "v":              # no blends after all: keep the labels honest
        parts.append(f"[{video_label}]null[v];[{audio_label}]anull[a]")
    return ";".join(parts)


def render_plan(plan: dict, out_path: str | Path, *, focus: str = "centre",
                focus_x: float | None = None,
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
        "-filter_complex", build_filtergraph(plan, focus=focus, focus_x=focus_x,
                                             source_fps=info.fps,
                                             with_audio=with_audio,
                                             source_duration=info.duration),
        "-map", "[v]", *(["-map", "[a]"] if with_audio else []),
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-r", str(fps),
        *(["-c:a", "aac", "-b:a", audio_bitrate] if with_audio else ["-an"]),
        # the video and audio are the same length by construction; -shortest keeps
        # the container honest if a future filter change ever breaks that
        *(["-shortest"] if with_audio else []),
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
             blend=plan["style"].get("transition", "cut"),
             dur=f"{rendered.duration:.1f}s",
             size=f"{out_path.stat().st_size / 1024:.0f} KB",
             source_fps=info.fps)
    return out_path
