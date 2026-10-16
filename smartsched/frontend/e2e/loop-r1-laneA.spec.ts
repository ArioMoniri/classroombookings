/**
 * Flow-loop round 1, lane A (docs/ROADMAP.md "Flow loop tickets — round 1", rounds/round-1-tickets.json) against the
 * REAL backend, gated E2E_REAL=1: mobile keyboard, phone sheets, shell primitives and the login form.
 *
 * - T-R1-02 the root viewport carries interactive-widget=resizes-content; with the book sheet's note focused and the
 *   viewport shrunk to 390 × 508 (the keyboard), the note sits between the sheet header and footer and "Talep et" /
 *   "Bu saati rezerve et" stays visible; the same for the wish sheet's room search on /moderation/me.
 * - T-R1-03 /admin/users › Yeni kullanıcı on a phone: before any scroll the save button is in the bottom 40 % and free
 *   (MOBILE M-05), the title and the close button stay visible after scrolling, the sheet is opaque.
 * - T-R1-04 the bell below md opens a full-width bottom sheet with rows ≥ 44 px.
 * - T-R1-05 Profil › Bildirimler as a TEACHER on a phone: no sideways scroller, no approver / room-owner rows.
 * - T-R1-06 /moderation/me as the linked academician: Taleplerim is a tab and the only aria-current item; the label
 *   leads the tab's text; Shift+? on Linux shows "Ctrl K"; the welcome toast is gone 10 s after login and never
 *   overlaps the tab bar; the touch user menu has no keyboard entry.
 * - T-R1-07 Turkish accessible names: no EN_WORDS hit in the book sheet, the user dialog, the withdraw dialog and a
 *   toast; the search trigger reads "Komut paleti (Ctrl+K)".
 * - T-R1-08 breadcrumbs: no "people" / "#" on the academician's own person page, no "recreate" on the preview; a
 *   focused crumb link shows a ring.
 * - T-R1-09 login: an empty Enter → two field messages, aria-invalid, no alert; a wrong password focuses the alert;
 *   the 429 lock belongs to one identifier; ?error=not_enabled reads as a state; limited.admin lands on /admin/users.
 *
 * Everything it makes is its own (a staff teacher, an academician linked to an unlinked instructor, a limited-admin
 * role and account, one pending wish); afterAll unlinks the instructor and withdraws the wish.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19210 NEXT_PUBLIC_API_URL=http://127.0.0.1:19210 PW_PORT=19211 \
 *     npx playwright test e2e/loop-r1-laneA.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Browser, type Locator, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";
import { pinLanguage } from "./language";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const STAFF = { username: `la.personel.${STAMP}`, email: `la.personel.${STAMP}@uni.edu.tr`, password: "Personel-2026!" };
const ACAD = { username: `la.akad.${STAMP}`, email: `la.akad.${STAMP}@uni.edu.tr`, password: "Akademisyen-2026!" };
const LIMITED = { username: `la.limited.${STAMP}`, email: `la.limited.${STAMP}@uni.edu.tr`, password: "Limited-2026!" };
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
const EN_WORDS = /\b(Close|Loading|Save|Cancel|Search|Submit|Next|Previous|Error|Something went wrong|Delete|Edit|Back|Open|Retry|Command or Control)\b/;

test.describe.configure({ mode: "serial", timeout: 240_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

const ctx = {} as { api: APIRequestContext; admin: string; acadId: number; instructorId: number | null; wishId: number | null; roleId: number | null; termId: number };

async function call<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token = ctx.admin): Promise<{ status: number; body: T }> {
  const res = await ctx.api.fetch(`${API}${path}`, { method, data: body, headers: { Authorization: `Bearer ${token}` } });
  const text = await res.text();
  return { status: res.status(), body: (text ? JSON.parse(text) : undefined) as T };
}
async function api<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token = ctx.admin): Promise<T> {
  const r = await call<T>(method, path, body, token);
  if (r.status >= 400) throw new Error(`${method} ${path} → ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}
async function token(identifier: string, password: string): Promise<string> {
  const body = identifier.includes("@") ? { email: identifier, password } : { username: identifier, password };
  const res = await ctx.api.post(`${API}/auth/login`, { data: body });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { access_token: string }).access_token;
}
const rect = (loc: Locator) => loc.evaluate((el) => { const r = el.getBoundingClientRect(); return { top: Math.round(r.top), bottom: Math.round(r.bottom), width: Math.round(r.width), height: Math.round(r.height) }; });
const isFree = (loc: Locator) => loc.evaluate((el) => { const r = el.getBoundingClientRect(); const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return t === el || el.contains(t); });
const clientHeight = (page: Page) => page.evaluate(() => document.documentElement.clientHeight);
const names = (page: Page) => page.evaluate(() => [...document.querySelectorAll("button, a, [role], input, textarea, select")].map((e) => (e.getAttribute("aria-label") || e.textContent || "").trim()).filter(Boolean));
async function phonePage(browser: Browser, id: string, password: string): Promise<Page> {
  const p = await (await browser.newContext(PHONE)).newPage();
  await login(p, id, password);
  return p;
}
/** /bookings on a phone: the free-slot list of the first bookable day ahead, then the book sheet */
async function openBookSheet(page: Page): Promise<void> {
  await page.goto("/bookings");
  let slot = page.getByTestId("free-slot").first();
  for (let i = 0; i < 6 && !(await slot.count()); i++) {
    await page.getByTestId("nav-next").click();
    await page.waitForTimeout(800);
    slot = page.getByTestId("free-slot").first();
  }
  await slot.click();
  await expect(page.getByTestId("book-sheet")).toBeVisible();
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.admin = await token(ADMIN_EMAIL, ADMIN_PASSWORD);
  await api("POST", "/users", { username: STAFF.username, email: STAFF.email, firstname: "P.", lastname: "T.", role: "TEACHER", password: STAFF.password });
  await api("PUT", "/auth/profile", { language: "tr" }, await token(STAFF.username, STAFF.password));
  const made = await api<{ id: number }>("POST", "/users", { username: ACAD.username, email: ACAD.email, firstname: "A.", lastname: "T.", role: "TEACHER", password: ACAD.password });
  ctx.acadId = made.id;
  const acad = await token(ACAD.username, ACAD.password);
  await api("PUT", "/auth/profile", { language: "tr" }, acad);
  // a limited user administrator (F-11 S03): user management only
  const roles = await api<{ id: number; name: string }[]>("GET", "/roles");
  const existing = roles.find((r) => r.name === `Kullanıcı yöneticisi ${STAMP}`);
  const role = existing ?? (await api<{ id: number }>("POST", "/roles", { name: `Kullanıcı yöneticisi ${STAMP}`, permissions: ["setup.users", "setup.roles", "room.view"] }));
  ctx.roleId = role.id;
  await api("POST", "/users", { username: LIMITED.username, email: LIMITED.email, firstname: "L.", lastname: "A.", role_id: role.id, password: LIMITED.password });
  // the academician: linked to an instructor of the current term nobody is linked to yet, with a pending wish
  const me = await api<{ current_term: { id: number } | null }>("GET", "/moderation/me");
  ctx.termId = me.current_term!.id;
  const people = await api<{ items: { id: number; requests: number; linked_user: boolean }[] }>("GET", `/terms/${ctx.termId}/moderation/people`);
  const free = people.items.filter((p) => !p.linked_user && p.requests >= 3).sort((a, b) => a.requests - b.requests);
  ctx.instructorId = free[0]?.id ?? null;
  ctx.wishId = null;
  if (ctx.instructorId) {
    await api("PUT", `/auth/sso/admin/users/${made.id}/instructor`, { instructor_id: ctx.instructorId });
    const m = await api<{ items: { request_id: number }[] }>("GET", `/moderation/me/matchings?term_id=${ctx.termId}`, undefined, acad);
    const first = m.items[0];
    if (first) {
      const w = await call<{ items?: { id: number }[] }>("POST", "/moderation/me/preferences", { kind: "building_preference", request_ids: [first.request_id], buildings: ["A"] }, acad);
      ctx.wishId = w.status < 300 ? (w.body.items?.[0]?.id ?? null) : null;
    }
  }
});

