/**
 * Motion audit (.claude/skills/motion_designer/references/audit.md) for the dashboard, the run report, the helper
 * (sheet, Göster ring; motion.md §3.21) and the welcome guide (WG-09: sheet open, tour steps, no scrim flash).
 * Runs against the REAL backend (E2E_REAL=1, see playwright.config.ts):
 *   E2E_REAL=1 PW_PORT=3600 npx playwright test e2e/motion-audit.spec.ts
 * Env: AUDIT_EMAIL / AUDIT_PASSWORD (default the seeded admin), AUDIT_RUN (a finished run id; e2e/global-setup.ts
 * sets it to the full-term solver run), MOTION_CPU (1 in CI; 4 for the device check), MOTION_STRICT.
 *
 * Always enforced: the 300 ms ceiling for finite animations, reduced motion and reduced transparency.
 * Frame budgets (dropped frames, worst long frame) are measured and logged on every run but enforced only with
 * MOTION_STRICT=1 (a dedicated device check): on a shared CI container even the no-op baseline click shows
 * 100–200 ms frames, so they would measure the machine, not the UI (same policy as e2e/calendar.spec.ts).
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { ADMIN_PASSWORD, login as signIn } from "./helpers";
import { pinLanguage } from "./language";
import { DESKTOP, PHONE, adminApi, makeAcademician, signIn as signInAs, unlink, type Api } from "./wg-helpers";

test.skip(process.env.E2E_REAL !== "1", "motion audit runs against the real backend: set E2E_REAL=1 (see playwright.config.ts)");
// the assertions read Turkish (the product default): pin it, whatever the previous spec left behind
pinLanguage("tr");

const EMAIL = process.env.AUDIT_EMAIL ?? "admin@smartsched.local";
// HB18-F15: no password literal here: AUDIT_PASSWORD, else the shared seed default of e2e/helpers.ts (E2E_ADMIN_PASSWORD)
const PASSWORD = process.env.AUDIT_PASSWORD ?? ADMIN_PASSWORD;
const STRICT = process.env.MOTION_STRICT === "1";
const RUN = process.env.AUDIT_RUN ?? process.env.E2E_SOLVER_RUN ?? "1";

type FrameReport = { frames: number; dropped: number; p95: number; longFrames: number; worstLongFrame: number };

const login = (page: Page) => signIn(page, EMAIL, PASSWORD);

async function startFrameProbe(page: Page): Promise<void> {
  await page.evaluate(() => {
    type Probe = { deltas: number[]; loaf: number[]; stop: boolean; po?: PerformanceObserver };
    const w = window as unknown as { __mf?: Probe };
    if (w.__mf) w.__mf.stop = true;
    const st: Probe = { deltas: [], loaf: [], stop: false };
    w.__mf = st;
    let last = performance.now();
    const tick = (t: number) => {
      st.deltas.push(t - last);
      last = t;
      if (!st.stop) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    if (PerformanceObserver.supportedEntryTypes.includes("long-animation-frame")) {
      st.po = new PerformanceObserver((list) => {
        for (const e of list.getEntries()) st.loaf.push(e.duration);
      });
      st.po.observe({ type: "long-animation-frame" });
    }
  });
}

async function stopFrameProbe(page: Page): Promise<FrameReport> {
  return page.evaluate(() => {
    const w = window as unknown as { __mf: { deltas: number[]; loaf: number[]; stop: boolean; po?: PerformanceObserver } };
    w.__mf.stop = true;
    w.__mf.po?.disconnect();
    const d = w.__mf.deltas.slice(1);
    const sorted = [...d].sort((a, b) => a - b);
    const budget = sorted[Math.floor(sorted.length / 2)] ?? 1000 / 60;
    const dropped = d.reduce((n, x) => n + Math.max(0, Math.round(x / budget) - 1), 0);
    return { frames: d.length, dropped, p95: sorted[Math.floor(sorted.length * 0.95)] ?? 0, longFrames: w.__mf.loaf.filter((x) => x > 50).length, worstLongFrame: Math.max(0, ...w.__mf.loaf) };
  });
}

/** Every finite CSS/WAAPI animation must be ≤ 300 ms (loops such as spinners are exempt). */
async function animationsOverCeiling(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    document
      .getAnimations()
      .map((a) => ({ a, t: a.effect?.getComputedTiming() }))
      .filter(({ t }) => t && t.iterations !== Infinity && Number(t.duration) + Number(t.delay ?? 0) > 300)
      .map(({ a, t }) => `${(a as CSSAnimation).animationName ?? a.id ?? "anim"} ${String(t?.duration)}ms`),
  );
}

