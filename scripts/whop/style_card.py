#!/usr/bin/env python3
"""Style card: choose the fonts and colours BEFORE the edit.

    python scripts/whop/style_card.py menu
    python scripts/whop/style_card.py show
    python scripts/whop/style_card.py serve --campaign street_you_grew_up_on
    python scripts/whop/style_card.py theme --campaign street_you_grew_up_on \
            --out work/street/whop_v6/style_theme.json

The card stores one style per campaign in
campaigns/<campaign>/style.json and writes a produce-ready theme next to
it. The preview panel renders through the REAL engine (motion/stage.html
driven by window.setTimeline/renderAt), so what you approve on the card is
exactly what the render will look like - no mock-up drift.

The user picks:
  fonts   - caption face, keyword/hero face, serif face, endcard face,
            list face (each one of the vendored OFL packs)
  colours - accent (keyword), caption text, keyword ink, keyword plate +
            plate ink, list head/bg/text, scene ground + scene ink
"""
from __future__ import annotations

import argparse
import json
import os
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
]

ROLES = [
    ("caption", "Caption text", "conn", "I DON'T COME HOME"),
    ("keyword", "Keyword / hero", "keyword", "CONNECTION"),
    ("serif", "Serif words", "serif", "reflection"),
    ("list", "List plates", "list", "FOCUSED"),
    ("endcard", "End card", "endcard", "STREET YOU GREW UP ON"),
]

COLORS = [
    ("accent", "Accent (scenes, badges)"),
    ("caption", "Caption text"),
    ("keyword", "Keyword ink"),
    ("plate", "Keyword plate"),
    ("plateInk", "Plate ink"),
    ("listHead", "List head"),
    ("listBg", "List plate ground"),
    ("listText", "List text"),
    ("sceneBg", "Full-screen scene ground"),
    ("sceneInk", "Scene ink"),
]

DEFAULT_STYLE = {
    "caption": "regular",
    "keyword": "displaybook",
    "serif": "serifbi",
    "list": "sansitalic",
    "endcard": "grande",
    "captionStyle": "impact",
    "colors": {
        "accent": "#14E5C5",
        "caption": "#FFFFFF",
        "keyword": "#14E5C5",
        "plate": "#14E5C5",
        "plateInk": "#0B0E11",
        "listHead": "#14E5C5",
        "listBg": "rgba(9,11,15,0.90)",
        "listText": "#FFFFFF",
        "sceneBg": "#101319",
        "sceneInk": "#FFFFFF",
    },
}


# ----------------------------------------------------------------- helpers
def style_path(campaign: str) -> Path:
    return ROOT / "campaigns" / campaign / "style.json"


def load_style(campaign: str) -> dict:
    p = style_path(campaign)
    if p.exists():
        try:
            st = json.loads(p.read_text())
            merged = json.loads(json.dumps(DEFAULT_STYLE))
            merged.update({k: v for k, v in st.items() if k != "colors"})
            merged["colors"].update(st.get("colors") or {})
            return merged
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_STYLE))


def save_style(campaign: str, style: dict) -> Path:
    p = style_path(campaign)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(style, indent=2) + "\n")
    write_theme(campaign, style)
    return p


def write_theme(campaign: str, style: dict) -> Path:
    """Emit a produce-ready theme: the whop base + the chosen roles/colors."""
    base = json.loads((ROOT / "motion" / "themes" / "whop.json").read_text())
    base["fonts"] = {k: style.get(k) for k, _n, _t, _s in ROLES}
    base["colors"] = style.get("colors") or {}
    base["accent"] = (style.get("colors") or {}).get("accent", base.get("accent", "#14E5C5"))
    base["captionStyle"] = style.get("captionStyle", base.get("captionStyle", "impact"))
    out = ROOT / "campaigns" / campaign / "style_theme.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(base, indent=2) + "\n")
    return out


