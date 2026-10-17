#!/usr/bin/env node
// SmartSched demo recorder: Playwright drives a scripted journey, Playwright's own video capture
// records it, and a post-processing engine adds Recordly-style polish.
//
//   node scripts/record/record.mjs --journey login-dashboard [--theme light|dark] [--lang en|tr]
//        [--engine ffmpeg|recordly|both|raw] [--out DIR] [--speed 1] [--headed] [--list]
//        [--repolish]   re-composite the take already in --out (lossless raw + timeline), without recording
//
// Env (all optional):
//   REC_BASE_URL     app URL (default http://127.0.0.1:3610 = scripts/record/stack.sh)
//   REC_EMAIL / REC_PASSWORD                 admin/planner credentials (default: the stack's seeded admin)
//   REC_TEACHER_EMAIL / REC_TEACHER_PASSWORD teacher credentials for teacher-booking
//   REC_TERM_CODE    term the journeys use (default 2026-BAHAR)
//   REC_THEME, REC_LANG, REC_ENGINE, REC_OUT  defaults for the flags
//   REC_VIEWPORT     WIDTHxHEIGHT (default 1440x900; record-all.sh uses 1280x800)
//   REC_FPS          pipeline frame rate (default 30; record-all.sh uses 20, see lib/fps.mjs)
//   RECORDLY_BIN     extracted Recordly AppImage executable (engine recordly/both)
//   REC_DEVICE       desktop (default) | phone: 390x844, deviceScaleFactor 3, isMobile + hasTouch (lib/touch.mjs), taps
//   REC_DSF          device scale factor of a desktop take (default 1; the launch video captures at 2)
//   REC_CAPTION_LANG caption language when it differs from the UI language (--lang)
//   --engine frames  the launch video's route (scripts/record/launch): keep the lossless screencast PNG frames +
//                    <name>.take.json (frames on the recorder clock, steps, pointer, keys); no compositing here
//   PLAYWRIGHT_BROWSERS_PATH (default /opt/pw-browsers when it exists)
//
// Output in --out (default ./recordings/<journey>-<theme>): <name>.mp4 (H.264), <name>.<clip>.gif (REC_GIF=1: one
// short clip per `clip` id, < 9 MB, REC_GIF_MAX_BYTES), <name>.webp (REC_WEBP=1, animated, < 4 MB),
// <name>.poster.png, <name>.timeline.json, <name>.raw.mp4 + .cursor.json + <name>.recordly (Recordly
// project), and with engine recordly/both <name>.recordly.mp4 rendered by Recordly itself.
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { Recorder } from "./lib/recorder.mjs";
import { toCfr, trimAndMap } from "./lib/video.mjs";
import { polish } from "./lib/polish.mjs";
import { exportWithRecordly, writeProject } from "./lib/recordly.mjs";
import { login, profileLanguage } from "./journeys/_shared.mjs";
import { startScreencast } from "./lib/screencast.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "../..");
const env = process.env;

const { values: args } = parseArgs({
  options: {
    journey: { type: "string", short: "j" },
    theme: { type: "string", default: env.REC_THEME ?? "light" },
    lang: { type: "string", default: env.REC_LANG ?? "en" },
    engine: { type: "string", default: env.REC_ENGINE ?? "ffmpeg" },
    out: { type: "string", default: env.REC_OUT },
    speed: { type: "string", default: "1" },
    headed: { type: "boolean", default: false },
    list: { type: "boolean", default: false },
    "no-captions": { type: "boolean", default: false },
    repolish: { type: "boolean", default: false },
  },
});