async function traceLayouts(browser: Browser, page: Page, name: string, run: () => Promise<void>): Promise<number> {
  // tracing itself adds main-thread work; AUDIT_TRACE=0 measures frames without it (layout count = -1)
  if (process.env.AUDIT_TRACE === "0") {
    await run();
    return -1;
  }
  await browser.startTracing(page, { path: `test-results/motion-trace-${name}.json`, screenshots: false, categories: ["devtools.timeline"] });
  await run();
  const buf = await browser.stopTracing();
  const json = JSON.parse(buf.toString()) as { traceEvents?: { name: string }[] } | { name: string }[];
  const events = Array.isArray(json) ? json : (json.traceEvents ?? []);
  return events.filter((e) => e.name === "Layout").length;
}

async function throttle(page: Page) {
  const rate = Number(process.env.MOTION_CPU ?? 1);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate });
  return rate;
}

const results: Record<string, unknown>[] = [];
test.afterAll(() => {
  console.log("MOTION AUDIT", JSON.stringify(results, null, 1));
});

test.describe("motion audit: dashboard", () => {
  test("palette, week change and heatmap segmented hold the budget", async ({ page, browser }) => {
    await login(page);
    await page.goto("/dashboard");
    await page.getByTestId("dashboard-hero").waitFor();
    await page.waitForTimeout(800);
    const rate = await throttle(page);

    const measure = async (name: string, interactions: number, run: () => Promise<void>) => {
      await startFrameProbe(page);
      let over: string[] = [];
      const layouts = await traceLayouts(browser, page, name, async () => {
        await run();
        over = await animationsOverCeiling(page);
        await page.waitForTimeout(450);
      });
      const report = await stopFrameProbe(page);
      results.push({ surface: "dashboard", name, ...report, layouts, over });
      expect.soft(over).toEqual([]);
      if (STRICT) {
        expect.soft(report.dropped).toBeLessThanOrEqual(3 * interactions);
        expect.soft(report.worstLongFrame).toBeLessThanOrEqual(rate > 1 ? 150 : 100);
      }
    };

    // calibration: the cost of an input that animates nothing (machine load, software raster)
    await measure("no-op click (baseline)", 1, async () => {
      await page.mouse.click(5, 880);
    });
    await measure("palette open + 2 moves", 3, async () => {
      await page.keyboard.press("ControlOrMeta+k");
      await page.getByRole("dialog").waitFor();
      await page.waitForTimeout(150);
      await page.keyboard.press("ArrowDown");
      await page.keyboard.press("ArrowDown");
    });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);

    await measure("week change (tickers)", 1, async () => {
      await page.getByRole("button", { name: /Önceki hafta|Previous week/ }).click();
      await page.waitForTimeout(600);
    });

    await measure("heatmap segmented ×2", 2, async () => {
      const seg = page.getByRole("tablist", { name: /Yoğun saatler|Busy hours|heatmap/i });
      await seg.getByRole("tab").nth(1).click();
      await page.waitForTimeout(150);
      await seg.getByRole("tab").nth(0).click();
    });
  });
});

test.describe("motion audit: run report", () => {
  test("tabs, more fixes and an issue group hold the budget", async ({ page, browser }) => {
    await login(page);
    await page.goto(`/runs/${RUN}`);
    await page.getByTestId("run-hero").waitFor();
    await page.waitForTimeout(800);
    // revisit: the ring is static (no draw on every visit)
    expect(await animationsOverCeiling(page)).toEqual([]);
    const rate = await throttle(page);
    const measure = async (name: string, interactions: number, run: () => Promise<void>) => {
      await startFrameProbe(page);
      let over: string[] = [];
      const layouts = await traceLayouts(browser, page, `run-${name.replace(/\W+/g, "-")}`, async () => {
        await run();
        over = await animationsOverCeiling(page);
        await page.waitForTimeout(450);
      });
      const report = await stopFrameProbe(page);
      results.push({ surface: "run report", name, ...report, layouts, over });
      expect.soft(over).toEqual([]);
      if (STRICT) {
        expect.soft(report.dropped).toBeLessThanOrEqual(3 * interactions);
        expect.soft(report.worstLongFrame).toBeLessThanOrEqual(rate > 1 ? 150 : 100);
      }
    };
    await measure("no-op click (baseline)", 1, async () => {
      await page.mouse.click(5, 880);
    });
    await measure("tab thumb ×2", 2, async () => {
      await page.getByTestId("tab-grid").click();
      await page.waitForTimeout(150);
      await page.getByTestId("tab-report").click();
    });
    await measure("issue group expand", 1, async () => {
      await page.locator("[data-testid^=issue-group-] button[aria-expanded]").first().click();
    });
  });
});