test.afterAll(async () => {
  if (!ctx.api) return;
  if (ctx.wishId) await call("DELETE", `/moderation/me/preferences/${ctx.wishId}`, undefined, await token(ACAD.username, ACAD.password)).catch(() => undefined);
  if (ctx.acadId && ctx.instructorId) await call("PUT", `/auth/sso/admin/users/${ctx.acadId}/instructor`, { instructor_id: null });
  await ctx.api.dispose();
});

test("T-R1-02 the keyboard viewport: the root meta resizes content; the book-sheet note and the wish-sheet room search clear the footer at 390 × 508", async ({ browser }) => {
  const page = await phonePage(browser, STAFF.username, STAFF.password);
  expect(await page.evaluate(() => document.querySelector("meta[name=viewport]")!.getAttribute("content"))).toContain("interactive-widget=resizes-content");
  await openBookSheet(page);
  const sheet = page.getByTestId("book-sheet");
  await page.locator("#book-notes").focus();
  await page.setViewportSize({ width: 390, height: 508 });
  await page.waitForTimeout(700);
  const note = await rect(page.locator("#book-notes"));
  const header = await rect(sheet.locator("[data-slot=sheet-header]"));
  const footer = await rect(sheet.locator("[data-slot=sheet-footer]"));
  const submit = page.getByTestId("book-submit");
  expect(note.top, JSON.stringify({ note, header })).toBeGreaterThanOrEqual(header.bottom - 1);
  expect(note.bottom, JSON.stringify({ note, footer })).toBeLessThanOrEqual(footer.top + 1);
  await expect(submit).toBeVisible();
  expect((await rect(submit)).bottom).toBeLessThanOrEqual(await clientHeight(page));
  expect(await isFree(submit)).toBe(true);
  await page.context().close();

  test.skip(!ctx.instructorId, "no unlinked instructor with requests in the current term");
  const ap = await phonePage(browser, ACAD.username, ACAD.password);
  await ap.goto("/moderation/me");
  await ap.getByTestId("wish-open").click();
  const ws = ap.getByTestId("wish-sheet");
  await expect(ws).toBeVisible();
  await ap.getByTestId("wish-room-search").focus();
  await ap.setViewportSize({ width: 390, height: 508 });
  await ap.waitForTimeout(700);
  const search = await rect(ap.getByTestId("wish-room-search"));
  const whdr = await rect(ws.locator("[data-slot=sheet-header]"));
  const wftr = await rect(ws.locator("[data-slot=sheet-footer]"));
  expect(search.top, JSON.stringify({ search, whdr })).toBeGreaterThanOrEqual(whdr.bottom - 1);
  expect(search.bottom, JSON.stringify({ search, wftr })).toBeLessThanOrEqual(wftr.top + 1);
  await expect(ap.getByTestId("wish-submit")).toBeVisible();
  await expect(ap.getByTestId("wish-submit")).toHaveText(/Onaya gönder/);
  await ap.context().close();
});