const journeysDir = join(HERE, "journeys");
const all = readdirSync(journeysDir).filter((f) => f.endsWith(".mjs") && !f.startsWith("_")).map((f) => f.replace(/\.mjs$/, ""));
if (args.list || !args.journey) {
  for (const id of all) {
    const j = (await import(pathToFileURL(join(journeysDir, `${id}.mjs`)).href)).default;
    console.log(`${id.padEnd(18)} db=${j.db.padEnd(6)} role=${j.role.padEnd(7)} verified=${j.verified || "no"}  ${j.title}`);
  }
  process.exit(args.journey ? 0 : args.list ? 0 : 1);
}
if (!all.includes(args.journey)) throw new Error(`unknown journey ${args.journey}; --list shows them`);
if (!["light", "dark"].includes(args.theme)) throw new Error("--theme must be light or dark");
if (!["ffmpeg", "recordly", "both", "raw", "frames"].includes(args.engine)) throw new Error("--engine must be ffmpeg, recordly, both, raw or frames");

const journey = (await import(pathToFileURL(join(journeysDir, `${args.journey}.mjs`)).href)).default;
const phone = (env.REC_DEVICE ?? "desktop") === "phone";
const [vw, vh] = (env.REC_VIEWPORT ?? (phone ? "390x844" : "1440x900")).split("x").map(Number);
const viewport = { width: vw, height: vh };
const dsf = Number(env.REC_DSF ?? (phone ? 3 : 1));
const baseURL = env.REC_BASE_URL ?? "http://127.0.0.1:3610";
const creds =
  journey.role === "teacher"
    ? { email: env.REC_TEACHER_EMAIL ?? "ogretmen@smartsched.local", password: env.REC_TEACHER_PASSWORD ?? "Teacher-2026!" }
    : { email: env.REC_EMAIL ?? "admin@smartsched.local", password: env.REC_PASSWORD ?? "Admin-2026!" };
const name = `${journey.id}-${args.theme}${args.lang === "en" ? "" : `-${args.lang}`}${phone ? "-phone" : ""}`;
const outDir = resolve(args.out ?? join(process.cwd(), "recordings", name));
mkdirSync(outDir, { recursive: true });
const log = (...m) => console.log(`[rec ${journey.id}]`, ...m);

// Playwright comes from the frontend's devDependencies (no extra install)
if (!env.PLAYWRIGHT_BROWSERS_PATH && existsSync("/opt/pw-browsers")) env.PLAYWRIGHT_BROWSERS_PATH = "/opt/pw-browsers";
const require = createRequire(join(REPO, "smartsched/frontend/package.json"));
const { chromium } = require("playwright");

