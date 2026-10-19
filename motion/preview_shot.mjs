#!/usr/bin/env node
// Render a still from the approved style-card preview through the real stage.
// The card owns the timeline so the screenshot can never drift from what the
// user sees or silently resurrect an obsolete hook/endcard sample.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";
import chromium from "@sparticuz/chromium";
import puppeteer from "puppeteer-core";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const OUT = process.argv[2] || path.join(ROOT, "work/style_card/preview.png");
const T = Number(process.argv[3] || 1.2);
const STY = process.argv[4] ? JSON.parse(process.argv[4]) : null;
const PREVIEW = "http://127.0.0.1:8010";
if (!Number.isFinite(T) || T < 0) throw new Error("time must be a non-negative number");

const libDir = "/tmp/al2023/lib";
if (!fs.existsSync(path.join(libDir, "libnss3.so"))) {
  const br = fs.readFileSync(path.join(HERE, "node_modules/@sparticuz/chromium/bin/al2023.tar.br"));
  fs.mkdirSync("/tmp/al2023", { recursive: true });
  fs.writeFileSync("/tmp/al2023/al2023.tar", zlib.brotliDecompressSync(br));
  execFileSync("tar", ["-xf", "/tmp/al2023/al2023.tar", "-C", "/tmp/al2023"]);
}
const browser = await puppeteer.launch({
  args: [...chromium.args, "--no-sandbox", "--disable-dev-shm-usage", "--force-color-profile=srgb"],
  executablePath: await chromium.executablePath(),
  headless: true,
  env: { ...process.env, LD_LIBRARY_PATH: libDir },
});
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1920 });
  const errs = [];
  page.on("pageerror", e => errs.push("pageerror: " + e.message));
  page.on("console", m => { if (m.type() === "error") errs.push("console: " + m.text()); });
  await page.goto(PREVIEW + "/", { waitUntil: "networkidle0", timeout: 60000 });
  await page.waitForFunction(
    () => document.getElementById("status")?.textContent === "live preview",
    { timeout: 30000 });
  const timeline = await page.evaluate(async override => {
    if (override) {
      style = override;
      buildPanel();
      push();
      await document.getElementById("pv").contentWindow.document.fonts.ready;
    }
    const play = document.getElementById("play");
    if (play.textContent === "pause") play.click();
    return previewTimeline();
  }, STY);

  await page.goto(PREVIEW + "/stage.html", { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.evaluate(tl => window.setTimeline(tl), timeline);
  await page.evaluate(() => document.fonts.ready.then(() => window.layoutStage()));
  const time = (T % timeline.duration) * 1000;
  await page.evaluate(ms => window.renderAt(ms), time);
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  await page.screenshot({ path: OUT });
  console.log("wrote", OUT, "at t=" + (time / 1000).toFixed(2));
  console.log("errors:", errs.length ? errs.slice(0, 6).join(" | ") : "none");
} finally {
  await browser.close();
}
