"""Central config: paths, platform presets and the default caption style.

Everything is overridable with environment variables (CLIPPER_*) so the same code
runs in this sandbox, on Windows, or on a cloud box without edits.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("CLIPPER_ROOT", Path(__file__).resolve().parent.parent))


def _p(env: str, default: Path) -> Path:
    return Path(os.environ.get(env, default))


CAMPAIGNS = _p("CLIPPER_CAMPAIGNS", ROOT / "campaigns")   # campaigns/<name>/{references,raw}
SAMPLES = _p("CLIPPER_SAMPLES", ROOT / "samples")         # committed synthetic samples
STYLES = _p("CLIPPER_STYLES", ROOT / "styles")            # styles/<campaign>.style.json
WORK = _p("CLIPPER_WORK", ROOT / "work")                  # intermediates (gitignored)
OUTPUT = _p("CLIPPER_OUTPUT", ROOT / "output")            # finished clips
MODELS = _p("CLIPPER_MODELS", ROOT / "models")            # downloaded weights
FONTS = _p("CLIPPER_FONTS", ROOT / "assets" / "fonts")    # optional extra fonts

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".ts", ".mts"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
MEDIA_EXT = VIDEO_EXT | AUDIO_EXT

# ---------------------------------------------------------------------------
# export presets - "export with FFmpeg using platform presets"
# ---------------------------------------------------------------------------
PLATFORMS: dict[str, dict] = {
    "tiktok": {
        "width": 1080, "height": 1920, "fps": 30,
        "vcodec": "libx264", "crf": 18, "preset": "medium", "pix_fmt": "yuv420p",
        "profile": "high", "level": "4.1", "acodec": "aac", "abitrate": "192k", "ar": 48000,
        "loudness_lufs": -14.0, "faststart": True, "max_bitrate": None,
    },
    "reels": {
        "width": 1080, "height": 1920, "fps": 30,
        "vcodec": "libx264", "crf": 18, "preset": "medium", "pix_fmt": "yuv420p",
        "profile": "high", "level": "4.1", "acodec": "aac", "abitrate": "192k", "ar": 48000,
        "loudness_lufs": -14.0, "faststart": True, "max_bitrate": 12_000_000,
    },
    "shorts": {
        "width": 1080, "height": 1920, "fps": 30,
        "vcodec": "libx264", "crf": 18, "preset": "medium", "pix_fmt": "yuv420p",
        "profile": "high", "level": "4.2", "acodec": "aac", "abitrate": "192k", "ar": 48000,
        "loudness_lufs": -14.0, "faststart": True, "max_bitrate": 16_000_000,
    },
}
DEFAULT_PLATFORM = "tiktok"

# ---------------------------------------------------------------------------
# default caption style (used when a campaign has no extracted profile yet,
# and as the fallback for every missing field in an extracted one)
# ---------------------------------------------------------------------------
DEFAULT_STYLE: dict = {
    "version": 1,
    "campaign": None,
    "source": {"references": [], "notes": "built-in default"},
    "pacing": {"avg_shot_len": None, "cuts_per_minute": None, "confidence": 0.0},
    "zoom": {"dominant": "punch_in", "punch_in_scale": 1.12, "punch_in_duration": 0.25,
             "confidence": 0.0},
    "transitions": {
        "in": "cut",            # cut | fade | fade_black | fade_white | any xfade blend
        "duration": 0.25,       # seconds a blend lasts
        "confidence": 0.0,
    },
    "captions": {
        "present": True,
        # font: we cannot identify a font from pixels reliably; this is the
        # editing default and campaign owners can override it in the style JSON.
        "font_family": "Montserrat",
        "font_weight": "bold",
        "italic": False,
        "casing": None,                 # None = keep transcript casing
        # sizes are derived from measured pixels; *_px is what we measured on the
        # reference, font_size_ass is the same thing expressed for a 1080x1920 canvas
        "font_size_ass": 96,
        "cap_height_ratio": 0.045,
        "primary_color": "#FFFFFF",
        "outline_color": "#000000",
        "outline_width": 5,
        "shadow": 0,
        "position": {"anchor": "bottom_center", "cx": 0.5, "cy": 0.80, "margin_v": 420},
        "karaoke": {"enabled": True, "highlight_color": "#FFE14D", "scale_pop": 1.06},
        "animation": {"in": "pop", "duration": 0.12},
        "max_lines": 1,
        "max_words_per_cue": 4,
        "max_chars_per_line": 22,
        "confidence": 0.0,
        "evidence": {"cue_count": 0, "frames": []},
    },
    "audio": {"music_bed": None, "target_lufs": -14.0, "speech_ratio": None, "confidence": 0.0},
}


def deep_merge(base: dict, override: dict | None) -> dict:
    """Recursively merge `override` onto a copy of `base` (dicts only)."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out