test.describe("motion audit: helper", () => {
  // HX-11 / motion.md §3.21: the helper sheet (desktop x 24 → 0 on springs.sheet, phone y 100 % → 0), the card enter
  // and the "Göster" ring. Works in index mode (no model): the sheet opens with ⌘J, the ring from the palette's
  // "Nerede?" row (Shift+Enter). The thinking shimmer is the only allowed loop.
  test("helper sheet open / close and Göster hold the budget", async ({ page, browser }) => {
    await login(page);
    await page.goto("/reserve");
    await page.locator('[data-tour="reserve-when"]').waitFor();
    await page.waitForTimeout(800);
    const rate = await throttle(page);
    const measure = async (name: string, interactions: number, run: () => Promise<void>) => {
      await startFrameProbe(page);
      let over: string[] = [];
      const layouts = await traceLayouts(browser, page, `helper-${name.replace(/\W+/g, "-")}`, async () => {
        await run();
        over = await animationsOverCeiling(page);
        await page.waitForTimeout(450);
      });
      const report = await stopFrameProbe(page);
      results.push({ surface: "helper", name, ...report, layouts, over });
      expect.soft(over).toEqual([]);
      if (STRICT) {
        expect.soft(report.dropped).toBeLessThanOrEqual(3 * interactions);
        expect.soft(report.worstLongFrame).toBeLessThanOrEqual(rate > 1 ? 150 : 100);
      }
    };
    await measure("no-op click (baseline)", 1, async () => {
      await page.mouse.click(5, 880);
    });
    await measure("sheet open (⌘J)", 1, async () => {
      await page.keyboard.press("ControlOrMeta+j");
      await page.getByTestId("helper-sheet").waitFor();
    });
    // the page stays usable: no scrim, ≤ 3 backdrop-filter surfaces while the sheet is open (blur budget)
    const blurred = await page.evaluate(() => [...document.querySelectorAll("*")].filter((el) => { const b = getComputedStyle(el).backdropFilter; return b && b !== "none"; }).length);
    results.push({ surface: "helper", check: "blur surfaces with the sheet open", blurred });
    expect.soft(blurred).toBeLessThanOrEqual(3);
    await measure("sheet close (Esc)", 1, async () => {
      // HB18-F15: index mode has no composer; Rehber modu's field takes the focus instead
      const composer = page.getByTestId("helper-composer").locator("textarea");
      await ((await composer.count()) ? composer : page.getByTestId("helper-guide-input")).focus();
      await page.keyboard.press("Escape");
      await page.getByTestId("helper-sheet").waitFor({ state: "detached" });
    });
    await measure("Göster: palette › Nerede? › ring", 2, async () => {
      await page.keyboard.press("ControlOrMeta+k");
      await page.getByRole("dialog").waitFor();
      await page.keyboard.type("tatil ekle");
      await page.waitForTimeout(400);
      await page.keyboard.press("Shift+Enter");
      await page.getByTestId("tour-ring").waitFor({ timeout: 5000 });
    });
    await page.keyboard.press("Escape");
  });

  test("reduced motion: the sheet and the ring reach their end state at once", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await login(page);
    await page.goto("/reserve");
    await page.locator('[data-tour="reserve-when"]').waitFor();
    await page.keyboard.press("ControlOrMeta+j");
    await page.getByTestId("helper-sheet").waitFor();
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const moving = await page.evaluate(
      () =>
        document.getAnimations().filter((a) => {
          const t = a.effect?.getComputedTiming();
          if (t && (t.iterations === Infinity || Number(t.duration) <= 1)) return false;
          const kf = (a.effect as KeyframeEffect | null)?.getKeyframes() ?? [];
          return kf.some((k) => "transform" in k || "translate" in k || "scale" in k);
        }).length,
    );
    // motion (framer) writes inline transforms, not WAAPI: the sheet must already sit at its end position
    const transform = await page.getByTestId("helper-sheet").evaluate((el) => getComputedStyle(el).transform);
    results.push({ check: "helper reduced motion", movingAnimations: moving, transform });
    expect(moving).toBe(0);
    expect(transform === "none" || /matrix\(1, 0, 0, 1, 0, 0\)/.test(transform)).toBeTruthy();
  });
});

