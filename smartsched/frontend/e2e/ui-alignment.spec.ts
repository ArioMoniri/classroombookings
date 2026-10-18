/**
 * UI alignment (docs/testing/ui-alignment/2026-10-18/report.md): in every row of the shell and the page toolbars the
 * icons' vertical centres differ by at most 1 px, the controls on one line share a centre, and one row uses one icon
 * size (docs/design/tokens.md §A.5 "nothing in one row mixes heights", §A3 icons 16/20, 14 in sm controls).
 * Measured at 1440 × 900 (mouse) and 390 × 844 (touch, isMobile), tr-TR, light and dark.
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx playwright test ui-alignment
 */
import { expect, test, type Browser, type BrowserContextOptions, type Page } from "@playwright/test";
import { REAL, SKIP_REASON, login } from "./helpers";

test.skip(!REAL, SKIP_REASON);

const DESKTOP: BrowserContextOptions = { viewport: { width: 1440, height: 900 } };
const PHONE: BrowserContextOptions = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 };
const ROUTES = ["/", "/timetable", "/find-room", "/reserve", "/bookings", "/runs", "/admin", "/admin/users", "/admin/rooms", "/admin/settings"];

type Box = { owner: string; cy: number; size: number };
type Row = { key: string; lines: { icons: Box[]; controls: Box[] }[] };

/** In the page: the rows under test, each split into visual lines (a wrapping toolbar is judged line by line). */
function measureRows(): Row[] {
  const visible = (el: Element) => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== "hidden" && cs.display !== "none";
  };
  const owner = (el: Element) => (el.getAttribute("data-testid") || el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40);
  const rows: Row[] = [];
  const add = (key: string, root: Element | null | undefined) => {
    if (!root || !visible(root)) return;
    // icons: lucide glyphs (keycaps and the 8 px status dots are not icons)
    const icons = [...root.querySelectorAll("svg")].filter((s) => visible(s) && !s.closest("[data-slot=kbd]") && !s.parentElement?.closest("svg") && s.getBoundingClientRect().width >= 10);
    const controls = [...root.querySelectorAll("button, a[href], input, select, [role=tab], [data-slot=input-group]")].filter(
      (el) => visible(el) && !el.parentElement?.closest("button, a[href], [role=tab], [data-slot=input-group]"),
    );
    const box = (el: Element, ownerEl: Element): Box & { top: number; bottom: number } => {
      const r = el.getBoundingClientRect();
      return { owner: owner(ownerEl), cy: r.top + r.height / 2, size: Math.round(r.width * 10) / 10, top: r.top, bottom: r.bottom };
    };
    const cs = controls.map((el) => box(el, el));
    const is = icons.map((s) => box(s, s.closest("button, a, [role=tab]") ?? s));
    // lines: controls whose vertical extents overlap belong to one line; icons go to the line of their centre
    const lines: { top: number; bottom: number; icons: Box[]; controls: Box[] }[] = [];
    for (const c of [...cs].sort((a, b) => a.top - b.top)) {
      const line = lines.find((l) => c.top < l.bottom && c.bottom > l.top);
      if (line) {
        line.controls.push(c);
        line.top = Math.min(line.top, c.top);
        line.bottom = Math.max(line.bottom, c.bottom);
      } else lines.push({ top: c.top, bottom: c.bottom, icons: [], controls: [c] });
    }
    for (const i of is) (lines.find((l) => i.cy >= l.top && i.cy <= l.bottom) ?? lines[0])?.icons.push(i);
    rows.push({ key, lines: lines.map(({ icons: a, controls: b }) => ({ icons: a, controls: b })) });
  };
  for (const h of document.querySelectorAll("header")) if (!h.closest("main")) add(h.querySelector("[role=toolbar]") ? "top bar" : "phone top bar", h);
  add("tab bar", document.querySelector("[data-slot=tab-bar]"));
  add("palette input", document.querySelector("[data-slot=command-input-wrapper]"));
  const theme = [...document.querySelectorAll("[data-testid=theme-toggle]")].find(visible);
  add("sidebar account", theme?.parentElement);
  const h1 = document.querySelector("main h1");
  const header = h1?.parentElement?.parentElement;
  add("page header actions", header && [...header.children].find((el) => el !== h1?.parentElement && el.querySelector("button, a")));
  document.querySelectorAll("main [role=toolbar], main [data-slot=toolbar]").forEach((t, i) => add(`toolbar ${i} (${t.getAttribute("aria-label") ?? ""})`, t));
  return rows;
}

