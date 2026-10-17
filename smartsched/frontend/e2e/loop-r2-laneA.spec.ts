/**
 * Flow-loop round 2, lane A (docs/ROADMAP.md "Flow loop tickets — round 2", rounds/round-2-tickets.json) against the
 * REAL backend, gated E2E_REAL=1: shell, UI primitives, login and auth.
 *
 * - T-R2-05 real 44 px boxes on touch (MOBILE M-02 with the centre re-probe): /profile#notifications switches, the
 *   save toast's close button, the /bookings recurring date table's segments, the /find-room filter chips, and the
 *   login locale buttons have an accessible name (M-11).
 * - T-R2-02 a confirm dialog (kit ConfirmDialog, /admin/holidays) is an aria-modal alertdialog; ten Tabs never leave
 *   it at 1440 and 768; Esc returns focus to the opener.
 * - T-R2-03 a forced password change lands on `next` within 2 s, the form never comes back, GET /me says false.
 * - T-R2-04 phone tab-bar labels fit their column (scrollWidth ≤ clientWidth, no overlap), the 99+ badge stays inside.
 * - T-R2-06 /reset-password: no LDAP hint, "24 saat", a 2-character code is the coded Turkish 400.
 * - T-R2-07 with reduced motion (emulated and in-app) the book sheet and the bell sheet do not slide: two frames after
 *   the open translate is none, opacity 1, no running animation.
 * - T-R2-08 a teacher's /moderation/me crumb is "Taleplerim" alone; the admin's trail keeps "Moderasyon".
 * - T-R2-01 at 390 × 508 (keyboard open) /profile "Yeni parola" and /find-room "Kaç kişi" are uncovered after the tap.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19310 NEXT_PUBLIC_API_URL=http://127.0.0.1:19310 PW_PORT=19311 \
 *     npx playwright test e2e/loop-r2-laneA.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";
import { pinLanguage } from "./language";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const TEACHER = { id: process.env.REC_TEACHER_EMAIL ?? "ogretmen@smartsched.local", password: process.env.REC_TEACHER_PASSWORD ?? "Teacher-2026!" };
const FORCED = { username: `la2.forced.${STAMP}`, email: `la2.forced.${STAMP}@uni.edu.tr`, password: "Forced-2026!", next: "Flow-2026!pw" };
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
const DESKTOP = { viewport: { width: 1440, height: 900 }, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
const TABLET = { viewport: { width: 768, height: 1024 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };

test.describe.configure({ mode: "serial", timeout: 240_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

const ctx = {} as { api: APIRequestContext; admin: string };
async function token(identifier: string, password: string): Promise<string> {
  const body = identifier.includes("@") ? { email: identifier, password } : { username: identifier, password };
  const res = await ctx.api.post(`${API}/auth/login`, { data: body });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { access_token: string }).access_token;
}

/** MOBILE.md M-02 (the lane's copy): offenders among the visible controls, with the ±22 px centre re-probe. */
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
    const inView = cy > 22 && cy < VH - 22 && cx > 22 && cx < VW - 22;
    if (!inView) continue;
    if ([[cx - 22, cy], [cx + 21, cy], [cx, cy - 22], [cx, cy + 21]].every(([x, y]) => hits(el, x, y))) continue;
    bad.push({ el: (el.dataset.testid || el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40), w: Math.round(w), h: Math.round(h) });
  }
  return bad;
})()`;
const m02 = (page: Page) => page.evaluate(M02) as Promise<{ el: string; w: number; h: number }[]>;
/** M-02 over the whole document in 0.8 × clientHeight steps (MOBILE.md: the probe only sees the viewport). */
async function m02Scrolled(page: Page): Promise<{ el: string; w: number; h: number }[]> {
  const out: { el: string; w: number; h: number }[] = [];
  const H = await page.evaluate(() => document.documentElement.clientHeight);
  const total = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0; y < total; y += Math.round(H * 0.8)) {
    await page.evaluate((y) => window.scrollTo(0, y), y);
    await page.waitForTimeout(120);
    out.push(...(await m02(page)));
  }
  return out;
}
const assertTouch = async (page: Page) => expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(true);
const focusText = (page: Page) => page.evaluate(() => { const a = document.activeElement as HTMLElement | null; return a ? (a.dataset.testid || a.getAttribute("aria-label") || a.textContent || a.tagName).trim().slice(0, 40) : ""; });

async function newPage(browser: Browser, opts: Record<string, unknown>, id: string, password: string): Promise<Page> {
  const p = await (await browser.newContext(opts)).newPage();
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
  await expect(page.locator("[data-slot=sheet-content],[data-slot=dialog-content]").last()).toBeVisible();
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.admin = await token(ADMIN_EMAIL, ADMIN_PASSWORD);
});
test.afterAll(async () => {
  await ctx.api?.dispose();
});

test("T-R2-05 real 44 px boxes on touch: switches, the toast close, the recurring date table, the filter chips, the locale names", async ({ browser }) => {
  const page = await newPage(browser, PHONE, TEACHER.id, TEACHER.password);
  await page.goto("/profile#notifications");
  await page.waitForTimeout(1200);
  await assertTouch(page);
  const switches = await page.locator("[role=switch]").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
  expect(switches.length).toBeGreaterThan(3);
  expect(switches.every((h) => h >= 44), `switch heights ${switches.join(",")}`).toBe(true);
  expect(await m02Scrolled(page), "M-02 /profile#notifications").toEqual([]);
  // the save toast's close button
  await page.goto("/profile");
  await page.getByTestId("profile-save").first().click();
  const close = page.locator("[data-sonner-toast] [data-close-button]").first();
  await expect(close).toBeVisible();
  const r = await close.evaluate((el) => { const b = el.getBoundingClientRect(); const t = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2); return { w: Math.round(b.width), h: Math.round(b.height), hit: t === el || el.contains(t) }; });
  expect(r).toEqual({ w: 44, h: 44, hit: true });
  expect(await close.getAttribute("aria-label")).toBe("Bildirimi kapat");
  // /find-room filters sheet: chips
  await page.goto("/find-room");
  const fo = page.getByTestId("fr-filters-open");
  if (await fo.count()) {
    await fo.click();
    await expect(page.getByTestId("fr-filters-sheet")).toBeVisible();
    await assertTouch(page);
    expect(await m02(page), "M-02 /find-room filters sheet").toEqual([]);
  }
  await page.context().close();

  // the recurring date table (admin, who may book series): every segment is a 44 px box
  const ap = await newPage(browser, PHONE, ADMIN_EMAIL, ADMIN_PASSWORD);
  await openBookSheet(ap);
  const sheet = ap.locator("[data-slot=sheet-content],[data-slot=dialog-content]").last();
  const recur = sheet.getByRole("tab", { name: /Her hafta|Tekrar/ }).or(sheet.getByRole("radio", { name: /Her hafta|Tekrar/ })).first();
  if (await recur.count()) {
    await recur.click();
    await ap.getByTestId("recur-preview-btn").click();
    await expect(ap.getByTestId("recur-preview")).toBeVisible({ timeout: 20_000 });
    await assertTouch(ap);
    const segs = await ap.getByTestId("recur-preview").locator("[role=tab],[role=radio]").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
    expect(segs.length).toBeGreaterThan(0);
    expect(segs.every((h) => h >= 44), `segment heights ${segs.join(",")}`).toBe(true);
    expect(await m02(ap), "M-02 recurring sheet").toEqual([]);
  }
  await ap.context().close();

  // the login card's locale toggle: an accessible name, not only a title (M-11)
  const lp = await (await browser.newContext(PHONE)).newPage();
  await lp.goto("/login?method=local");
  const names = await lp.locator("[data-testid^=locale-option-]").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")));
  expect(names).toEqual(expect.arrayContaining(["Türkçe", "English"]));
  await lp.context().close();
});

test("T-R2-02 the confirm dialog is an aria-modal alertdialog that traps Tab (1440 keyboard, 768 tablet) and Esc returns focus", async ({ browser }) => {
  for (const opts of [DESKTOP, TABLET]) {
    const page = await newPage(browser, opts, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/admin/holidays");
    const del = page.getByRole("button", { name: /\bsil\b/i }).first();
    await expect(del).toBeVisible();
    await del.focus();
    await page.keyboard.press("Enter");
    const dlg = page.locator("[role=alertdialog]").last();
    await expect(dlg).toBeVisible();
    expect(await dlg.getAttribute("aria-modal")).toBe("true");
    for (let i = 0; i < 10; i++) {
      await page.keyboard.press("Tab");
      expect(await page.evaluate(() => !!document.activeElement?.closest("[role=alertdialog]")), `Tab ${i + 1} left the dialog at ${opts.viewport.width}`).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dlg).toBeHidden();
    expect(await focusText(page)).toMatch(/sil/i);
    await page.context().close();
  }
});

test("T-R2-03 a forced password change leaves /login/change-password for `next` within 2 s; /me says false", async ({ browser }) => {
  const created = await ctx.api.post(`${API}/users`, { headers: { Authorization: `Bearer ${ctx.admin}` }, data: { username: FORCED.username, email: FORCED.email, full_name: "Zorunlu Değişim", role: "TEACHER", password: FORCED.password, force_password_reset: true } });
  expect(created.status(), await created.text()).toBe(201);
  for (const opts of [DESKTOP, PHONE]) {
    const page = await (await browser.newContext(opts)).newPage();
    await page.goto("/login?method=local&next=%2Fmy-bookings");
    await page.getByTestId("login-identifier").fill(FORCED.email);
    await page.getByTestId("login-password").fill(FORCED.password);
    await page.getByTestId("login-submit").click();
    await page.waitForURL(/\/login\/change-password/, { timeout: 30_000 });
    await page.locator("#cur").fill(FORCED.password);
    await page.locator("#new").fill(FORCED.next);
    await page.locator("#again").fill(FORCED.next);
    const saved = page.waitForResponse((r) => r.url().includes("/auth/change-password") && r.request().method() === "POST");
    await page.getByRole("button", { name: "Kaydet ve devam et" }).click();
    expect((await saved).status()).toBe(200);
    const t0 = Date.now(); // the ticket's clock starts at the 200 (the re-login and the /me refetch come after it)
    await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 15_000 });
    expect(Date.now() - t0).toBeLessThan(2000);
    await expect(page.getByText("Parola değiştirildi")).toBeVisible();
    await page.waitForTimeout(2500);
    expect(new URL(page.url()).pathname).not.toContain("/login");
    const me = await page.evaluate(async () => (await fetch("/api/v1/auth/me")).json() as Promise<{ force_password_reset: boolean }>);
    expect(me.force_password_reset).toBe(false);
    await page.context().close();
    // the next viewport starts from the changed password: reset the flag through the admin
    const id = ((await created.json()) as { id: number }).id;
    await ctx.api.put(`${API}/users/${id}`, { headers: { Authorization: `Bearer ${ctx.admin}` }, data: { password: FORCED.password, force_password_reset: true } });
  }
});

test("T-R2-04 phone tab-bar labels fit their column, nothing overlaps, the 99+ badge stays inside", async ({ browser }) => {
  const M09 = `(() => { const nr = document.querySelector('nav[aria-label="Sekmeler"]').getBoundingClientRect(); return [...document.querySelectorAll('nav[aria-label="Sekmeler"] a, nav[aria-label="Sekmeler"] button')].map((e) => { const lab = e.querySelector('[data-slot=tab-label]'); const b = e.querySelector('[data-testid=tab-badge]'); const lr = lab.getBoundingClientRect(); const br = b?.getBoundingClientRect(); return { text: e.innerText.trim(), name: e.getAttribute('aria-label'), sw: lab.scrollWidth, cw: lab.clientWidth, left: lr.left, right: lr.right, badge: br ? { inside: br.left >= nr.left && br.right <= nr.right && br.top >= nr.top && br.bottom <= nr.bottom, text: b.textContent } : null }; }); })()`;
  type Row = { text: string; name: string; sw: number; cw: number; left: number; right: number; badge: { inside: boolean; text: string } | null };
  for (const [id, pw, route] of [[TEACHER.id, TEACHER.password, "/my-bookings"], [ADMIN_EMAIL, ADMIN_PASSWORD, "/requests"]] as const) {
    const page = await newPage(browser, PHONE, id, pw);
    await page.goto(route);
    await expect(page.locator('nav[aria-label="Sekmeler"]')).toBeVisible();
    // the tabs follow the permission list and the counts (GET /auth/me, /requests): wait for the full set
    await expect.poll(async () => ((await page.evaluate(M09)) as Row[]).length, { timeout: 15_000 }).toBeGreaterThanOrEqual(4);
    const rows = (await page.evaluate(M09)) as Row[];
    for (const r of rows) {
      expect(r.sw, `${route} label '${r.text}' scrollWidth ${r.sw} > clientWidth ${r.cw}`).toBeLessThanOrEqual(r.cw);
      expect(r.text.startsWith(r.name.split(",")[0]!), `${route} innerText '${r.text}' starts with '${r.name}'`).toBe(true);
    }
    for (let i = 0; i < rows.length - 1; i++) expect(rows[i]!.right, `${route} '${rows[i]!.text}' overlaps '${rows[i + 1]!.text}'`).toBeLessThanOrEqual(rows[i + 1]!.left + 0.5);
    if (route === "/requests") {
      const badge = rows.find((r) => r.badge);
      if (badge) {
        expect(badge.badge!.inside).toBe(true);
        expect(badge.badge!.text).toMatch(/^(\d{1,2}|99\+)$/);
      }
    }
    await page.context().close();
  }
});

test("T-R2-06 /reset-password: own hint without LDAP, '24 saat', a short code is the coded Turkish 400", async ({ browser }) => {
  const page = await (await browser.newContext(DESKTOP)).newPage();
  await page.goto("/reset-password");
  await page.getByLabel("E-posta ya da kullanıcı adı").fill("kimse@uni.edu.tr");
  await page.getByRole("button", { name: "Kod gönder" }).click();
  await expect(page.getByTestId("reset-requested")).toContainText("24 saat");
  await page.getByRole("button", { name: "Kodum var" }).click();
  const form = page.getByLabel("Tek kullanımlık kod").locator("xpath=ancestor::form");
  const text = await form.innerText();
  expect(text).not.toMatch(/LDAP|Dizin/);
  expect(text).toContain("En az 8 karakter.");
  await page.context().close();
  const r = await ctx.api.post(`${API}/auth/password-reset/confirm`, { data: { token: "12", password: "Flow-2026!pw" } });
  expect(r.status()).toBe(400);
  const body = await r.text();
  expect(body).toContain("Kod hatalı ya da süresi dolmuş. Yenisini isteyin.");
  expect(body).not.toContain("String should");
});

test("T-R2-07 with reduced motion the book sheet and the bell sheet do not slide in (OS and in-app), 1440 + 390", async ({ browser }) => {
  const PROBE = `(() => new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(() => { const el = [...document.querySelectorAll('[data-slot=sheet-content],[data-slot=dialog-content]')].at(-1); const cs = getComputedStyle(el); res({ translate: cs.translate, transform: cs.transform, opacity: cs.opacity, running: el.getAnimations().filter((a) => a.playState === 'running').length }); }))))()`;
  type P = { translate: string; transform: string; opacity: string; running: number };
  for (const base of [DESKTOP, PHONE]) {
    for (const inApp of [false, true]) {
      const page = await newPage(browser, { ...base, reducedMotion: inApp ? "no-preference" : "reduce" }, TEACHER.id, TEACHER.password);
      if (inApp) {
        // the in-app switch (Ayarlar › Görünüm › Hareketi azalt) is stored per user; the shell's init script applies it
        await page.evaluate(async () => {
          const me = (await (await fetch("/api/v1/auth/me")).json()) as { id: number };
          localStorage.setItem("smartsched.appearance.lastUser", String(me.id));
          localStorage.setItem(`smartsched.appearance.${me.id}`, JSON.stringify({ motion: "reduced", transparency: "system" }));
        });
      }
      await page.goto("/bookings");
      if (inApp) await expect(page.locator('html[data-motion="reduced"]')).toHaveCount(1);
      // a free slot: the phone's free-slot list, the desktop grid's first available cell
      const free = () => (base === PHONE ? page.getByTestId("free-slot") : page.locator('[data-tone="available"]')).first();
      await page.waitForTimeout(800);
      for (let i = 0; i < 6 && !(await free().count()); i++) { await page.getByTestId("nav-next").click(); await page.waitForTimeout(800); }
      await free().click();
      await expect(page.locator("[data-slot=sheet-content],[data-slot=dialog-content]").last()).toBeVisible();
      const book = (await page.evaluate(PROBE)) as P;
      expect(book.translate, `book sheet ${base.viewport.width} inApp=${inApp}`).toBe("none");
      expect(book.opacity).toBe("1");
      expect(book.running).toBe(0);
      if (base === DESKTOP) expect(book.transform).toMatch(/^(none|matrix\(1, 0, 0, 1, )/);
      await page.keyboard.press("Escape");
      await expect(page.locator("[data-slot=sheet-content]")).toHaveCount(0);
      // the bell is a bottom sheet below md only (T-R1-04); on the desktop the sync panel is the second popup
      const opener = base === PHONE ? page.getByTestId("notification-bell").locator("visible=true").first() : page.getByTestId("sync-open").locator("visible=true").first();
      if (await opener.count()) {
        await opener.click();
        await expect(page.locator("[data-slot=sheet-content],[data-slot=dialog-content]").last()).toBeVisible();
        const second = (await page.evaluate(PROBE)) as P;
        expect(second.translate, `second popup ${base.viewport.width} inApp=${inApp}`).toBe("none");
        expect(second.opacity).toBe("1");
        expect(second.running).toBe(0);
      }
      await page.context().close();
    }
  }
});

test("T-R2-08 a teacher's /moderation/me crumb has no 'Moderasyon'; the admin's trail is unchanged", async ({ browser }) => {
  for (const opts of [DESKTOP, PHONE]) {
    const tp = await newPage(browser, opts, TEACHER.id, TEACHER.password);
    await tp.goto("/moderation/me");
    const crumbs = tp.locator('nav[aria-label="Konum"]');
    await expect(crumbs.first()).toContainText("Taleplerim");
    expect((await crumbs.allInnerTexts()).join(" ")).not.toContain("Moderasyon");
    await tp.context().close();
  }
  const ap = await newPage(browser, DESKTOP, ADMIN_EMAIL, ADMIN_PASSWORD);
  await ap.goto("/moderation/me");
  await expect(ap.locator('nav[aria-label="Konum"]').first()).toContainText("Moderasyon");
  await ap.context().close();
});

test("T-R2-01 keyboard open (390 × 508): /profile 'Yeni parola' and /find-room 'Kaç kişi' stay uncovered, the sticky action visible", async ({ browser }) => {
  const page = await newPage(browser, PHONE, TEACHER.id, TEACHER.password);
  for (const [route, field, action] of [["/profile", "#pw-new", "[data-testid=profile-save]"], ["/find-room", "#fr-head", "[data-testid=fr-search], [data-testid=fr-submit], button[type=submit]"]] as const) {
    await page.goto(route);
    const f = page.locator(field).first();
    if (!(await f.count())) continue;
    await f.scrollIntoViewIfNeeded();
    await page.setViewportSize({ width: 390, height: 508 }); // the keyboard takes 336 px (MOBILE.md M-12)
    await f.tap();
    await page.waitForTimeout(400);
    const r = await f.evaluate((el) => { const b = el.getBoundingClientRect(); const t = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2); return { top: Math.round(b.top), bottom: Math.round(b.bottom), vh: document.documentElement.clientHeight, hit: t === el || el.contains(t) }; });
    expect(r.top, `${route} ${field} top`).toBeGreaterThanOrEqual(0);
    expect(r.bottom, `${route} ${field} bottom ${JSON.stringify(r)}`).toBeLessThanOrEqual(r.vh);
    expect(r.hit, `${route} ${field} covered ${JSON.stringify(r)}`).toBe(true);
    const a = page.locator(action).first();
    if (await a.count()) await expect(a).toBeInViewport();
    await page.setViewportSize({ width: 390, height: 844 });
  }
  await page.context().close();
});
