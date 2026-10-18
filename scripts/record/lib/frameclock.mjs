// Deterministic capture for the launch video (record.mjs --engine frames): the page runs on Chromium's virtual time
// and paints only when this module sends it a BeginFrame, so every 1/60 s of page time is rendered and captured
// exactly once, however slow the host is. A screencast samples a live page instead and gets whatever Chrome managed
// to paint (on a loaded host 3-30 paints per second), which reads as judder once the take is played at 60 fps.
//
// One tick:  Emulation.setVirtualTimePolicy(pauseIfNetworkFetchesPending, budget 16.67 ms) → wait for
//            virtualTimeBudgetExpired → HeadlessExperimental.beginFrame(frameTime += 16.67 ms, screenshot PNG)
// so timers, Date, performance.now, requestAnimationFrame, CSS transitions/animations and the motion library all see
// the same clock, and a frame is a pure function of page time. Waiting for the server costs no page time (the budget
// pauses while a fetch is pending): a slow answer becomes a cut instead of dead air.
//
// Needs chrome-headless-shell (Playwright's default headless browser) launched with DETERMINISTIC_ARGS and a page
// created with enableBeginFrameControl (openControlledPage). The device scale factor must be a launch flag
// (--force-device-scale-factor): beginFrame screenshots are taken at the window's scale, not the emulated one.
import { createHash } from "node:crypto";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { writeFile } from "node:fs/promises";
import { join } from "node:path";

export const FRAME_MS = 1000 / 60;

export const deterministicArgs = (dsf) => [
  "--deterministic-mode",
  "--enable-begin-frame-control",
  "--run-all-compositor-stages-before-draw",
  "--disable-new-content-rendering-timeout",
  "--disable-threaded-animation",
  "--disable-threaded-scrolling",
  "--disable-checker-imaging",
  "--disable-image-animation-resync",
  `--force-device-scale-factor=${dsf}`,
];

/** A page of `context` whose frames this process drives (Target.createTarget with enableBeginFrameControl). */
export async function openControlledPage(browser, context, viewport) {
  const probe = await context.newPage();
  const pcdp = await context.newCDPSession(probe);
  const { targetInfo } = await pcdp.send("Target.getTargetInfo");
  await pcdp.detach().catch(() => undefined);
  const bcdp = await browser.newBrowserCDPSession();
  const pageP = context.waitForEvent("page");
  await bcdp.send("Target.createTarget", { url: "about:blank", enableBeginFrameControl: true, browserContextId: targetInfo.browserContextId, width: viewport.width, height: viewport.height });
  const page = await pageP;
  await probe.close();
  await bcdp.detach().catch(() => undefined);
  return page;
}

/**
 * The page clock. start() before the first navigation (a controlled page does not paint, and so cannot load, without
 * BeginFrames); now() is page time in ms since start(); sleep(ms) waits for that much page time.
 * capture(dir) / stopCapture() keep a PNG per tick, skipping a frame identical to the one before (its time is kept).
 */
export class FrameClock {
  constructor(page, { log = () => {}, stallMs = 60, advanceAfterMs = 4000 } = {}) {
    this.page = page;
    this.log = log;
    this.stallMs = stallMs;
    this.advanceAfterMs = advanceAfterMs;
    this.ticks = 0;
    this.lastTick = 0;
    this.base = 1e6;
    this.cap = null;
    this.stats = { ticks: 0, pumps: 0, advanced: 0, shotMs: [] };
    this.waiters = [];
    this.running = false;
  }

  now() {
    return this.ticks * FRAME_MS;
  }

