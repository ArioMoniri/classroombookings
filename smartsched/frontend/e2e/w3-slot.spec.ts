/**
 * Wave 3 W3-SLOT against the REAL backend (gated E2E_REAL=1): the administrator's slot display
 * (docs/design/v3/slot-display.md) and quick reservation /reserve (docs/design/v3/quick-reserve.md).
 *
 * - SD: the admin changes the slot display in Ayarlar › Ders saatleri (label "Saat", density "Sıkı"); a teacher's /bookings
 *   grid headers and /reserve slot chips follow (time first, 32 px rows on a fine pointer, data-density=compact).
 * - QR: a teacher books in ≤ 3 taps from /reserve (room row, Rezerve et), sees the receipt, "Geri al" undoes it through
 *   the real P7 undo (POST /audit/{id}/undo) and the booking is gone from /bookings/mine; at 1440 (mouse) and 390 touch.
 * - MOBILE M-01 (no horizontal scroll), M-02 (44 px targets, centre re-probe), M-03 (16 px inputs), M-05 (primary
 *   action in the bottom 40 %) on /reserve and /bookings at 390 × 844.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19540 NEXT_PUBLIC_API_URL=http://127.0.0.1:19540 PW_PORT=19541 \
 *     npx playwright test e2e/w3-slot.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";
import { pinLanguage } from "./language";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const TEACHER = { id: process.env.REC_TEACHER_EMAIL ?? "ogretmen@smartsched.local", password: process.env.REC_TEACHER_PASSWORD ?? "Teacher-2026!" };
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
const DESKTOP = { viewport: { width: 1440, height: 900 }, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
const KEYS = ["unit", "block_minutes", "label", "period_name", "time_format", "density", "first_period", "last_period", "hide_short", "hide_weekend", "default_view_desktop", "default_view_phone", "min_length", "quick_span"];

test.describe.configure({ mode: "serial", timeout: 240_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

const ctx = {} as { api: APIRequestContext; admin: string; teacher: string };

async function token(identifier: string, password: string): Promise<string> {
  const body = identifier.includes("@") ? { email: identifier, password } : { username: identifier, password };
  const res = await ctx.api.post(`${API}/auth/login`, { data: body });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { access_token: string }).access_token;
}
const auth = (t: string) => ({ Authorization: `Bearer ${t}` });

async function resetDisplay() {
  const extra = Object.fromEntries(KEYS.map((k) => [`booking.slot_display.${k}`, ""]));
  const r = await ctx.api.put(`${API}/settings`, { headers: auth(ctx.admin), data: { extra } });
  expect(r.ok(), await r.text()).toBeTruthy();
}

async function cancelMine() {
  const mine = await (await ctx.api.get(`${API}/bookings/mine`, { headers: auth(ctx.teacher) })).json();
  const ids = (mine as { id: number }[]).map((b) => b.id);
  if (ids.length) await ctx.api.post(`${API}/bookings/cancel-multi`, { headers: auth(ctx.teacher), data: { booking_ids: ids, reason: null } });
}

async function open(browser: Browser, device: typeof DESKTOP | typeof PHONE, who: { id: string; password: string }): Promise<Page> {
  const context = await browser.newContext(device);
  const page = await context.newPage();
  await login(page, who.id, who.password);
  return page;
}

/** MOBILE.md M-02 (the lane's copy, centre re-probe ±22 px). */
const M02 = `(() => {
  const SEL = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=checkbox],[role=radio],[role=switch],[role=menuitem],[role=option],[role=slider],[tabindex]:not([tabindex="-1"])';
  const hits = (el, x, y) => { const t = document.elementFromPoint(x, y); return t && (t === el || el.contains(t)); };
  const bad = [];
  for (const el of document.querySelectorAll(SEL)) {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === "hidden" || el.closest('[aria-hidden="true"],[inert]')) continue;
    if (el.checkVisibility && !el.checkVisibility()) continue;
    if (r.width <= 1 && r.height <= 1 && el !== document.activeElement) continue;
    if (el.tagName === "A" && cs.display === "inline" && /^(P|LI|TD|SPAN|DD)$/.test(el.parentElement?.tagName ?? "")) continue;
    let w = r.width, h = r.height;
    const lab = el.labels?.[0]; if (lab) { const l = lab.getBoundingClientRect(); w = Math.max(w, l.width); h = Math.max(h, l.height); }
    if (w >= 44 && h >= 44) continue;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const VW = document.documentElement.clientWidth, VH = document.documentElement.clientHeight;
    if (!(cy > 22 && cy < VH - 22 && cx > 22 && cx < VW - 22)) continue;
    if ([[cx - 22, cy], [cx + 21, cy], [cx, cy - 22], [cx, cy + 21]].every(([x, y]) => hits(el, x, y))) continue;
    bad.push({ el: (el.dataset.testid || el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40), w: Math.round(w), h: Math.round(h) });
  }
  return bad;
})()`;

