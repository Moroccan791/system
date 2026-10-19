#!/usr/bin/env python3
"""Style card: choose the fonts and colours BEFORE the edit.

    python scripts/whop/style_card.py menu
    python scripts/whop/style_card.py show
    python scripts/whop/style_card.py serve --campaign street_you_grew_up_on
    python scripts/whop/style_card.py theme --campaign street_you_grew_up_on \
            --out work/street/whop_v6/style_theme.json

The card inherits campaign defaults and stores an independent choice
per video in campaigns/<campaign>/postN/style.json. It writes a matching
produce-ready theme next to each video and into motion/themes/. The preview panel renders through the REAL engine (motion/stage.html
driven by window.setTimeline/renderAt), so what you approve on the card is
exactly what the render will look like - no mock-up drift.

The user picks:
  fonts   - caption face, keyword/hero face, serif face, endcard face,
            list face (each one of the vendored OFL packs)
  colours - project accent (also the spoken-keyword ink), caption text,
            serif ink, end-card ink, keyword plate + plate ink, list
            head/bg/text, scene ground + scene ink
"""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "assets" / "fonts"
STAGE = ROOT / "motion" / "stage.html"

# name -> (label, specimen, css family)   css family mirrors motion/stage.html
PACKS = [
    ("montserrat", "Montserrat ExtraBold", "workhorse", "MontserratX"),
    ("anton", "Anton", "tall condensed caps", "PackAnton"),
    ("bebas", "Bebas Neue", "clean tall caps", "PackBebas"),
    ("grotesk", "Space Grotesk Bold", "geometric sans", "PackGrotesk"),
    ("serif", "Playfair Display Bold", "display serif", "PackSerif"),
    ("archivo", "Archivo Black", "chunky poster caps", "PackArchivo"),
    ("poppins", "Poppins ExtraBold", "rounded friendly", "PackPoppins"),
    ("luckiest", "Luckiest Guy", "cartoon display", "PackLuckiest"),
    ("oblique", "Archivo Medium Italic", "medium oblique", "PackOblique"),
    ("serifbi", "Playfair Display Bold Italic", "bold italic", "PackSerifBoldItalic"),
    ("sansitalic", "Montserrat Italic", "sans italic", "PackSansItalic"),
    ("regular", "Inter Regular", "regular", "PackRegular"),
    ("displaybook", "Newsreader Book Italic", "display book italic", "PackDisplayBook"),
    ("grande", "Outfit Semibold", "grande semibold", "PackGrande"),
    ("cabinet", "Cabinet Grotesk", "user grotesk", "PackCabinet"),
    ("jasper", "Jasper", "user display cut", "PackJasper"),
]

ROLES = [
    ("caption", "Caption text", "conn", "MY WORTH ISN'T IN MY BODY."),
    ("keyword", "Keyword / hero", "keyword", "WORTH"),
    ("serif", "Reflective phrase", "serif", "I AM BEAUTIFUL AS I AM."),
    ("list", "Secondary graphic text", "list", "MY BODY"),
    ("endcard", "End card", "endcard", "FOLLOW FOR MORE"),
]

COLORS = [
    ("accent", "Project accent / keyword ink"),
    ("caption", "Caption text"),
    ("serif", "Serif words"),
    ("endcard", "End card title"),
    ("plate", "Keyword plate"),
    ("plateInk", "Plate ink"),
    ("listHead", "List head"),
    ("listBg", "List plate ground"),
    ("listText", "List text"),
    ("sceneBg", "Full-screen scene ground"),
    ("sceneInk", "Scene ink"),
]

