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

    mode = mode or cap_style.get("mode") or "karaoke"
    twidth, theight = int(preset["width"]), int(preset["height"])
    if mode == "block":
        from . import block as block_mod

        blocks = getattr(block_mod, "segment_sentences")(transcript.words)
        ass_path, block_info = block_mod.write_block_ass(
            work / "captions.ass", transcript.words, style,
            width=twidth, height=theight,
            end=min(float(info.duration or 1e9), float(transcript.duration or 1e9)))
        cues = blocks  # the report reads block structure instead of word cues
        log.info("blocks", n=len(block_info))
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
        burn(src, out, ass_path, preset=preset, fit=fit, start=start, duration=duration,
             target_size=(twidth, theight),
             grade=style.get("grade") or None, inserts=inserts)
        output_path = str(out)
        log.info("wrote", output=output_path)

    result = CaptionResult(
        source=str(src), provider=transcript.provider,
        duration=round(transcript.duration, 3), n_words=len(transcript.words), n_cues=len(cues),
        elapsed=round(time.time() - t0, 2), ass=str(ass_path), output=output_path,
        work_dir=str(work), transcript=str(work / "transcript.json"),
        cues=str(work / "cues.json"), style=style_from, warnings=warnings,
    )
    result.report = str(jsonio.save(work / "report.json", result.to_dict()))
    return result
