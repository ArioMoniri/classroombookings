/**
 * Motion audit (.claude/skills/motion_designer/references/audit.md) for the dashboard and the run report.
 * Runs against the REAL backend (E2E_REAL=1, see playwright.config.ts):
 *   E2E_REAL=1 PW_PORT=3600 npx playwright test e2e/motion-audit.spec.ts
 * Env: AUDIT_EMAIL / AUDIT_PASSWORD (default the seeded admin), AUDIT_RUN (a finished run id; e2e/global-setup.ts
 * sets it to the full-term solver run), MOTION_CPU (1 in CI; 4 for the device check).
 */
import { expect, test, type Browser, type Page } from "@playwright/test";
import { login as signIn } from "./helpers";

test.skip(process.env.E2E_REAL !== "1", "motion audit runs against the real backend: set E2E_REAL=1 (see playwright.config.ts)");

const EMAIL = process.env.AUDIT_EMAIL ?? "admin@smartsched.local";
const PASSWORD = process.env.AUDIT_PASSWORD ?? "Admin-2026!";
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
      expect.soft(report.dropped).toBeLessThanOrEqual(3 * interactions);
      expect.soft(report.worstLongFrame).toBeLessThanOrEqual(rate > 1 ? 150 : 100);
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
      expect.soft(report.dropped).toBeLessThanOrEqual(3 * interactions);
      expect.soft(report.worstLongFrame).toBeLessThanOrEqual(rate > 1 ? 150 : 100);
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
