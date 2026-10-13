"""Tiny browser: watch raw footage, references, generated styles and finished
clips without leaving the workspace.

    python -m clipper serve --port 8000

Binds 0.0.0.0 (so it works behind the sandbox preview proxy) and supports
HTTP Range requests, which is what <video> seeking needs.
"""
from __future__ import annotations

import html
from urllib.parse import quote
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .. import config
from ..util import jsonio

MEDIA = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
AUDIO = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".opus"}


def fmt_time(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes}:{seconds - minutes * 60:04.1f}"


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _card(path: Path, root: Path, label: str | None = None) -> str:
    rel = path.relative_to(root).as_posix()
    title = label or path.name
    size = _human(path.stat().st_size)
    suffix = path.suffix.lower()
    if suffix in MEDIA:
        body = (f'<video controls preload="metadata" src="/media/{html.escape(rel)}"></video>')
    elif suffix in AUDIO:
        body = f'<audio controls preload="metadata" src="/media/{html.escape(rel)}"></audio>'
    elif suffix == ".json":
        body = f'<a class="link" href="/media/{html.escape(rel)}" target="_blank">open json</a>'
    elif suffix in (".ass", ".txt", ".md"):
        body = f'<a class="link" href="/media/{html.escape(rel)}" target="_blank">open {suffix[1:]}</a>'
    elif suffix in (".png", ".jpg", ".jpeg", ".webp"):
        body = f'<a href="/media/{html.escape(rel)}" target="_blank"><img src="/media/{html.escape(rel)}"></a>'
    else:
        body = f'<a class="link" href="/media/{html.escape(rel)}" target="_blank">open</a>'
    return (f'<figure class="card"><figcaption><b>{html.escape(title)}</b>'
            f'<span>{html.escape(rel)} · {size}</span></figcaption>{body}</figure>')


def _section(title: str, blurb: str, cards: list[str]) -> str:
    if not cards:
        return ""
    return (f'<section><h2>{html.escape(title)}</h2><p class="blurb">{html.escape(blurb)}</p>'
            f'<div class="grid">{"".join(cards)}</div></section>')


def _candidate_cards() -> tuple[list[str], str]:
    """One seekable player per candidate moment, grouped by source file."""
    rows: list[str] = []
    count = 0
    for payload_path in sorted(config.WORK.glob("*/candidates/*.json")):
        try:
            payload = jsonio.load(payload_path, {}) or {}
        except Exception:
            continue
        source = Path(payload.get("source", {}).get("file", ""))
        if not source.exists():
            continue
        try:
            rel = quote(str(source.relative_to(config.ROOT)), safe="/")
        except ValueError:
            rel = None
        if rel is None:
            continue
        group: list[str] = []
        for c in payload.get("candidates", []):
            count += 1
            # a media fragment makes the browser play exactly the candidate
            src = f"{rel}#t={c['start']:.2f},{c['end']:.2f}"
            reasons = "".join(f"<li>{html.escape(str(r))}</li>" for r in c.get("reasons", [])[:3])
            snippet = html.escape((c.get("text") or "")[:150])
            group.append(
                f'<figure class="card">'
                f'<video src="{src}" controls preload="metadata"></video>'
                f'<figcaption><b>{html.escape(str(c.get("id", "")))} '
                f'{fmt_time(c["start"])}–{fmt_time(c["end"])}</b>'
                f'<span>score {c["score"]:.2f} · {c["duration"]:.1f}s</span></figcaption>'
                + (f'<p class="quote">{snippet}</p>' if snippet else "")
                + (f'<ul class="why">{reasons}</ul>' if reasons else "")
                + "</figure>")
        if group:
            head = (f'<h3 class="camp">{html.escape(source.name)}'
                    f'<span>{html.escape(payload.get("mode", ""))} · '
                    f'{html.escape(str(payload.get("target", {}).get("platform", "")))}</span></h3>')
            rows.append(head + f'<div class="grid">{"".join(group)}</div>')
    return rows, f"{count} candidate moment(s) chosen from your raw footage"


