"""Command line interface.

    python -m clipper doctor
    python -m clipper captions raw.mp4 --campaign mycampaign
    python -m clipper transcribe raw.mp4 --asr faster_whisper --model small
    python -m clipper scan mycampaign
    python -m clipper serve --port 8000
    python -m clipper samples
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

from . import __version__, config
from .util import log


# ---------------------------------------------------------------------------
def cmd_doctor(args: argparse.Namespace) -> int:
    ok = True
    print(f"clipper {__version__}")
    print(f"python       {sys.version.split()[0]}  ({platform.system()} {platform.machine()})")
    print(f"root         {config.ROOT}")
    print()
    print("ffmpeg")
    try:
        from . import ffmpeg as ff

        print(f"  binary     {ff.ffmpeg_exe()}")
        ver = ff.run([ff.ffmpeg_exe(), "-version"], check=False).stdout.splitlines()[0]
        print(f"  version    {ver}")
        print(f"  ffprobe    {ff.ffprobe_exe() or 'not found (using ffmpeg parsing fallback)'}")
        for f in ("subtitles", "ass", "overlay", "zoompan", "xfade", "drawtext"):
            print(f"  filter     {f:<9} {'yes' if ff.has_filter(f) else 'NO'}")
        for e in ("libx264", "aac", "libx265"):
            print(f"  encoder    {e:<9} {'yes' if ff.has_encoder(e) else 'NO'}")
        if not ff.has_filter("subtitles"):
            ok = False
            print("             !! no libass: install a full ffmpeg build to burn captions")
    except Exception as exc:
        ok = False
        print(f"  ERROR {exc}")
    print()
    print("python deps")
    for mod, why in (("numpy", "arrays"), ("cv2", "stage 1 style extraction"),
                     ("onnxruntime", "silero VAD"), ("silero_vad", "VAD model"),
                     ("moonshine_cpp", "ASR (default)"), ("faster_whisper", "ASR (best quality)")):
        try:
            mod_obj = __import__(mod)
            ver = getattr(mod_obj, "__version__", "?")
            print(f"  {mod:<15} {str(ver):<10} ok        ({why})")
        except Exception:
            hint = {"cv2": "pip install opencv-python-headless",
                    "moonshine_cpp": "pip install moonshine-cpp",
                    "faster_whisper": "pip install faster-whisper (optional)",
                    "silero_vad": "pip install silero-vad",
                    "onnxruntime": "pip install onnxruntime"}.get(mod, "pip install " + mod)
            level = "missing  " if mod in ("cv2",) else "optional "
            print(f"  {mod:<15} {'-':<10} {level} ({why}; {hint})")
    print()
    print("ASR providers")
    from .asr import get_provider, list_providers

    for name in list_providers():
        try:
            prov = get_provider(name)
            if prov.available():
                extra = ""
                try:
                    if hasattr(prov, "_resolve_model_dir"):
                        extra = f" model={prov._resolve_model_dir()}"
                except Exception:
                    pass
                print(f"  {name:<15} ready{extra}")
            else:
                print(f"  {name:<15} unavailable")
                if name == "moonshine":
                    ok = False
        except Exception as exc:
            print(f"  {name:<15} unavailable ({type(exc).__name__})")
    print()
    print("voice activity detection")
    try:
        from .align.vad import SileroVAD

        vad = SileroVAD()
        print(f"  silero     {'ready' if vad.available() else 'unavailable'}  {vad.model_path or ''}")
    except Exception as exc:
        print(f"  silero     error: {exc}")
    print()
    for label, path in (("campaigns", config.CAMPAIGNS), ("styles", config.STYLES),
                        ("work", config.WORK), ("output", config.OUTPUT), ("models", config.MODELS)):
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write-test"
            probe.write_text("x")
            probe.unlink()
            print(f"{label:<12} {path}  writable")
        except Exception as exc:
            ok = False
            print(f"{label:<12} {path}  ERROR {exc}")
    print()
    print("RESULT:", "ready" if ok else "problems found (see above)")
    return 0 if ok else 1


def cmd_scan(args: argparse.Namespace) -> int:
    from .ingest.scan import find_campaign_dirs, scan_campaign

    if not args.campaign:
        dirs = find_campaign_dirs()
        if not dirs:
            print("no campaigns found. expected: campaigns/<name>/{references,raw}")
            return 1
        for d in dirs:
            scan_campaign(d)
        return 0
    scan_campaign(args.campaign)
    return 0


def cmd_transcribe(args: argparse.Namespace) -> int:
    from .asr import get_provider
    from .ffmpeg import decode_audio, write_wav
    from .util import jsonio

    src = Path(args.file)
    if not src.exists():
        print(f"file not found: {src}")
        return 1
    audio = decode_audio(src, rate=16000)
    kwargs = {}
    if args.model:
        kwargs["model"] = args.model
    prov = get_provider(args.asr, **kwargs) if args.asr != "auto" else get_provider("auto")
    transcript = prov.transcribe(audio, 16000)
    out = Path(args.out) if args.out else config.WORK / src.stem / "transcript.json"
    jsonio.save(out, transcript.to_dict())
    print(f"provider : {transcript.provider}")
    print(f"words    : {len(transcript.words)}")
    print(f"duration : {transcript.duration:.1f}s")
    print(f"text     : {transcript.text[:400]}")
    print(f"written  : {out}")
    return 0


def cmd_captions(args: argparse.Namespace) -> int:
    from .captions import run_captions

    kwargs = {}
    if args.asr != "auto":
        asr_kwargs = {}
        if args.model:
            asr_kwargs["model"] = args.model
        if args.device:
            asr_kwargs["device"] = args.device
        if args.compute_type:
            asr_kwargs["compute_type"] = args.compute_type
        kwargs["provider"] = args.asr
        kwargs["asr_kwargs"] = asr_kwargs
    result = run_captions(
        args.file, args.out, style_path=args.style, campaign=args.campaign,
        platform=args.platform, fit=args.fit, ass_only=args.ass_only,
        max_words=args.max_words, mode=args.mode, **kwargs,
    )
    print(json.dumps(result.to_dict(), indent=2))
    for w in result.warnings:
        log.warn(w)
    return 0


def cmd_style(args: argparse.Namespace) -> int:
    from .ingest.scan import find_campaign_dirs
    from .style.extract import DEFAULT_SAMPLE_FPS, DEFAULT_SAMPLE_WIDTH, extract_style

    targets: list[Path] = []
    if args.campaign:
        targets = [Path(args.campaign)]
    else:
        targets = find_campaign_dirs()
        if not targets:
            print("no campaigns found. expected: campaigns/<name>/{references,raw}")
            return 1
    for target in targets:
        profile = extract_style(target, fps=args.fps or DEFAULT_SAMPLE_FPS,
                                width=args.width or DEFAULT_SAMPLE_WIDTH,
                                max_seconds=args.max_seconds, save_evidence=not args.no_evidence)
        caps = profile.get("captions", {})
        print()
        print(f"campaign : {profile['campaign']}")
        print(f"style    : {config.STYLES / (profile['campaign'] + '.style.json')}")
        print(f"pacing   : {profile['pacing'].get('avg_shot_len')}s avg shot, "
              f"{profile['pacing'].get('cuts_per_minute')} cuts/min")
        print(f"zoom     : {profile['zoom'].get('dominant')} "
              f"{profile['zoom'].get('punch_in_scale') or ''} "
              f"({profile['zoom'].get('punch_in_duration') or '-'}s)")
        if caps.get("present"):
            print(f"captions : font {caps.get('font_size_ass')}px, "
                  f"{caps.get('primary_color')} on {caps.get('outline_color')} "
                  f"(outline {caps.get('outline_width')}), casing {caps.get('casing') or 'as-is'}, "
                  f"cy {caps.get('position', {}).get('cy')}")
            karaoke = caps.get("karaoke", {})
            print(f"           karaoke {karaoke.get('enabled')} "
                  f"{karaoke.get('highlight_color') or ''}, "
                  f"{caps.get('max_words_per_cue')} words/cue, {caps.get('max_lines')} line(s)")
        else:
            print("captions : none detected")
        print(f"audio    : {profile['audio'].get('target_lufs')} LUFS, "
              f"music bed {profile['audio'].get('music_bed')}")
        print(f"confidence: {profile.get('confidence')}")
        if profile.get("source", {}).get("notes"):
            print(f"notes    : {profile['source']['notes']}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .serve.viewer import serve

    serve(port=args.port, host=args.host)
    return 0


def cmd_samples(args: argparse.Namespace) -> int:
    from .samples import make_demo_campaign

    out = make_demo_campaign(force=args.force)
    print(f"sample campaign ready: {out}")
    print("open it with: python -m clipper serve")
    return 0


# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("clipper", description="Whop clipping pipeline",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="check ffmpeg, deps, models and folders").set_defaults(func=cmd_doctor)

    s = sub.add_parser("scan", help="stage 0: probe a campaign folder into work/<name>/manifest.json")
    s.add_argument("campaign", nargs="?", help="campaign folder name (omit to scan all)")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("transcribe", help="speech to timed words")
    s.add_argument("file")
    s.add_argument("--asr", default="auto", help="auto | moonshine | faster_whisper | fixture")
    s.add_argument("--model", default=None, help="whisper model size, e.g. small / medium")
    s.add_argument("--out", default=None, help="output transcript.json path")
    s.set_defaults(func=cmd_transcribe)

    s = sub.add_parser("captions", help="stage 3: styled, burned-in captions (9:16)")
    s.add_argument("file")
    s.add_argument("--out", default=None, help="output video path")
    s.add_argument("--style", default=None, help="path to a style profile json")
    s.add_argument("--campaign", default=None, help="use styles/<campaign>.style.json")
    s.add_argument("--platform", default=config.DEFAULT_PLATFORM, choices=sorted(config.PLATFORMS))
    s.add_argument("--fit", default="cover", choices=["cover", "blurpad", "none"])
    s.add_argument("--asr", default="auto")
    s.add_argument("--model", default=None)
    s.add_argument("--device", default=None, help="cpu | cuda (faster_whisper)")
    s.add_argument("--compute-type", default=None, help="int8 | float16 | float32")
    s.add_argument("--max-words", type=int, default=None, help="words per cue")
    s.add_argument("--mode", default=None, choices=["line", "word"], help="caption look")
    s.add_argument("--ass-only", action="store_true", help="write .ass, do not encode video")
    s.set_defaults(func=cmd_captions)

    s = sub.add_parser("style", help="stage 1: learn a campaign style from /references")
    s.add_argument("campaign", nargs="?", help="campaign folder (omit to do all)")
    s.add_argument("--fps", type=float, default=None, help="analysis sampling rate (default 6)")
    s.add_argument("--width", type=int, default=None, help="analysis frame width (default 320)")
    s.add_argument("--max-seconds", type=float, default=None, help="only analyse the start of each reference")
    s.add_argument("--no-evidence", action="store_true", help="skip annotated evidence frames")
    s.set_defaults(func=cmd_style)

    s = sub.add_parser("serve", help="browse footage, styles and finished clips")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--host", default="0.0.0.0")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("samples", help="generate a tiny synthetic campaign for testing")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_samples)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        log.error(str(exc))
        if "--debug" in (argv or sys.argv):
            raise
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
