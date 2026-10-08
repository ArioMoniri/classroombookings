// Playwright side of the recording pipeline: drives the page like a person (eased pointer moves,
// visible typing, pauses) and logs everything the post-processing needs into a timeline:
//   steps[]   caption + time span + the bounding box the camera should frame
//   pointer[] {t, x, y, type: move|down|up|click} in CSS pixels of the viewport (= video pixels)
// Times are milliseconds on the recorder clock; record.mjs maps them onto the video clock with a
// sync flash (a magenta frame painted at a logged instant and found again in the video).

export const SYNC_COLOR = "#ff00ff";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const easeInOut = (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);

export class Recorder {
  /** @param {import('playwright').Page} page */
  constructor(page, { speed = 1, viewport, log = () => {} } = {}) {
    this.page = page;
    this.speed = speed; // >1 = slower, more deliberate demo
    this.viewport = viewport;
    this.log = log;
    this.t0 = performance.now();
    this.pointer = [];
    this.steps = [];
    this.marks = {};
    this.current = null;
    this.pos = { x: viewport.width * 0.62, y: viewport.height * 0.72 };
  }

  now() {
    return Math.round(performance.now() - this.t0);
  }

  async wait(ms) {
    await sleep(ms * this.speed);
  }

  /** Paint a full-viewport magenta frame for ~300 ms; returns [start, end] on the recorder clock. */
  async syncFlash() {
    await this.page.evaluate((color) => {
      const d = document.createElement("div");
      d.id = "__rec_sync";
      d.style.cssText = `position:fixed;inset:0;z-index:2147483647;background:${color}`;
      document.documentElement.appendChild(d);
      return new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    }, SYNC_COLOR);
    const start = this.now();
    await sleep(350);
    await this.page.evaluate(() => {
      document.getElementById("__rec_sync")?.remove();
      return new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    });
    const end = this.now();
    this.marks.sync = { start, end };
    return [start, end];
  }

  /** Mark the start of the part of the video that is kept (everything before is trimmed). */
  begin() {
    this.marks.begin = this.now();
  }

  end() {
    this.marks.end = this.now();
  }

  /**
   * A captioned step. `focus` (optional) is a locator whose box the camera frames for the whole step;
   * actions inside the step (click/type/drag) add their own targets, which win while they happen.
   */
  async step(caption, fn, { focus = null, zoom = true, hold = 900, poster = false } = {}) {
    const step = { caption, startMs: this.now(), endMs: 0, targets: [], zoom, poster };
    this.steps.push(step);
    this.current = step;
    this.log(`step: ${caption}`);
    if (focus) await this.frame(focus);
    try {
      await fn(this);
    } finally {
      await this.wait(hold);
      step.endMs = this.now();
      this.current = null;
    }
  }

  async box(target) {
    const loc = typeof target === "string" ? this.page.locator(target) : target;
    await loc.first().waitFor({ state: "visible", timeout: 30_000 });
    await loc.first().scrollIntoViewIfNeeded().catch(() => undefined);
    const b = await loc.first().boundingBox();
    if (!b) throw new Error(`no bounding box for ${target}`);
    return b;
  }

  addTarget(b, kind) {
    if (!this.current) return;
    this.current.targets.push({ t: this.now(), kind, x: b.x, y: b.y, w: b.width, h: b.height });
  }

  /** Frame a region without touching it (e.g. "look at the result card"). */
  async frame(target, { dwell = 600 } = {}) {
    const b = await this.box(target);
    this.addTarget(b, "frame");
    await this.wait(dwell);
    return b;
  }

  /** Eased pointer move, logged at ~60 Hz. */
  async moveTo(x, y, { duration = 650 } = {}) {
    const from = { ...this.pos };
    const dist = Math.hypot(x - from.x, y - from.y);
    const ms = Math.max(180, Math.min(duration * this.speed, 250 + dist * 0.9));
    const n = Math.max(6, Math.round(ms / 16));
    for (let i = 1; i <= n; i++) {
      const u = easeInOut(i / n);
      const px = from.x + (x - from.x) * u;
      const py = from.y + (y - from.y) * u;
      await this.page.mouse.move(px, py);
      this.pointer.push({ t: this.now(), x: px, y: py, type: "move" });
      await sleep(ms / n);
    }
    this.pos = { x, y };
  }