def build_index(root: Path) -> str:
    campaigns_html: list[str] = []
    for campaign_dir in sorted([*_subdirs(config.CAMPAIGNS), *_subdirs(config.SAMPLES)]):
        rows: list[str] = []
        for sub, kind in (("references", "reference"), ("raw", "raw")):
            folder = campaign_dir / sub
            if folder.is_dir():
                for f in sorted(folder.rglob("*")):
                    if f.is_file():
                        rows.append(_card(f, root, label=f"{kind} · {f.name}"))
        if rows:
            campaigns_html.append(
                f'<h3 class="camp">{html.escape(campaign_dir.name)}'
                f'<span>{html.escape(str(campaign_dir.relative_to(root)))}</span></h3>'
                f'<div class="grid">{"".join(rows)}</div>')

    styles = [_card(p, root) for p in sorted(config.STYLES.glob("*.json"))] if config.STYLES.exists() else []
    outputs = [_card(p, root) for p in sorted(config.OUTPUT.rglob("*")) if p.is_file()] if config.OUTPUT.exists() else []
    work = [_card(p, root) for p in sorted(config.WORK.rglob("*"))
            if p.is_file() and p.suffix.lower() in {".mp4", ".json", ".ass", ".png", ".wav"}] if config.WORK.exists() else []

    candidates, candidates_blurb = _candidate_cards()
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>clipper · workspace</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 :root {{ color-scheme: dark; }}
 * {{ box-sizing: border-box; }}
 body {{ margin:0; background:#0c0d10; color:#e8e8ea; font:15px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,Arial; }}
 header {{ padding:22px 26px; border-bottom:1px solid #23252c; display:flex; gap:14px; align-items:baseline; flex-wrap:wrap; }}
 header h1 {{ font-size:19px; margin:0; letter-spacing:.2px; }}
 header span {{ color:#8b90a0; font-size:13px; }}
 main {{ padding:8px 26px 60px; }}
 h2 {{ font-size:15px; text-transform:uppercase; letter-spacing:.14em; color:#9aa1b4; margin:34px 0 4px; }}
 h3.camp {{ font-size:15px; margin:26px 0 8px; display:flex; gap:10px; align-items:baseline; }}
 h3.camp span {{ color:#6f7484; font-size:12px; font-weight:400; }}
 .blurb {{ color:#7f8496; margin:0 0 12px; font-size:13px; }}
 .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:14px; }}
 .card {{ margin:0; background:#14161c; border:1px solid #23252c; border-radius:12px; padding:10px; }}
 .card figcaption {{ display:flex; flex-direction:column; margin-bottom:8px; }}
 .card figcaption b {{ font-size:13px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
 .card figcaption span {{ color:#6f7484; font-size:11px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
 video, img {{ width:100%; border-radius:8px; background:#000; max-height:420px; object-fit:contain; display:block; }}
 audio {{ width:100%; }}
 a.link {{ color:#7cc4ff; font-size:13px; }}
 .empty {{ color:#6f7484; font-size:14px; }}
 .quote {{ color:#c9cdd8; font-size:12.5px; margin:8px 0 0; font-style:italic; }}
 ul.why {{ margin:6px 0 0; padding-left:16px; color:#8b90a0; font-size:12px; }}
</style></head><body>
<header><h1>clipper · workspace</h1>
<span>{html.escape(str(root))}</span></header>
<main>
{''.join(campaigns_html) or '<p class="empty">No campaigns found. Put a folder in campaigns/&lt;name&gt;/references and /raw, or run <code>python -m clipper samples</code>.</p>'}
{_section("Candidate moments", candidates_blurb, candidates)}
{_section("Style profiles", "extracted from your references (stage 1 output)", styles)}
{_section("Finished clips", "ready to upload to TikTok / Reels / Shorts", outputs)}
{_section("Work files", "intermediates: transcripts, cues, .ass subtitles", work)}
</main></body></html>"""


def _subdirs(base: Path) -> list[Path]:
    if not base.exists():
        return []
    return [p for p in sorted(base.iterdir()) if p.is_dir()]


class ViewerHandler(BaseHTTPRequestHandler):
    root: Path = config.ROOT
    server_version = "clipper-viewer/0.1"

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        if os.environ.get("CLIPPER_VIEWER_VERBOSE"):
            super().log_message(fmt, *args)

    # -- helpers ---------------------------------------------------------
    def _resolve(self, rel: str) -> Path | None:
        rel = unquote(rel).lstrip("/")
        target = (self.root / rel).resolve()
        try:
            target.relative_to(self.root.resolve())
        except ValueError:
            return None
        return target if target.exists() and target.is_file() else None

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
            if m:
                start = int(m.group(1)) if m.group(1) else 0
                end = int(m.group(2)) if m.group(2) else len(data) - 1
                start = max(0, min(start, len(data) - 1))
                end = max(start, min(end, len(data) - 1))
                chunk = data[start:end + 1]
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(chunk)
                return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # -- routes ----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path)
        if route.path in ("/", "/index.html"):
            body = build_index(self.root).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if route.path.startswith("/media/"):
            target = self._resolve(route.path[len("/media/"):])
            if target:
                self._send_file(target)
            else:
                self.send_error(404, "not found")
            return
        if route.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_error(404, "not found")


def serve(port: int = 8000, host: str = "0.0.0.0", root: Path | None = None) -> None:
    handler = type("BoundViewer", (ViewerHandler,), {"root": root or config.ROOT})
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"clipper viewer → http://{host}:{port}  (root: {handler.root})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