async function mobileChecks(page: Page, label: string) {
  // M-01: no horizontal page scroll
  const m01 = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  expect(m01.sw, `${label} M-01`).toBeLessThanOrEqual(m01.cw + 1);
  // M-02: 44 px targets
  expect(await page.evaluate(M02), `${label} M-02`).toEqual([]);
  // M-03: 16 px text in every visible field
  const small = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>("input:not([type=hidden]):not([type=checkbox]):not([type=radio]),select,textarea")]
      .filter((el) => el.getBoundingClientRect().width > 0 && !el.closest("[inert],[aria-hidden=true]"))
      .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
      .map((el) => el.dataset.testid || el.getAttribute("aria-label") || el.tagName),
  );
  expect(small, `${label} M-03`).toEqual([]);
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.admin = await token(ADMIN_EMAIL, ADMIN_PASSWORD);
  ctx.teacher = await token(TEACHER.id, TEACHER.password);
  await resetDisplay();
  await cancelMine();
});

test.afterAll(async () => {
  await resetDisplay();
  await cancelMine();
  await ctx.api.dispose();
});

test("SD: the admin changes the slot display; the teacher's grid and /reserve follow (1440)", async ({ browser }) => {
  const admin = await open(browser, DESKTOP, { id: ADMIN_EMAIL, password: ADMIN_PASSWORD });
  await admin.goto("/settings?tab=slots");
  const card = admin.getByTestId("slot-display-settings");
  await expect(card).toBeVisible();
  await expect(admin.getByTestId("slot-preview")).toBeVisible();
  await admin.getByTestId("sd-label-time").click();
  await admin.getByTestId("sd-density-compact").click();
  // the preview follows in the same frame: its header now reads a time range
  await expect(admin.getByTestId("sd-preview-grid-body").locator("thead th").nth(1)).toHaveText(/^\d{2}:\d{2}–\d{2}:\d{2}$/);
  await admin.getByTestId("sd-save").click();
  await expect(admin.getByText("Görünüm kaydedildi")).toBeVisible();
  const got = await (await ctx.api.get(`${API}/bookings/slot-display`, { headers: auth(ctx.teacher) })).json();
  expect(got).toMatchObject({ label: "time", density: "compact" });
  await admin.context().close();

  const teacher = await open(browser, DESKTOP, TEACHER);
  await teacher.goto("/bookings?lens=grid");
  const grid = teacher.getByTestId("booking-grid");
  await expect(grid).toBeVisible();
  await expect(grid.locator("thead th").nth(1)).toHaveText(/^\d{2}:\d{2}–\d{2}:\d{2}$/);
  await expect(grid.locator("tbody")).toHaveAttribute("data-density", "compact");
  const h = await grid.locator("tbody [data-cell]").first().evaluate((el) => el.getBoundingClientRect().height);
  expect(h).toBeLessThanOrEqual(33);
  // the accessible name still says the period
  expect(await grid.locator("tbody [data-cell]").first().getAttribute("aria-label")).toMatch(/P\d+|\d+\. ders/);
  // the first action is quick reserve
  await expect(teacher.getByTestId("bookings-quick-reserve")).toBeVisible();

  await teacher.goto("/reserve");
  const chip = teacher.getByTestId("qr-slots").getByRole("radio").first();
  await expect(chip).toBeVisible();
  await expect(chip).toContainText(/^\s*\d{2}:\d{2}/);
  await teacher.context().close();
  await resetDisplay();
});