let tl, raw, proj;
if (args.repolish) {
  // re-composite an existing take (lossless raw + timeline in --out) with the current pipeline settings
  raw = [`${name}.raw.mkv`, `${name}.raw.mp4`].map((f) => join(outDir, f)).find((f) => existsSync(f));
  if (!raw) throw new Error(`--repolish: no ${name}.raw.mkv/.mp4 in ${outDir}`);
  if (raw.endsWith(".mkv")) env.REC_LOSSLESS = "1";
  tl = JSON.parse(readFileSync(join(outDir, `${name}.timeline.json`), "utf8"));
  proj = { project: join(outDir, `${name}.recordly`) };
  log(`repolish ${raw}`);
} else {
  // ---- 1. record ---------------------------------------------------------------------------------
  const videoDir = join(outDir, ".video");
  // REC_CAPTURE: "video" = Playwright's recordVideo (VP8), "screencast" = lossless PNG frames (lib/screencast.mjs);
// a journey's own `capture` wins
  const capture = args.engine === "frames" ? "screencast" : journey.capture ?? env.REC_CAPTURE ?? "video"; // a journey can insist (see import-generate)
  if (capture === "screencast") env.REC_LOSSLESS = "1";
  let sc = null;
  rmSync(videoDir, { recursive: true, force: true });
  const browser = await chromium.launch({ headless: !args.headed });
  const context = await browser.newContext({
    baseURL,
    viewport,
    deviceScaleFactor: dsf,
    ...(phone ? { isMobile: true, hasTouch: true } : {}),
    colorScheme: args.theme,
    locale: args.lang === "tr" ? "tr-TR" : "en-GB",
    timezoneId: "Europe/Istanbul",
    ...(capture === "video" ? { recordVideo: { dir: videoDir, size: viewport } } : {}),
  });
  await context.addCookies([{ name: "NEXT_LOCALE", value: args.lang, url: baseURL }]);
  await context.addInitScript((theme) => {
    try {
      localStorage.setItem("theme", theme); // next-themes
      // keep the cookie's language: the booking pages otherwise apply the profile language once per session
      sessionStorage.setItem("crbs.profile-language", "1");
    } catch {
      /* ignore */
    }
    // no scrollbars / caret blink in demos
    const css = "::-webkit-scrollbar{width:0!important;height:0!important}*{caret-color:auto}";
    document.addEventListener("DOMContentLoaded", () => {
      const s = document.createElement("style");
      s.textContent = css;
      document.head.appendChild(s);
    });
  }, args.theme);
  const page = await context.newPage();
  const rec = new Recorder(page, { speed: Number(args.speed), viewport, log, touch: phone });
  const ctx = { page, baseURL, creds, lang: args.lang, captionLang: env.REC_CAPTION_LANG ?? args.lang, theme: args.theme, device: phone ? "phone" : "desktop", termCode: env.REC_TERM_CODE ?? "2026-BAHAR" };

  let failure = null;
  try {
    if (journey.id !== "login-dashboard") {
    await login(page, creds);
    await profileLanguage(page, args.lang); // the app follows the profile language once signed in
  }
    log("setup");
    await journey.setup.call(journey, ctx);
    await page.waitForLoadState("networkidle").catch(() => undefined);
    if (capture === "screencast") {
      sc = await startScreencast(page, join(outDir, args.engine === "frames" ? `${name}.frames` : ".frames"), viewport, { scale: dsf, keep: args.engine === "frames" });
      await rec.wait(400);
    }
    await rec.syncFlash();
    await rec.wait(250);
    rec.begin();
    await journey.run.call(journey, rec, ctx);
    rec.end();
  } catch (e) {
    failure = e;
    rec.end();
    await page.screenshot({ path: join(outDir, `${name}.failure.png`) }).catch(() => undefined);
  }
  const video = page.video();
  const screencastFile = sc ? await sc.stop(join(outDir, `${name}.screencast.mkv`)).catch((e) => (failure ??= e, null)) : null;
  if (args.engine === "frames") {
    await context.close();
    await browser.close();
    const tlRec = rec.timeline();
    if (failure) {
      writeFileSync(join(outDir, `${name}.timeline.recorder.json`), JSON.stringify(tlRec, null, 2));
      log(`journey failed: ${failure.message.split("\n")[0]} (screenshot ${name}.failure.png)`);
      process.exit(2);
    }
    const fr = JSON.parse(readFileSync(join(screencastFile, "frames.json"), "utf8"));
    const take = { version: 1, journey: { id: journey.id, title: journey.title, theme: args.theme, lang: args.lang, captionLang: ctx.captionLang, device: ctx.device },
      viewport, dsf, framesDir: `${name}.frames`, frames: fr.frames.map((f) => ({ t: +(f.t - tlRec.t0).toFixed(1), file: f.file })), timeline: tlRec };
    writeFileSync(join(outDir, `${name}.take.json`), JSON.stringify(take));
    const lags = fr.frames.map((f) => f.lag).filter((x) => x != null).sort((a, b) => a - b);
    log(`frames: ${take.frames.length} unique PNG frames at ${viewport.width * dsf}x${viewport.height * dsf}, ${((tlRec.marks.end - tlRec.marks.begin) / 1000).toFixed(1)} s, arrival lag p50 ${lags[lags.length >> 1] ?? "-"} ms -> ${name}.take.json`);
    process.exit(0);
  }
  await context.close();
  await browser.close();
  const webm = screencastFile ?? (await video?.path());
  const rawTimeline = rec.timeline();
  writeFileSync(join(outDir, `${name}.timeline.recorder.json`), JSON.stringify(rawTimeline, null, 2));
  if (failure) {
    log(`journey failed: ${failure.message.split("\n")[0]} (screenshot ${name}.failure.png, raw video ${webm})`);
    process.exit(2);
  }

  // ---- 2. normalise + sync + trim ----------------------------------------------------------------
  log("post: cfr + sync + trim");
  const cfr = toCfr(webm, join(outDir, `${name}.cfr.mp4`));
  raw = join(outDir, `${name}.raw.${capture === "screencast" ? "mkv" : "mp4"}`);
  tl = trimAndMap(cfr, rawTimeline, raw);
  if (screencastFile) rmSync(screencastFile, { force: true });
  tl.journey = { id: journey.id, title: journey.title, verified: journey.verified, theme: args.theme, lang: args.lang };
  writeFileSync(join(outDir, `${name}.timeline.json`), JSON.stringify(tl, null, 2));
  rmSync(cfr, { force: true });
  rmSync(videoDir, { recursive: true, force: true });
  log(`sync offset ${tl.sync.offsetMs.toFixed(0)} ms, kept ${(tl.durationMs / 1000).toFixed(1)} s`);

  // ---- 3. Recordly project (always: a human can open it in Recordly to fine-tune) ---------------
  // Recordly opens H.264 4:2:0; the lossless RGB take is for our compositor only
  let recordlyVideo = raw;
  if (raw.endsWith(".mkv")) {
    recordlyVideo = raw.replace(/\.mkv$/, ".mp4");
    execFileSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-i", raw, "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", recordlyVideo]);
  }
  proj = writeProject({ video: recordlyVideo, tl, outDir, name, theme: args.theme });
  log(`recordly project ${proj.project} (${proj.zoomRegions} zooms, ${proj.captions} captions)`);
}
const result = { journey: tl.journey, outDir, files: {} };
// ---- 4. engines --------------------------------------------------------------------------------
if (args.engine === "ffmpeg" || args.engine === "both") {
  const t = performance.now();
  const r = polish({ raw, tl, outDir, name, theme: args.theme, captions: !args["no-captions"] });
  result.ffmpeg = { ...r, seconds: +((performance.now() - t) / 1000).toFixed(1) };
  log(`ffmpeg: ${r.mp4} (${(statSync(r.mp4).size / 1e6).toFixed(1)} MB, ${(r.durationMs / 1000).toFixed(1)} s), poster ${r.poster} in ${result.ffmpeg.seconds} s`);
  if (r.webpInfo) log(`webp ${(r.webpInfo.bytes / 1e6).toFixed(2)} MB @ ${r.webpInfo.width}px/${r.webpInfo.fps}fps/q${r.webpInfo.quality}`);
  for (const g of r.gifs) {
    log(`gif ${g.id}: ${(g.bytes / 1e6).toFixed(2)} MB, ${g.seconds.toFixed(1)} s @ ${g.width}px/${g.fps}fps, ${g.frames} frames, delays ${g.min}-${g.max}/100 s${g.irregular ? `, ${g.irregular} irregular` : ""}${g.fits ? "" : " OVER BUDGET: shorten this clip"}`);
  }
}
if (args.engine === "recordly" || args.engine === "both") {
  const t = performance.now();
  const out = join(outDir, `${name}.recordly.mp4`);
  const r = exportWithRecordly({ project: proj.project, out });
  result.recordly = { out, seconds: +((performance.now() - t) / 1000).toFixed(1), frames: r.report?.metrics?.frameCount };
  log(`recordly: ${out} in ${result.recordly.seconds} s`);
}
writeFileSync(join(outDir, `${name}.result.json`), JSON.stringify(result, null, 2));
// keep the folder tidy: assets/palette are build intermediates
for (const f of readdirSync(outDir)) if (f.endsWith(".palette.png") || f.endsWith(".master.mkv") && !env.REC_KEEP_MASTER || (f.endsWith(".filter.txt") && !env.REC_KEEP_ASSETS)) rmSync(join(outDir, f));
if (existsSync(join(outDir, `${name}.assets`)) && !env.REC_KEEP_ASSETS) rmSync(join(outDir, `${name}.assets`), { recursive: true, force: true });
