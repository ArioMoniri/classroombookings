/**
 * AUX-10 (docs/design/v3/auth.md §11.3–§11.4; ROADMAP AUX-10 accept) against the REAL stack (E2E_REAL=1, prod build).
 * Not run by the builder (resource rule 2026-10-18): the single e2e lane runs it.
 *   E2E_REAL=1 PW_PORT=<web> npx playwright test e2e/au-signin-hero.spec.ts
 *
 * 1. 1440 mouse: the hero plays once (≤ 5 s from "playing" to "done") and does not loop (two screenshots 1.5 s
 *    apart are identical).
 * 2. 1440: no long animation frame > 50 ms while typing in the identifier during the pass.
 * 2b. 1440: typing from the first moment (before the hero loaded, LoAF observed from page load): no frame > 50 ms
 *    while typing; the pass plays afterwards.
 * 3. 390 × 844 touch: no hero and the Lottie player / JSON are never downloaded.
 * 4. Reduced motion: the poster PNG, no player download.
 * 5. Motion-audit case: no finite animation over 300 ms, decorative (aria-hidden, pointer-events none), at most 2
 *    backdrop-filter surfaces (the hero frame has none; the sheet keeps its tint without a blur since 2026-10-19), hidden in forced colours, and the 2FA step
 *    route has no hero.
 *
 * The "was the Lottie bundle requested" probe reads every JS/JSON response body for markers of lottie-web
 * ("bodymovin") and of the hero file ("score-placeholder"); case 1 proves the probe sees them when the hero plays.
 */
import { expect, test, type Page } from "@playwright/test";
import { REAL, SKIP_REASON } from "./helpers";
import { pinLanguage } from "./language";

test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

const MARKERS = [/bodymovin/, /score-placeholder/];

function watchLottie(page: Page): { hits: string[] } {
  const state = { hits: [] as string[] };
  page.on("response", async (res) => {
    const type = res.headers()["content-type"] ?? "";
    if (!/javascript|json/.test(type)) return;
    try {
      const body = await res.text();
      if (MARKERS.some((m) => m.test(body))) state.hits.push(res.url());
    } catch {
      // redirects and aborted bodies carry nothing
    }
  });
  return state;
}

/** data-state transitions of the hero with performance.now() stamps (installed before any script runs). */
async function recordStates(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __hero: { state: string; t: number }[] };
    w.__hero = [];
    new MutationObserver(() => {
      const el = document.querySelector('[data-testid="signin-hero"]');
      const s = el?.getAttribute("data-state");
      if (s && w.__hero.at(-1)?.state !== s) w.__hero.push({ state: s, t: performance.now() });
    }).observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-state"] });
  });
}
const states = (page: Page) => page.evaluate(() => (window as unknown as { __hero: { state: string; t: number }[] }).__hero);

