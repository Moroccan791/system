"""Burn the .ass into the video with ffmpeg (libass), and shape the frame to 9:16.

Filter path escaping is the classic Windows trap (`C:\\Users\\...` inside
`subtitles=` needs `C\\:/Users/...`), so it lives in one tested helper.
"""
from __future__ import annotations

from pathlib import Path

from .. import config
from ..ffmpeg import has_filter, render as ff_render, probe
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


def burn(src: str | Path, dst: str | Path, ass_path: str | Path, *,
         preset: dict | None = None, fit: str = "cover",
         fonts_dir: str | Path | None = None, start: float | None = None,
         duration: float | None = None, loudness: bool = True,
         target_size: tuple[int, int] | None = None) -> Path:
    """Encode `src` to `dst` with the subtitles burned in."""
    if not has_filter("subtitles"):
        raise RuntimeError(
            "this ffmpeg build has no 'subtitles' filter (no libass) - "
            "install a full build: https://www.gyan.dev/ffmpeg/builds/"
        )
    p = dict(preset or {})
    src_info = probe(src)
    chain = fit_chain(src_info.width, src_info.height, fit, target_size)
    subs = f"subtitles=filename='{escape_filter_path(ass_path)}'"
    if fonts_dir:
        subs += f":fontsdir='{escape_filter_path(fonts_dir)}'"
    else:
        fonts_dir_default = config.FONTS
        if fonts_dir_default.exists() and any(fonts_dir_default.iterdir()):
            subs += f":fontsdir='{escape_filter_path(fonts_dir_default)}'"
    if chain:
        vf = f"{chain},{subs}"
    else:
        vf = subs
    af = None
    if src_info.has_audio and p.get("loudness_lufs") is not None and loudness:
        af = f"loudnorm=I={p['loudness_lufs']}:TP=-1.5:LRA=11"
    log.info("rendering", out=Path(dst).name, fit=fit, size=f"{src_info.width}x{src_info.height}")
    return ff_render(src, dst, vf=vf, af=af, preset=p, start=start, duration=duration)