test("T-R1-03 phone user dialog: save in thumb reach before any scroll, title and close stay, opaque sheet (F-11 S01, M-05)", async ({ browser }) => {
  const page = await phonePage(browser, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/users");
  await page.getByTestId("users-new").click();
  const dlg = page.getByTestId("user-dialog");
  await expect(dlg).toBeVisible();
  await page.waitForTimeout(400);
  const vh = await clientHeight(page);
  const save = page.getByTestId("user-save");
  const b = await rect(save);
  expect(b.top, JSON.stringify(b)).toBeGreaterThanOrEqual(0.6 * vh - 1);
  expect(b.bottom).toBeLessThanOrEqual(vh);
  expect(await isFree(save)).toBe(true);
  const title = dlg.locator("[data-slot=dialog-title]");
  const close = dlg.locator("[data-slot=dialog-close]").first();
  await expect(title).toBeVisible();
  await expect(close).toBeVisible();
  await expect(close).toHaveAccessibleName("Kapat");
  const surface = await dlg.evaluate((el) => { const cs = getComputedStyle(el); return { bg: cs.backgroundColor, backdrop: cs.backdropFilter }; });
  expect(surface.bg).toMatch(/^rgb\(/); // no alpha channel: the tab bar cannot show through
  expect(surface.backdrop === "none" || surface.backdrop === "").toBe(true);
  // the body scrolls, the three stay
  await dlg.evaluate((el) => { const body = el.querySelector("[data-slot=dialog-body]"); if (body) body.scrollTop = 1e6; });
  await page.waitForTimeout(300);
  const b2 = await rect(save);
  expect(b2.top).toBeGreaterThanOrEqual(0.6 * vh - 1);
  expect(b2.bottom).toBeLessThanOrEqual(vh);
  await expect(title).toBeInViewport();
  await expect(close).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
  await page.context().close();
});

test("T-R1-04 the bell on a phone opens a full-width bottom sheet with 44 px rows and hands focus back", async ({ browser }) => {
  const page = await phonePage(browser, STAFF.username, STAFF.password);
  await page.goto("/my-bookings");
  const bell = page.locator("[data-testid=notification-bell]:visible");
  await bell.click();
  const panel = page.getByTestId("notification-panel");
  await expect(panel).toBeVisible();
  await page.waitForTimeout(400);
  expect(await panel.getAttribute("data-variant")).toBe("sheet");
  const pr = await rect(panel);
  expect(pr.width).toBeGreaterThanOrEqual(388);
  expect(Math.abs(pr.bottom - (await clientHeight(page)))).toBeLessThanOrEqual(2);
  const rows = await panel.locator("[data-testid^=notification-]:not([data-testid=notification-panel])").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height));
  for (const h of rows) expect(h).toBeGreaterThanOrEqual(44);
  const badge = page.getByTestId("notification-count");
  if (await badge.count()) expect(await badge.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(11);
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  expect(await page.evaluate(() => document.activeElement?.getAttribute("data-testid"))).toBe("notification-bell");
  await page.context().close();
});

test("T-R1-05 Profil › Bildirimler as a TEACHER on a phone: cards, no sideways table, no approver or room-owner rows", async ({ browser }) => {
  const page = await phonePage(browser, STAFF.username, STAFF.password);
  await page.goto("/profile#notifications");
  const prefs = page.getByTestId("notification-prefs");
  await expect(prefs.getByTestId("prefs-group-approvals")).toBeVisible({ timeout: 20_000 });
  await prefs.locator("details").evaluateAll((ds) => ds.forEach((d) => ((d as HTMLDetailsElement).open = true)));
  expect(await prefs.locator("table").count()).toBe(0);
  expect(await prefs.locator("[data-testid^=prefs-cards-]").count()).toBeGreaterThan(0);
  const scrollers = await prefs.evaluate((el) => [...el.querySelectorAll("*")].filter((e) => /(auto|scroll)/.test(getComputedStyle(e).overflowX) && e.scrollWidth > e.clientWidth + 1).length);
  expect(scrollers).toBe(0);
  const text = await prefs.innerText();
  expect(text).not.toMatch(/Onayımı bekleyen yeni oda talepleri/);
  expect(text).not.toMatch(/Sorumlu olduğum odaya/);
  // every switch row is a 44 px label row
  const rows = await prefs.locator("[data-testid^=prefs-cards-] li li").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height));
  for (const h of rows) expect(h).toBeGreaterThanOrEqual(44);
  await page.context().close();
});

