"""Style profile schema: defaults, validation, rounding, confidence."""
from __future__ import annotations

from .. import config

# fields stage 1 is allowed to set, and how to sanitise them
_NUMERIC = {
    "captions.font_size_ass": (24, 260),
    "captions.outline_width": (0, 40),
    "captions.cap_height_ratio": (0.005, 0.30),
    "captions.max_words_per_cue": (1, 12),
    "captions.max_lines": (1, 3),
    "captions.max_chars_per_line": (6, 80),
    "captions.position.cx": (0.0, 1.0),
    "captions.position.cy": (0.02, 0.98),
    "zoom.punch_in_scale": (1.0, 2.0),
    "zoom.punch_in_duration": (0.05, 5.0),
    "pacing.avg_shot_len": (0.1, 60.0),
    "pacing.cuts_per_minute": (0.0, 600.0),
}


def _get(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set(d: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    cur = d
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


# fields that are conceptually counts/sizes and must stay integers
_INTEGER_FIELDS = {
    "captions.font_size_ass", "captions.outline_width", "captions.max_words_per_cue",
    "captions.max_lines", "captions.max_chars_per_line",
}


def sanitize(profile: dict) -> dict:
    """Clamp numbers into sane ranges and drop empty dicts."""
    out = dict(profile)
    for key, (lo, hi) in _NUMERIC.items():
        val = _get(out, key)
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            clamped = min(max(float(val), lo), hi)
            if key in _INTEGER_FIELDS:
                _set(out, key, int(round(clamped)))
            else:
                _set(out, key, round(clamped, 4))
    return out


def apply_defaults(profile: dict) -> dict:
    """Fill every missing field from the built-in default profile."""
    merged = config.deep_merge(config.DEFAULT_STYLE, profile)
    # never let an extractor inherit a *default* confidence
    merged["version"] = config.DEFAULT_STYLE.get("version", 1)
    return sanitize(merged)


def overall_confidence(profile: dict) -> float:
    parts = []
    for section in ("captions", "pacing", "zoom", "audio"):
        conf = _get(profile, f"{section}.confidence")
        if isinstance(conf, (int, float)):
            parts.append(float(conf))
    if not parts:
        return 0.0
    return round(sum(parts) / len(parts), 3)


def notes_for(profile: dict) -> list[str]:
    """Human-readable caveats - shown in the CLI and stored in the profile."""
    notes: list[str] = []
    if not profile.get("captions", {}).get("present"):
        notes.append("no captions detected in the references; captioning will use defaults")
    if profile.get("captions", {}).get("font_family") is None:
        notes.append("font family cannot be identified from pixels - keeping the default; "
                     "set captions.font_family by hand if the campaign uses a specific font")
    unc = profile.get("captions", {}).get("font_size_uncertainty")
    if isinstance(unc, (int, float)) and unc >= 0.2:
        notes.append(
            f"font size carries about +/-{int(unc * 100)}% uncertainty: the font face cannot be "
            "identified from pixels, so the size is right for the rendering default "
            "(Montserrat) and off if the campaign uses a much wider/taller face"
        )
    if profile.get("captions", {}).get("confidence", 0) < 0.4:
        notes.append("caption measurements are low confidence - check work/<campaign>/style/evidence/")
    if profile.get("pacing", {}).get("confidence", 0) < 0.35:
        notes.append("pacing is low confidence (static reference or very few cuts)")
    return notes
