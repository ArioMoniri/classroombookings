#!/usr/bin/env node
// SmartSched launch video renderer: lossless takes (record.mjs --engine frames) + the story (story.mjs) → a lossless
// 60 fps master, rendered offline frame by frame in headless Chromium (compositor.html), never from screen video.
//
//   node scripts/record/launch/render.mjs --takes DIR --out FILE.mkv [--format landscape|vertical]
//        [--fps 60] [--from SEC] [--to SEC] [--workers 2] [--still SEC=FILE.png ...] [--plan]
//
// Why offline: the camera, cursor, ripples, captions and the Lottie intro/outro are computed for each output frame
// from the logged timeline, so motion is exactly 60 fps, and a busy host only makes the render slower, never the
// video choppier. The page underneath is the take's own PNG frames (1.5x device pixels on desktop, 2x on the phone),
// shown through a spring camera with sub-pixel transforms. A deterministic take (record.mjs --engine frames,
// lib/frameclock.mjs) has a frame for every 1/60 s of page time: scene starts and the take's kept spans are put on
// that grid, so output frame n shows take tick n of its span, one to one, never a repeat.
//
// Output: FILE.mkv (H.264 RGB lossless, -qp 0) + FILE.plan.json (scene list with output times, captions: the
// subtitle track and the README loop window are cut from it by launch.sh). Licence: same as the repository.
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { existsSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { cameraTrack, pointerAt, shots } from "../lib/camera.mjs";
import { deterministicArgs, openControlledPage } from "../lib/frameclock.mjs";
import { buildStory, BRAND } from "./story.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "../../..");
const env = process.env;
const { values: args } = parseArgs({
  options: {
    takes: { type: "string" }, // a folder of takes, or several joined with ':'

    out: { type: "string" },
    format: { type: "string", default: "landscape" },
    fps: { type: "string", default: "60" },
    from: { type: "string" },
    to: { type: "string" },
    workers: { type: "string", default: env.LAUNCH_WORKERS ?? "2" },
    still: { type: "string", multiple: true },
    plan: { type: "boolean", default: false },
    theme: { type: "string", default: "light" },
    scenes: { type: "string" }, // comma-separated scene ids: render only these (previews)
    story: { type: "string", default: "launch" }, // launch | clip (one take, for the README feature clips) | hero (README loop)
    take: { type: "string" }, // clip: the take name (e.g. find-room-light)
    steps: { type: "string" }, // clip: "first-last" step indexes (default: all)
    title: { type: "string" }, // clip: chapter chip label
    clip: { type: "string" }, // clip: the steps whose `clip` id is this (instead of --steps)
  },
});
const FPS = Number(args.fps);
const FMT = args.format;
const log = (...m) => console.log(`[launch ${FMT}]`, ...m);
if (!env.PLAYWRIGHT_BROWSERS_PATH && existsSync("/opt/pw-browsers")) env.PLAYWRIGHT_BROWSERS_PATH = "/opt/pw-browsers";
const require = createRequire(join(REPO, "smartsched/frontend/package.json"));
const { chromium } = require("playwright");
const lottiePath = require.resolve("lottie-web/build/player/lottie_svg.min.js");

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const ease = (u) => (u <= 0 ? 0 : u >= 1 ? 1 : u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
const easeOut = (u) => 1 - Math.pow(1 - clamp(u, 0, 1), 3);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// ---- takes ---------------------------------------------------------------------------------------------------
const FRAME = 1000 / 60;
const onGrid = (ms) => Math.round(ms / FRAME) * FRAME;
const takeCache = new Map();
function loadTake(dir, name) {
  if (takeCache.has(name)) return takeCache.get(name);
  // --takes may list several folders (DIR:DIR, the hero cut uses the launch takes and the clip takes)
  const file = dir.split(":").map((d) => join(d, `${name}.take.json`)).find((f) => existsSync(f)) ?? join(dir.split(":")[0], `${name}.take.json`);
  if (!existsSync(file)) throw new Error(`missing take ${file}: run launch.sh record (or record.mjs --engine frames)`);
  dir = dirname(file);
  const t = JSON.parse(readFileSync(file, "utf8"));
  t.dir = join(dir, t.framesDir);
  t.ft = Float64Array.from(t.frames.map((f) => f.t));
  t.grid = t.capture?.mode === "deterministic" && FPS === 60;
  takeCache.set(name, t);
  return t;
}
function frameAt(take, recT) {
  const ft = take.ft;
  let lo = 0;
  let hi = ft.length - 1;
  if (recT <= ft[0]) return take.frames[0];
  if (recT >= ft[hi]) return take.frames[hi];
  while (hi - lo > 1) {
    const m = (lo + hi) >> 1;
    if (ft[m] <= recT) lo = m;
    else hi = m;
  }
  return take.frames[lo];
}
const srcOf = (take, f) => pathToFileURL(join(take.dir, f.file)).href;

/** Kept spans of a take between two steps, with the off-camera cuts (Recorder.cut) removed; local ms ↔ recorder ms. */
function segment(take, sel) {
  const tl = take.timeline;
  const steps = tl.steps;
  const [a, b] = sel.steps ?? [0, steps.length - 1];
  const start = Math.max(tl.marks.begin, steps[a].startMs - (sel.leadMs ?? 350));
  const end = Math.min(tl.marks.end, steps[b].endMs + (sel.tailMs ?? 0));
  let spans = [[start, end]];
  for (const c of tl.cuts ?? []) {
    spans = spans.flatMap(([s, e]) => (c.end <= s || c.start >= e ? [[s, e]] : [[s, c.start], [c.end, e]].filter(([x, y]) => y - x > 30)));
  }
  // long still stretches the story asks to shorten: [{atStep, keepMs}] trims the end of that step's hold
  for (const tr of sel.trim ?? []) {
    const st = steps[tr.step];
    const cutFrom = st.startMs + tr.keepMs;
    if (cutFrom < st.endMs) spans = spans.flatMap(([s, e]) => (st.endMs <= s || cutFrom >= e ? [[s, e]] : [[s, cutFrom], [st.endMs, e]].filter(([x, y]) => y - x > 30)));
  }
  // still stretches (no new frame, no pointer event, no step start) longer than maxIdleMs are shortened to it: waits
  // for the server and slow page operations on a loaded host otherwise read as dead air
  const maxIdle = sel.maxIdleMs ?? Number(env.LAUNCH_MAX_IDLE_MS ?? 2000);
  if (maxIdle > 0) {
    const ev = [...take.frames.map((f) => f.t), ...tl.pointer.map((q) => q.t), ...steps.map((x) => x.startMs), ...steps.flatMap((x) => (x.targets ?? []).map((g) => g.t)), ...(tl.keys ?? []).map((k) => k.t), ...(tl.keys ?? []).map((k) => k.t + (k.ms ?? 0))]
      .filter((x) => x >= start && x <= end).sort((x, y) => x - y);
    ev.unshift(start);
    ev.push(end);
    for (let i = 0; i < ev.length - 1; i++) {
      const [ga, gb] = [ev[i] + maxIdle, ev[i + 1] - 120];
      if (gb - ga > 200) spans = spans.flatMap(([s, e]) => (gb <= s || ga >= e ? [[s, e]] : [[s, ga], [gb, e]].filter(([x, y]) => y - x > 30)));
    }
  }
  // deterministic takes: whole ticks only, so a span plays tick after tick
  if (take.grid) spans = spans.map(([s, e]) => [onGrid(s), onGrid(e)]).filter(([s, e]) => e - s >= FRAME);
  const offs = [];
  let acc = 0;
  for (const [s, e] of spans) {
    offs.push({ s, e, l0: acc });
    acc += e - s;
  }
  const toRec = (l) => {
    for (const o of offs) if (l < o.l0 + (o.e - o.s)) return o.s + Math.max(0, l - o.l0);
    const o = offs[offs.length - 1];
    return o.e;
  };
  const toLocal = (r) => {
    for (const o of offs) if (r >= o.s && r <= o.e) return o.l0 + (r - o.s);
    return null;
  };
  return { durMs: acc, toRec, toLocal, steps: steps.slice(a, b + 1).map((s, i) => ({ ...s, index: a + i })) };
}

/** Spring camera on the segment clock (lib/camera.mjs, the same maths as the README clips, at 60 fps). */
function camera(take, seg, opts) {
  const vp = take.viewport;
  const steps = seg.steps.map((s) => ({
    ...s,
    startMs: seg.toLocal(Math.max(s.startMs, seg.toRec(0))) ?? 0,
    endMs: seg.toLocal(Math.min(s.endMs, seg.toRec(seg.durMs))) ?? seg.durMs,
    targets: (s.targets ?? []).map((t) => ({ ...t, t: seg.toLocal(t.t) })).filter((t) => t.t != null),
  }));
  const sh = opts.zoom === false ? [] : shots(steps, vp, opts);
  return cameraTrack(sh, vp, seg.durMs, { fps: FPS, ...opts });
}

// ---- story → scenes on the output clock ----------------------------------------------------------------------
if (args.clip && !args.steps) {
  const t = loadTake(args.takes, args.take);
  const idx = t.timeline.steps.map((s, i) => (s.clip === args.clip ? i : -1)).filter((i) => i >= 0);
  if (!idx.length) throw new Error(`take ${args.take} has no steps with clip "${args.clip}"`);
  args.steps = `${idx[0]}-${idx[idx.length - 1]}`;
}
const story = buildStory({ format: FMT, theme: args.theme, story: args.story, take: args.take, steps: args.steps?.split("-").map(Number), title: args.title });
const [W, H] = story.size;
const XF = story.crossfadeMs ?? 500;
let tCursor = 0;
const scenes = [];
const only = args.scenes ? new Set(args.scenes.split(",")) : null;
for (const sc of story.scenes.filter((x) => !only || only.has(x.id))) {
  const s = { ...sc };
  if (s.kind === "take") {
    s.parts = (s.views ?? [{ take: s.take, steps: s.steps, trim: s.trim, role: "main" }]).map((v) => {
      const take = loadTake(args.takes, v.take);
      if (v.clip && !v.steps) {
        const idx = take.timeline.steps.map((x, i) => (x.clip === v.clip ? i : -1)).filter((i) => i >= 0);
        if (!idx.length) throw new Error(`take ${v.take} has no steps with clip "${v.clip}"`);
        v = { ...v, steps: [idx[0], idx[idx.length - 1]] };
      }
      const seg = segment(take, v);
      if (v.maxMs && seg.durMs > v.maxMs) seg.durMs = v.maxMs; // a cut that must stay short (the README hero) ends early
      const cam = camera(take, seg, { ...(story.camera?.[take.journey.device] ?? {}), ...(v.camera ?? {}) });
      return { ...v, take, seg, cam };
    });
    s.durMs = Math.max(...s.parts.map((p) => p.seg.durMs / (p.speed ?? 1))) + (s.extraMs ?? 0);
  }
  s.start = onGrid(tCursor);
  s.durMs = onGrid(s.durMs);
  s.end = s.start + s.durMs;
  scenes.push(s);
  tCursor = s.end - (s.overlapNext === false ? 0 : XF);
}
const totalMs = scenes[scenes.length - 1].end;
log(`story: ${scenes.length} scenes, ${(totalMs / 1000).toFixed(1)} s at ${FPS} fps (${W}x${H})`);
const plan = {
  format: FMT, W, H, fps: FPS, durationMs: totalMs,
  scenes: scenes.map((s) => ({ id: s.id, kind: s.kind, start: s.start, end: s.end, chapter: s.chapter ?? null, takes: s.parts?.map((p) => p.take.journey.id + (p.take.journey.device === "phone" ? "-phone" : "")) })),
  captions: [],
};

// ---- per-frame state -----------------------------------------------------------------------------------------
function sceneAlpha(s, t) {
  const fin = s.index === 0 ? 1 : clamp((t - s.start) / XF, 0, 1);
  const fout = s.overlapNext === false || s.index === scenes.length - 1 ? 1 : clamp((s.end - t) / XF, 0, 1);
  return { fin: ease(fin), fout: ease(fout) };
}
scenes.forEach((s, i) => (s.index = i));

function viewState(p, local, box, kind) {
  const take = p.take;
  const lt = clamp(local * (p.speed ?? 1), 0, p.seg.durMs);
  // on the grid, sample half a tick late: the frame painted at tick k is shown for [k, k+1), robust to float error
  const recT = take.grid ? onGrid(p.seg.toRec(lt)) + FRAME / 2 : p.seg.toRec(lt);
  const f = frameAt(take, recT);
  const ci = clamp(Math.round((lt / 1000) * FPS), 0, p.cam.length - 1);
  let cam = p.cam[ci];
  const vp = take.viewport;
  // the box may be taller/wider than 16:10 views: fit the camera rectangle to the box aspect inside the viewport
  const aspect = box.w / box.h;
  let cw = cam.w;
  let ch = cam.w / aspect;
  if (ch > vp.height) {
    ch = vp.height / (cam.z || 1);
    cw = ch * aspect;
  }
  const cx = clamp(cam.cx, cw / 2, vp.width - cw / 2);
  const cy = clamp(cam.cy, ch / 2, vp.height - ch / 2);
  const camR = { x: cx - cw / 2, y: cy - ch / 2, w: cw, h: ch };
  const L = { kind, box, src: srcOf(take, f), srcW: vp.width, srcH: vp.height, cam: camR };
  const ptr = take.timeline.pointer;
  if (take.journey.device === "phone") {
    L.taps = ptr.filter((q) => q.type === "click" && recT >= q.t - 60 && recT - q.t < 520).map((q) => ({ x: q.x, y: q.y, age: clamp((recT - q.t + 60) / 580, 0, 1) }));
  } else {
    const c = pointerAt(ptr, recT, { x: vp.width * 0.62, y: vp.height * 0.72 });
    const pressed = ptr.some((q) => q.type === "down" && recT >= q.t && recT - q.t < 140);
    L.cursor = { x: c.x, y: c.y, pressed };
    L.cursorScale = 1.15;
    L.ripples = ptr.filter((q) => q.type === "click" && recT >= q.t && recT - q.t < 650).map((q) => ({ x: q.x, y: q.y, age: (recT - q.t) / 650 }));
  }
  // next distinct frames for the preloader
  const nexts = [];
  for (const dt of [40, 120, 300]) {
    const g = frameAt(take, p.seg.toRec(clamp(lt + dt, 0, p.seg.durMs)));
    if (g !== f) nexts.push(srcOf(take, g));
  }
  return { L, recT, lt, nexts };
}

function captionFor(s, p, recT) {
  const st = p.seg.steps.find((x) => recT >= x.startMs - 150 && recT <= x.endMs);
  if (!st) return null;
  const text = s.captions?.[st.index] ?? st.caption;
  if (!text) return null;
  const a = clamp((recT - st.startMs + 150) / 220, 0, 1) * clamp((st.endMs - recT) / 220, 0, 1);
  return { text, a: ease(a), key: `${p.take.journey.id}:${st.index}` };
}

function keysFor(p, recT) {
  for (const k of p.take.timeline.keys ?? []) {
    const len = k.text ? k.text.length : 0;
    const dur = (k.ms ?? 0) + 1300;
    if (recT >= k.t && recT < k.t + dur) {
      const a = clamp((recT - k.t) / 160, 0, 1) * clamp((k.t + dur - recT) / 260, 0, 1);
      if (k.text) {
        const n = clamp(Math.ceil(((recT - k.t) / Math.max(1, k.ms ?? 1)) * len), 0, len);
        return { html: `<span class="kbd" style="padding:6px 12px;font-size:22px">⌨</span><span class="kbd" style="padding:6px 14px;font-size:22px">${esc(k.text.slice(0, n)) || "&nbsp;"}</span>`, a };
      }
      const label = { Enter: "↵ Enter", Escape: "Esc", Tab: "⇥ Tab" }[k.key] ?? k.key;
      return { html: `<span class="kbd" style="padding:6px 14px;font-size:22px">${esc(label)}</span>`, a };
    }
  }
  return null;
}

function captionLayer(c, alpha, geo) {
  const fs = geo.capFont;
  return {
    kind: "html", cls: `caption${geo.capWrap ? " wrap" : ""}`, html: esc(c.text),
    style: { top: `${geo.capY}px`, fontSize: `${fs}px`, padding: `${Math.round(fs * 0.55)}px ${Math.round(fs * 1.1)}px`, opacity: String(c.a * alpha),
      ...(geo.capWrap ? { width: `${geo.capW}px`, borderRadius: "28px", lineHeight: "1.25" } : {}) },
  };
}

function chipLayer(s, alpha, geo) {
  if (!s.chapter) return null;
  const fs = geo.chipFont;
  return { kind: "html", cls: "chip", html: `<b style="width:${fs * 1.6}px;height:${fs * 1.6}px;font-size:${fs * 0.85}px">${esc(s.chapter.n)}</b>${esc(s.chapter.label)}`,
    style: { left: `${geo.chipX}px`, top: `${geo.chipY}px`, fontSize: `${fs}px`, padding: `${fs * 0.35}px ${fs * 0.9}px ${fs * 0.35}px ${fs * 0.4}px`, opacity: String(alpha) } };
}

function stateAt(t) {
  const layers = [];
  const preload = [];
  const caps = [];
  for (const s of scenes) {
    if (t < s.start || t > s.end) continue;
    const { fin, fout } = sceneAlpha(s, t);
    const local = t - s.start;
    // a transition is a short overlap, not a long double exposure: the outgoing scene is gone by 65 % of the crossfade
    // and the incoming one starts at 35 %; text (captions, chips, titles) does not overlap at all
    const cardS = (a) => clamp((a - 0.35) / 0.65, 0, 1);
    const textS = (a) => clamp((a - 0.5) / 0.5, 0, 1);
    const alpha = Math.min(cardS(fin), cardS(fout));
    const textAlpha = Math.min(textS(fin), textS(fout));
    // enter: rise + scale from 0.965; exit: fade (the next scene covers it)
    const enterK = 1 - fin;
    const tf = `translateY(${(enterK * 36).toFixed(2)}px) scale(${(1 - enterK * 0.035).toFixed(4)})`;
    for (const L of s.render({ t, local, alpha, textAlpha, fin, fout, tf, W, H, viewState, captionFor, keysFor, captionLayer, chipLayer, esc, ease, easeOut, clamp, caps, preload, BRAND })) layers.push(L);
  }
  return { W, H, layers, preload: [...new Set(preload)].slice(0, 6), caps };
}

for (const s of scenes) if (!s.render) throw new Error(`scene ${s.id} has no render()`);

// captions track (for the WebVTT sidecar): sample every 100 ms
{
  let cur = null;
  for (let t = 0; t <= totalMs; t += 100) {
    const st = stateAt(t);
    const c = st.caps.find((x) => x.a > 0.5);
    const key = c ? c.text : null;
    if (key !== (cur?.text ?? null)) {
      if (cur) plan.captions.push({ ...cur, end: t });
      cur = c ? { text: c.text, start: t } : null;
    }
  }
  if (cur) plan.captions.push({ ...cur, end: totalMs });
}
const planFile = (args.out ?? join(HERE, "launch.mkv")).replace(/\.\w+$/, ".plan.json");
writeFileSync(planFile, JSON.stringify(plan, null, 2));
log(`plan ${planFile}`);
if (args.plan) process.exit(0);

// ---- render ----------------------------------------------------------------------------------------------------
const lottieData = Object.fromEntries(story.lotties.map((n) => [n, JSON.parse(readFileSync(join(REPO, "docs/lottie", `${n}-${args.theme}.json`), "utf8"))]));

// The compositor page paints only when told to (BeginFrame control, lib/frameclock.mjs): draw(state), then one
// HeadlessExperimental.beginFrame that runs every compositor stage before it draws and returns the screenshot. A
// Page.captureScreenshot right after draw() now and then returned the frame before (two renders of the same second
// differed, and the master had repeated frames in the middle of a Lottie); this cannot.
const FRAME_MS = 1000 / FPS;
async function openPage(browser) {
  // one context per worker: each is its own window, so no worker is a throttled background tab
  const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  const page = await openControlledPage(browser, context, { width: W, height: H });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const cdp = await page.context().newCDPSession(page);
  const ctx = { page, cdp, errors, tick: 1e6, last: null };
  await pumping(ctx, (async () => {
    await page.goto(pathToFileURL(join(HERE, "compositor.html")).href);
    await page.addScriptTag({ path: lottiePath });
    for (const [n, d] of Object.entries(lottieData)) await page.evaluate(([n, d]) => window.loadLottie(n, d), [n, d]);
    await page.evaluate(() => document.fonts.ready);
  })());
  return ctx;
}

/** Await `work` while sending frames that draw nothing: a page under BeginFrame control loads, decodes and runs its
 * promises only on frames. */
async function pumping(ctx, work) {
  let done = false;
  const w = work.finally(() => (done = true));
  while (!done) {
    await Promise.race([w.catch(() => undefined), new Promise((ok) => setTimeout(ok, 15))]);
    if (!done) await ctx.cdp.send("HeadlessExperimental.beginFrame", { frameTimeTicks: (ctx.tick += 0.01), interval: FRAME_MS, noDisplayUpdates: true });
  }
  return w;
}

async function shoot(ctx, t) {
  const st = stateAt(t);
  await pumping(ctx, ctx.page.evaluate((s) => window.draw(s), st));
  ctx.tick = Math.max(ctx.tick + 0.01, 1e6 + t);
  const r = await ctx.cdp.send("HeadlessExperimental.beginFrame", { frameTimeTicks: ctx.tick, interval: FRAME_MS, screenshot: { format: "png", optimizeForSpeed: true } });
  // no damage: nothing changed since the last frame, which is then this frame too
  if (r.screenshotData) ctx.last = Buffer.from(r.screenshotData, "base64");
  if (!ctx.last) throw new Error(`no frame at ${t} ms (beginFrame without damage before any frame)`);
  return ctx.last;
}

const LAUNCH_ARGS = ["--allow-file-access-from-files", "--disable-gpu", "--font-render-hinting=none", "--force-color-profile=srgb", "--hide-scrollbars", ...deterministicArgs(1)];
if (args.still?.length) {
  const browser = await chromium.launch({ args: LAUNCH_ARGS });
  const ctx = await openPage(browser);
  for (const spec of args.still) {
    const [sec, file] = spec.split("=");
    writeFileSync(file, await shoot(ctx, Number(sec) * 1000));
    log(`still ${sec}s -> ${file}`);
  }
  await browser.close();
  process.exit(0);
}

// Chunks of CHUNK frames, each its own lossless file (out.cNNNN.mkv): a worker owns a browser and pulls chunks from a
// queue; a finished chunk is never rendered again (a re-run resumes), and a chunk whose browser died (memory pressure
// on a shared host) is retried on a fresh browser.
const out = resolve(args.out);
const CHUNK = Number(env.LAUNCH_CHUNK ?? 600);
const f0 = Math.round((Number(args.from ?? 0) * FPS));
const f1 = Math.min(Math.floor((totalMs / 1000) * FPS), args.to ? Math.round(Number(args.to) * FPS) : Infinity);
const chunks = [];
for (let a = f0, i = 0; a < f1; a += CHUNK, i++) chunks.push({ i, a, b: Math.min(f1, a + CHUNK), file: `${out}.c${String(i).padStart(4, "0")}.mkv`, tries: 0 });
const todo = chunks.filter((c) => !existsSync(c.file));
const nW = Math.max(1, Math.min(Number(args.workers), todo.length || 1));
const t0 = performance.now();
const total = todo.reduce((n, c) => n + c.b - c.a, 0);
let done = 0;
log(`${chunks.length} chunks of ${CHUNK} frames, ${chunks.length - todo.length} already rendered, ${nW} workers`);

async function renderChunk(ctx, c) {
  const tmp = `${c.file}.tmp.mkv`;
  const ff = spawn("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "png", "-i", "-",
    "-c:v", "libx264rgb", "-preset", "ultrafast", "-qp", "0", "-pix_fmt", "rgb24", tmp], { stdio: ["pipe", "inherit", "inherit"] });
  const closed = new Promise((ok, fail) => ff.on("close", (code) => (code === 0 ? ok() : fail(new Error(`ffmpeg chunk ${c.i} exited ${code}`)))));
  closed.catch(() => undefined); // a chunk abandoned below kills its ffmpeg: that rejection is expected
  try {
    for (let f = c.a; f < c.b; f++) {
      const png = await shoot(ctx, (f / FPS) * 1000);
      if (!ff.stdin.write(png)) await new Promise((r) => ff.stdin.once("drain", r));
      done++;
      if (done % (FPS * 5) === 0) {
        const el = (performance.now() - t0) / 1000;
        log(`${done}/${total} frames, ${(done / el).toFixed(1)} fps, eta ${(((total - done) / done) * el / 60).toFixed(1)} min`);
      }
    }
  } catch (e) {
    ff.stdin.destroy();
    ff.kill("SIGKILL");
    rmSync(tmp, { force: true });
    throw e;
  }
  ff.stdin.end();
  await closed;
  renameSync(tmp, c.file);
}

async function worker(wi) {
  let browser = null;
  let ctx = null;
  for (;;) {
    const c = todo.shift();
    if (!c) break;
    try {
      if (!browser) {
        browser = await chromium.launch({ args: LAUNCH_ARGS });
        ctx = await openPage(browser);
      }
      await renderChunk(ctx, c);
    } catch (e) {
      c.tries++;
      log(`worker ${wi}: chunk ${c.i} failed (${e.message.split("\n")[0]}), try ${c.tries}/3 on a fresh browser`);
      await browser?.close().catch(() => undefined);
      browser = null;
      if (c.tries >= 3) throw e;
      todo.unshift(c);
    }
  }
  if (ctx?.errors.length) log(`page errors (worker ${wi}): ${ctx.errors.slice(0, 3).join(" | ")}`);
  await browser?.close().catch(() => undefined);
}
await Promise.all(Array.from({ length: nW }, (_, i) => worker(i)));
const list = `${out}.parts.txt`;
writeFileSync(list, chunks.map((c) => `file '${c.file}'`).join("\n"));
await new Promise((ok, fail) => spawn("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", list, "-c", "copy", out], { stdio: "inherit" })
  .on("close", (c) => (c === 0 ? ok() : fail(new Error("concat failed")))));
if (!env.LAUNCH_KEEP_CHUNKS) for (const c of chunks) rmSync(c.file, { force: true });
rmSync(list, { force: true });
log(`master ${out}: ${f1 - f0} frames in ${((performance.now() - t0) / 60000).toFixed(1)} min`);