async function bookInThreeTaps(page: Page, tap: (sel: ReturnType<Page["getByTestId"]>) => Promise<void>) {
  await page.goto("/reserve");
  await expect(page.getByTestId("quick-reserve")).toBeVisible();
  // a day and a slot are preselected
  await expect(page.getByTestId("qr-days").locator('[aria-checked="true"]')).toHaveCount(1);
  await expect(page.getByTestId("qr-slots").locator('[aria-checked="true"]')).toHaveCount(1);
  const rows = page.getByTestId("qr-rooms").locator('[role=radio][data-action="book"]');
  await expect(rows.first()).toBeVisible({ timeout: 20_000 });
  let taps = 0;
  const count = async (sel: ReturnType<Page["getByTestId"]>) => {
    taps++;
    await tap(sel);
  };
  const first = rows.first();
  const code = (await first.getAttribute("data-testid"))!.replace("qr-room-", "");
  await count(first);
  await expect(first).toHaveAttribute("aria-checked", "true");
  const submit = page.getByTestId("qr-submit");
  await expect(submit).toHaveText(/Rezerve et/);
  await count(submit);
  const receipt = page.getByTestId("qr-receipt");
  await expect(receipt).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("qr-receipt-title")).toHaveText("Rezerve edildi");
  await expect(page.getByTestId("qr-receipt-title")).toBeFocused();
  expect(taps).toBeLessThanOrEqual(3);
  const mine = (await (await ctx.api.get(`${API}/bookings/mine`, { headers: auth(ctx.teacher) })).json()) as { id: number; room_name: string }[];
  expect(mine.length).toBeGreaterThan(0);
  // Geri al: the real undo; the same room is selected again and focused
  await tap(page.getByTestId("qr-undo"));
  await expect(page.getByText("Rezervasyon geri alındı").first()).toBeVisible({ timeout: 20_000 });
  const after = (await (await ctx.api.get(`${API}/bookings/mine`, { headers: auth(ctx.teacher) })).json()) as unknown[];
  expect(after.length).toBe(mine.length - 1);
  await expect(page.getByTestId(`qr-room-${code}`)).toHaveAttribute("aria-checked", "true", { timeout: 20_000 });
  await expect.poll(() => page.evaluate(() => document.activeElement?.tagName)).not.toBe("BODY");
}

test("QR: a teacher books in ≤ 3 clicks from /reserve and undoes it (1440)", async ({ browser }) => {
  const page = await open(browser, DESKTOP, TEACHER);
  await bookInThreeTaps(page, (l) => l.click());
  await page.context().close();
});

test("QR: the same with one thumb at 390 × 844, and MOBILE M-01/02/03/05 on /reserve and /bookings", async ({ browser }) => {
  const page = await open(browser, PHONE, TEACHER);
  await bookInThreeTaps(page, (l) => l.tap());
  // M-05: the primary action sits in the bottom 40 % of the screen
  await page.getByTestId("qr-again").tap();
  const box = await page.getByTestId("qr-submit").boundingBox();
  expect(box).not.toBeNull();
  expect(box!.y).toBeGreaterThan(844 * 0.6);
  expect(box!.y + box!.height).toBeLessThanOrEqual(844);
  await mobileChecks(page, "/reserve");
  await page.getByTestId("qr-rooms").locator('[role=radio][data-action="book"]').first().tap();
  await page.getByTestId("qr-note-add").tap();
  await expect(page.getByTestId("qr-note")).toBeFocused();
  await mobileChecks(page, "/reserve (note open)");
  await page.goto("/bookings");
  await expect(page.getByTestId("free-slots").or(page.getByTestId("booking-grid"))).toBeVisible({ timeout: 20_000 });
  await mobileChecks(page, "/bookings");
  await page.context().close();
});
