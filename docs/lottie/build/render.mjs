#!/usr/bin/env node
// Render SmartSched Lottie JSON to PNG frames with lottie-web (svg renderer) in headless Chromium,
// then let render.sh assemble GIF/MP4/poster with ffmpeg.
// Licence: same as the repository (AGPL-3.0). Original work.
//
// Dependencies are NOT installed in the repo. Point LOTTIE_BUILD_DEPS at a scratch npm project:
//   mkdir -p /tmp/lottie-build && (cd /tmp/lottie-build && npm init -y && npm i lottie-web@5.13.0 playwright-core@1.55.1)
//   LOTTIE_BUILD_DEPS=/tmp/lottie-build CHROMIUM=/path/to/chrome node docs/lottie/build/render.mjs <json> <framesDir> [--scale 1] [--frames 0,90]
//
// Exits non-zero on any console error / page error while loading or stepping the animation.

import { createRequire } from "node:module";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const deps = process.env.LOTTIE_BUILD_DEPS;
if (!deps) { console.error("Set LOTTIE_BUILD_DEPS to a directory containing node_modules/{lottie-web,playwright-core}"); process.exit(2); }
const req = createRequire(join(resolve(deps), "package.json"));
const { chromium } = req("playwright-core");
const lottiePath = req.resolve("lottie-web/build/player/lottie_svg.min.js");

const args = process.argv.slice(2);
const [jsonPath, outDir] = args;
const opt = (name, dflt) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : dflt; };
const scale = Number(opt("--scale", "1"));
const only = opt("--frames", null)?.split(",").map(Number);

const data = JSON.parse(readFileSync(jsonPath, "utf8"));
const bg = data.layers.find((l) => l.nm === "background")?.shapes?.[0]?.it?.find((i) => i.ty === "fl")?.c?.k ?? [1, 1, 1, 1];
const bgCss = `rgb(${bg.slice(0, 3).map((c) => Math.round(c * 255)).join(",")})`;
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined, args: ["--disable-gpu", "--font-render-hinting=none"] });
const page = await browser.newPage({ viewport: { width: data.w, height: data.h }, deviceScaleFactor: scale });
const errors = [];
page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") errors.push(`${m.type()}: ${m.text()}`); });
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));

await page.setContent(`<!doctype html><html><head><style>
  html,body{margin:0;padding:0;background:${bgCss};overflow:hidden}
  #c{width:${data.w}px;height:${data.h}px}
</style></head><body><div id="c"></div></body></html>`);
await page.addScriptTag({ path: lottiePath });
await page.evaluate((anim) => new Promise((ok, fail) => {
  const a = window.lottie.loadAnimation({ container: document.getElementById("c"), renderer: "svg", loop: false, autoplay: false, animationData: anim,
    rendererSettings: { preserveAspectRatio: "xMidYMid meet", progressiveLoad: false } });
  a.addEventListener("data_failed", () => fail(new Error("data_failed")));
  a.addEventListener("error", (e) => fail(new Error("lottie error " + JSON.stringify(e))));
  a.addEventListener("DOMLoaded", () => { window.__anim = a; ok(); });
}), data);

const total = data.op - data.ip;
const frames = only ?? Array.from({ length: total }, (_, i) => i);
const el = await page.$("#c");
for (const f of frames) {
  await page.evaluate((fr) => window.__anim.goToAndStop(fr, true), f);
  const buf = await el.screenshot({ type: "png" });
  writeFileSync(join(outDir, `f${String(f).padStart(4, "0")}.png`), buf);
}
const info = await page.evaluate(() => ({ total: window.__anim.totalFrames, fr: window.__anim.frameRate }));
await browser.close();

if (errors.length) { console.error(`console errors for ${jsonPath}:\n` + errors.join("\n")); process.exit(1); }
console.log(`${jsonPath}: ${frames.length} frames rendered (lottie totalFrames=${info.total}, ${info.fr} fps, scale ${scale}), no console errors`);