# Per-video starting points only. None is a universal Whop colour; each new
# card gets a distinct draft, and the user can replace any role colour.
PALETTES = [
    {"id": "copper", "label": "Copper / graphite", "colors": {
        "accent": "#D9824B", "caption": "#F8F4EC", "keyword": "#D9824B",
        "serif": "#F8F4EC", "endcard": "#D9824B", "plate": "#D9824B",
        "plateInk": "#1B1512", "listHead": "#D9824B", "listBg": "#191512",
        "listText": "#F8F4EC", "sceneBg": "#14110F", "sceneInk": "#F8F4EC"}},
    {"id": "iris", "label": "Iris / midnight", "colors": {
        "accent": "#8E82D7", "caption": "#F7F5FF", "keyword": "#8E82D7",
        "serif": "#F7F5FF", "endcard": "#8E82D7", "plate": "#8E82D7",
        "plateInk": "#151321", "listHead": "#8E82D7", "listBg": "#171521",
        "listText": "#F7F5FF", "sceneBg": "#13121B", "sceneInk": "#F7F5FF"}},
    {"id": "meadow", "label": "Moss / parchment", "colors": {
        "accent": "#78A974", "caption": "#F5F3EA", "keyword": "#78A974",
        "serif": "#F5F3EA", "endcard": "#78A974", "plate": "#78A974",
        "plateInk": "#111710", "listHead": "#78A974", "listBg": "#151A14",
        "listText": "#F5F3EA", "sceneBg": "#111611", "sceneInk": "#F5F3EA"}},
    {"id": "ochre", "label": "Ochre / plum", "colors": {
        "accent": "#D7A73C", "caption": "#FFF7E7", "keyword": "#D7A73C",
        "serif": "#FFF7E7", "endcard": "#D7A73C", "plate": "#D7A73C",
        "plateInk": "#20181B", "listHead": "#D7A73C", "listBg": "#1B1418",
        "listText": "#FFF7E7", "sceneBg": "#191317", "sceneInk": "#FFF7E7"}},
    {"id": "cobalt", "label": "Cobalt / chalk", "colors": {
        "accent": "#4D79D1", "caption": "#F4F7FC", "keyword": "#4D79D1",
        "serif": "#F4F7FC", "endcard": "#4D79D1", "plate": "#4D79D1",
        "plateInk": "#101827", "listHead": "#4D79D1", "listBg": "#111824",
        "listText": "#F4F7FC", "sceneBg": "#0F1622", "sceneInk": "#F4F7FC"}},
    {"id": "clay", "label": "Clay / ink", "colors": {
        "accent": "#C7654E", "caption": "#F7F0E9", "keyword": "#C7654E",
        "serif": "#F7F0E9", "endcard": "#C7654E", "plate": "#C7654E",
        "plateInk": "#211512", "listHead": "#C7654E", "listBg": "#1C1413",
        "listText": "#F7F0E9", "sceneBg": "#181110", "sceneInk": "#F7F0E9"}},
    {"id": "glacier", "label": "Glacier / charcoal", "colors": {
        "accent": "#77A7C8", "caption": "#F0F5F7", "keyword": "#77A7C8",
        "serif": "#F0F5F7", "endcard": "#77A7C8", "plate": "#77A7C8",
        "plateInk": "#11191F", "listHead": "#77A7C8", "listBg": "#12191E",
        "listText": "#F0F5F7", "sceneBg": "#11171B", "sceneInk": "#F0F5F7"}},
    {"id": "citron", "label": "Citron / aubergine", "colors": {
        "accent": "#C4BD3A", "caption": "#FAF9E8", "keyword": "#C4BD3A",
        "serif": "#FAF9E8", "endcard": "#C4BD3A", "plate": "#C4BD3A",
        "plateInk": "#1A1810", "listHead": "#C4BD3A", "listBg": "#181613",
        "listText": "#FAF9E8", "sceneBg": "#171512", "sceneInk": "#FAF9E8"}},
]

DEFAULT_STYLE = {
    "caption": "regular",
    "keyword": "displaybook",
    "serif": "serifbi",
    "list": "sansitalic",
    "endcard": "grande",
    "captionStyle": "editorial",
    "radius": "sharp",
    # Non-video fallback only. New video cards receive a unique draft palette.
    "colors": dict(PALETTES[0]["colors"]),
}


# ----------------------------------------------------------------- helpers
SLUG = re.compile(r"^[a-zA-Z0-9_-]+$")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
LEGACY_LIST_BG = re.compile(r"^rgba\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,"
                            r"\s*\d{1,3}\s*,\s*(?:0|1|0?\.\d+)\s*\)$")


def validate_style(style: dict) -> bool:
    """Do not embed untrusted font names/colour CSS in the preview."""
    if not isinstance(style, dict):
        return False
    roles = {r[0] for r in ROLES}
    packs = {p[0] for p in PACKS}
    if set(style) - (roles | {"colors", "captionStyle", "radius"}):
        return False
    if any(style.get(role) not in packs for role in roles):
        return False
    if style.get("captionStyle") != "editorial":
        return False
    if style.get("radius") not in ("sharp", "round", "pill"):
        return False
    colors = style.get("colors")
    if not isinstance(colors, dict) or set(colors) - (
            {c[0] for c in COLORS} | {"keyword"}):
        return False
    for name, value in colors.items():
        if not isinstance(value, str) or not (HEX.fullmatch(value) or (
                name == "listBg" and LEGACY_LIST_BG.fullmatch(value))):
            return False
    return True