test.describe("motion audit: helper drag on phones (HX-19)", () => {
  // HX-19 / motion.md §3.21: the phone sheet's 44 px handle drags it 1:1; a release past 30 % or a flick closes it in
  // ≤ 200 ms (dur.fast ease.out) and the focus returns to the opener; a short slow drag springs back (springs.sheet).
  // Reduced motion: the drag still works, the snap-back and the close are instant. Real touch through CDP.
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "tr-TR", timezoneId: "Europe/Istanbul" });

  /** A touch swipe from (x, y0) to (x, y1) in `ms`, in `steps` moves (CDP touch → pointer events of type touch). */
  async function swipe(page: Page, x: number, y0: number, y1: number, ms: number, steps = 8): Promise<number> {
    const cdp = await page.context().newCDPSession(page);
    const at = (y: number) => [{ x, y, id: 1 }];
    await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: at(y0) });
    for (let i = 1; i <= steps; i++) {
      await page.waitForTimeout(ms / steps);
      await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: at(y0 + ((y1 - y0) * i) / steps) });
    }
    const released = await page.evaluate(() => performance.now());
    await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    return released;
  }

  /** Opens the sheet from a marked page button (the opener the focus must come back to); returns the handle box. */
  async function openFromButton(page: Page) {
    await page.goto("/reserve");
    await page.locator('[data-tour="reserve-when"]').waitFor();
    await page.waitForTimeout(600);
    await page.locator("main button:visible").first().evaluate((el) => {
      el.setAttribute("data-hx19-opener", "");
      (el as HTMLElement).focus();
    });
    await page.keyboard.press("ControlOrMeta+j");
    await page.getByTestId("helper-sheet").waitFor();
    await page.waitForTimeout(400); // enter settled (springs.sheet ≈ 270 ms)
    const handle = page.getByTestId("helper-handle");
    await expect(handle).toHaveAccessibleName(/Kapat \(aşağı sürükleyin\)|Close \(drag down\)/);
    const box = (await handle.boundingBox())!;
    expect(box.height).toBeGreaterThanOrEqual(44);
    expect(box.width).toBeGreaterThanOrEqual(44);
    expect(await handle.getAttribute("tabindex")).toBe("-1");
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  }

  /** ms from `released` until the sheet leaves the DOM. */
  async function detachedAfter(page: Page, released: number): Promise<number> {
    await page.getByTestId("helper-sheet").waitFor({ state: "detached", timeout: 2000 });
    return (await page.evaluate(() => performance.now())) - released;
  }

  const focusOnOpener = (page: Page) => page.evaluate(() => document.activeElement?.hasAttribute("data-hx19-opener") ?? false);
  const sheetTransform = (page: Page) => page.getByTestId("helper-sheet").evaluate((el) => getComputedStyle(el).transform);
  const identity = (t: string) => t === "none" || /matrix\(1, 0, 0, 1, 0, 0\)/.test(t);

  for (const reduced of [false, true]) {
    const label = reduced ? "reduced motion" : "full motion";

    test(`${label}: drag past 30 % closes, focus returns to the opener`, async ({ page, browser }) => {
      if (reduced) await page.emulateMedia({ reducedMotion: "reduce" });
      await login(page);
      const h = await openFromButton(page);
      await throttle(page);
      await startFrameProbe(page);
      let ms = 0;
      let over: string[] = [];
      const layouts = await traceLayouts(browser, page, `helper-drag-${reduced ? "rm" : "full"}`, async () => {
        const released = await swipe(page, h.x, h.y, h.y + 844 * 0.45, 300);
        over = await animationsOverCeiling(page);
        ms = await detachedAfter(page, released);
      });
      const report = await stopFrameProbe(page);
      results.push({ surface: "helper", name: `phone drag dismiss (${label})`, ...report, layouts, over, exitMs: Math.round(ms) });
      expect.soft(over).toEqual([]);
      // the exit is ≤ 200 ms (120 ms token) plus AnimatePresence's removal frame; reduced motion is instant
      expect.soft(ms).toBeLessThanOrEqual(reduced ? 80 : 260);
      await expect.poll(() => focusOnOpener(page)).toBe(true);
      if (STRICT) expect.soft(report.dropped).toBeLessThanOrEqual(3);
    });

    test(`${label}: a short slow drag springs back, a flick closes`, async ({ page }) => {
      if (reduced) await page.emulateMedia({ reducedMotion: "reduce" });
      await login(page);
      const h = await openFromButton(page);
      // 120 px over 800 ms ends still: under 30 % and no flick → it stays and returns to y 0
      await swipe(page, h.x, h.y, h.y + 120, 800, 10);
      await page.waitForTimeout(80);
      await expect(page.getByTestId("helper-sheet")).toBeVisible();
      if (reduced) expect(identity(await sheetTransform(page))).toBeTruthy(); // back on the next frame
      await expect.poll(async () => identity(await sheetTransform(page)), { timeout: 600 }).toBe(true); // springs.sheet settles ≈ 270 ms
      // the trailing click of a drag must not count as a tap
      await page.waitForTimeout(150);
      await expect(page.getByTestId("helper-sheet")).toBeVisible();
      // 90 px in 50 ms is a flick: it closes although it is under 30 %
      const released = await swipe(page, h.x, h.y, h.y + 90, 50, 3);
      const ms = await detachedAfter(page, released);
      results.push({ surface: "helper", name: `phone flick dismiss (${label})`, exitMs: Math.round(ms) });
      expect.soft(ms).toBeLessThanOrEqual(reduced ? 80 : 260);
      await expect.poll(() => focusOnOpener(page)).toBe(true);
    });
  }

  test("keyboard and screen reader keep ✕ and Esc; the ✕ exit is ≤ 200 ms and faster than the enter", async ({ page }) => {
    await login(page);
    await openFromButton(page);
    await expect(page.getByTestId("helper-close")).toHaveAccessibleName("Kapat");
    const released = await page.evaluate(() => performance.now());
    await page.keyboard.press("Escape");
    const ms = await detachedAfter(page, released);
    results.push({ surface: "helper", name: "phone Esc exit", exitMs: Math.round(ms) });
    expect.soft(ms).toBeLessThanOrEqual(260); // dur.base 180 ms + the removal frame
    await expect.poll(() => focusOnOpener(page)).toBe(true);
  });
});

