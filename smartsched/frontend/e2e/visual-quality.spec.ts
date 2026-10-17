/**
 * Visual-quality gate (docs/review/2026-10-15-uiux-visual-review.md §5; design-system overhaul 2026-10-15).
 * Runs against the REAL backend like every spec here (E2E_REAL=1, see playwright.config.ts). Two projects run
 * it: `chromium` (desktop, fine pointer) and `mobile` (390 × 844, isMobile, hasTouch → pointer: coarse).
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 E2E_TERM_CODE=2026-GUZ npx playwright test visual-quality
 *
 * Checks (per route unless noted):
 *   focus     25 Tab presses: every focused element draws a ≥ 2 px solid outline (or a ≥ 3 px field halo) that is
 *             not clipped by an overflow ancestor
 *   controls  buttons / fields / segmented tracks use the control-height scale: {24,28,32,40} on fine pointers,
 *             {32,36,44,48} on coarse ones (xs/sm keep a 44 px hit area through ::after)
 *   segmented never wraps (one row) and is ≤ 46 px tall; the thumb rests inside its track (±1 px) in both themes
 *   type      font sizes on the scale; cards and glass panels have radii ≤ 24 × --corner-k
 *   layout    no horizontal page overflow at 390 / on the mobile project; no KPI overlap on the dashboard at 1024
 *   columns   /rooms column resize handle: keyboard resize works and the width survives a reload
 *   axe       color-contrast, target-size, label, nested-interactive: 0 violations on the design-system routes
 *   fields    inputs draw the --border-control edge (3:1, verified numerically by verify-contrast.mjs)
 *   brand     the favicon is not the create-next-app default
 *   baseline  toHaveScreenshot (maxDiffPixelRatio 0.01, [data-dynamic] masked) when VISUAL_BASELINE=1
 */
import { createHash } from "node:crypto";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { REAL, SKIP_REASON, login } from "./helpers";
import { pinLanguage } from "./language";

const AXE = path.resolve(process.cwd(), "node_modules/axe-core/axe.min.js");

test.skip(!REAL, SKIP_REASON);
// the assertions read Turkish (the product default): pin it, whatever the previous spec left behind
pinLanguage("tr");

/** Screens the design-system overhaul owns: every check applies. */
const OWN = ["/dashboard", "/timetable", "/classes", "/runs", "/generate", "/rooms", "/onboarding"];
/** Other agents' screens: focus and overflow only, until they migrate to the primitives (hand-off list). */
const OTHERS = ["/bookings", "/my-bookings", "/find-room", "/approvals", "/settings"];
const FINE_HEIGHTS = [24, 28, 32, 40];
const COARSE_HEIGHTS = [32, 36, 44, 48];
const FONT_SCALE = [10, 11, 12, 13, 14, 16, 18, 20, 22, 24, 28, 34];
const NEXT_DEFAULT_FAVICON = "2be26fb5639bc7a24d9c816567b0de5f";

const isMobile = () => test.info().project.name === "mobile";

async function settle(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  // one loading signal per region: wait until no skeleton pulses (screens take seconds on the real data)
  await expect
    .poll(async () => page.locator("[data-slot=skeleton], [data-loading=true]").count(), { timeout: 45_000 })
    .toBe(0)
    .catch(() => undefined);
  await page.waitForTimeout(500);
}

async function setTheme(page: Page, theme: "light" | "dark") {
  await page.evaluate((th) => {
    document.documentElement.classList.toggle("dark", th === "dark");
    document.documentElement.classList.toggle("light", th === "light");
  }, theme);
  await page.waitForTimeout(150);
}