  async start() {
    this.cdp = await this.page.context().newCDPSession(this.page);
    await this.cdp.send("Emulation.setVirtualTimePolicy", { policy: "pause" });
    this.running = true;
    this.loop = this.#run().catch((e) => {
      this.error = e;
      this.running = false;
      for (const w of this.waiters.splice(0)) w.fail(e);
    });
  }

  async #budget() {
    const expired = new Promise((ok) => this.cdp.once("Emulation.virtualTimeBudgetExpired", ok));
    await this.cdp.send("Emulation.setVirtualTimePolicy", { policy: "pauseIfNetworkFetchesPending", budget: FRAME_MS });
    const t0 = performance.now();
    for (;;) {
      const done = await Promise.race([expired.then(() => true), new Promise((ok) => setTimeout(() => ok(false), this.stallMs))]);
      if (done) return;
      if (!this.running) return;
      if (performance.now() - t0 > this.advanceAfterMs) {
        // a fetch that never finishes (a stream, a long poll) would hold page time forever: let this tick pass anyway
        this.stats.advanced++;
        const again = new Promise((ok) => this.cdp.once("Emulation.virtualTimeBudgetExpired", ok));
        await this.cdp.send("Emulation.setVirtualTimePolicy", { policy: "advance", budget: FRAME_MS });
        await again;
        return;
      }
      // a response is handed to the page on its next frame: while a fetch is pending, a frame that draws nothing
      // (and moves the frame clock by 10 µs) lets the page take it, so page time can go on
      this.stats.pumps++;
      this.lastTick += 0.01;
      await this.cdp.send("HeadlessExperimental.beginFrame", { frameTimeTicks: this.lastTick, interval: FRAME_MS, noDisplayUpdates: true });
    }
  }

  async #run() {
    while (this.running) {
      await this.#budget();
      this.lastTick = Math.max(this.lastTick + 0.01, this.base + (this.ticks + 1) * FRAME_MS);
      const cap = this.cap;
      const a = performance.now();
      const r = await this.cdp.send("HeadlessExperimental.beginFrame", { frameTimeTicks: this.lastTick, interval: FRAME_MS, ...(cap ? { screenshot: { format: "png", optimizeForSpeed: true } } : {}) });
      this.ticks++;
      this.stats.ticks++;
      if (cap && r.screenshotData) {
        this.stats.shotMs.push(performance.now() - a);
        cap.keep(this.now(), r.screenshotData);
      }
      const t = this.now();
      this.waiters = this.waiters.filter((w) => (t >= w.at ? (w.ok(), false) : true));
    }
  }

  sleep(ms) {
    if (this.error) return Promise.reject(this.error);
    const at = this.now() + Math.max(0, ms);
    return new Promise((ok, fail) => this.waiters.push({ at, ok, fail }));
  }

  /** Keep the frames from now on in `dir` (PNG, lossless). */
  capture(dir) {
    rmSync(dir, { recursive: true, force: true });
    mkdirSync(dir, { recursive: true });
    const frames = [];
    const writes = [];
    let lastHash = null;
    this.cap = {
      dir,
      frames,
      writes,
      keep(t, data) {
        const hash = createHash("sha1").update(data).digest("hex");
        if (hash === lastHash) {
          frames[frames.length - 1].dup = (frames[frames.length - 1].dup ?? 0) + 1;
          return;
        }
        lastHash = hash;
        const file = `f_${String(frames.length).padStart(6, "0")}.png`;
        frames.push({ t: +t.toFixed(3), file });
        writes.push(writeFile(join(dir, file), Buffer.from(data, "base64")));
      },
    };
  }

  /** Stop keeping frames; writes frames.json in the capture folder and returns {dir, frames}. */
  async stopCapture() {
    const cap = this.cap;
    this.cap = null;
    if (!cap) throw new Error("stopCapture without capture");
    await Promise.all(cap.writes);
    if (cap.frames.length < 2) throw new Error(`captured ${cap.frames.length} frames`);
    const shot = [...this.stats.shotMs].sort((a, b) => a - b);
    writeFileSync(join(cap.dir, "frames.json"), JSON.stringify({ clock: "page virtual time ms", fps: 60, frames: cap.frames }));
    return { dir: cap.dir, frames: cap.frames, shotP50: shot[shot.length >> 1] ?? null };
  }

  /** One PNG of the current page (a controlled page cannot use page.screenshot()). */
  async snapshot(file) {
    let data = null;
    const prev = this.cap;
    await new Promise((ok) => {
      this.cap = { keep: (_t, d) => { data = d; ok(); } };
    });
    this.cap = prev;
    if (data) writeFileSync(file, Buffer.from(data, "base64"));
  }

  async stop() {
    this.running = false;
    await this.loop;
  }
}
