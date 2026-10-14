"""Burn the .ass into the video with ffmpeg (libass), and shape the frame to 9:16.

Filter path escaping is the classic Windows trap (`C:\\Users\\...` inside
`subtitles=` needs `C\\:/Users/...`), so it lives in one tested helper.
"""
from __future__ import annotations

from pathlib import Path

from .. import config
from ..ffmpeg import ffmpeg_exe, has_filter, render as ff_render, probe
from ..util import log


def escape_filter_path(path: str | Path) -> str:
    """Escape a path for use inside an ffmpeg filter argument."""
    p = str(Path(path).resolve()).replace("\\", "/")
    p = p.replace(":", r"\:")
    p = p.replace("'", r"\'")
    return p


def fit_chain(width: int, height: int, fit: str = "cover", target: tuple[int, int] | None = None) -> str:
    """Scale/crop a source frame to the target canvas."""
    tw, th = target or (config.PLATFORMS[config.DEFAULT_PLATFORM]["width"],
                        config.PLATFORMS[config.DEFAULT_PLATFORM]["height"])
    if fit == "none":
        return f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=black"
    if fit == "blurpad":
        # blurred copy behind, sharp source in the middle (podcast-style vertical)
        return (f"split=2[bg][fg];"
                f"[bg]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},"
                f"boxblur=20:2[bgblur];"
                f"[fg]scale={tw}:{th}:force_original_aspect_ratio=decrease[fgscaled];"
                f"[bgblur][fgscaled]overlay=(W-w)/2:(H-h)/2")
    # cover (default): fill the canvas, centre crop
    return (f"scale={tw}:{th}:force_original_aspect_ratio=increase,"
            f"crop={tw}:{th},setsar=1")


def subtitles_filter(ass_path: str | Path, fonts_dir: str | Path | None = None) -> str:
    """`subtitles=...` filter with the repo font directory attached.

    Passing fontsdir matters more than it looks: without it libass resolves the
    font through system fontconfig and silently falls back to whatever is
    installed (DejaVu on a bare container), which changes glyph metrics and
    therefore every size the style extractor measures.
    """
    filt = f"subtitles=filename='{escape_filter_path(ass_path)}'"
    directory = Path(fonts_dir) if fonts_dir else config.FONTS
    if directory.exists() and any(directory.glob("*.ttf")):
        filt += f":fontsdir='{escape_filter_path(directory)}'"
    return filt


def grade_chain(grade: dict | None) -> str:
    """The "cinematic" finish as plain ffmpeg filters: vignette + a mild grade.

    From the tutorial recipe: a feathered dark pull at the frame edges (they
    mask a black video; `vignette` is the same thing, free) and a small
    contrast/saturation lift. Both stay subtle - a grade you notice on its own
    is a grade turned up too far.
    """
    if not grade:
        return ""
    parts = []
    amount = float(grade.get("vignette") or 0.0)
    if amount > 0.01:
        # vignette angle: 0.28 -> ~PI/5.6; the filter's max is PI/2 (very dark)
        angle = max(0.05, min(amount, 1.0)) * 1.35
        parts.append(f"vignette=angle={angle:.3f}")
    contrast = float(grade.get("contrast") or 1.0)
    saturation = float(grade.get("saturation") or 1.0)
    if abs(contrast - 1.0) > 0.005 or abs(saturation - 1.0) > 0.005:
        parts.append(f"eq=contrast={contrast:.3f}:saturation={saturation:.3f}")
    return ",".join(parts)


def _insert_chains(inserts: list[dict], base_w: int, base_h: int,
                   subs_label: str) -> tuple[str, list[str]]:
    """Overlay still images on the rendered frames, timed and faded.

    Each insert: {"file", "start", "duration", "at"}. Files are looped at the
    container level (`-loop 1 -t <duration>`); here they are scaled to 86% of
    frame width, alpha-faded, and placed mid-frame by default ("top_safe" puts
    them above the caption zone). The story-matched insert from the recipe:
    appears exactly when the word lands, leaves when the beat ends.
    """
    chains: list[str] = []
    pre: list[str] = []
    prev = subs_label
    for i, ins in enumerate(inserts):
        t = float(ins.get("start") or 0.0)
        dur = max(0.2, float(ins.get("duration") or 1.8))
        where = str(ins.get("at") or "middle")
        fd = min(0.25, dur / 4.0)
        if where == "full":
            # the tutorial's actual pattern: a cutaway. The picture REPLACES
            # the picture for the beat - never pasted across the subject's face
            scaler = (f"scale={base_w}:{base_h}:force_original_aspect_ratio=increase,"
                      f"crop={base_w}:{base_h}")
            y = "0"
        else:
            scaler = f"scale={int(base_w * 0.86)}:-2:force_original_aspect_ratio=decrease"
            y = "((H-h)*0.52)" if where == "top_safe" else "(H-h)/2-h*0.18"
        pre.append(
            f"[{i + 1}:v]{scaler},"
            f"setsar=1,fade=t=in:st=0:d={fd:.3f}:alpha=1,"
            f"fade=t=out:st={dur - fd:.3f}:d={fd:.3f}:alpha=1,setpts=PTS-STARTPTS+{t:.3f}/TB[ov{i}]")
        chains.append(
            f"[{prev}][ov{i}]overlay=(W-w)/2:{y}:eof_action=pass[vins{i}]")
        prev = f"vins{i}"
    return ";".join(chains), pre