test("T-R1-06 tabs, user menu, shortcuts and the welcome toast", async ({ browser }) => {
  test.skip(!ctx.instructorId, "no unlinked instructor with requests in the current term");
  const page = await phonePage(browser, ACAD.username, ACAD.password);
  // right after login: the welcome toast sits above the tab bar
  const toast = page.locator("[data-sonner-toast]").first();
  if (await toast.count()) {
    const t = await rect(toast);
    const bar = await rect(page.locator("nav[aria-label=Sekmeler]"));
    expect(t.bottom <= bar.top || t.top >= bar.bottom, JSON.stringify({ t, bar })).toBe(true);
  }
  await page.goto("/moderation/me");
  const tabs = page.locator("nav[aria-label=Sekmeler] a, nav[aria-label=Sekmeler] button");
  await expect(page.getByTestId("tab-nav-moderation-me")).toBeVisible();
  const info = await tabs.evaluateAll((els) => els.map((e) => ({ id: e.getAttribute("data-testid"), text: (e as HTMLElement).innerText.trim(), name: e.getAttribute("aria-label") ?? "", current: e.getAttribute("aria-current") })));
  expect(info.filter((t) => t.current === "page").map((t) => t.id)).toEqual(["tab-nav-moderation-me"]);
  for (const t of info) expect(t.text.startsWith(t.name.split(",")[0]!), JSON.stringify(t)).toBe(true);
  await page.goto("/profile");
  await expect(page.getByTestId("open-drawer")).toHaveAttribute("aria-current", "page");
  expect(await page.locator("nav[aria-label=Sekmeler] [aria-current]").count()).toBe(1);
  // ten seconds after login, no toast is left
  await page.waitForTimeout(Math.max(0, 10_000 - 6_000));
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 12_000 });
  await page.getByTestId("user-menu").click();
  const items = page.locator("[role=menuitem]");
  await expect(items.first()).toBeVisible();
  expect(await items.evaluateAll((els) => els.map((e) => (e as HTMLElement).innerText))).not.toContainEqual(expect.stringMatching(/Klavye/));
  await page.context().close();

  // desktop (Linux): Shift+? shows Ctrl K and g t → Taleplerim; the search trigger is named in Turkish
  const d = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "tr-TR", timezoneId: "Europe/Istanbul" })).newPage();
  await login(d, ACAD.username, ACAD.password);
  await d.goto("/moderation/me");
  await expect(d.getByTestId("open-palette")).toHaveAttribute("aria-label", "Komut paleti (Ctrl+K)");
  await d.keyboard.press("Shift+?");
  const sheet = d.getByTestId("shortcuts-sheet");
  await expect(sheet).toBeVisible();
  const text = (await sheet.innerText()).replace(/\s+/g, " ");
  expect(text).toMatch(/Ctrl K/);
  expect(text).not.toContain("⌘");
  expect(text).toContain("Taleplerim sayfasına git");
  expect(await sheet.locator("kbd").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")))).toContain("G sonra T");
  await d.context().close();
});

