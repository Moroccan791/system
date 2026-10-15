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
    # cover (default): fill the canvas, centre crop. lanczos, not the
    # default bicubic: this scale is usually an upscale of a face-sized
    # crop, and lanczos keeps the edges bicubic smears away
    return (f"scale={tw}:{th}:force_original_aspect_ratio=increase:flags=lanczos,"
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
    denoise = float(grade.get("denoise") or 0.0)
    if denoise > 0.01:
        # the sources are 720p/480p web downloads; their compression noise
        # is what turns to mush on faces across two encodes. A light 3D
        # denoise first gives the encoder (and the sharpener below) skin
        # to work with instead of mosquito noise
        d = min(max(denoise, 0.0), 1.0)
        parts.append(f"hqdn3d={1.5 + 2.5 * d:.2f}:{1.0 + 1.8 * d:.2f}:"
                     f"{3.0 + 3.0 * d:.2f}:{2.0 + 2.5 * d:.2f}")
    amount = float(grade.get("vignette") or 0.0)
    if amount > 0.01:
        # vignette angle: 0.28 -> ~PI/5.6; the filter's max is PI/2 (very dark)
        angle = max(0.05, min(amount, 1.0)) * 1.35
        parts.append(f"vignette=angle={angle:.3f}")
    contrast = float(grade.get("contrast") or 1.0)
    saturation = float(grade.get("saturation") or 1.0)
    if abs(contrast - 1.0) > 0.005 or abs(saturation - 1.0) > 0.005:
        parts.append(f"eq=contrast={contrast:.3f}:saturation={saturation:.3f}")
    sharpen = float(grade.get("sharpen") or 0.0)
    if sharpen > 0.01:
        # contrast-adaptive sharpening: built for detail recovery on
        # upscaled footage, without the halos plain unsharp leaves
        parts.append(f"cas={min(max(sharpen, 0.0), 1.0):.2f}")
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
            # the picture for the beat - never pasted across the subject's face.
            # A frozen still reads as a pasted photo, so the cutaway drifts:
            # rendered 12% oversize and slowly pushed in across its whole
            # beat (Ken Burns), which is what makes it feel like footage.
            frames = max(1, round(dur * 30))
            scaler = (f"scale={int(base_w * 1.12)}:{int(base_h * 1.12)}"
                      f":force_original_aspect_ratio=increase:flags=lanczos,"
                      f"crop={int(base_w * 1.12)}:{int(base_h * 1.12)},"
                      f"zoompan=z='1+0.07*on/{frames}'"
                      f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                      f":d=1:s={base_w}x{base_h}:fps=30")
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


def punch_chain(punches: list[dict], width: int, height: int, *,
                max_zoom: float = 0.085) -> str:
    """Camera punches: a fast zoom spike on each payoff word, then settle.

    One gaussian bump per punch (sigma ~0.10s), summed and clamped; the crop
    window rides the bump and scales back to frame. It runs before the
    subtitles burn inside the same pass, so captions never move.
    """
    if not punches:
        return ""
    # scale with eval=frame, NOT crop: crop's w/h expressions have no clock
    # (n/t exist only for its x/y), so a t-based crop size silently stays
    # identity forever. Whether the spike really lands cannot be eyeballed
    # and ORB keypoint medians lie on talking-head footage (the speaker's
    # arms own the frame edges), so tests/test_punch_grid.py proves it the
    # only trustworthy way: a synthetic grid, template-matched at two
    # scales. The same sweep on real footage (static shelf patch, scales
    # 0.95-1.15) reads 1.00 calm -> ~1.05 on the payoff punch.
    bumps = "+".join(
        f"{float(pn.get('strength') or 1.0):.2f}*exp(-pow((t-{float(pn['at']):.3f})/0.105,2))"
        for pn in punches)
    env = f"min(1,{bumps})"
    gain = max_zoom * 1.094          # zoom factor matching the old crop depth
    zoom = f"(1+{gain:.4f}*{env})"
    return (f"scale=w='iw*{zoom}':h='ih*{zoom}':eval=frame,"
            f"crop={width}:{height}:x='(iw-ow)/2':y='(ih-oh)*0.38'")


def burn(src: str | Path, dst: str | Path, ass_path: str | Path, *,
         preset: dict | None = None, fit: str = "cover",
         fonts_dir: str | Path | None = None, start: float | None = None,
         duration: float | None = None, loudness: bool = True,
         target_size: tuple[int, int] | None = None,
         grade: dict | None = None,
         inserts: list[dict] | None = None,
         outro: float = 0.0,
         sfx: list[dict] | None = None,
         punches: list[dict] | None = None,
         watermark: dict | None = None,
         music: str | None = None, music_volume: float = 0.5) -> Path:
    """Encode `src` to `dst` with the subtitles burned in.

    Grade goes *before* subtitles so the text stays crisp white; timed image
    inserts sit under the text, so captions stay readable over a cutaway.
    Camera punches also run before the subtitles burn (single pass - the
    grid test in tests/test_punch_grid.py proves the spike survives libass),
    so the captions themselves never move while the picture spikes.
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
    punchf = punch_chain(punches or [], tw, th)
    stages = ",".join(x for x in (chain, punchf, grd) if x)
    af = None
    if src_info.has_audio and p.get("loudness_lufs") is not None and loudness:
        af = f"loudnorm=I={p['loudness_lufs']}:TP=-1.5:LRA=11"
    # the ending is part of the edit: picture and sound leave together over
    # the last `outro` seconds instead of stopping mid-air on a hard cut
    eff_dur = float(duration) if duration else float(src_info.duration or 0.0) - float(start or 0.0)
    vfade = afade = ""
    if outro and eff_dur > float(outro) + 0.1:
        vfade = f"fade=t=out:st={eff_dur - float(outro):.3f}:d={float(outro):.3f}"
        afade = f"afade=t=out:st={eff_dur - float(outro):.3f}:d={float(outro):.3f}"
    log.info("rendering", out=Path(dst).name, fit=fit, size=f"{src_info.width}x{src_info.height}")

    if not inserts and not sfx and not watermark and not music:
        vf = ",".join(x for x in (stages, subs, vfade) if x)
        afull = ",".join(x for x in (af, afade) if x) or None
        return ff_render(src, dst, vf=vf, af=afull, preset=p, start=start, duration=duration)

    # with inserts and/or sfx: -filter_complex, extra inputs. Inserts
    # overlay BEFORE the subtitles burn: a cutaway replaces the picture,
    # never the words - the caption keeps talking over the B-roll.
    fc_parts = []
    if stages:
        fc_parts.append(f"[0:v]{stages}[vg]")
    base = "vg" if stages else "0:v"
    ins_chain, pre_chains = _insert_chains(inserts or [], tw, th, base)
    fc_parts.extend(pre_chains)
    if ins_chain:
        fc_parts.append(ins_chain)
        base = ins_chain.rsplit("[", 1)[-1].rstrip("]")
    fc_parts.append(f"[{base}]{subs}[vsub]")
    fc = ";".join(fc_parts)
    last_v = "vsub"
    if vfade:
        fc += f";[{last_v}]{vfade}[vfinal]"
        last_v = "vfinal"

    args = [ffmpeg_exe(), "-y", "-nostdin", "-v", "error", "-stats"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(src)]
    if duration:
        args += ["-t", f"{duration:.3f}"]
    else:
        full = probe(src).duration or 0.0
        duration = full - (start or 0.0)
    for ins in inserts or []:
        args += ["-loop", "1", "-t", f"{max(0.2, float(ins.get('duration') or 1.8)):.3f}",
                 "-i", str(ins["file"])]
    audio_label = None
    if (sfx or music) and src_info.has_audio:
        base_idx = 1 + len(inserts or [])
        a_parts = [f"[0:a]{af or 'anull'}[abase]"]
        labels = ["[abase]"]
        if music:
            # the bed loops under everything, sidechain-ducked by the
            # voice itself: it breathes down on every syllable and comes
            # back in the gaps, like the reference edits
            mus_idx = base_idx + len(sfx or [])
            a_parts[0] = f"[0:a]{af or 'anull'},asplit[vmain][vkey]"
            labels = ["[vmain]"]
            a_parts.append(f"[{mus_idx}:a]atrim=0:{float(duration or 0):.3f},"
                           f"asetpts=N/SR/TB,volume={float(music_volume):.2f}[musraw]")
            a_parts.append("[musraw][vkey]sidechaincompress=threshold=0.015:"
                           "ratio=8:attack=15:release=280:makeup=1[musduck]")
            labels.append("[musduck]")
        for j, s_ in enumerate(sfx or []):
            ms = int(float(s_.get("at") or 0.0) * 1000)
            rate = float(s_.get("rate") or 1.0)
            # asetrate+aresample = a few % of pitch humanization, so repeated
            # keystrokes never sound like one sample looping
            pitch = (f"asetrate=48000*{rate:.4f},aresample=48000,"
                     if abs(rate - 1.0) > 0.001 else "")
            a_parts.append(f"[{base_idx + j}:a]{pitch}adelay={ms}|{ms},"
                           f"volume={float(s_.get('volume') or 0.45):.2f}[sfx{j}]")
            labels.append(f"[sfx{j}]")
        # normalize=0 matters: amix's default divides the whole mix by the
        # input count, so every added sfx quietly turned the SPEECH down
        # (measured: -12dB with the full sound-design stack). The voice is
        # the mix; effects sit under it at their own volumes.
        a_parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:"
                       f"dropout_transition=0:normalize=0[amix]")
        a_parts.append(f"[amix]{afade}[aout]" if afade else "[amix]anull[aout]")
        fc += ";" + ";".join(a_parts)
        audio_label = "aout"
        for s_ in sfx or []:
            args += ["-i", str(s_["file"])]
        if music:
            args += ["-stream_loop", "-1", "-i", str(music)]
    if watermark:
        # brand mark last of all: above the captions and above the outro
        # fade, pinned for the whole clip, full opacity - campaign briefs
        # that mandate a watermark say keep it clear and never crop it off
        wm_idx = 1 + len(inserts or []) + ((len(sfx or []) + (1 if music else 0))
                                           if audio_label else 0)
        pos = str(watermark.get("position") or "tr").lower()
        mgn = int(watermark.get("margin") or 36)
        xy = {"tr": (f"W-w-{mgn}", str(mgn)), "br": (f"W-w-{mgn}", f"H-h-{mgn}"),
              "bc": ("(W-w)/2", f"H-h-{mgn}"), "tl": (str(mgn), str(mgn)),
              "bl": (str(mgn), f"H-h-{mgn}")}.get(pos, (f"W-w-{mgn}", str(mgn)))
        wm_w = max(40, int(tw * float(watermark.get("width_frac") or 0.24)))
        fc += (f";[{wm_idx}:v]scale={wm_w}:-2,format=rgba[wm]"
               f";[{last_v}][wm]overlay={xy[0]}:{xy[1]}[vwm]")
        last_v = "vwm"
        args += ["-loop", "1", "-t", f"{duration:.3f}", "-i",
                 str(watermark["file"])]
    args += ["-filter_complex", fc, "-map", f"[{last_v}]"]
    if src_info.has_audio:
        args += ["-map", f"[{audio_label}]" if audio_label else "0:a?"]
    if af and not audio_label:
        afull = ",".join(x for x in (af, afade) if x)
        args += ["-af", afull]
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
