"""The type library, made loadable, and one setting that picks the face.

Every face we own except Montserrat was a `.woff2`, which PIL cannot open, so
`_load_font` fell through to the one `.otf` in the folder and every edit in the
house got the same typeface without anyone deciding that. A font is a decision,
so:

    assets/fonts/family.json   {"main": "Anton", "accent": null}

`ensure()` converts a `.woff2` to `.ttf` once (fontTools, needs brotli), which is
the only reason the rest of the library was invisible. `main()` returns the path
that config names, so changing the typeface is a data change and the compositor
never needs editing again.
"""

from __future__ import annotations

import json
from pathlib import Path

FONT_DIR = Path("assets/fonts")
# The EDITING faces live here, one folder, and nothing else is offered for a
# video. The rest of assets/fonts belongs to the campaign (whop) chain and stays
# out of the way so "which font" is a two-second question, not a menu of twelve.
EDIT_DIR = FONT_DIR / "edit"
OUT_DIR = FONT_DIR / "ttf"
CONFIG = FONT_DIR / "family.json"

# Faces worth having for this kind of edit: heavy enough to sit over footage at
# 15-20% of frame height, and distinct enough that choosing between them is a
# real choice.
CANDIDATES = {
    "Anton": "Anton.woff2",                    # condensed impact, the overedit default
    "ArchivoBlack": "ArchivoBlack.woff2",      # wide, heavy, poster
    "BebasNeue": "BebasNeue.woff2",            # condensed caps, tall
    "PoppinsExtraBold": "Poppins-ExtraBold.woff2",
    "SpaceGroteskBold": "SpaceGrotesk-Bold.woff2",
    "OutfitSemibold": "Outfit-Semibold.woff2",
    "PlayfairBold": "PlayfairDisplay-Bold.woff2",      # serif, for a sad card
    "PlayfairItalic": "PlayfairDisplay-BoldItalic.woff2",
    "MontserratExtraBold": "Montserrat-ExtraBold.ttf",
    "MontserratBold": "Montserrat-Bold.ttf",
    "CabinetGroteskBlack": "CabinetGrotesk-Black.otf",
    "LuckiestGuy": "LuckiestGuy.woff2",
}

_cache: dict[str, Path] = {}


def ensure(name: str) -> Path:
    """A path PIL can open for this face, converting woff2 once if needed."""
    if name in _cache and _cache[name].exists():
        return _cache[name]
    if name in edit_faces():
        src = edit_faces()[name]
    elif name in CANDIDATES:
        src = FONT_DIR / CANDIDATES[name]
    else:
        raise FileNotFoundError(f"{name}: not in {EDIT_DIR} or the library")
    if not src.exists():
        raise FileNotFoundError(f"{name}: {src} is missing")
    if src.suffix.lower() in (".ttf", ".otf"):
        _cache[name] = src
        return src

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dst = OUT_DIR / (src.stem + ".ttf")
    if not dst.exists():
        from fontTools.ttLib import TTFont

        font = TTFont(str(src))
        font.flavor = None
        font.save(str(dst))
    _cache[name] = dst
    return dst


def edit_faces() -> dict[str, Path]:
    """Every face dropped into assets/fonts/edit, by filename.

    Auto-discovered on purpose: a new font is a file, not a code change. Unzip
    into that folder, run `python -m studio.fonts --list`, choose.
    """
    if not EDIT_DIR.exists():
        return {}
    out = {}
    for p in sorted(EDIT_DIR.iterdir()):
        if p.suffix.lower() in (".ttf", ".otf", ".woff2", ".woff"):
            out[p.stem] = p
    return out


def available() -> dict[str, str]:
    """face -> the file it converts from, for everything present on disk."""
    faces = {n: str(f.relative_to(FONT_DIR)) for n, f in edit_faces().items()}
    faces.update({n: f for n, f in CANDIDATES.items()
                  if (FONT_DIR / f).exists() and n not in faces})
    return faces


def config() -> dict:
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text())
        except json.JSONDecodeError:
            pass
    return {"main": "CabinetGroteskBlack", "accent": None}


def set_family(main: str, accent: str | None = None) -> Path:
    ensure(main)
    if accent:
        ensure(accent)
    CONFIG.write_text(json.dumps({"main": main, "accent": accent}, indent=1) + "\n")
    _cache.clear()
    return CONFIG


def main() -> Path:
    name = config().get("main") or "CabinetGroteskBlack"
    try:
        return ensure(name)
    except Exception:
        return ensure("CabinetGroteskBlack")


def accent() -> Path | None:
    name = config().get("accent")
    if not name:
        return None
    try:
        return ensure(name)
    except Exception:
        return None


def specimen(out: str | Path, text: str = "IS A BEAUTY",
             faces: list[str] | None = None, tile_w: int = 640,
             plate: tuple[str, float] | None = None,
             cap_frac: float = 0.115) -> Path:
    """The same word, every face, at the size it will actually be set."""
    import numpy as np
    from PIL import Image, ImageDraw

    from .typecards import composite, render_card

    faces = faces or list(edit_faces()) or [
        f for f in available() if f != "CabinetGroteskBlack"]
    tiles = []
    for name in faces:
        path = ensure(name)
        try:
            card = render_card(text, 1920, 1080, cap_frac=cap_frac,
                               font_path=str(path))
        except Exception as exc:                      # a face that will not load
            tiles.append((name, None, str(exc)))
            continue
        tiles.append((name, card, ""))

    ok = [(n, c) for n, c, e in tiles if c is not None]
    if not ok:
        raise RuntimeError("no face loaded")

    # A face is judged on the picture, not on grey. Same frame for every face, so
    # the only variable is the type.
    base = None
    if plate:
        import subprocess

        import imageio_ffmpeg

        path, t = plate
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error",
                        "-y", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                        "/tmp/spec_plate.png"], check=True)
        base = Image.open("/tmp/spec_plate.png").convert("RGB").resize((1920, 1080))
    h = int(tile_w * 9 / 16)
    rows = (len(ok) + 1) // 2
    sheet = Image.new("RGB", (tile_w * 2, h * rows), (20, 20, 22))
    for r, (name, card) in enumerate(ok):
        if base is None:
            frame = np.full((1080, 1920, 3), 34, dtype=np.uint8)
            composite(frame, card)
        else:
            from .typecards import scrim

            frame = np.asarray(base).copy()
            scrim(frame, card, amount=0.34, blur=14)
            composite(frame, card)
        im = Image.fromarray(frame).resize((tile_w, h))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 210, 20], fill=(0, 0, 0))
        d.text((5, 5), name, fill=(255, 220, 0))
        sheet.paste(im, ((r % 2) * tile_w, (r // 2) * h))
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(p, quality=92)
    return p


def main_cli(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="the type library")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--specimen", default=None)
    ap.add_argument("--set", default=None, help="face name to use from now on")
    ap.add_argument("--accent", default=None)
    a = ap.parse_args(argv)
    if a.list:
        cur = config().get("main")
        for n in available():
            print(f"  {n:22s} {'<- in use' if n == cur else ''}")
        return 0
    if a.set:
        print(set_family(a.set, a.accent))
        return 0
    if a.specimen:
        print(specimen(a.specimen))
        return 0
    print(json.dumps(config()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