test("T-R1-07 Turkish accessible names in the shared dialogs and toasts (F-13 A01)", async ({ browser }) => {
  for (const mobile of [false, true]) {
    const page = mobile ? await phonePage(browser, STAFF.username, STAFF.password) : await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "tr-TR" })).newPage();
    if (!mobile) await login(page, STAFF.username, STAFF.password);
    const toastClose = page.locator("[data-sonner-toast] button[aria-label]").first();
    if (await toastClose.count()) expect(await toastClose.getAttribute("aria-label")).toBe("Bildirimi kapat");
    expect((await names(page)).filter((n) => EN_WORDS.test(n))).toEqual([]);
    await openBookSheet(page);
    await expect(page.getByTestId("book-sheet").locator("[data-slot=sheet-close]")).toHaveAccessibleName("Kapat");
    expect((await names(page)).filter((n) => EN_WORDS.test(n))).toEqual([]);
    await page.context().close();
  }
  const adm = await phonePage(browser, ADMIN_EMAIL, ADMIN_PASSWORD);
  await adm.goto("/admin/users");
  await adm.getByTestId("users-new").click();
  await expect(adm.getByTestId("user-dialog")).toBeVisible();
  expect((await names(adm)).filter((n) => EN_WORDS.test(n))).toEqual([]);
  await adm.context().close();
  if (ctx.wishId) {
    const ap = await phonePage(browser, ACAD.username, ACAD.password);
    await ap.goto("/moderation/me");
    await ap.getByTestId("wish-withdraw").first().click();
    await expect(ap.getByTestId("wish-withdraw-confirm")).toBeVisible();
    expect((await names(ap)).filter((n) => EN_WORDS.test(n))).toEqual([]);
    await ap.keyboard.press("Escape");
    await ap.context().close();
  }
});