def print_menu() -> None:
    print("FONT PACKS (all OFL, vendored in assets/fonts/)\n")
    for name, face, vibe, _css in PACKS:
        print(f"  {name:<12} {face:<28} {vibe}")
    print("\nROLES: caption text, keyword/hero, serif words, list plates, end card")
    print("COLOURS: accent, caption text, keyword ink, keyword plate + plate ink,")
    print("         list head/ground/text, scene ground + scene ink")
    print("\n  python scripts/whop/style_card.py serve --campaign <name>")


# ------------------------------------------------------------- the server
PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Style card</title>
<style>
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
  iframe { width:360px; height:640px; border:0; border-radius:10px; background:#000; transform-origin:top center; }
  .framewrap { width:360px; height:640px; overflow:hidden; border-radius:10px; }
  .bar { display:flex; gap:8px; align-items:center; }
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
      <button class="ghost" id="save">save style</button>
      <span id="status">loading…</span>
    </div>
  </div>
</div>
<script>
const PACKS = __PACKS__;
const ROLES = __ROLES__;
const COLORS = __COLORS__;
let style = __STYLE__, playing = true, t = 0, last = 0;

const panel = document.getElementById("panel");
document.getElementById("camp").textContent = __CAMPAIGN__;

function famOf(name) { const p = PACKS.find(x => x[0] === name); return p ? p[3] : "MontserratX"; }
function labelOf(name) { const p = PACKS.find(x => x[0] === name); return p ? p[1] : name; }

function buildPanel() {
panel.innerHTML = "<h2>Type - per role</h2>" +
  ROLES.map(r => `<div class="row"><label>${r[1]}</label>
      <select data-role="${r[0]}">${PACKS.map(p =>
        `<option value="${p[0]}"${p[0]===style[r[0]]?" selected":""}>${p[1]} - ${p[2]}</option>`).join("")}</select></div>
      <div class="spec" data-spec="${r[0]}" style="font-family:'${famOf(style[r[0]])}'">${r[3]}
        <small>${labelOf(style[r[0]])}</small></div>`).join("") +
  `<h2>Colours</h2>` +
  COLORS.map(c => `<div class="row"><label>${c[1]}</label>
      <input type="color" data-color="${c[0]}" value="${hexOf(style.colors[c[0]])}"></div>`).join("") +
  `<h2>Caption look</h2>
   <div class="row"><label>Word treatment</label>
     <select id="cstyle">${["editorial","impact","pop","karaoke","stretch","bounce"].map(s =>
       `<option${s===style.captionStyle?" selected":""}>${s}</option>`).join("")}</select></div>`;
}
buildPanel();

function hexOf(v) { if (!v) return "#ffffff"; if (v.startsWith("#")) return v.slice(0,7);
  if (v.startsWith("rgba")) { const n = v.match(/[\d.]+/g); return "#" + n.slice(0,3)
    .map(x => (+x).toString(16).padStart(2,"0")).join(""); } return "#ffffff"; }

panel.addEventListener("change", e => {
  const t2 = e.target;
  if (t2.dataset.role) { style[t2.dataset.role] = t2.value;
    const sp = panel.querySelector(`[data-spec="${t2.dataset.role}"]`);
    sp.style.fontFamily = "'" + famOf(t2.value) + "'";
    sp.querySelector("small").textContent = labelOf(t2.value); }
  else if (t2.dataset.color) style.colors[t2.dataset.color] = t2.value;
  else if (t2.id === "cstyle") style.captionStyle = t2.value;
  else return;
  push();
});

function previewTimeline() {
  const c = style.colors;
  return { width:1080, height:1920, fps:30, duration:9,
    theme: { radius:"sharp", glow:0, speed:1, easing:"pop", fontMode:"sans",
             captionStyle: style.captionStyle,
             fonts: { caption:style.caption, keyword:style.keyword, serif:style.serif,
                      list:style.list, endcard:style.endcard },
             colors: c },
    brand: { accent: c.accent },
    items: [
      { type:"broll", mode:"fullbleed", at:0, until:9, src:"/preview/face.jpg" },
      { type:"poster", at:0.20, until:3.60, zone:[0.58,0.82], captionStyle:style.captionStyle,
        rows:[ [ {w:"I",at:0.20,kind:"conn"},{w:"DON'T",at:0.38,kind:"conn"},{w:"COME",at:0.56,kind:"conn"} ],
               [ {w:"HOME",at:0.78,kind:"key"} ] ] },
      { type:"poster", at:3.70, until:6.10, zone:[0.50,0.72], captionStyle:style.captionStyle,
        rows:[ [ {w:"WHAT'S",at:3.80,kind:"conn"} ],
               [ {w:"IMPORTANT",at:4.20,kind:"hero"} ] ] },
      { type:"list", at:6.20, until:8.40, zone:[0.58,0.95], title:"KEEPS ME", accent:c.accent,
        items:[ {text:"BUSY",at:6.40},{text:"SANE",at:6.95},{text:"FOCUSED",at:7.50} ] },
      { type:"endcard", at:8.45, until:9, title:"STREET YOU GREW UP ON",
        sub:"@street_you_grew_up_on", accent:c.accent, wordSize:86 } ] };
}

const fr = document.getElementById("pv");
let frameReady = false;
fr.addEventListener("load", () => {
  const w = fr.contentWindow;
  w.setTimeline(previewTimeline());
  w.document.fonts.ready.then(() => { w.layoutStage(); frameReady = true; push(); });
});
function push() { if (!frameReady) return; const w = fr.contentWindow;
  w.setTimeline(previewTimeline()); w.document.fonts.ready.then(() => w.layoutStage()); }
function loop(ts) {
  if (frameReady) { const dt = (ts - last) / 1000; last = ts;
    if (playing) { t = (t + dt) % 9; fr.contentWindow.renderAt(t); } }
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
document.getElementById("play").onclick = (e) => { playing = !playing;
  e.target.textContent = playing ? "pause" : "play"; };
document.getElementById("save").onclick = async () => {
  const st = document.getElementById("status"); st.textContent = "saving…"; st.className = "";
  const r = await fetch("/api/save", { method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify(style) });
  st.textContent = r.ok ? "saved - the next render uses this" : "save failed";
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
            page = (PAGE.replace("__PACKS__", json.dumps(PACKS))
                        .replace("__ROLES__", json.dumps(ROLES))
                        .replace("__COLORS__", json.dumps(COLORS))
                        .replace("__STYLE__", json.dumps(self.style))
                        .replace("__CAMPAIGN__", json.dumps(self.campaign)))
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
            f = _preview_face()
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
        st = json.loads(json.dumps(DEFAULT_STYLE))
        st.update({k: v for k, v in data.items() if k != "colors"})
        st["colors"].update(data.get("colors") or {})
        self.style = st
        save_style(self.campaign, st)
        return self._send(200, b"saved", "text/plain")


def serve(campaign: str, port: int) -> None:
    Handler.campaign = campaign
    Handler.style = load_style(campaign)
    _preview_face()
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"style card: http://0.0.0.0:{port}  (campaign {campaign})")
    srv.serve_forever()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("menu", help="print the font/colour menu")
    s2 = sub.add_parser("show", help="print the saved style")
    s2.add_argument("--campaign", default="street_you_grew_up_on")
    s3 = sub.add_parser("serve", help="serve the interactive style card")
    s3.add_argument("--campaign", default="street_you_grew_up_on")
    s3.add_argument("--port", type=int, default=8010)
    s4 = sub.add_parser("theme", help="write a produce-ready theme json")
    s4.add_argument("--campaign", default="street_you_grew_up_on")
    s4.add_argument("--out", default="")
    a = ap.parse_args()

    if a.cmd == "menu":
        print_menu()
    elif a.cmd == "show":
        print(json.dumps(load_style(a.campaign), indent=2))
    elif a.cmd == "serve":
        serve(a.campaign, a.port)
    elif a.cmd == "theme":
        st = load_style(a.campaign)
        out = Path(a.out) if a.out else ROOT / "campaigns" / a.campaign / "style_theme.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        write_theme(a.campaign, st)
        out.write_text((ROOT / "campaigns" / a.campaign / "style_theme.json").read_text())
        print(f"theme written: {out}")
    else:
        print_menu()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