def style_path(campaign: str, video: str | None = None) -> Path:
    if not SLUG.fullmatch(campaign) or (video and not SLUG.fullmatch(video)):
        raise ValueError("campaign and video must be simple slugs")
    root = ROOT / "campaigns" / campaign
    return root / video / "style.json" if video else root / "style.json"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    c = hex_color.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(hex_color: str) -> float:
    def linear(c: int) -> float:
        x = c / 255
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (linear(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _generated_palette(campaign: str, video: str, used: set[str]) -> dict:
    """Make a readable, deterministic new colour when all curated palettes are used."""
    seed = int.from_bytes(hashlib.sha256(
        f"{campaign}/{video}".encode()).digest()[:4], "big") % 360
    used = {c.upper() for c in used if HEX.fullmatch(c)}
    used_rgb = [_rgb(c) for c in used]
    candidates = []
    # Search a coarse perceptual wheel; choose the colour furthest from all
    # sibling accents while maintaining strong contrast on the dark stage.
    for step in range(72):
        hue = ((seed + step * 5) % 360) / 360
        for lightness in (0.54, 0.60, 0.66, 0.70):
            for saturation in (0.62, 0.72):
                rgb = tuple(round(x * 255) for x in
                            colorsys.hls_to_rgb(hue, lightness, saturation))
                color = "#" + "".join(f"{x:02X}" for x in rgb)
                if color.upper() in used or _contrast(color, "#14110F") < 3.0:
                    continue
                distance = min((sum((x - y) ** 2 for x, y in zip(rgb, old)) ** 0.5
                                for old in used_rgb), default=442.0)
                candidates.append((distance, -step, color, hue))
    if not candidates:
        raise ValueError("could not generate a distinct readable palette")
    _distance, _step, accent, hue = max(candidates)
    bg = "#" + "".join(f"{round(x * 255):02X}" for x in
                        colorsys.hls_to_rgb(hue, 0.095, 0.30))
    list_bg = "#" + "".join(f"{round(x * 255):02X}" for x in
                             colorsys.hls_to_rgb(hue, 0.125, 0.30))
    return {"id": "generated", "label": "Generated / unique",
            "colors": {"accent": accent, "caption": "#F8F4EC",
                       "keyword": accent, "serif": "#F8F4EC",
                       "endcard": accent, "plate": accent,
                       "plateInk": bg, "listHead": accent,
                       "listBg": list_bg, "listText": "#F8F4EC",
                       "sceneBg": bg, "sceneInk": "#F8F4EC"}}


def palette_for_video(campaign: str, video: str) -> dict:
    """Return a distinct *draft* palette for a new video card.

    post5_demo keeps the cobalt draft used in the earlier preview unless a
    sibling has actually saved it. For all other cards, the slug seeds the
    order; occupied accents are skipped. Exhausting the eight presets yields
    a generated, contrast-checked colour rather than a silent duplicate.
    """
    folder = ROOT / "campaigns" / campaign
    used: set[str] = set()
    if folder.exists():
        for path in folder.glob("*/style.json"):
            if path.parent.name == video:
                continue
            try:
                color = json.loads(path.read_text()).get("colors", {}).get("accent")
                if isinstance(color, str) and HEX.fullmatch(color):
                    used.add(color.upper())
            except (OSError, json.JSONDecodeError, AttributeError):
                continue
    if video == "post5_demo":
        seed = next(i for i, p in enumerate(PALETTES) if p["id"] == "cobalt")
    else:
        seed = int.from_bytes(hashlib.sha256(video.encode()).digest()[:2], "big") % len(PALETTES)
    for offset in range(len(PALETTES)):
        palette = PALETTES[(seed + offset) % len(PALETTES)]
        if palette["colors"]["accent"].upper() not in used:
            return palette
    return _generated_palette(campaign, video, used)


def load_style(campaign: str, video: str | None = None) -> dict:
    """Campaign defaults, then this video's saved choice or a unique draft."""
    merged = json.loads(json.dumps(DEFAULT_STYLE))
    campaign_path = style_path(campaign)
    own_path = style_path(campaign, video) if video else None
    for path in (campaign_path, own_path) if own_path else (campaign_path,):
        if not path or not path.exists():
            continue
        try:
            saved = json.loads(path.read_text())
            merged.update({k: v for k, v in saved.items() if k != "colors"})
            merged["colors"].update(saved.get("colors") or {})
        except (json.JSONDecodeError, TypeError):
            raise ValueError(f"invalid style file: {path}")
    if own_path and not own_path.exists():
        merged["colors"].update(palette_for_video(campaign, video)["colors"])
    # The chosen project accent is the only keyword ink. New cards always
    # use the approved flat editorial treatment, never legacy marker/impact.
    merged["colors"]["keyword"] = merged["colors"]["accent"]
    merged["captionStyle"] = "editorial"
    return merged


def _style_digest(style: dict) -> str:
    canonical = json.dumps(style, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_style_approved(campaign: str, video: str | None,
                      expected_digest: str | None = None) -> bool:
    """True only when this video's saved style matches its card receipt/theme."""
    if (not isinstance(campaign, str) or not campaign
            or not isinstance(video, str) or not video):
        return False
    try:
        p = style_path(campaign, video)
    except ValueError:
        return False
    receipt_path = p.with_name("style_approval.json")
    try:
        style = json.loads(p.read_text())
        receipt = json.loads(receipt_path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return (receipt.get("approved") is True
            and receipt.get("campaign") == campaign
            and receipt.get("video") == video
            and receipt.get("style_sha256") == _style_digest(style)
            and (expected_digest is None or receipt.get("style_sha256") == expected_digest)
            and style.get("captionStyle") == "editorial")


def save_style(campaign: str, style: dict, video: str | None = None) -> Path:
    p = style_path(campaign, video)
    style = json.loads(json.dumps(style))
    style["captionStyle"] = "editorial"
    style["colors"]["keyword"] = style["colors"]["accent"]
    if not validate_style(style):
        raise ValueError("style card contains an unsupported font or colour")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(style, indent=2) + "\n")
    if video:
        receipt = {"version": 1, "approved": True, "campaign": campaign,
                   "video": video, "style_sha256": _style_digest(style)}
        p.with_name("style_approval.json").write_text(
            json.dumps(receipt, indent=2) + "\n")
    write_theme(campaign, style, video, approved=bool(video))
    return p


def write_theme(campaign: str, style: dict, video: str | None = None,
                approved: bool | None = None) -> Path:
    """Emit a per-video theme; only a saved style-card choice is approved."""
    base = json.loads((ROOT / "motion" / "themes" / "whop.json").read_text())
    base["fonts"] = {k: style.get(k) for k, _n, _t, _s in ROLES}
    base["fontPack"] = style.get("caption") or "regular"
    base["radius"] = style.get("radius", "sharp")
    base["colors"] = dict(style.get("colors") or {})
    accent = base["colors"].get("accent")
    if not isinstance(accent, str) or not HEX.fullmatch(accent):
        raise ValueError("style card needs a selected project accent")
    base["accent"] = accent
    base["colors"]["keyword"] = accent
    base["captionStyle"] = "editorial"
    if approved is None:
        approved = is_style_approved(campaign, video)
    approved = bool(approved and is_style_approved(campaign, video))
    base["styleCard"] = {"approved": approved, "campaign": campaign,
                         "video": video or ""}
    if approved:
        base["styleCard"]["style_sha256"] = _style_digest(style)
    out = style_path(campaign, video).with_name("style_theme.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(base, indent=2) + "\n")
    engine = ROOT / "motion" / "themes" / (campaign + ("__" + video if video else "") + ".json")
    engine.parent.mkdir(parents=True, exist_ok=True)
    engine.write_text(json.dumps(base, indent=2) + "\n")
    return out


def print_menu() -> None:
    print("FONT PACKS (all OFL, vendored in assets/fonts/)\n")
    for name, face, vibe, _css in PACKS:
        print(f"  {name:<12} {face:<28} {vibe}")
    print("\nROLES: caption text, keyword/hero, serif words, list plates, end card")
    print("COLOURS: accent (= spoken-keyword ink), caption/serif/endcard text, keyword plate + plate ink,")
    print("         list head/ground/text, scene ground + scene ink")
    print("\n  python scripts/whop/style_card.py serve --campaign <name> --video post<N>")


# ------------------------------------------------------------- the server
PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Style card</title>
<style>
  __FONT_FACES__
  :root { --bg:#0b0e11; --card:#141920; --line:#232a33; --ink:#e9eef2; --dim:#8fa3ad; --acc:#14e5c5; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:14px/1.45 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  header { padding:16px 22px; border-bottom:1px solid var(--line); display:flex; align-items:baseline; gap:14px; }
  header h1 { margin:0; font-size:16px; letter-spacing:.02em; }
  header span { color:var(--dim); font-size:12px; }
  .wrap { display:grid; grid-template-columns:minmax(420px,1fr) 420px; gap:0; height:calc(100vh - 57px); }
  .panel { padding:18px 22px; overflow:auto; }
  .right { border-left:1px solid var(--line); background:#0e1216; display:flex; flex-direction:column; align-items:center; gap:10px; padding-top:16px; }
  h2 { font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--dim); margin:22px 0 10px; }
  h2:first-child { margin-top:0; }
  .row { display:grid; grid-template-columns:170px 1fr; gap:12px; align-items:center; margin-bottom:9px; }
  label { color:var(--dim); font-size:12.5px; }
  select, input[type=color], input[type=text] {
    background:var(--card); color:var(--ink); border:1px solid var(--line);
    border-radius:8px; padding:7px 9px; font:inherit; width:100%; }
  input[type=color] { height:34px; padding:2px; cursor:pointer; }
  .spec { font-size:26px; line-height:1.15; margin:2px 0 12px; min-height:30px;
          -webkit-text-stroke:1px rgba(0,0,0,.5); paint-order:stroke fill; }
  .spec small { display:block; font-size:11px; color:var(--dim); letter-spacing:.08em; text-transform:uppercase; }
  /* The engine is fixed at 1080x1920. Scale the WHOLE iframe, never
     give it a 360x640 viewport (that cropped the preview to top-left). */
  iframe { width:1080px; height:1920px; border:0; background:#000;
           transform:scale(0.3333333); transform-origin:top left; }
  .framewrap { width:360px; height:640px; overflow:hidden; border-radius:10px; }
  .bar { display:flex; gap:8px; align-items:center; }
  .preview-note { width:360px; padding:0 4px; color:var(--dim); font-size:11px;
                  line-height:1.35; text-align:center; }
  button { background:var(--acc); color:#04120f; border:0; border-radius:8px; padding:9px 16px;
           font:600 13px inherit; cursor:pointer; }
  button.ghost { background:#1b222b; color:var(--ink); }
  #status { color:var(--dim); font-size:12px; }
  #status.ok { color:var(--acc); }
</style></head>
<body>
<header><h1>Style card</h1><span id="camp"></span><span>fonts &amp; colours are chosen BEFORE the edit</span></header>
<div class="wrap">
  <div class="panel" id="panel"></div>
  <div class="right">
    <div class="framewrap"><iframe id="pv" src="/stage.html"></iframe></div>
    <div class="bar">
      <button id="play">pause</button>
      <button class="ghost" id="save">__SAVE_LABEL__</button>
      <span id="status">loading…</span>
    </div>
    <div class="preview-note">Style and graphics preview only; final captions will sync to the source audio and keep the existing hook.</div>
  </div>
</div>
<script>
const PACKS = __PACKS__;
const ROLES = __ROLES__;
const COLORS = __COLORS__;
const PALETTES = __PALETTES__;
let style = __STYLE__, playing = true, t = 0, last = 0;

const panel = document.getElementById("panel");
document.getElementById("camp").textContent = __CAMPAIGN__;

function famOf(name) { const p = PACKS.find(x => x[0] === name); return p ? p[3] : "MontserratX"; }
function labelOf(name) { const p = PACKS.find(x => x[0] === name); return p ? p[1] : name; }
function inkOf(role) {
  const c = style.colors;
  return ({ caption:c.caption, keyword:c.accent, serif:c.serif,
            list:c.listText, endcard:c.endcard })[role] || "#ffffff";
}

function currentPaletteId() {
  const p = PALETTES.find(p => Object.entries(p.colors).every(([k,v]) => style.colors[k] === v));
  return p ? p.id : "custom";
}
function buildPanel() {
  document.documentElement.style.setProperty("--acc", style.colors.accent);
  panel.innerHTML = `<h2>Colour palette — per video</h2>
  <div class="row"><label>Starting palette</label><select id="palette">
    <option value="custom"${currentPaletteId()==="custom"?" selected":""}>Current / custom</option>
    ${PALETTES.map(p => `<option value="${p.id}"${p.id===currentPaletteId()?" selected":""}>${p.label}</option>`).join("")}
  </select></div>
  <p class="hint">Draft only. Choose or customize the colours for this video before editing; the big-word ink follows your accent.</p>` +
  `<h2>Type — per role</h2>` +
  ROLES.map(r => `<div class="row"><label>${r[1]}</label>
      <select data-role="${r[0]}">${PACKS.map(p =>
        `<option value="${p[0]}"${p[0]===style[r[0]]?" selected":""}>${p[1]} - ${p[2]}</option>`).join("")}</select></div>
      <div class="spec" data-spec="${r[0]}" style="font-family:'${famOf(style[r[0]])}';color:${inkOf(r[0])}">${r[3]}
        <small>${labelOf(style[r[0]])}</small></div>`).join("") +
  `<h2>Colours — customize any role</h2>` +
  COLORS.map(c => `<div class="row"><label>${c[1]}</label>
      <input type="color" data-color="${c[0]}" value="${hexOf(style.colors[c[0]])}"></div>`).join("") +
  `<h2>Caption treatment</h2><p class="hint">Flat editorial type, verbatim word timing, no marker bars or colour wipes.</p>`;
}
buildPanel();

function hexOf(v) { if (!v) return "#ffffff"; if (v.startsWith("#")) return v.slice(0,7);
  if (v.startsWith("rgba")) { const n = v.match(/[\d.]+/g); return "#" + n.slice(0,3)
    .map(x => (+x).toString(16).padStart(2,"0")).join(""); } return "#ffffff"; }

panel.addEventListener("change", e => {
  const t2 = e.target;
  if (t2.id === "palette") {
    const p = PALETTES.find(x => x.id === t2.value);
    if (p) {
      style.colors = { ...style.colors, ...p.colors };
      style.colors.keyword = style.colors.accent;
      buildPanel();
    }
    push(); return;
  }
  if (t2.dataset.role) { style[t2.dataset.role] = t2.value;
    const sp = panel.querySelector(`[data-spec="${t2.dataset.role}"]`);
    sp.style.fontFamily = "'" + famOf(t2.value) + "'";
    sp.querySelector("small").textContent = labelOf(t2.value); }
  else if (t2.dataset.color) {
    style.colors[t2.dataset.color] = t2.value;
    if (t2.dataset.color === "accent") {
      style.colors.keyword = t2.value;
      document.documentElement.style.setProperty("--acc", t2.value);
    }
    const role = t2.dataset.color === "listText" ? "list" : t2.dataset.color;
    const sp = panel.querySelector(`[data-spec="${role}"]`);
    if (sp) sp.style.color = t2.value;
    if (t2.dataset.color === "accent")
      panel.querySelector('[data-spec="keyword"]').style.color = t2.value;
  } else return;
  push();
});

const PREVIEW_DURATION = 24.15;
function previewTimeline() {
  const c = style.colors;
  const poster = (at, until, rows) => ({ type:"poster", at, until,
    zone:[0.82,0.90], connSize:84, captionStyle:"editorial", hardOut:true, rows });
  return { width:1080, height:1920, fps:30, duration:PREVIEW_DURATION,
    theme: { radius:"sharp", glow:0, speed:1, easing:"soft", fontMode:"sans",
             captionStyle:"editorial",
             fonts: { caption:style.caption, keyword:style.keyword, serif:style.serif,
                      list:style.list, endcard:style.endcard },
             colors: c },
    brand: { accent: c.accent },
    items: [
      { type:"broll", mode:"fullbleed", at:0, until:PREVIEW_DURATION,
        src:"/preview/face.jpg" },
      poster(0.20, 2.36, [
        [ {w:"My",at:0.20,kind:"conn"},{w:"worth",at:0.20,kind:"key"},
          {w:"isn't",at:0.20,kind:"conn"} ],
        [ {w:"in",at:0.20,kind:"conn"},{w:"my",at:0.20,kind:"conn"},
          {w:"body.",at:0.20,kind:"conn"} ] ]),
      poster(2.42, 5.04, [
        [ {w:"my",at:2.50,kind:"conn"},{w:"husband",at:2.75,kind:"word"},
          {w:"doesn't",at:3.05,kind:"conn"} ],
        [ {w:"love",at:3.45,kind:"word"},{w:"me",at:3.72,kind:"conn"},
          {w:"because",at:3.92,kind:"conn"} ] ]),
      poster(5.05, 6.44, [
        [ {w:"of",at:5.12,kind:"conn"},{w:"my",at:5.35,kind:"conn"},
          {w:"body.",at:5.60,kind:"word"} ] ]),
      poster(6.50, 8.58, [
        [ {w:"my",at:6.55,kind:"conn"},{w:"family",at:6.82,kind:"word"},
          {w:"doesn't",at:7.16,kind:"conn"} ],
        [ {w:"love",at:7.50,kind:"word"},{w:"me",at:7.77,kind:"conn"},
          {w:"because",at:8.00,kind:"conn"} ] ]),
      poster(8.60, 9.78, [
        [ {w:"of",at:8.68,kind:"conn"},{w:"my",at:8.89,kind:"conn"},
          {w:"body.",at:9.10,kind:"word"} ] ]),
      poster(9.85, 12.10, [
        [ {w:"I'm",at:9.90,kind:"conn"},{w:"not",at:10.12,kind:"conn"},
          {w:"sitting",at:10.35,kind:"word"} ],
        [ {w:"in",at:10.88,kind:"conn"},{w:"this",at:11.10,kind:"conn"},
          {w:"chair",at:11.34,kind:"word"} ] ]),
      poster(12.12, 13.35, [
        [ {w:"because",at:12.18,kind:"conn"},{w:"of",at:12.48,kind:"conn"},
          {w:"my",at:12.67,kind:"conn"},{w:"body.",at:12.88,kind:"word"} ] ]),
      poster(13.45, 15.05, [
        [ {w:"I",at:13.50,kind:"conn"},{w:"am",at:13.70,kind:"conn"},
          {w:"beautiful",at:13.95,kind:"word"} ],
        [ {w:"as",at:14.48,kind:"conn"},{w:"I",at:14.68,kind:"conn"},
          {w:"am.",at:14.88,kind:"word"} ] ]),
      poster(15.12, 16.40, [
        [ {w:"But",at:15.18,kind:"conn"},{w:"most",at:15.48,kind:"word"},
          {w:"importantly,",at:15.78,kind:"word"} ] ]),
      poster(16.45, 18.25, [
        [ {w:"I'm",at:16.52,kind:"conn"},{w:"a",at:16.74,kind:"conn"},
          {w:"good",at:16.90,kind:"word"} ],
        [ {w:"human.",at:17.28,kind:"word"} ] ]),
      { type:"vector", name:"shield", mode:"fullbleed", at:16.52, until:17.72,
        label:"GOOD HUMAN", color:c.accent },
      poster(18.28, 18.94, [ [ {w:"And,",at:18.30,kind:"word"} ] ]),
      poster(18.96, 20.95, [
        [ {w:"That's",at:19.02,kind:"word"},{w:"what",at:19.28,kind:"conn"},
          {w:"I",at:19.48,kind:"conn"} ],
        [ {w:"hold",at:19.80,kind:"word"},{w:"true",at:20.08,kind:"word"},
          {w:"to",at:20.38,kind:"conn"},{w:"my",at:20.58,kind:"conn"} ] ]),
      poster(20.98, 22.10, [ [ {w:"heart.",at:21.06,kind:"key"} ] ]),
      { type:"endcard", at:22.65, until:PREVIEW_DURATION,
        title:"FOLLOW FOR MORE", titleLines:["FOLLOW", "FOR MORE"],
        sub:"", accent:c.accent, wordSize:148 } ] };
}

const fr = document.getElementById("pv");
let frameReady = false;
fr.addEventListener("load", () => {
  const w = fr.contentWindow;
  w.setTimeline(previewTimeline());
  w.document.fonts.ready.then(() => {
    w.layoutStage(); frameReady = true; push();
    document.getElementById("status").textContent = "live preview";
  });
});
function push() { if (!frameReady) return; const w = fr.contentWindow;
  w.setTimeline(previewTimeline()); w.document.fonts.ready.then(() => w.layoutStage()); }
function loop(ts) {
  if (frameReady) { const dt = (ts - last) / 1000; last = ts;
    if (playing) { t = (t + dt) % PREVIEW_DURATION; fr.contentWindow.renderAt(t * 1000); } }
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
document.getElementById("play").onclick = (e) => { playing = !playing;
  e.target.textContent = playing ? "pause" : "play"; };
document.getElementById("save").onclick = async () => {
  const st = document.getElementById("status"); st.textContent = "saving…"; st.className = "";
  const r = await fetch("/api/save", { method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify(style) });
  st.textContent = r.ok ? __SAVE_SUCCESS__ : "save failed";
  st.className = r.ok ? "ok" : "";
};
// the embedded style IS the server's saved style (both come from
// load_style); no fetch/reload loop - a reload loop re-requested the
// fonts forever and fought the preview.
fetch("/api/style").then(r => r.json()).then(s => {
  if (s && s.caption) { style = s; buildPanel(); push(); }
});
</script>
</body></html>"""


def _preview_face() -> Path:
    """A still of the speaker to preview type against real footage."""
    out = ROOT / "work" / "style_card" / "face.jpg"
    if out.exists():
        return out
    src = ROOT / "campaigns" / "street_you_grew_up_on" / "post1" / "street_post1_v5.mp4"
    if not src.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, "-y", "-v", "error", "-ss", "2.6", "-i", str(src),
                    "-frames:v", "1", "-q:v", "3", str(out)], check=False)
    return out


class Handler(BaseHTTPRequestHandler):
    campaign = "street_you_grew_up_on"
    video: str | None = None
    face_path: Path | None = None
    style: dict = DEFAULT_STYLE

    def log_message(self, *a):  # keep the console clean
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/index.html"):
            # Font faces live in the stage *iframe* by default; the
            # parent must load them too for the specimen labels. Reuse
            # the same declarations so the specimen is honest.
            faces = "\n".join(re.findall(r"@font-face\s*\{[^}]+\}",
                                        STAGE.read_text(encoding="utf-8")))
            faces = faces.replace("file:///home/user/system/assets/fonts/", "/fonts/")
            save_label = "approve fonts & colours" if self.video else "save campaign draft"
            save_success = ("saved — approved for this video; editing may begin"
                            if self.video else "saved as a campaign draft — not approved for any video")
            page = (PAGE.replace("__FONT_FACES__", faces)
                        .replace("__PACKS__", json.dumps(PACKS))
                        .replace("__ROLES__", json.dumps(ROLES))
                        .replace("__COLORS__", json.dumps(COLORS))
                        .replace("__PALETTES__", json.dumps(PALETTES))
                        .replace("__STYLE__", json.dumps(self.style))
                        .replace("__SAVE_LABEL__", save_label)
                        .replace("__SAVE_SUCCESS__", json.dumps(save_success))
                        .replace("__CAMPAIGN__", json.dumps(self.campaign + (" / " + self.video if self.video else ""))))
            return self._send(200, page.encode(), "text/html; charset=utf-8")
        if p == "/stage.html":
            html = STAGE.read_text(encoding="utf-8")
            # serve the fonts over http so the browser will load them
            html = html.replace("file:///home/user/system/assets/fonts/", "/fonts/")
            html = html.replace('"file://" + item.src', 'item.src')
            return self._send(200, html.encode(), "text/html; charset=utf-8")
        if p == "/api/style":
            return self._send(200, json.dumps(self.style).encode(), "application/json")
        if p.startswith("/fonts/"):
            f = FONTS / Path(p).name
            if not f.exists():
                return self._send(404, b"no font", "text/plain")
            return self._send(200, f.read_bytes(), "font/woff2")
        if p == "/preview/face.jpg":
            f = self.face_path or _preview_face()
            if not f.exists():
                return self._send(404, b"no preview", "text/plain")
            return self._send(200, f.read_bytes(), "image/jpeg")
        return self._send(404, b"nope", "text/plain")

    def do_POST(self):
        if urlparse(self.path).path != "/api/save":
            return self._send(404, b"nope", "text/plain")
        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, b"bad json", "text/plain")
        if not isinstance(data, dict) or not isinstance(data.get("colors"), dict):
            return self._send(400, b"invalid style", "text/plain")
        st = json.loads(json.dumps(DEFAULT_STYLE))
        st.update({k: v for k, v in data.items() if k != "colors"})
        st["colors"].update(data["colors"])
        st["colors"]["keyword"] = st["colors"]["accent"]
        if not validate_style(st) or set(data) - (
                {r[0] for r in ROLES} | {"colors", "captionStyle", "radius"}):
            return self._send(400, b"invalid font/colour choice", "text/plain")
        type(self).style = st
        save_style(self.campaign, st, self.video)
        return self._send(200, b"saved", "text/plain")


def serve(campaign: str, video: str | None, port: int,
          preview: str | None = None) -> None:
    Handler.campaign = campaign
    Handler.video = video
    Handler.style = load_style(campaign, video)
    Handler.face_path = Path(preview).resolve() if preview else _preview_face()
    if not Handler.face_path.exists():
        raise FileNotFoundError(f"speaker preview missing: {Handler.face_path}")
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    label = campaign + (" / " + video if video else "")
    print(f"style card: http://0.0.0.0:{port}  ({label})")
    srv.serve_forever()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("menu", help="print the font/colour menu")
    s2 = sub.add_parser("show", help="print the saved style")
    s2.add_argument("--campaign", default="street_you_grew_up_on")
    s2.add_argument("--video", default="")
    s3 = sub.add_parser("serve", help="serve the interactive style card")
    s3.add_argument("--campaign", default="street_you_grew_up_on")
    s3.add_argument("--video", default="")
    s3.add_argument("--preview", default="", help="clean still of this video's speaker")
    s3.add_argument("--port", type=int, default=8010)
    s4 = sub.add_parser("theme", help="write a produce-ready theme json")
    s4.add_argument("--campaign", default="street_you_grew_up_on")
    s4.add_argument("--video", default="")
    s4.add_argument("--out", default="")
    a = ap.parse_args()

    if a.cmd == "menu":
        print_menu()
    elif a.cmd == "show":
        print(json.dumps(load_style(a.campaign, a.video or None), indent=2))
    elif a.cmd == "serve":
        serve(a.campaign, a.video or None, a.port, a.preview or None)
    elif a.cmd == "theme":
        video = a.video or None
        st = load_style(a.campaign, video)
        produced = write_theme(a.campaign, st, video)
        if a.out:
            out = Path(a.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(produced.read_text())
            print(f"theme written: {out}")
        else:
            print(f"theme written: {produced}")
    else:
        print_menu()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
