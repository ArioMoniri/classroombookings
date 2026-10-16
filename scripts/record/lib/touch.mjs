// Touch contexts for the flow loop (docs/testing/flows/README.md §3, MOBILE.md "How to run").
//
//   import { createRequire } from "node:module";
//   const require = createRequire(import.meta.url);
//   const { chromium } = require("/home/user/classroombookings/smartsched/frontend/node_modules/playwright");
//   import { VIEWPORTS, newFlowPage, assertTouch, shot } from "/home/user/classroombookings/scripts/record/lib/touch.mjs";
//   const { ctx, page } = await newFlowPage(browser, "phone");
//   await assertTouch(page);              // before every M-02 / M-03 / M-05 measurement
//   await shot(page, `${EV}/shots/F01-S03-staff-phone.png`);   // full page, then touch is switched back on
//
// Why (T-R1-45, measured 2026-10-16 on Playwright 1.56.1 + chromium-1194 headless shell): a
// `page.screenshot({ fullPage: true })` of a page taller than the viewport, in an isMobile + hasTouch context,
// switches Chromium's touch emulation off for the rest of that page's life, across navigations and reloads:
// `(pointer: coarse)` and `(hover: none)` stop matching and navigator.maxTouchPoints drops to 0. The coarse-pointer
// tokens (globals.css: --control-h-md 32 -> 44 px, inputs 16 px) then fall back to the mouse sizes, and every later
// M-02/M-03 reading on that page is a desktop reading at phone width. Round 1 measured "32 px" this way.
// `page.setViewportSize()` does not bring it back; Emulation.setTouchEmulationEnabled does.
// The CDP media emulation `Emulation.setEmulatedMedia({ features: [{ name: "pointer", value: "coarse" }, ...] })`
// that README §3 used to recommend has no effect on `pointer` / `hover` in this Chromium build: `hasTouch` alone
// makes them match.

export const VIEWPORTS = {
  desktop: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, locale: "tr-TR", timezoneId: "Europe/Istanbul" },
  tablet: { viewport: { width: 768, height: 1024 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: "tr-TR", timezoneId: "Europe/Istanbul" },
  phone: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, locale: "tr-TR", timezoneId: "Europe/Istanbul" },
};

const cdpOf = new WeakMap();
const touchPages = new WeakSet();

/** A new context + page for one viewport id; `extra` is merged into the context options (storageState, reducedMotion, …). */
export async function newFlowPage(browser, vp, extra = {}) {
  const opts = { ...VIEWPORTS[vp], ...extra };
  const ctx = await browser.newContext(opts);
  const page = await ctx.newPage();
  if (opts.hasTouch) touchPages.add(page);
  return { ctx, page, vp };
}

/** Switch touch emulation back on (after anything that may have dropped it). No-op on a desktop page. */
export async function rearmTouch(page) {
  if (!touchPages.has(page)) return;
  let cdp = cdpOf.get(page);
  if (!cdp) { cdp = await page.context().newCDPSession(page); cdpOf.set(page, cdp); }
  await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 1 });
}

/** The page's pointer state, as the CSS sees it. */
export async function touchState(page) {
  return page.evaluate(() => ({
    coarse: matchMedia("(pointer: coarse)").matches,
    hoverNone: matchMedia("(hover: none)").matches,
    maxTouchPoints: navigator.maxTouchPoints,
    controlHmd: getComputedStyle(document.documentElement).getPropertyValue("--control-h-md").trim(),
  }));
}

/** Throws unless a touch page really has a coarse pointer and no hover. Call it before every touch measurement. */
export async function assertTouch(page) {
  if (!touchPages.has(page)) return;
  const s = await touchState(page);
  if (!s.coarse || !s.hoverNone || s.maxTouchPoints < 1) {
    throw new Error(`touch emulation is off (${JSON.stringify(s)}): a full-page screenshot without shot()? Measurements would be desktop sizes.`);
  }
}

/** Screenshot (full page by default) that leaves a touch page in touch mode. */
export async function shot(page, path, { fullPage = true, ...rest } = {}) {
  try {
    await page.screenshot({ path, fullPage, ...rest });
  } finally {
    if (fullPage) await rearmTouch(page);
  }
  return path;
}