  async moveOnto(target, { at = [0.5, 0.5] } = {}) {
    const b = await this.box(target);
    const x = b.x + b.width * at[0];
    const y = b.y + b.height * at[1];
    await this.moveTo(x, y);
    return b;
  }

  async click(target, { at, after = 500, kind = "click" } = {}) {
    const b = await this.moveOnto(target, { at });
    this.addTarget(b, kind);
    await this.wait(120);
    await this.page.mouse.down();
    this.pointer.push({ t: this.now(), x: this.pos.x, y: this.pos.y, type: "down" });
    await sleep(70);
    await this.page.mouse.up();
    this.pointer.push({ t: this.now(), x: this.pos.x, y: this.pos.y, type: "click" });
    await this.wait(after);
    return b;
  }

  async type(target, text, { delay = 55, clear = true, after = 400 } = {}) {
    await this.click(target, { after: 150 });
    const loc = typeof target === "string" ? this.page.locator(target) : target;
    if (clear) await loc.first().fill("");
    await this.page.keyboard.type(text, { delay: delay * this.speed });
    await this.wait(after);
  }

  async press(key, { after = 400 } = {}) {
    await this.page.keyboard.press(key);
    await this.wait(after);
  }

  /** Drag with visible pointer travel; `to` is a locator (centre) or {x, y}. */
  async drag(from, to, { after = 700, steps = 40 } = {}) {
    const fb = await this.moveOnto(from);
    let tx, ty, tb;
    if (to && typeof to.x === "number" && typeof to.y === "number" && !to.locator) {
      tx = to.x;
      ty = to.y;
      tb = { x: tx - 40, y: ty - 20, width: 80, height: 40 };
    } else {
      tb = await this.box(to);
      tx = tb.x + tb.width / 2;
      ty = tb.y + tb.height / 2;
    }
    const union = {
      x: Math.min(fb.x, tb.x),
      y: Math.min(fb.y, tb.y),
      width: Math.max(fb.x + fb.width, tb.x + tb.width) - Math.min(fb.x, tb.x),
      height: Math.max(fb.y + fb.height, tb.y + tb.height) - Math.min(fb.y, tb.y),
    };
    this.addTarget(union, "drag");
    await this.page.mouse.down();
    this.pointer.push({ t: this.now(), x: this.pos.x, y: this.pos.y, type: "down" });
    const from0 = { ...this.pos };
    for (let i = 1; i <= steps; i++) {
      const u = easeInOut(i / steps);
      const px = from0.x + (tx - from0.x) * u;
      const py = from0.y + (ty - from0.y) * u;
      await this.page.mouse.move(px, py);
      this.pointer.push({ t: this.now(), x: px, y: py, type: "move" });
      await sleep(22 * this.speed);
    }
    this.pos = { x: tx, y: ty };
    await this.wait(150);
    await this.page.mouse.up();
    this.pointer.push({ t: this.now(), x: tx, y: ty, type: "up" });
    await this.wait(after);
  }

  timeline() {
    return {
      version: 1,
      viewport: this.viewport,
      marks: this.marks,
      steps: this.steps,
      pointer: this.pointer,
    };
  }
}

/** First locator of several candidates that is visible (UI is being redesigned; journeys list
 * the current selector first and the likely redesigned ones after it). */
export async function pick(page, candidates, { timeout = 15_000 } = {}) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    for (const c of candidates) {
      const loc = typeof c === "string" ? page.locator(c) : c;
      if (await loc.first().isVisible().catch(() => false)) return loc.first();
    }
    await sleep(250);
  }
  throw new Error(`none of the candidates became visible: ${candidates.map(String).join(" | ")}`);
}
