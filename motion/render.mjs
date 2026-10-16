#!/usr/bin/env node
/* Deterministic frame renderer for the motion-graphics layer.
 *
 *   node render.mjs <timeline.json> <framesDir> [--from F] [--to F]
 *
 * Reads a validated timeline (see schema.json), drives stage.html in a
 * headless Chromium, and writes transparent PNG frames at the timeline
 * fps plus render_stats.json (semi-transparent-frame accounting for QC).
 * Every frame is a pure function of its timestamp: no clocks, no rAF.
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import zlib from "node:zlib";

import chromium from "@sparticuz/chromium";
import puppeteer from "puppeteer-core";

const HERE = path.dirname(fileURLToPath(import.meta.url));

async function ensureLibs() {
  // @sparticuz/chromium ships the NSS libs its binary needs on non-Lambda
  // hosts inside al2023.tar.br; extract once and point the loader at them.
  const libDir = "/tmp/al2023/lib";
  if (!fs.existsSync(path.join(libDir, "libnss3.so"))) {
    const br = fs.readFileSync(path.join(HERE, "node_modules/@sparticuz/chromium/bin/al2023.tar.br"));
    fs.mkdirSync("/tmp/al2023", { recursive: true });
    fs.writeFileSync("/tmp/al2023.tar", zlib.brotliDecompressSync(br));
    execFileSync("tar", ["-xf", "/tmp/al2023.tar", "-C", "/tmp/al2023"]);
  }
  return libDir;
}

async function main() {
  const [timelinePath, framesDir] = process.argv.slice(2);
  if (!timelinePath || !framesDir) {
    console.error("usage: node render.mjs <timeline.json> <framesDir> [--from F] [--to F]");
    process.exit(2);
  }
  const args = process.argv.slice(4);
  const opt = (name) => {
    const i = args.indexOf(name);
    return i >= 0 ? Number(args[i + 1]) : null;
  };
  const tl = JSON.parse(fs.readFileSync(timelinePath, "utf8"));
  // media srcs may be repo-root-relative; the stage wants absolute paths
  for (const item of tl.items || []) {
    if (item.src && !item.src.startsWith("/")) {
      item.src = path.resolve(HERE, "..", item.src);
    }
  }
  const fps = tl.fps || 30;
  const total = Math.round((tl.duration || 10) * fps);
  const from = opt("--from") ?? 0;
  const to = opt("--to") ?? total - 1;
  fs.mkdirSync(framesDir, { recursive: true });

  const libDir = await ensureLibs();
  const browser = await puppeteer.launch({
    args: [...chromium.args, "--no-sandbox", "--disable-dev-shm-usage",
           "--force-color-profile=srgb", "--allow-file-access-from-files"],
    executablePath: await chromium.executablePath(),
    headless: true,
    env: { ...process.env, LD_LIBRARY_PATH: libDir },
  });
  const page = await browser.newPage();
  await page.setViewport({ width: tl.width || 1080, height: tl.height || 1920 });
  await page.goto("file://" + path.join(HERE, "stage.html"));
  await page.evaluate((t) => window.setTimeline(t), tl);
  await page.evaluate(() => document.fonts.ready.then(() => true));
  await page.evaluate(() => window.layoutStage());
  // PiP / B-roll stills must be decoded before any frame is shot
  await page.evaluate(() => Promise.all([...document.images].map((img) =>
    img.complete ? 1 : new Promise((r) => { img.onload = img.onerror = () => r(1); }))));
  // video B-roll: metadata must be in before the first seek
  await page.evaluate(() => Promise.all([...document.querySelectorAll("video")].map((v) =>
    v.readyState >= 1 ? 1 : new Promise((r) => {
      v.addEventListener("loadedmetadata", () => r(1), { once: true });
      v.addEventListener("error", () => r(1), { once: true });
      setTimeout(() => r(1), 4000);
    }))));

  let semiFrames = 0, semiMaxRun = 0;
  const t0 = Date.now();
  for (let f = from; f <= to; f++) {
    const stats = await page.evaluate((ms) => window.renderAt(ms), (f / fps) * 1000);
    await page.evaluate(() => window.syncVideos());
    semiFrames += stats.semiFrames > 0 ? 1 : 0;
    semiMaxRun = Math.max(semiMaxRun, stats.semiMaxRun || 0);
    const out = path.join(framesDir, String(f).padStart(5, "0") + ".png");
    await page.screenshot({ path: out, omitBackground: true });
    if (f % 60 === 0) process.stderr.write(`frame ${f}/${to}\r`);
  }
  await browser.close();
  const report = { frames: to - from + 1, fps, semiTransparentFrames: semiFrames,
                   semiMaxConsecutive: semiMaxRun,
                   seconds: (Date.now() - t0) / 1000 };
  fs.writeFileSync(path.join(framesDir, "render_stats.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
}

main().catch((e) => { console.error(e); process.exit(1); });