test.describe("motion audit: preferences", () => {
  test("reduced motion: end state at once, no transform animations", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await login(page);
    await page.goto("/dashboard");
    await page.getByTestId("dashboard-hero").waitFor();
    await page.getByRole("button", { name: /Önceki hafta|Previous week/ }).click();
    await page.keyboard.press("ControlOrMeta+k");
    await page.getByRole("dialog").waitFor();
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const moving = await page.evaluate(
      () =>
        document.getAnimations().filter((a) => {
          const t = a.effect?.getComputedTiming();
          if (t && (t.iterations === Infinity || Number(t.duration) <= 1)) return false;
          const kf = (a.effect as KeyframeEffect | null)?.getKeyframes() ?? [];
          return kf.some((k) => "transform" in k || "translate" in k || "scale" in k);
        }).length,
    );
    results.push({ check: "reduced motion", movingAnimations: moving });
    expect(moving).toBe(0);
  });

  test("reduced transparency: glass becomes opaque", async ({ page }) => {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-transparency", value: "reduce" }] });
    await login(page);
    for (const [path, id] of [["/dashboard", "dashboard-hero"], [`/runs/${RUN}`, "run-hero"]] as const) {
      await page.goto(path);
      const hero = page.getByTestId(id);
      await hero.waitFor();
      const style = await hero.evaluate((el) => ({ backdrop: getComputedStyle(el).backdropFilter }));
      results.push({ check: "reduced transparency", path, ...style });
      expect(style.backdrop === "none" || style.backdrop === "").toBeTruthy();
    }
  });
});