function check(where: string, rows: Row[]) {
  const problems: string[] = [];
  for (const row of rows)
    for (const [n, line] of row.lines.entries()) {
      const label = `${where} · ${row.key}${row.lines.length > 1 ? ` line ${n + 1}` : ""}`;
      const spread = (b: Box[]) => (b.length < 2 ? 0 : Math.max(...b.map((x) => x.cy)) - Math.min(...b.map((x) => x.cy)));
      const list = (b: Box[]) => b.map((x) => `${x.owner}@${x.cy.toFixed(1)}/${x.size}`).join(", ");
      if (spread(line.icons) > 1) problems.push(`${label}: icon centres differ by ${spread(line.icons).toFixed(1)} px (${list(line.icons)})`);
      if (spread(line.controls) > 1) problems.push(`${label}: control centres differ by ${spread(line.controls).toFixed(1)} px (${list(line.controls)})`);
      const sizes = [...new Set(line.icons.map((i) => i.size))];
      if (sizes.length > 1) problems.push(`${label}: icon sizes ${sizes.join(" / ")} in one row (${list(line.icons)})`);
    }
  return problems;
}

async function settle(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  // the skeletons give way to the real controls; give the springs a moment to rest
  await page.waitForTimeout(600);
}

async function audit(browser: Browser, baseURL: string, device: BrowserContextOptions, colorScheme: "light" | "dark") {
  const context = await browser.newContext({ ...device, baseURL, locale: "tr-TR", timezoneId: "Europe/Istanbul", colorScheme });
  const page = await context.newPage();
  await login(page);
  const problems: string[] = [];
  for (const path of ROUTES) {
    await settle(page, path);
    problems.push(...check(path, await page.evaluate(measureRows)));
  }
  // the ⌘K palette's input row, opened from the shell's own trigger
  await settle(page, "/");
  await page.getByTestId(device.isMobile ? "open-palette-mobile" : "helper-trigger").click();
  await expect(page.locator("[data-slot=command-input-wrapper]")).toBeVisible();
  const palette = (await page.evaluate(measureRows)).filter((r) => r.key === "palette input");
  expect(palette, "the palette input row is measured").toHaveLength(1);
  problems.push(...check("palette", palette));
  await context.close();
  return problems;
}

for (const [name, device] of [["desktop 1440 (mouse)", DESKTOP], ["phone 390 (touch)", PHONE]] as const) {
  for (const scheme of ["light", "dark"] as const) {
    test(`rows share one centre line and one icon size · ${name} · ${scheme}`, async ({ browser }, info) => {
      test.setTimeout(240_000);
      const problems = await audit(browser, String(info.project.use.baseURL), device, scheme);
      expect(problems, problems.join("\n")).toEqual([]);
    });
  }
}

test("the phone tab bar's search glyph is on the tabs' icon line, at their size", async ({ browser }, info) => {
  const context = await browser.newContext({ ...PHONE, baseURL: String(info.project.use.baseURL), locale: "tr-TR", timezoneId: "Europe/Istanbul" });
  const page = await context.newPage();
  await login(page);
  await settle(page, "/");
  const glyph = async (sel: string) => (await page.locator(sel).locator("svg").first().boundingBox())!;
  const tab = await glyph("[data-slot=tab-bar] nav li:first-child");
  const search = await glyph("[data-testid=open-palette-mobile]");
  expect(Math.abs(tab.y + tab.height / 2 - (search.y + search.height / 2))).toBeLessThanOrEqual(1);
  expect(search.width).toBe(tab.width);
  // still a ≥ 44 px target with its accessible name
  const button = (await page.getByTestId("open-palette-mobile").boundingBox())!;
  expect(Math.min(button.width, button.height)).toBeGreaterThanOrEqual(44);
  await expect(page.getByTestId("open-palette-mobile")).toHaveAccessibleName("Ara veya sor");
  await context.close();
});