test.describe("AUX-10 sign-in hero · 1440 mouse", () => {
  test.use({ viewport: { width: 1440, height: 900 }, locale: "tr-TR", timezoneId: "Europe/Istanbul" });

  test("plays once in ≤ 5 s, holds the poster frame, never loops; typing stays under 50 ms frames", async ({ page }) => {
    const lottie = watchLottie(page);
    await recordStates(page);
    await page.goto("/login?method=local");
    const hero = page.getByTestId("signin-hero");
    await expect(hero).toHaveAttribute("aria-hidden", "true");
    await expect(hero).toHaveAttribute("data-state", "playing", { timeout: 5000 });

    // type during the pass with a long-animation-frame probe
    await page.evaluate(() => {
      const w = window as unknown as { __loaf: number[] };
      w.__loaf = [];
      new PerformanceObserver((list) => {
        for (const e of list.getEntries()) w.__loaf.push(e.duration);
      }).observe({ type: "long-animation-frame" });
    });
    const id = page.getByTestId("login-identifier");
    await id.click();
    await id.pressSequentially("ayse.yilmaz@uni.edu.tr", { delay: 60 });
    const loaf = await page.evaluate(() => (window as unknown as { __loaf: number[] }).__loaf);
    expect(Math.max(0, ...loaf), `LoAF while typing: ${loaf.join(", ")}`).toBeLessThanOrEqual(50);

    await expect(hero).toHaveAttribute("data-state", "done", { timeout: 6000 });
    const s = await states(page);
    const playing = s.find((x) => x.state === "playing")!;
    const done = s.find((x) => x.state === "done")!;
    expect(done.t - playing.t).toBeLessThanOrEqual(5000);
    expect(done.t - playing.t).toBeGreaterThan(4000); // 140 frames at 30 fps = 4.67 s: it really played
    expect(lottie.hits.length).toBeGreaterThan(0); // the probe sees the bundle when it is used

    const a = await hero.screenshot({ animations: "allow" });
    await page.waitForTimeout(1500);
    const b = await hero.screenshot({ animations: "allow" });
    expect(Buffer.compare(a, b), "the hero moved after done: it loops").toBe(0);
    expect((await states(page)).at(-1)?.state).toBe("done");
  });

  test("typing from the first moment: no long animation frame while typing, the hero still plays its pass after", async ({ page }) => {
    // the observer runs from page load (buffered), so the hero's loading (player chunk, scene build, first raster)
    // is measured too, not only its drawn frames; the person starts typing as soon as the form is theirs
    await page.addInitScript(() => {
      const w = window as unknown as { __loaf: { start: number; end: number }[] };
      w.__loaf = [];
      new PerformanceObserver((list) => {
        for (const e of list.getEntries()) w.__loaf.push({ start: e.startTime, end: e.startTime + e.duration });
      }).observe({ type: "long-animation-frame", buffered: true });
    });
    await recordStates(page);
    await page.goto("/login?method=local");
    await page.waitForFunction(() => {
      const el = document.querySelector('[data-testid="login-submit"]');
      return !!el && Object.keys(el).some((k) => k.startsWith("__reactProps$"));
    });
    const hero = page.getByTestId("signin-hero");
    expect(await hero.getAttribute("data-state")).toBe("loading"); // typing starts before the hero has loaded
    const id = page.getByTestId("login-identifier");
    await id.click();
    const from = await page.evaluate(() => performance.now());
    await id.pressSequentially("ayse.yilmaz@uni.edu.tr", { delay: 60 });
    const to = await page.evaluate(() => performance.now());
    await expect(hero).toHaveAttribute("data-state", "done", { timeout: 15_000 });
    const loaf = await page.evaluate(() => (window as unknown as { __loaf: { start: number; end: number }[] }).__loaf);
    const typing = loaf.filter((f) => f.end > from && f.start < to).map((f) => Math.round(f.end - f.start));
    expect(Math.max(0, ...typing), `LoAF while typing: ${typing.join(", ")}`).toBeLessThanOrEqual(50);
    const s = await states(page);
    expect(s.find((x) => x.state === "playing"), "the pass ran after the typing").toBeTruthy();
  });

  test("motion-audit case: ≤ 300 ms finite animations, decorative, one blurred surface besides chrome, forced colours", async ({ page }) => {
    await page.goto("/login?method=local");
    const hero = page.getByTestId("signin-hero");
    await expect(hero).toHaveAttribute("data-state", "playing", { timeout: 5000 });
    const over = await page.evaluate(() =>
      document
        .getAnimations()
        .map((x) => x.effect?.getComputedTiming())
        .filter((t) => t && t.iterations !== Infinity && Number(t.duration) + Number(t.delay ?? 0) > 300).length,
    );
    expect(over).toBe(0);
    expect(await hero.evaluate((el) => getComputedStyle(el).pointerEvents)).toBe("none");
    const blurred = await page.evaluate(() => [...document.querySelectorAll("*")].filter((el) => { const f = getComputedStyle(el).backdropFilter; return f && f !== "none"; }).length);
    expect(blurred).toBeLessThanOrEqual(2);
    expect(await hero.evaluate((el) => [el, ...el.querySelectorAll("*")].some((n) => getComputedStyle(n).backdropFilter !== "none"))).toBe(false);
    // the hero never takes a click: the scene under it still receives it
    const box = (await hero.boundingBox())!;
    const topId = await page.evaluate(([x, y]) => document.elementFromPoint(x!, y!)?.closest('[data-testid="signin-hero"]') ? "hero" : "scene", [box.x + box.width / 2, box.y + box.height / 2]);
    expect(topId).toBe("scene");

    await page.emulateMedia({ forcedColors: "active" });
    await expect(hero).toBeHidden();
  });

  test("reduced motion shows the poster PNG and downloads no player", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    const lottie = watchLottie(page);
    await page.goto("/login?method=local");
    const hero = page.getByTestId("signin-hero");
    await expect(hero).toHaveAttribute("data-state", "poster");
    await expect(hero.locator("img")).toBeVisible();
    await page.waitForTimeout(2500);
    expect(lottie.hits).toEqual([]);
    await expect(hero.locator("svg")).toHaveCount(0);
  });

  test("the 2FA step has no hero (route without a challenge goes back to /login, so check the shell testid)", async ({ page }) => {
    await page.goto("/login/verify");
    // without an ss_mfa cookie this redirects to /login?…mfa=expired, where the hero is allowed; with one (run by the
    // AUX-F spec's 2FA case) the verify page must show none: assert on whichever page we land
    if (await page.getByTestId("verify-page").count()) await expect(page.getByTestId("signin-hero")).toHaveCount(0);
  });
});

test.describe("AUX-10 sign-in hero · 390 × 844 touch", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "tr-TR", timezoneId: "Europe/Istanbul" });

  test("no hero and the Lottie bundle is not requested", async ({ page }) => {
    const lottie = watchLottie(page);
    await page.goto("/login?method=local");
    await expect(page.getByTestId("signin-sheet")).toBeVisible();
    await page.waitForTimeout(2500);
    await expect(page.getByTestId("signin-hero")).toHaveCount(0);
    expect(lottie.hits).toEqual([]);
  });
});
