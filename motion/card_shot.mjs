#!/usr/bin/env node
// Screenshot a running style-card page (dev check).
//   node card_shot.mjs <url> <out.png>
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import zlib from "zlib";
import chromium from "@sparticuz/chromium";
import puppeteer from "puppeteer-core";

const MOTION = "/home/user/system/motion";
const URL_ = process.argv[2] || "http://127.0.0.1:8011/";
const OUT = process.argv[3] || "/home/user/system/work/style_card/card.png";
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
await page.setViewport({ width: 1280, height: 1000 });
const errs = [];
page.on("pageerror", e => errs.push(e.message.slice(0, 160)));
page.on("requestfailed", r => errs.push("REQ " + r.url().slice(0, 90)));
await page.goto(URL_, { waitUntil: "domcontentloaded", timeout: 30000 });
await new Promise(r => setTimeout(r, 6000));
const state = await page.evaluate(() => ({
  rows: document.querySelectorAll("#panel .row").length,
  status: document.getElementById("status")?.textContent,
  fonts: [...document.querySelectorAll("[data-spec]")].map(e => e.querySelector("small")?.textContent),
}));
console.log("STATE", JSON.stringify(state));
fs.mkdirSync(path.dirname(OUT), { recursive: true });
await page.screenshot({ path: OUT, timeout: 25000 });
console.log("wrote", OUT, "errors:", errs.length ? errs.slice(0, 4).join(" | ") : "none");
await browser.close();
