"""Timecode helpers used by ffmpeg args, ASS timestamps and logs."""
from __future__ import annotations


def fmt_seconds(seconds: float) -> str:
    """0.5 -> '0.50' (what ffmpeg -ss/-t like)."""
    return f"{max(0.0, float(seconds)):.3f}"


def fmt_hms(seconds: float) -> str:
    """1.5 -> '00:00:01.500' (ffmpeg -i logs)."""
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def fmt_ass(seconds: float) -> str:
    """1.5 -> '0:00:01.50' (ASS Dialogue start/end, centiseconds)."""
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def parse_timestamp(text: str) -> float:
    """'00:01:02.500' or '62.5' -> 62.5"""
    text = text.strip()
    if ":" not in text:
        return float(text)
    parts = text.split(":")
    sec = float(parts[-1])
    for i, p in enumerate(reversed(parts[:-1]), start=1):
        sec += float(p) * (60 ** i)
    return sec