test.describe("visual quality (design system)", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("brand: the favicon is not the create-next-app default", async ({ page }) => {
    const res = await page.request.get("/favicon.ico");
    expect(res.ok()).toBeTruthy();
    expect(createHash("md5").update(await res.body()).digest("hex")).not.toBe(NEXT_DEFAULT_FAVICON);
  });

  for (const path of [...OWN, ...OTHERS]) {
    test(`focus ring on every tab stop and no horizontal overflow: ${path}`, async ({ page }) => {
      await settle(page, path);
      if (isMobile() || page.viewportSize()!.width <= 400) {
        // against the device width, not innerWidth: on a touch phone a too-wide element widens the layout
        // viewport itself (innerWidth 502 on a 390 screen), so scrollWidth − innerWidth stayed 0
        const overflow = await page.evaluate((w) => document.scrollingElement!.scrollWidth - w, page.viewportSize()!.width);
        expect(overflow, "horizontal page overflow").toBeLessThanOrEqual(1);
      }
      if (isMobile()) return; // focus rings are a keyboard check
      await page.locator("body").click({ position: { x: 2, y: 2 } }).catch(() => undefined);
      const misses: string[] = [];
      for (let i = 0; i < 25; i++) {
        await page.keyboard.press("Tab");
        const r = await page.evaluate(() => {
          const el = document.activeElement as HTMLElement | null;
          if (!el || el === document.body) return null;
          const cs = getComputedStyle(el);
          const width = parseFloat(cs.outlineWidth) || 0;
          const offset = parseFloat(cs.outlineOffset) || 0;
          const ring = cs.outlineStyle !== "none" && width >= 2;
          const halo = /(\d+(?:\.\d+)?)px\s*(?:rgb|#|color)/.test(cs.boxShadow) && /0px 0px 0px ([3-9]|\d{2,})px/.test(cs.boxShadow);
          // clipped: the ring (rect + offset + width) must fit inside every overflow-clipping ancestor
          const pad = offset >= 0 ? offset + width : 0;
          const rect = el.getBoundingClientRect();
          let clipped = false;
          for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
            const s = getComputedStyle(a);
            if (s.overflowX === "visible" && s.overflowY === "visible") continue;
            const b = a.getBoundingClientRect();
            if (rect.left - pad < b.left - 1 || rect.right + pad > b.right + 1 || rect.top - pad < b.top - 1 || rect.bottom + pad > b.bottom + 1) {
              // an element scrolled partly out of its scroller is not a clipped ring
              if (rect.top >= b.top && rect.bottom <= b.bottom && rect.left >= b.left && rect.right <= b.right) clipped = true;
            }
          }
          const label = `${el.tagName.toLowerCase()}${el.getAttribute("data-slot") ? `[${el.getAttribute("data-slot")}]` : ""} "${(el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 40)}"`;
          return { ok: (ring || halo) && !clipped, label, ring, halo, clipped };
        });
        if (r && !r.ok) misses.push(`${r.label} ring=${r.ring} halo=${r.halo} clipped=${r.clipped}`);
      }
      expect(misses, `tab stops without a visible ring on ${path}`).toEqual([]);
    });
  }

  for (const path of OWN) {
    test(`controls, segmented, type and radii on the scale: ${path}`, async ({ page }) => {
      await settle(page, path);
      const coarse = isMobile();
      const report = await page.evaluate(
        ({ heights, fonts }) => {
          const vis = (el: Element) => {
            const r = (el as HTMLElement).getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
          };
          const bad: string[] = [];
          const near = (v: number, set: number[]) => set.some((h) => Math.abs(v - h) <= 0.6);
          // controls built on the primitives
          const sel = "[data-slot=button]:not([data-size=icon]):not([data-size^=icon-]), [data-slot=icon-button], [data-slot=native-select] select, [data-slot=select-trigger], [data-slot=input], [data-slot=date-field] input, [data-slot=segmented-control] [data-part=track]";
          for (const el of document.querySelectorAll(sel)) {
            if (!vis(el) || el.closest("[data-slot=chip]") || (el as HTMLElement).className.includes("underline-offset")) continue;
            const h = (el as HTMLElement).getBoundingClientRect().height;
            if (!near(h, heights)) bad.push(`control ${el.getAttribute("data-slot") ?? el.tagName} ${Math.round(h * 10) / 10}px "${(el.textContent ?? "").trim().slice(0, 30)}"`);
          }
          // segmented: one row, ≤ 46 px, thumb inside the track
          for (const track of document.querySelectorAll("[data-slot=segmented-control] [data-part=track], [data-slot=tabs-list]")) {
            if (!vis(track)) continue;
            const items = [...track.querySelectorAll("[role=tab], [role=radio]")].filter(vis);
            const tops = new Set(items.map((i) => Math.round(i.getBoundingClientRect().top)));
            const tr = track.getBoundingClientRect();
            if (tops.size > 1) bad.push(`segmented wraps (${tops.size} rows)`);
            if (tr.height > 46) bad.push(`segmented ${Math.round(tr.height)}px tall`);
            const thumb = track.querySelector("[data-slot=segmented-thumb], [data-slot=tabs-indicator]");
            if (thumb && vis(thumb)) {
              const t = thumb.getBoundingClientRect();
              if (t.top < tr.top - 1 || t.bottom > tr.bottom + 1 || t.left < tr.left - 1 || t.right > tr.right + 1) bad.push(`segmented thumb outside its track by ${Math.round(Math.max(tr.top - t.top, t.bottom - tr.bottom))}px`);
            }
          }
          // type scale (leaf text only); the fluid titles resolve to their clamp() value at this viewport
          const probe = document.createElement("span");
          document.body.appendChild(probe);
          for (const v of ["--text-large-title", "--text-title-1", "--text-title-2", "--text-title-3"]) {
            probe.style.fontSize = `var(${v})`;
            fonts.push(parseFloat(getComputedStyle(probe).fontSize));
          }
          probe.remove();
          const k = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--corner-k")) || 1;
          const seen = new Set<string>();
          for (const el of document.querySelectorAll("main *")) {
            if (!vis(el) || !(el.childNodes.length && [...el.childNodes].some((n) => n.nodeType === 3 && (n.textContent ?? "").trim()))) continue;
            const fs = parseFloat(getComputedStyle(el).fontSize);
            if (!fonts.some((f) => Math.abs(f - fs) < 0.6) && !seen.has(String(fs))) {
              seen.add(String(fs));
              bad.push(`font-size ${fs}px "${(el.textContent ?? "").trim().slice(0, 30)}"`);
            }
          }
          for (const el of document.querySelectorAll("main [data-slot=card], main [data-glass]")) {
            if (!vis(el)) continue;
            const r = parseFloat(getComputedStyle(el).borderTopLeftRadius);
            if (r > 24 * k + 0.5 && r < 999) bad.push(`radius ${r}px on ${el.getAttribute("data-slot") ?? el.getAttribute("data-glass")}`);
          }
          return bad;
        },
        { heights: coarse ? COARSE_HEIGHTS : FINE_HEIGHTS, fonts: FONT_SCALE },
      );
      expect(report, `design-system violations on ${path}`).toEqual([]);
    });
  }

  test("segmented thumb rests inside its track in both themes (motion skill §8)", async ({ page }) => {
    test.skip(isMobile(), "desktop check");
    for (const theme of ["light", "dark"] as const) {
      await settle(page, "/generate?step=scope");
      await setTheme(page, theme);
      await page.waitForTimeout(500);
      const off = await page.evaluate(() =>
        [...document.querySelectorAll("[data-slot=segmented-control] [data-part=track]")].map((tr) => {
          const t = tr.querySelector("[data-slot=segmented-thumb]");
          if (!t || (t as HTMLElement).offsetParent === null) return 0;
          const a = tr.getBoundingClientRect();
          const b = t.getBoundingClientRect();
          return Math.max(a.top - b.top, b.bottom - a.bottom, a.left - b.left, b.right - a.right, 0);
        }),
      );
      for (const o of off) expect(o, `thumb offset (${theme})`).toBeLessThanOrEqual(1);
    }
  });

  test("dashboard KPIs never overlap at 1024", async ({ page }) => {
    test.skip(isMobile(), "desktop width check");
    await page.setViewportSize({ width: 1024, height: 800 });
    await settle(page, "/dashboard");
    const boxes = await page.locator("[data-testid=dashboard-hero] dl > div").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().toJSON() as DOMRect));
    expect(boxes.length).toBeGreaterThan(0);
    for (let i = 0; i < boxes.length; i++)
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i];
        const b = boxes[j];
        const overlap = a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
        expect(overlap, `KPI ${i} overlaps KPI ${j}`).toBe(false);
      }
  });

  test("rooms table: keyboard column resize persists across a reload", async ({ page }) => {
    test.skip(isMobile(), "the table turns into cards on phones");
    await settle(page, "/rooms");
    const handle = page.locator("[data-slot=column-resize][data-column=tags]");
    await expect(handle).toBeVisible();
    const before = Number(await handle.getAttribute("aria-valuenow"));
    await handle.focus();
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("Shift+ArrowRight");
    await expect(handle).toHaveAttribute("aria-valuenow", String(before + 40));
    await page.reload();
    await settle(page, "/rooms");
    await expect(page.locator("[data-slot=column-resize][data-column=tags]")).toHaveAttribute("aria-valuenow", String(before + 40));
    // double-click auto-fits again (and clears the stored width)
    await page.locator("[data-slot=column-resize][data-column=tags]").dblclick();
    await expect(page.locator("[data-slot=column-resize][data-column=tags]")).not.toHaveAttribute("aria-valuenow", String(before + 40));
  });

  test("fields draw the 3:1 control edge", async ({ page }) => {
    await settle(page, "/rooms");
    const shadow = await page.getByTestId("rooms-search").locator("xpath=ancestor::*[@data-slot='input-group'][1]").evaluate((el) => getComputedStyle(el).boxShadow);
    const token = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--border-control").trim());
    expect(token).not.toBe("");
    expect(shadow).toMatch(/inset/);
    expect(shadow).not.toBe("none");
  });

  for (const theme of ["light", "dark"] as const) {
    test(`axe: contrast, target size, labels, nesting (${theme})`, async ({ page }) => {
      const results: string[] = [];
      for (const path of OWN) {
        await settle(page, path);
        await setTheme(page, theme);
        await page.addScriptTag({ path: AXE });
        const v = await page.evaluate(async () => {
          // @ts-expect-error injected axe-core
          const r = await window.axe.run(document.querySelector("main") ?? document, { runOnly: ["color-contrast", "target-size", "label", "nested-interactive"], resultTypes: ["violations"] });
          return (r.violations as { id: string; nodes: { target: string[] }[] }[]).map((x) => `${x.id}: ${x.nodes.length} (${x.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")})`);
        });
        for (const x of v) results.push(`${path} ${x}`);
      }
      expect(results).toEqual([]);
    });
  }

  test("visual baselines", async ({ page }) => {
    test.skip(process.env.VISUAL_BASELINE !== "1", "set VISUAL_BASELINE=1 to compare screenshots (baselines are platform-specific)");
    for (const path of OWN) {
      await settle(page, path);
      await expect(page).toHaveScreenshot(`${path.replace(/\W+/g, "_") || "root"}.png`, { maxDiffPixelRatio: 0.01, mask: [page.locator("[data-dynamic]")], fullPage: false });
    }
  });
});
