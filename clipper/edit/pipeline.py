"""Stage 4 - assemble the chosen moments into vertical clips.

Reads what stage 2 picked (`work/<campaign>/candidates/*.json`), asks stage 1's
profile how the campaign cuts and moves the camera, and writes:

    work/<campaign>/edits/<clip>.plan.json   what will happen, before it happens
    work/<campaign>/edits/<clip>.mp4         the assembled clip (no captions yet)

Stage 5 adds captions, loudness and the platform encode.
"""
from __future__ import annotations

from pathlib import Path

from .. import config
from ..select import energy as energy_mod
from ..select.pipeline import load_transcript
from ..util import jsonio, log
from . import plan as plan_mod
from . import render as render_mod


def load_style(campaign: str | None = None, style_path: str | Path | None = None) -> dict:
    """The style profile to edit by: explicit path, campaign file, or defaults."""
    from ..style.profile import apply_defaults

    if style_path:
        data = jsonio.load(style_path, {}) or {}
        data.setdefault("path", str(style_path))
        return apply_defaults(data)
    if campaign:
        candidate = config.STYLES / f"{campaign}.style.json"
        if candidate.exists():
            data = jsonio.load(candidate, {}) or {}
            data.setdefault("path", str(candidate))
            return apply_defaults(data)
        log.warn("no style profile for this campaign, using defaults",
                 expected=str(candidate))
    return apply_defaults({})


def candidates_for(campaign: str | None, work_dir: Path | None = None,
                   media: str | None = None) -> list[dict]:
    """All candidate payloads written by stage 2."""
    folder = (Path(work_dir) if work_dir else (config.WORK / campaign if campaign else config.WORK))
    out: list[dict] = []
    for path in sorted(folder.glob("candidates/*.json")):
        if media and Path(media).stem != path.stem:
            continue
        payload = jsonio.load(path, None)
        if payload:
            payload["_path"] = str(path)
            out.append(payload)
    return out


def edit_campaign(campaign: str, *, top: int | None = None, shot_len: float | None = None,
                  platform: str = "tiktok", focus: str = "centre", focus_x: float | None = None,
                  style_path=None,
                  ids: list[str] | None = None, transcript=None, work_dir: Path | None = None,
                  render: bool = True, transition: str | None = None,
                  transition_duration: float | None = None, tag: str | None = None) -> list[dict]:
    """Assemble the candidates of one campaign into clips.

    `transition` / `transition_duration` override the style profile for this run
    (`--transition fade`), and `tag` renames the output so variants can sit next
    to each other in `edits/` instead of overwriting each other.
    """
    style = load_style(campaign, style_path)
    if transition or transition_duration:
        override: dict = {}
        if transition:
            override["in"] = transition
        if transition_duration:
            override["duration"] = transition_duration
        style = config.deep_merge(style, {"transitions": override})
    payloads = candidates_for(campaign, work_dir)
    if not payloads:
        raise RuntimeError(f"no candidates for '{campaign}' - run `python -m clipper select "
                           f"{campaign}` first")
    out_dir = (Path(work_dir) if work_dir else (config.WORK / campaign)) / "edits"
    results: list[dict] = []

    for payload in payloads:
        source = Path(payload["source"]["file"])
        candidates = payload.get("candidates", [])
        if top is not None:
            candidates = sorted(candidates, key=lambda c: -c["score"])[:top]
        if ids:
            candidates = [c for c in candidates if c.get("id") in ids]
        if not candidates:
            continue

        words = []
        if transcript:
            words = load_transcript(transcript)
        else:
            found = None
            from ..select.pipeline import find_transcript

            found = find_transcript(source, payload.get("campaign"))
            if found:
                words = load_transcript(found) or []
        curve = None
        try:
            curve = energy_mod.energy_curve(source)
        except Exception:                       # silent footage still edits fine
            log.debug("no audio curve for cut snapping", file=source.name)

        for candidate in candidates:
            candidate = {**candidate, "file": str(source),
                         "source_name": source.stem}
            built = plan_mod.build_plan(candidate, style=style, words=words, curve=curve,
                                        platform=platform, shot_len=shot_len,
                                        campaign=payload.get("campaign") or campaign)
            stem = f"{source.stem}_{str(candidate.get('id', 'clip')).lstrip('#')}"
            if tag:
                stem = f"{stem}_{tag}"
            plan_path = out_dir / f"{stem}.plan.json"
            jsonio.save(plan_path, built)
            record = {"plan": built, "plan_path": str(plan_path), "clip": None}
            if render:
                clip_path = out_dir / f"{stem}.mp4"
                render_mod.render_plan(built, clip_path, focus=focus, focus_x=focus_x)
                record["clip"] = str(clip_path)
            log.step("edit", clip=stem, shots=len(built["shots"]),
                     seconds=f"{built['clip']['duration']:.1f}")
            results.append(record)
    if not results:
        raise RuntimeError("nothing matched - check --top / --ids")
    return results
