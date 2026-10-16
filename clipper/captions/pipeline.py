"""Stage 3 - captions, end to end.

    video/audio file
        -> decode audio (16 kHz mono)
        -> ASR provider           (moonshine | faster_whisper | fixture)
        -> word timings           (native, or energy alignment when missing)
        -> cues                   (2-4 words, sentence aware)
        -> style profile          -> .ass
        -> ffmpeg burn-in         -> 1080x1920 ready for TikTok/Reels/Shorts

Every intermediate is written to work/<name>/ so the stage can be re-run
partially, inspected, or reused by the edit stage.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .. import config
from ..asr import get_provider
from ..asr.base import Transcript
from ..ffmpeg import decode_audio, probe
from ..util import jsonio, log
from .ass import write_ass
from .cues import group_words
from .render import burn


@dataclass
class CaptionResult:
    source: str
    provider: str
    duration: float
    n_words: int
    n_cues: int
    elapsed: float
    ass: str | None = None
    output: str | None = None
    work_dir: str | None = None
    transcript: str | None = None
    cues: str | None = None
    report: str | None = None
    style: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def resolve_style(name: str | None = None, style_path: str | Path | None = None,
                  platform: str = config.DEFAULT_PLATFORM) -> tuple[dict, str]:
    """Default style <- platform loudness <- (styles/<name>.style.json | explicit path)."""
    preset = config.PLATFORMS.get(platform, config.PLATFORMS[config.DEFAULT_PLATFORM])
    style = config.deep_merge(config.DEFAULT_STYLE, {"audio": {"target_lufs": preset["loudness_lufs"]}})
    source = "built-in default"
    candidate: Path | None = None
    if style_path:
        candidate = Path(style_path)
    elif name:
        p = config.STYLES / f"{name}.style.json"
        candidate = p if p.exists() else None
    if candidate and candidate.exists():
        user = jsonio.load(candidate, {}) or {}
        style = config.deep_merge(style, user)
        source = str(candidate)
    return style, source


def _apply_word_fixes(words, fixes: dict[str, str]) -> int:
    """Word corrections as data ('fence' -> 'offense'), applied to every
    transcript word before anything is timed, tightened or captioned - so
    a fix told once lives in the creator's profile and heals every future
    clip. Matching ignores case and surrounding punctuation; the
    replacement inherits both, so 'Fence,' becomes 'Offense,'."""
    if not fixes:
        return 0
    table = {str(k).strip().lower(): str(v) for k, v in fixes.items()}
    n = 0
    for w in words:
        text = str(w.text)
        core = text.strip(".,!?;:\"'()[]")
        if not core or core.lower() not in table:
            continue
        rep = table[core.lower()]
        if core[:1].isupper():
            rep = rep[:1].upper() + rep[1:]
        i = text.index(core)
        w.text = text[:i] + rep + text[i + len(core):]
        n += 1
    return n


def _select_hits(block_info: list[dict]) -> list[dict]:
    """Camera-punch / sound-pop moments from caption blocks.

    Chronological, >=6s apart, at most 5 - and the climax is reserved
    FIRST: the strongest sentence-complete block in the last 45% of the
    clip. Reserving "the last block" instead backfired on real footage:
    the final block is often a crosstalk tail fragment ("From a dead
    yeah 68 of them") and the spike landed in the fade-out on junk
    while the actual payoff sentence went unpunched.
    """
    timed = sorted((b for b in block_info
                    if float(b.get("emphasis_at") or 0) >= 1.2),
                   key=lambda b: float(b["emphasis_at"]))
    if not timed:
        return []
    dur = max(float(b.get("end") or 0) for b in block_info)

    def hit(b: dict) -> dict:
        return {"at": float(b["emphasis_at"]),
                "strength": float(b.get("emphasis_strength") or 0.8)}

    late = [b for b in timed
            if float(b["emphasis_at"]) >= 0.55 * dur
            and float(b["emphasis_at"]) <= dur - 1.0] or timed
    climax = max(late, key=lambda b: (
        float(b.get("emphasis_strength") or 0.8),
        1 if str(b.get("text") or "").rstrip().endswith((".", "?", "!")) else 0,
        len(str(b.get("text") or "").split()),
        float(b["emphasis_at"])))
    picked = [hit(climax)]
    for b in timed:
        if len(picked) >= 5:
            break
        at = float(b["emphasis_at"])
        if all(abs(at - float(p["at"])) >= 6.0 for p in picked):
            picked.append(hit(b))
    picked.sort(key=lambda p: p["at"])
    return picked


def _typing_strokes(hook_lines, block_info, name, cap_style) -> list[dict]:
    """Keystroke sfx for typed text: the hook headline types word by word
    (marks come from the same hook_word_times the ASS used, so sound and
    text land on the same frame), every caption block lands with one very
    light tick. Five synthesized variants, a random pick per stroke,
    +-10% volume / +-3% pitch - human, never looped."""
    import random

    from . import keysfx
    from .block import hook_type_marks

    bank = keysfx.bank_files()
    if not bank:
        return []
    rng = random.Random(f"keys:{name}")
    key_vol = float(cap_style.get("key_volume") or 0.10)
    tick_vol = float(cap_style.get("tick_volume") or 0.07)
    strokes: list[dict] = []
    for at, kind in hook_type_marks(hook_lines or []):
        if kind == "enter":
            strokes.append({"at": at, "file": bank["enter"],
                            "volume": round(key_vol * 1.1, 3),
                            "rate": round(rng.uniform(0.99, 1.01), 3)})
        else:
            strokes.append({"at": at, "file": rng.choice(bank["keys"]),
                            "volume": round(key_vol * rng.uniform(0.9, 1.1), 3),
                            "rate": round(rng.uniform(0.97, 1.03), 3)})
    for b in block_info:
        at = float(b.get("start") or 0)
        if at < 0.05:
            continue
        strokes.append({"at": at, "file": rng.choice(bank["keys"]),
                        "volume": round(tick_vol * rng.uniform(0.9, 1.1), 3),
                        "rate": round(rng.uniform(0.97, 1.03), 3)})
    if strokes:
        log.info("typing sound", n=len(strokes), key_vol=key_vol,
                 tick_vol=tick_vol)
    return strokes


def run_captions(
    src: str | Path,
    out: str | Path | None = None,
    *,
    style: dict | None = None,
    style_path: str | Path | None = None,
    campaign: str | None = None,
    provider: str = "auto",
    platform: str = config.DEFAULT_PLATFORM,
    fit: str = "cover",
    burn_in: bool = True,
    ass_only: bool = False,
    work_name: str | None = None,
    max_words: int | None = None,
    mode: str | None = None,
    start: float | None = None,
    duration: float | None = None,
    asr_kwargs: dict | None = None,
    words: list | None = None,
    inserts: list[dict] | None = None,
    accent: str | None = None,
    hook: str | None = None,
    outro_text: str | None = None,
    fade_out: float | None = None,
    whoosh: list[float] | None = None,
    punch: bool = False,
    tighten: bool = False,
    tighten_gap: float | None = None,
    sound: bool = False,
    typing_sound: bool = True,
    cards: list[dict] | None = None,
    stickers: list[dict] | None = None,
    lists: list[dict] | None = None,
    music: str | None = None,
    handle: str | None = None,
    word_fixes: dict | None = None,
    watermark: str | None = None,
) -> CaptionResult:
    t0 = time.time()
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(src)
    preset = config.PLATFORMS.get(platform, config.PLATFORMS[config.DEFAULT_PLATFORM])
    name = work_name or src.stem
    work = config.WORK / name
    work.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    if style is None:
        style, style_from = resolve_style(campaign, style_path, platform)
    else:
        style, style_from = style, "explicit dict"
    log.info("style", source=style_from)

    if max_words:
        style = config.deep_merge(style, {"captions": {"max_words_per_cue": int(max_words)}})
    if accent:
        style = config.deep_merge(style, {"captions": {"block": {"emphasis_color": accent}}})
    if not typing_sound:
        # the headline must not type silently: the ASS stagger and the
        # keystroke mix are one feature, gated by the same flag
        style = config.deep_merge(style, {"captions": {"block": {"typing_hook": False}}})
    cap_style = style["captions"]

    info = probe(src)
    log.info("source", file=src.name, duration=f"{info.duration:.1f}s",
             size=f"{info.width}x{info.height}", audio=info.has_audio)
    if not info.has_audio:
        raise RuntimeError(f"{src.name} has no audio track - captions need speech")
    if words:
        pass
    elif info.height and info.width and info.height < info.width and fit == "cover":
        warnings.append("source is landscape; the frame is centre-cropped to 9:16 (stage 4 "
                        "adds speaker tracking / split layouts)")

    if words:
        # timings came from the source transcript through the edit plan (captions.remap),
        # so there is nothing to recognise and, more to the point, nothing to re-guess
        from ..asr.base import Word

        given = [w if isinstance(w, Word) else Word.from_dict(w) for w in words]
        transcript = Transcript(words=given, text=" ".join(w.text for w in given),
                                language="en", provider="plan", duration=float(info.duration or 0.0),
                                meta={"source": "remapped from the source transcript"})
        log.info("transcript", words=len(transcript.words), provider="plan (remapped)")
    else:
        audio = decode_audio(src, rate=16000, start=start, duration=duration)
        with log.step("asr", provider=provider):
            prov = get_provider(provider, **(asr_kwargs or {})) if provider != "auto" else get_provider("auto")
            transcript: Transcript = prov.transcribe(audio, 16000)
        log.info("transcript", words=len(transcript.words), provider=transcript.provider,
                 chars=len(transcript.text))
    if not transcript.words:
        warnings.append("no words recognised - is there speech in this file?")
    if transcript.provider == "plan":
        warnings.append("word timings carried over from the source transcript through the edit "
                        "plan - no second speech recognition pass")
    elif transcript.words and all(w.source != "native" for w in transcript.words) and \
            transcript.provider == "moonshine":
        warnings.append("word timings are estimated by the energy aligner (+/- ~100 ms); "
                        "use --asr faster_whisper for exact timings")

    fixes = dict(cap_style.get("word_fixes") or {})
    if word_fixes:
        fixes.update(word_fixes)
    if fixes and transcript.words:
        applied = _apply_word_fixes(transcript.words, fixes)
        if applied:
            transcript.text = " ".join(w.text for w in transcript.words)
            log.info("word fixes", applied=applied, rules=fixes)

    tighten_on = tighten or bool(cap_style.get("tighten"))
    if tighten_on and transcript.words:
        # cut the dead air between sentences and carry every timestamp
        # (words, whooshes, inserts) through the cuts - see captions.tighten
        from . import tighten as tighten_mod
        from .remap import remap_words

        total = float(duration) if duration else float(info.duration or 0.0)
        gap = float(tighten_gap or cap_style.get("tighten_gap")
                    or tighten_mod.DEFAULT_MIN_GAP)
        cuts = tighten_mod.dead_air_cuts(transcript.words, min_gap=gap)
        if cuts:
            segs = tighten_mod.kept_segments(cuts, total)
            tightened_path = work / "tightened.mp4"
            tighten_mod.assemble(src, segs, tightened_path,
                                 offset=float(start or 0.0))
            plan = {"shots": [{"start": s, "end": e} for s, e in segs]}
            new_words = remap_words(plan, transcript.words)
            transcript = Transcript(
                words=new_words,
                text=" ".join(w.text for w in new_words),
                language=transcript.language, provider=transcript.provider,
                duration=tighten_mod.kept_duration(segs),
                meta={**(transcript.meta or {}), "tightened": True})
            if whoosh:
                whoosh = [tighten_mod.map_time(t, cuts) for t in whoosh]
            if inserts:
                inserts = [{**i, "start": tighten_mod.map_time(
                    float(i.get("start") or 0.0), cuts)} for i in inserts]
            removed = round(total - tighten_mod.kept_duration(segs), 2)
            src = tightened_path
            info = probe(src)
            start = duration = None
            log.info("tightened", cuts=len(cuts), removed_s=removed,
                     duration=f"{info.duration:.1f}s")
        else:
            log.info("tightened", cuts=0, note="no pause long enough to cut")

    want_punch = punch or bool(cap_style.get("camera_punch"))
    hook_lines = [x.strip() for x in hook.split("|") if x.strip()] if hook else None
    outro_line = outro_text if outro_text is not None else cap_style.get("outro_text")
    handle_line = handle if handle is not None else (
        (cap_style.get("handles") or {}).get(platform)
        or cap_style.get("handle"))
    fade_seconds = (float(fade_out) if fade_out is not None
                    else float(cap_style.get("fade_out_seconds") or 0.0))
    # campaign brand watermark: CLI spec "FILE[,POS[,FRAC]]" or a profile
    # captions.watermark (string same format, or dict). Full-duration,
    # topmost layer - see captions.render.burn.
    wm_spec = watermark if watermark is not None else cap_style.get("watermark")
    wm = None
    if wm_spec:
        if isinstance(wm_spec, dict):
            wm = {"file": str(wm_spec.get("file") or ""),
                  "position": str(wm_spec.get("position") or "tr"),
                  "width_frac": float(wm_spec.get("width_frac") or 0.24)}
        else:
            parts = [x.strip() for x in str(wm_spec).split(",")]
            wm = {"file": parts[0],
                  "position": parts[1] if len(parts) > 1 and parts[1] else "tr",
                  "width_frac": float(parts[2]) if len(parts) > 2 and parts[2] else 0.24}
        if not wm["file"] or not Path(wm["file"]).exists():
            raise FileNotFoundError(f"watermark file not found: {wm['file']!r}")
        log.info("watermark", file=Path(wm["file"]).name,
                 position=wm["position"], width_frac=wm["width_frac"])
    sfx = None
    if whoosh:
        whoosh_wav = config.ROOT / "assets" / "sfx" / "whoosh.wav"
        if whoosh_wav.exists():
            sfx = [{"at": float(t), "file": str(whoosh_wav), "volume": 0.45} for t in whoosh]
        else:
            warnings.append(f"whoosh requested but {whoosh_wav} is missing - skipped")

    sound_on = sound or bool(cap_style.get("sound_design"))
    if sound_on:
        # a riser swelling under the hook is the cheapest retention trick in
        # the book; the matching pops ride the camera punches and are added
        # in the block branch below, where the punch times are known
        riser_wav = config.ROOT / "assets" / "sfx" / "riser.wav"
        if riser_wav.exists():
            sfx = [{"at": 0.0, "file": str(riser_wav), "volume": 0.20}] + list(sfx or [])
        else:
            warnings.append(f"sound design requested but {riser_wav} is missing - skipped")

    mode = mode or cap_style.get("mode") or "karaoke"
    twidth, theight = int(preset["width"]), int(preset["height"])
    if mode == "poster":
        from . import poster as poster_mod

        ass_path, block_info = poster_mod.write_poster_ass(
            work / "captions.ass", transcript.words, style,
            width=twidth, height=theight,
            end=min(float(info.duration or 1e9), float(transcript.duration or 1e9)),
            hook_lines=hook_lines, outro_text=outro_line,
            handle=handle_line, cards=cards, stickers=stickers, lists=lists)
        cues = block_info
        log.info("poster blocks", n=len(block_info),
                 cards=len(cards or []), stickers=len(stickers or []))
        punch_list = None
        if want_punch:
            picked = _select_hits(block_info)
            punch_list = picked or None
            if punch_list:
                log.info("camera punches", at=[p["at"] for p in punch_list])
        if not block_info:
            warnings.append("no poster blocks produced")
        if typing_sound and block_info:
            strokes = _typing_strokes(hook_lines, block_info, name, cap_style)
            if strokes:
                sfx = list(sfx or []) + strokes
        jsonio.save(work / "cues.json", {"mode": "poster",
                                        "count": len(block_info),
                                        "blocks": block_info})
    elif mode == "block":
        from . import block as block_mod

        blocks = getattr(block_mod, "segment_sentences")(transcript.words)
        ass_path, block_info = block_mod.write_block_ass(
            work / "captions.ass", transcript.words, style,
            width=twidth, height=theight,
            end=min(float(info.duration or 1e9), float(transcript.duration or 1e9)),
            hook_lines=hook_lines, outro_text=outro_line,
            handle=handle_line)
        cues = blocks  # the report reads block structure instead of word cues
        log.info("blocks", n=len(block_info))
        punch_list = None
        if want_punch or sound_on:
            # a spike on every big word is a seizure, not a style
            picked = _select_hits(block_info)
            if want_punch:
                punch_list = picked or None
                if punch_list:
                    log.info("camera punches", at=[p["at"] for p in punch_list])
            if sound_on and picked:
                # one pop per punch, on the exact frame the big word lands -
                # the ear confirms what the eye just saw zoom
                pop_wav = config.ROOT / "assets" / "sfx" / "pop.wav"
                if pop_wav.exists():
                    sfx = list(sfx or []) + [
                        {"at": p["at"], "file": str(pop_wav), "volume": 0.32}
                        for p in picked]
                    log.info("sound pops", n=len(picked),
                             at=[p["at"] for p in picked])
        if typing_sound and block_info:
            strokes = _typing_strokes(hook_lines, block_info, name, cap_style)
            if strokes:
                sfx = list(sfx or []) + strokes
            else:
                warnings.append("typing sound on but the key bank is missing "
                                "(run: python -m clipper.captions.keysfx)")
        if not block_info:
            warnings.append("no caption blocks produced")
        jsonio.save(work / "cues.json", {"mode": "block", "count": len(block_info),
                                         "blocks": block_info})
    else:
        cues = group_words(
            transcript.words,
            max_words=int(cap_style.get("max_words_per_cue") or 4),
            max_chars=int(cap_style.get("max_chars_per_line") or 22),
            max_lines=int(cap_style.get("max_lines") or 1),
        )
        log.info("cues", n=len(cues))
        if not cues:
            warnings.append("no cues produced")
        ass_path = write_ass(work / "captions.ass", cues, style,
                             width=twidth, height=theight, mode=mode)
        jsonio.save(work / "cues.json", {"count": len(cues),
                                         "cues": [c.to_dict() for c in cues]})
    jsonio.save(work / "transcript.json", transcript.to_dict())
    jsonio.save(work / "style.used.json", style)

    output_path = None
    if burn_in and not ass_only:
        out = Path(out) if out else config.OUTPUT / f"{name}.captioned.mp4"
        from .musicbed import bed_file

        music_path = bed_file(music) if music else None
        if music and not music_path:
            warnings.append(f"music bed '{music}' not found in assets/music - skipped")
        burn(src, out, ass_path, preset=preset, fit=fit, start=start, duration=duration,
             target_size=(twidth, theight),
             grade=style.get("grade") or None, inserts=inserts,
             outro=fade_seconds, sfx=sfx,
             punches=punch_list if mode in ("block", "poster") else None,
             watermark=wm, music=music_path)
        output_path = str(out)
        log.info("wrote", output=output_path)

        # automated QC on every render (House rule): first caption within
        # 1 s, no caption over a face, no static shot over 4 s, sane
        # loudness, headline matching the opening words. The report lands
        # next to the video; failures ride along as warnings.
        try:
            from ..qc import run_qc

            report = run_qc(
                out, ass=ass_path, hook_lines=hook_lines,
                words=[{"text": str(w.text), "start": float(w.start)}
                       for w in transcript.words])
            qc_path = out.with_name(out.stem + ".qc.json")
            jsonio.save(qc_path, report)
            log.info("qc", status="PASS" if report["ok"] else "FAIL",
                     report=str(qc_path),
                     failed=[c["name"] for c in report["checks"]
                             if c["status"] == "fail"])
            for c in report["checks"]:
                if c["status"] == "fail":
                    warnings.append(f"qc: {c['name']}: {c['detail']}")
        except Exception as exc:  # QC must never sink a finished render
            warnings.append(f"qc: could not run ({exc})")

    result = CaptionResult(
        source=str(src), provider=transcript.provider,
        duration=round(transcript.duration, 3), n_words=len(transcript.words), n_cues=len(cues),
        elapsed=round(time.time() - t0, 2), ass=str(ass_path), output=output_path,
        work_dir=str(work), transcript=str(work / "transcript.json"),
        cues=str(work / "cues.json"), style=style_from, warnings=warnings,
    )
    result.report = str(jsonio.save(work / "report.json", result.to_dict()))
    return result
