# Motion audit procedure

Run it for every PR that adds or changes motion, and once per surface before a release. It answers five questions:

1. **Ceiling**: does every one-shot animation finish in ≤ 300 ms?
2. **Frames**: does the interaction hold 60 fps on a 4× throttled CPU (≤ 2 dropped frames per interaction, no long animation frame > 50 ms)?
3. **Properties**: do only `transform`, `opacity` and `filter` (small elements) animate, with no per-frame Layout?
4. **Reduced motion**: with `prefers-reduced-motion: reduce`, is every movement gone and does the UI reach its end state at once?
5. **Reduced transparency**: with `prefers-reduced-transparency: reduce` (or `data-transparency="reduced"`), are glass surfaces opaque, and is the motion still correct?

## 1. Manual pass (5 minutes per surface)

- Chrome DevTools → **Rendering**: enable *Frame Rendering Stats*, *Paint flashing* and *Layout Shift Regions*. Emulate `prefers-reduced-motion` and `prefers-reduced-transparency`.
- **Performance** panel, CPU 4× slowdown, record the interaction. In the frames track look for red frames. In the Main track, during the animation, look for purple **Layout** blocks: there should be none except one at the start and end of a FLIP (`layout` prop).
- **Animations** panel (More tools → Animations): replay at 10 % and check that springs settle without a visible jump at the end and that exits are faster than entrances.
- Interrupt everything: click the segmented control twice fast, flick the sheet and grab it mid-flight, press Esc during a palette open. Nothing may restart from its first frame.

## 2. Automated pass (Playwright)

Copy this into `smartsched/frontend/e2e/motion-audit.spec.ts`, fill in the selectors for the surface, and run `npx playwright test e2e/motion-audit.spec.ts --project=chromium --trace on`. Open the trace with `npx playwright show-trace test-results/**/trace.zip`: its filmstrip and action timeline show each step. The Chrome trace written by `startTracing` (`motion-trace.json`) loads into DevTools → Performance for frame-level inspection.

```ts
import { expect, test, type Browser, type Page } from "@playwright/test";

type FrameReport = { frames: number; dropped: number; p95: number; longFrames: number; worstLongFrame: number };

/** rAF probe + Long Animation Frames (Chromium 123+). Frame budget = median interval, so 120 Hz displays work. */
async function startFrameProbe(page: Page): Promise<void> {
  await page.evaluate(() => {
    type Probe = { deltas: number[]; loaf: number[]; stop: boolean; po?: PerformanceObserver };
    const w = window as unknown as { __mf?: Probe };
    if (w.__mf) w.__mf.stop = true; // never stack two rAF loops
    const st: Probe = { deltas: [], loaf: [], stop: false }; // each loop owns its state
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
    return {
      frames: d.length,
      dropped,
      p95: sorted[Math.floor(sorted.length * 0.95)] ?? 0,
      longFrames: w.__mf.loaf.filter((x) => x > 50).length,
      worstLongFrame: Math.max(0, ...w.__mf.loaf),
    };
  });
}

/** Every finite CSS/WAAPI animation must be ≤ 300 ms (motion also runs on WAAPI, so most springs show up here). */
async function animationsOverCeiling(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    document
      .getAnimations()
      .map((a) => ({ a, t: a.effect?.getComputedTiming() }))
      .filter(({ t }) => t && t.iterations !== Infinity && Number(t.duration) + Number(t.delay ?? 0) > 300)
      .map(({ a, t }) => `${(a as CSSAnimation).animationName ?? a.id ?? "anim"} ${String(t?.duration)}ms`),
  );
}

/** Count Layout events in a Chrome trace taken around the interaction. */
async function traceLayouts(browser: Browser, page: Page, run: () => Promise<void>): Promise<number> {
  await browser.startTracing(page, { path: "test-results/motion-trace.json", screenshots: true, categories: ["devtools.timeline"] });
  await run();
  const buf = await browser.stopTracing();
  const json = JSON.parse(buf.toString()) as { traceEvents?: { name: string }[] } | { name: string }[];
  const events = Array.isArray(json) ? json : (json.traceEvents ?? []);
  return events.filter((e) => e.name === "Layout").length;
}

test.describe("motion audit: command palette", () => {
  test("holds 60 fps on 4x CPU, stays under the ceiling, no per-frame layout", async ({ page, browser }) => {
    await page.goto("/dashboard");
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });

    await startFrameProbe(page);
    const layouts = await traceLayouts(browser, page, async () => {
      await page.keyboard.press("ControlOrMeta+k");
      await page.getByRole("dialog").waitFor();
      expect(await animationsOverCeiling(page)).toEqual([]);
      await page.waitForTimeout(400);
      await page.keyboard.press("ArrowDown");
      await page.keyboard.press("ArrowDown");
      await page.waitForTimeout(400);
    });
    const report = await stopFrameProbe(page);
    console.log("palette", report, { layouts });

    expect(report.dropped).toBeLessThanOrEqual(2);
    expect(report.longFrames).toBe(0);
    expect(layouts).toBeLessThanOrEqual(6); // open + 2 selection moves; FLIP measures ≈ 2 per change
  });

  test("reduced motion: end state on the next frame, no transform animation", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/dashboard");
    await page.keyboard.press("ControlOrMeta+k");
    const dialog = page.getByRole("dialog");
    await dialog.waitFor();
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const transform = await dialog.evaluate((el) => getComputedStyle(el).transform);
    expect(["none", "matrix(1, 0, 0, 1, 0, 0)"]).toContain(transform);
    const moving = await page.evaluate(() =>
      document.getAnimations().filter((a) => {
        const kf = (a.effect as KeyframeEffect | null)?.getKeyframes() ?? [];
        return kf.some((k) => "transform" in k || "translate" in k || "scale" in k);
      }).length,
    );
    expect(moving).toBe(0);
  });

  test("reduced transparency: glass becomes opaque", async ({ page }) => {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-reduced-transparency", value: "reduce" }],
    });
    await page.goto("/dashboard");
    await page.keyboard.press("ControlOrMeta+k");
    const dialog = page.getByRole("dialog");
    await dialog.waitFor();
    const style = await dialog.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { backdrop: cs.backdropFilter, bg: cs.backgroundColor };
    });
    expect(style.backdrop === "none" || style.backdrop === "").toBeTruthy();
    expect(style.bg).not.toMatch(/rgba\(.*, 0\.[0-8]\d*\)$/); // alpha ≥ 0.9
  });
});
```

Notes:
- `page.emulateMedia({ reducedMotion })` is native in Playwright. Reduced transparency has no Playwright option, so use CDP `Emulation.setEmulatedMedia` features (Chromium only). The app's `data-transparency="reduced"` path can be tested in every browser by setting the attribute in `page.addInitScript`.
- Headless Chromium paces rAF at about 60 Hz, which makes dropped-frame counts comparable between runs. Run on the CI image, not a laptop, for thresholds.
- The Layout count threshold is per surface. Record the baseline in the surface's spec and fail on regressions (+50 %).
- For drag patterns, drive the pointer with `page.mouse.move(x, y, { steps: 20 })` between `down()` and `up()`. Probe frames across the whole drag.

## 3. Report format (append to the surface spec or the PR)

```
Motion audit: <surface> (<date>, <commit>)
| Interaction | dropped (4× CPU) | LoAF > 50 ms | Layout events | over-ceiling | reduced motion | reduced transparency |
| palette open | 1 | 0 | 2 | none | end state ✓ | opaque ✓ |
```

A failure in any column blocks the PR (strict-reviewer gate). Waivers go in the spec with a reason.