test("T-R1-08 breadcrumbs name the pages, never a route word or an id; crumb links show a focus ring", async ({ browser }) => {
  test.skip(!ctx.instructorId, "no unlinked instructor with requests in the current term");
  const d = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "tr-TR" })).newPage();
  await login(d, ACAD.username, ACAD.password);
  await d.goto(`/moderation/people/${ctx.instructorId}`);
  const crumbs = d.locator("nav[aria-label=Konum] li");
  await expect(crumbs.last()).toHaveText("Geçmişim");
  const texts = await crumbs.evaluateAll((els) => els.map((e) => (e as HTMLElement).innerText.trim()).filter(Boolean));
  expect(texts.join(" / ")).toBe("Taleplerim / Geçmişim");
  const link = d.locator("nav[aria-label=Konum] a").first();
  await link.focus();
  const ring = await d.evaluate(() => { const cs = getComputedStyle(document.activeElement!); return { outline: cs.outlineStyle, width: parseFloat(cs.outlineWidth) || 0 }; });
  expect(ring.outline).not.toBe("none");
  expect(ring.width).toBeGreaterThanOrEqual(2);
  await d.context().close();
  const adm = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "tr-TR" })).newPage();
  await login(adm, ADMIN_EMAIL, ADMIN_PASSWORD);
  await adm.goto("/moderation/recreate/1");
  await expect(adm.locator("nav[aria-label=Konum] li").last()).toHaveText("Yeniden çözüm önizlemesi");
  await adm.goto(`/moderation/people/${ctx.instructorId}`);
  const planner = await adm.locator("nav[aria-label=Konum] li").evaluateAll((els) => els.map((e) => (e as HTMLElement).innerText.trim()).filter(Boolean));
  expect(planner).toEqual(["Moderasyon", "Kişiler", "Kişi"]);
  await adm.context().close();
});

test("T-R1-09 login: field messages, focus on the alert, a per-identifier lock, SSO off as a state, the limited admin's landing page (F-12 S02, F-11 S04)", async ({ browser }) => {
  for (const mobile of [false, true]) {
    const page = await (await browser.newContext(mobile ? PHONE : { viewport: { width: 1440, height: 900 }, locale: "tr-TR" })).newPage();
    await page.goto("/login?method=local");
    await page.getByTestId("login-identifier").focus();
    await page.keyboard.press("Enter");
    await expect(page.getByTestId("login-identifier-required")).toHaveText("Kullanıcı adı veya e-posta gerekli");
    await expect(page.getByTestId("login-password-required")).toHaveText("Parola gerekli");
    await expect(page.getByTestId("login-identifier")).toHaveAttribute("aria-invalid", "true");
    await expect(page.getByTestId("login-password")).toHaveAttribute("aria-invalid", "true");
    await expect(page.getByTestId("login-identifier")).toHaveAttribute("aria-describedby", /./);
    await expect(page.getByTestId("login-identifier")).toHaveAttribute("inputmode", "email");
    expect(await page.locator("[role=alert]").count()).toBe(0);
    await page.getByTestId("login-identifier").fill(STAFF.username);
    await page.getByTestId("login-password").fill("wrong-password");
    await page.getByTestId("login-submit").click();
    await expect(page.getByTestId("login-error")).toBeFocused();
    await page.context().close();
  }
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "tr-TR" })).newPage();
  await page.goto("/login?method=local");
  // eleven failures for a throwaway identifier → 429; another identifier is not locked
  const X = `la.lock.${STAMP}`;
  let status = 0;
  for (let i = 0; i < 11 && status !== 429; i++) {
    await page.getByTestId("login-identifier").fill(X);
    await page.getByTestId("login-password").fill("nope");
    const [res] = await Promise.all([page.waitForResponse((r) => r.url().includes("/auth/login")), page.getByTestId("login-submit").click()]);
    status = res.status();
  }
  expect(status).toBe(429);
  await expect(page.getByTestId("login-submit")).toBeDisabled();
  await page.getByTestId("login-identifier").fill(STAFF.username);
  await expect(page.getByTestId("login-submit")).toBeEnabled();
  // SSO switched off: a state, no support code
  await page.goto("/login?error=not_enabled&ref=S-9");
  await expect(page.getByTestId("signin-notice-not_enabled")).toHaveText("Microsoft ile giriş bu kurumda henüz açık değil.");
  expect(await page.getByText("S-9").count()).toBe(0);
  // the limited admin lands on the first page they may use
  const forbidden: string[] = [];
  page.on("response", (r) => { if (r.status() === 403) forbidden.push(r.url()); });
  await login(page, LIMITED.username, LIMITED.password);
  await page.waitForTimeout(1500);
  expect(new URL(page.url()).pathname).toBe("/admin/users");
  expect(forbidden).toEqual([]);
  await page.context().close();
});