test.describe("motion audit: welcome", () => {
  // WG-09 (welcome-guide.md §8): the first sign-in sheet settles in ≤ 240 ms (ceiling 300 enforced like every block),
  // the tour's scrim never flashes off between steps, a cross-route step included (WG10-F07: the runner keeps a hold
  // scrim until the next step's overlay is drawn), ≤ 3 dropped frames per interaction (MOTION_STRICT only, WG10-F08:
  // re-measure on a GPU runner) and reduced motion moves nothing. A fresh academician per test: the sheet is real.
  test.describe.configure({ mode: "serial", timeout: 180_000 });
  let api: Api;
  const linked: { id: number; instructorId: number | null }[] = [];
  test.beforeAll(async () => {
    api = await adminApi();
  });
  test.afterAll(async () => {
    for (const p of linked) await unlink(api, p);
    await api.ctx.dispose();
  });

  /** Per animation frame: is a scrim (Joyride's overlay or the runner's hold scrim) or the step card on screen? */
  async function startScrimProbe(page: Page) {
    await page.evaluate(() => {
      const w = window as unknown as { __scrim?: { gaps: number; frames: number; stop: boolean } };
      const st = { gaps: 0, frames: 0, stop: false };
      w.__scrim = st;
      const tick = () => {
        st.frames++;
        if (!document.querySelector('.react-joyride__overlay, [data-testid="tour-scrim-hold"], [data-testid="tour-card"]')) st.gaps++;
        if (!st.stop) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  }
  const stopScrimProbe = (page: Page) =>
    page.evaluate(() => {
      const w = window as unknown as { __scrim: { gaps: number; frames: number; stop: boolean } };
      w.__scrim.stop = true;
      return { gaps: w.__scrim.gaps, frames: w.__scrim.frames };
    });

  for (const [label, opts] of [
    ["1440", DESKTOP],
    ["390", PHONE],
  ] as const) {
    test(`${label}: sheet open, tour steps across routes, no scrim flash`, async ({ browser }) => {
      const ayse = await makeAcademician(api, `wg.motion.${label}`);
      linked.push(ayse);
      const { context, page } = await signInAs(browser, ayse, opts);
      // start away from /reserve so step 2 ("Önce zamanı seçin", /reserve) is a cross-route step
      await page.goto("/my-bookings", { waitUntil: "domcontentloaded" });
      const sheet = page.getByTestId("welcome-sheet");
      await startFrameProbe(page);
      await sheet.waitFor({ timeout: 20_000 });
      const over = await animationsOverCeiling(page);
      await page.waitForTimeout(450);
      const open = await stopFrameProbe(page);
      results.push({ surface: "welcome", name: `sheet open ${label}`, ...open, over });
      expect.soft(over).toEqual([]);
      if (STRICT) expect.soft(open.dropped).toBeLessThanOrEqual(3);

      await page.getByTestId("welcome-start-tour").click();
      const card = page.getByTestId("tour-card");
      await card.waitFor({ timeout: 15_000 });
      await page.waitForTimeout(300);
      const text = (await page.getByTestId("tour-counter").textContent()) ?? "";
      const total = Number(/\/ (\d+)/.exec(text)?.[1] ?? 1);
      for (let step = 1; step < Math.min(total, 4); step++) {
        await startScrimProbe(page);
        await startFrameProbe(page);
        await page.getByTestId("tour-next").click();
        await expect(page.getByTestId("tour-counter")).toContainText(`${step + 1} /`, { timeout: 10_000 });
        await page.waitForTimeout(400);
        const scrim = await stopScrimProbe(page);
        const frames = await stopFrameProbe(page);
        results.push({ surface: "welcome", name: `tour step ${step} → ${step + 1} ${label}`, url: page.url(), ...frames, scrimGaps: scrim.gaps, scrimFrames: scrim.frames });
        expect.soft(scrim.gaps, `frames with neither scrim nor card, step ${step} → ${step + 1}`).toBe(0);
        if (STRICT) expect.soft(frames.dropped).toBeLessThanOrEqual(3);
      }
      await page.keyboard.press("Escape");
      await expect(card).toBeHidden();
      await context.close();
    });
  }

  test("390 reduced motion: the sheet and the tour move nothing", async ({ browser }) => {
    const ayse = await makeAcademician(api, "wg.motion.rm");
    linked.push(ayse);
    const context = await browser.newContext({ ...PHONE, reducedMotion: "reduce" });
    const page = await context.newPage();
    await signIn(page, ayse.username, ayse.password);
    await page.goto("/my-bookings", { waitUntil: "domcontentloaded" });
    await page.getByTestId("welcome-sheet").waitFor({ timeout: 20_000 });
    const moving = () =>
      page.evaluate(
        () =>
          document.getAnimations().filter((a) => {
            const t = a.effect?.getComputedTiming();
            if (!t || t.iterations === Infinity || Number(t.duration) <= 1 || a.playState !== "running") return false;
            const kf = (a.effect as KeyframeEffect | null)?.getKeyframes() ?? [];
            return kf.some((k) => "transform" in k || "translate" in k || "scale" in k);
          }).length,
      );
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const onSheet = await moving();
    await page.getByTestId("welcome-start-tour").click();
    await page.getByTestId("tour-card").waitFor({ timeout: 15_000 });
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const onTour = await moving();
    results.push({ surface: "welcome", check: "reduced motion", onSheet, onTour });
    expect.soft(onSheet).toBe(0);
    expect.soft(onTour).toBe(0);
    await page.keyboard.press("Escape");
    await context.close();
  });
});
