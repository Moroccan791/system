#!/usr/bin/env node
// Render the style-card preview timeline through the real engine and
// screenshot it.  node _shot_preview.mjs <out.png> <t-seconds>
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import zlib from "zlib";
import chromium from "@sparticuz/chromium";
import puppeteer from "puppeteer-core";

const MOTION = "/home/user/system/motion";
const OUT = process.argv[2] || "/home/user/system/work/style_card/preview.png";
const T = Number(process.argv[3] || 1.2);
const STY = process.argv[4] ? JSON.parse(process.argv[4]) : null;

const libDir = "/tmp/al2023/lib";
if (!fs.existsSync(path.join(libDir, "libnss3.so"))) {
  const br = fs.readFileSync(path.join(MOTION, "node_modules/@sparticuz/chromium/bin/al2023.tar.br"));
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
const page = await browser.newPage();
await page.setViewport({ width: 1080, height: 1920 });
const errs = [];
page.on("pageerror", e => errs.push("pageerror: " + e.message));
page.on("console", m => { if (m.type() === "error") errs.push("console: " + m.text()); });
await page.goto("http://127.0.0.1:8010/stage.html", { waitUntil: "domcontentloaded", timeout: 60000 });

const style = STY || {
  caption: "regular", keyword: "displaybook", serif: "serifbi",
  list: "sansitalic", endcard: "grande", captionStyle: "impact",
  colors: { accent: "#14E5C5", caption: "#FFFFFF", keyword: "#14E5C5",
            plate: "#14E5C5", plateInk: "#0B0E11", listHead: "#14E5C5",
            listBg: "rgba(9,11,15,0.90)", listText: "#FFFFFF",
            sceneBg: "#101319", sceneInk: "#FFFFFF" },
};
const tl = {
  width: 1080, height: 1920, fps: 30, duration: 9,
  theme: { radius: "sharp", glow: 0, speed: 1, easing: "pop", fontMode: "sans",
           captionStyle: style.captionStyle,
           fonts: { caption: style.caption, keyword: style.keyword, serif: style.serif,
                    list: style.list, endcard: style.endcard },
           colors: style.colors },
  brand: { accent: style.colors.accent },
  items: [
    { type: "broll", mode: "fullbleed", at: 0, until: 9, src: "/preview/face.jpg" },
    { type: "poster", at: 0.20, until: 3.60, zone: [0.58, 0.82], captionStyle: style.captionStyle,
      rows: [ [ { w: "I", at: 0.20, kind: "conn" }, { w: "DON'T", at: 0.38, kind: "conn" }, { w: "COME", at: 0.56, kind: "conn" } ],
              [ { w: "HOME", at: 0.78, kind: "key" } ] ] },
    { type: "poster", at: 3.70, until: 6.10, zone: [0.50, 0.72], captionStyle: style.captionStyle,
      rows: [ [ { w: "WHAT'S", at: 3.80, kind: "conn" } ],
              [ { w: "IMPORTANT", at: 4.20, kind: "hero" } ] ] },
    { type: "list", at: 6.20, until: 8.40, zone: [0.58, 0.95], title: "KEEPS ME", accent: style.colors.accent,
      items: [ { text: "BUSY", at: 6.40 }, { text: "SANE", at: 6.95 }, { text: "FOCUSED", at: 7.50 } ] },
    { type: "endcard", at: 8.45, until: 9, title: "STREET YOU GREW UP ON",
      sub: "@street_you_grew_up_on", accent: style.colors.accent, wordSize: 86 },
  ],
};
await page.evaluate((t) => window.setTimeline(t), tl);
await page.evaluate(() => document.fonts.ready.then(() => true));
await page.evaluate(() => window.layoutStage());
await page.evaluate((t) => window.renderAt(t), T);
fs.mkdirSync(path.dirname(OUT), { recursive: true });
await page.screenshot({ path: OUT });
console.log("wrote", OUT, "at t=" + T);
console.log("errors:", errs.length ? errs.slice(0, 6).join(" | ") : "none");
await browser.close();