def burn(src: str | Path, dst: str | Path, ass_path: str | Path, *,
         preset: dict | None = None, fit: str = "cover",
         fonts_dir: str | Path | None = None, start: float | None = None,
         duration: float | None = None, loudness: bool = True,
         target_size: tuple[int, int] | None = None,
         grade: dict | None = None,
         inserts: list[dict] | None = None) -> Path:
    """Encode `src` to `dst` with the subtitles burned in.

    Grade goes *before* subtitles so the text stays crisp white; timed image
    inserts overlay after them (they live under the text, like the tutorials').
    """
    if not has_filter("subtitles"):
        raise RuntimeError(
            "this ffmpeg build has no 'subtitles' filter (no libass) - "
            "install a full build: https://www.gyan.dev/ffmpeg/builds/"
        )
    p = dict(preset or {})
    src_info = probe(src)
    tw, th = target_size or (config.PLATFORMS[config.DEFAULT_PLATFORM]["width"],
                             config.PLATFORMS[config.DEFAULT_PLATFORM]["height"])
    chain = fit_chain(src_info.width, src_info.height, fit, target_size)
    grd = grade_chain(grade)
    subs = subtitles_filter(ass_path, fonts_dir)
    stages = ",".join(x for x in (chain, grd) if x)
    af = None
    if src_info.has_audio and p.get("loudness_lufs") is not None and loudness:
        af = f"loudnorm=I={p['loudness_lufs']}:TP=-1.5:LRA=11"
    log.info("rendering", out=Path(dst).name, fit=fit, size=f"{src_info.width}x{src_info.height}")

    if not inserts:
        vf = f"{stages},{subs}" if stages else subs
        return ff_render(src, dst, vf=vf, af=af, preset=p, start=start, duration=duration)

    # with inserts: -filter_complex, extra image inputs
    subs_chain, pre_chains = _insert_chains(inserts, tw, th, "vsub")
    fc_parts = []
    if stages:
        fc_parts.append(f"[0:v]{stages}[vg]")
    fc_parts.append(f"[{('vg' if stages else '0:v')}]{subs}[vsub]")
    fc_parts.extend(pre_chains)
    fc_parts.append(subs_chain)
    fc = ";".join(fc_parts)
    last_v = fc.rsplit("[", 1)[-1].rstrip("]")

    args = [ffmpeg_exe(), "-y", "-nostdin", "-v", "error", "-stats"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(src)]
    if duration:
        args += ["-t", f"{duration:.3f}"]
    else:
        full = probe(src).duration or 0.0
        duration = full - (start or 0.0)
    for ins in inserts:
        args += ["-loop", "1", "-t", f"{max(0.2, float(ins.get('duration') or 1.8)):.3f}",
                 "-i", str(ins["file"])]
    args += ["-filter_complex", fc, "-map", f"[{last_v}]"]
    if src_info.has_audio:
        args += ["-map", "0:a?"]
    if af:
        args += ["-af", af]
    args += ["-c:v", p.get("vcodec", "libx264"), "-preset", p.get("preset", "medium"),
             "-crf", str(p.get("crf", 18)), "-pix_fmt", p.get("pix_fmt", "yuv420p")]
    if p.get("fps"):
        args += ["-r", str(p["fps"])]
    if src_info.has_audio:
        args += ["-c:a", p.get("acodec", "aac"), "-b:a", p.get("abitrate", "192k"),
                 "-ar", str(p.get("ar", 48000))]
    if p.get("faststart"):
        args += ["-movflags", "+faststart"]
    args += [str(dst)]
    from ..ffmpeg import run
    proc = run(args, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg render failed: {proc.stderr[-400:]}")
    return Path(dst)
