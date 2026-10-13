"""Generate a synthetic campaign so the whole pipeline can be exercised without
real footage.

    python -m clipper samples      # builds samples/campaign_demo
    python -m clipper scan         # probe it
    python -m clipper style campaign_demo     # learn a style from it

`references/reference_01.mp4` is built to contain the things stage 1 measures -
hard cuts, a punch-in at the start of every shot, and burned-in captions with a
known style - so the extracted profile can be compared against the truth printed
by this module. `raw/raw_01.mp4` is the stand-in for a creator's long-form
upload (a tone, because real ASR needs real speech).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import config
from .asr.base import Word
from .captions.ass import write_ass
from .captions.cues import group_words
from .captions.render import subtitles_filter
from .ffmpeg import ffmpeg_exe, probe
from .synth import textured_scene, write_video, zoom_frame
from .util import log

# the style the demo reference is rendered with - what stage 1 should recover
DEMO_STYLE = config.deep_merge(config.DEFAULT_STYLE, {
    "captions": {
        "font_family": "Montserrat",
        "font_size_ass": 104,
        "casing": "upper",
        "primary_color": "#FFFFFF",
        "outline_color": "#000000",
        "outline_width": 6,
        "position": {"anchor": "bottom_center", "cx": 0.5, "cy": 0.72},
        "karaoke": {"enabled": True, "highlight_color": "#FFE14D"},
        "animation": {"in": "none"},
        "max_words_per_cue": 3,
        "max_lines": 1,
        "max_chars_per_line": 16,
    },
})
DEMO_SHOT_LEN = 2.0
DEMO_PUNCH = 1.13
DEMO_PUNCH_OVER = 0.3
DEMO_SCRIPT = [
    ("HOOK", "THEM", "FIRST"), ("KEEP", "IT", "TIGHT"), ("NINE", "BY", "SIXTEEN"),
    ("CUTS", "ON", "BEAT"), ("PUNCH", "IN", "HARD"), ("CAPTIONS", "STAY", "CENTERED"),
    ("END", "ON", "STRONG"),
]

# soft studio backdrop for the raw stand-in
RAW_BG = ("color=c=0x141a24:s=1080x1920:d=7.5,"
          "drawbox=x=140:y=300:w=800:h=800:color=0x22304a@1:t=fill,"
          "drawbox=x='140+40*sin(2*PI*t/7.5)':y=340:w=320:h=320:color=0x35507a@1:t=fill,"
          "vignette=PI/5")
RAW_TONE = ("sine=frequency=180:sample_rate=48000:duration=7.5,"
            "aeval=val(0)*0.06+0.02*sin(2*PI*40*t):c=same")


def demo_words() -> list[Word]:
    """Timed words that match the demo script (6 cues over ~9 s)."""
    words: list[Word] = []
    t = 0.35
    for cue in DEMO_SCRIPT:
        for token in cue:
            words.append(Word(text=token, start=round(t, 3), end=round(t + 0.42, 3),
                              prob=1.0, source="fixture"))
            t += 0.46
        t += 0.22
    return words


def _demo_base_frames(shot_count: int, fps: int, size: tuple[int, int]):
    """3 shots of DEMO_SHOT_LEN, each opening with a punch-in (streamed)."""
    w, h = size
    per_shot = int(DEMO_SHOT_LEN * fps)
    for i in range(shot_count):
        base = textured_scene(w, h, seed=101 + i * 17)
        for j in range(per_shot):
            elapsed = j / fps
            scale = 1.0 + (DEMO_PUNCH - 1.0) * min(1.0, elapsed / DEMO_PUNCH_OVER)
            yield zoom_frame(base, scale)


def build_demo_reference(path: Path, *, fps: int = 30, size: tuple[int, int] = (1080, 1920),
                         burn: bool = True) -> dict:
    """Reference clip with known cuts, punch-ins and caption style."""
    shots = max(1, len(DEMO_SCRIPT) // 2)   # 3 shots
    silent = path.with_name("_reference_silent.mp4")
    write_video(str(silent), _demo_base_frames(shots, fps, size), fps=fps,
                audio_source="sine=frequency=210:sample_rate=48000:duration=%.2f"
                             % (shots * DEMO_SHOT_LEN))

    cuts = [round(i * DEMO_SHOT_LEN, 3) for i in range(1, shots)]
    if not burn:
        silent.replace(path)
        return {"cuts": cuts, "punch_scale": DEMO_PUNCH, "punch_over": DEMO_PUNCH_OVER}

    cues = group_words(demo_words(), max_words=3, max_chars=16, max_lines=1, gap_break=9)
    ass = path.with_name("_reference.ass")
    write_ass(ass, cues, DEMO_STYLE, width=size[0], height=size[1])
    proc = subprocess.run([
        ffmpeg_exe(), "-y", "-v", "error", "-i", str(silent),
        "-vf", subtitles_filter(ass),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(path),
    ], capture_output=True, text=True)
    silent.unlink(missing_ok=True)
    ass.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"reference render failed: {proc.stderr.strip()[-400:]}")
    return {"cuts": cuts, "punch_scale": DEMO_PUNCH, "punch_over": DEMO_PUNCH_OVER,
            "font_size_ass": DEMO_STYLE["captions"]["font_size_ass"],
            "primary_color": DEMO_STYLE["captions"]["primary_color"],
            "highlight_color": DEMO_STYLE["captions"]["karaoke"]["highlight_color"],
            "cy": DEMO_STYLE["captions"]["position"]["cy"],
            "max_words_per_cue": DEMO_STYLE["captions"]["max_words_per_cue"]}


def _render_raw(path: Path, duration: float = 7.5) -> Path:
    proc = subprocess.run([
        ffmpeg_exe(), "-y", "-v", "error",
        "-f", "lavfi", "-i", RAW_BG, "-f", "lavfi", "-i", RAW_TONE,
        "-t", f"{duration}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
        "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(path),
    ], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"raw stand-in render failed: {proc.stderr.strip()[-400:]}")
    return path


def make_demo_campaign(force: bool = False) -> Path:
    campaign = config.SAMPLES / "campaign_demo"
    refs = campaign / "references"
    raw = campaign / "raw"
    refs.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)
    ref_video = refs / "reference_01.mp4"
    raw_video = raw / "raw_01.mp4"

    if not force and ref_video.exists() and raw_video.exists():
        log.info("sample campaign already exists", path=str(campaign))
        return campaign

    log.info("rendering sample reference", out=ref_video.name)
    truth = build_demo_reference(ref_video)
    log.info("rendering sample raw stand-in", out=raw_video.name)
    _render_raw(raw_video)

    (campaign / "README.md").write_text(
        "# campaign_demo (synthetic)\n\n"
        "Generated by `python -m clipper samples`.\n\n"
        "`references/reference_01.mp4` was rendered with a *known* style:\n\n"
        f"- 3 shots of {DEMO_SHOT_LEN:.0f}s each, hard cuts at {truth['cuts']}\n"
        f"- a {truth['punch_scale']}x punch-in over {truth['punch_over']}s at each cut\n"
        f"- captions: Montserrat {truth['font_size_ass']}px, upper case, "
        f"{truth['primary_color']} with a {truth['highlight_color']} karaoke highlight,\n"
        f"  centred at cy={truth['cy']}, {truth['max_words_per_cue']} words per cue\n\n"
        "So `python -m clipper style campaign_demo` can be checked against the list above.\n\n"
        "`raw/raw_01.mp4` stands in for the creator's long-form upload (a tone: real\n"
        "speech recognition needs real speech, so use a real file to test captions).\n",
        encoding="utf-8")

    for p in (ref_video, raw_video):
        info = probe(p)
        log.info("sample", file=p.name, size=f"{p.stat().st_size / 1024:.0f} KB",
                 res=f"{info.width}x{info.height}", dur=f"{info.duration:.1f}s")
    log.info("demo reference ground truth", **{k: v for k, v in truth.items() if k != "cuts"})
    return campaign
