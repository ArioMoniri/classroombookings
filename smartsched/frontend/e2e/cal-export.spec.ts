/**
 * CAL-08 / CAL-09 "Takvimime ekle" against the REAL backend (gated E2E_REAL=1), research doc §6 T1, T2, T13, T14,
 * at 1440 × 900 (mouse) and 390 × 844 (touch, tr-TR, Europe/Istanbul).
 *
 * - T1  Profil › Takvim › "Takvimime ekle": the sheet opens with focus on the heading; three scope cards; Derslerim
 *       says "{n} ders saati" (or the plain lead while the backend does not count hours).
 * - T2  Derslerim → Takvim bağlantısı → approve (consent tick the first time): exactly three taps + the tick; the
 *       webcal / Google / Outlook / Kopyala actions; the https link answers 200 text/calendar with a VTIMEZONE.
 * - T13 Dr. Mehmet (another department, no permission): the department card of Psikoloji is closed with its reason,
 *       and a forged POST /calendar/subscriptions answers 403 department_not_allowed.
 * - T14 Kaldır on the link row: the confirm text, the link answers 404 afterwards, focus moves to the next row or to
 *       "Takvimime ekle" (never <body>).
 * - Phone: the sheet covers the viewport, no sideways scroll (M-01), the primary action is ≥ 44 px and sits in the
 *   sticky footer (M-02, M-05), text inputs are ≥ 16 px (M-03).
 * - CAL-09: Ayarlar › Entegrasyonlar shows the export block with co-instructor names off.
 *
 * Everything it makes is its own (two academicians, their links); afterAll unlinks the instructor, revokes the
 * links and puts the KVKK switch back.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19750 NEXT_PUBLIC_API_URL=http://127.0.0.1:19750 PW_PORT=19751 \
 *     npx playwright test e2e/cal-export.spec.ts --output=<scratch>
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";
import { pinLanguage } from "./language";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const AYSE = { username: `cal.ayse.${STAMP}`, email: `cal.ayse.${STAMP}@uni.edu.tr`, password: "Akademisyen-2026!" };
const MEHMET = { username: `cal.mehmet.${STAMP}`, email: `cal.mehmet.${STAMP}@uni.edu.tr`, password: "Akademisyen-2026!" };
const DESKTOP = { viewport: { width: 1440, height: 900 }, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };

test.describe.configure({ mode: "serial", timeout: 240_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

const ctx = {} as {
  api: APIRequestContext;
  admin: string;
  ayseId: number;
  mehmetId: number;
  instructorId: number | null;
  departmentId: number | null;
  departmentName: string;
  syncWasOn: boolean;
  urlWasSet: boolean;
};

async function call<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token = ctx.admin): Promise<{ status: number; body: T; headers: Record<string, string> }> {
  const res = await ctx.api.fetch(path.startsWith("http") ? path : `${API}${path}`, { method, data: body, headers: { Authorization: `Bearer ${token}` } });
  const text = await res.text();
  let parsed: unknown = text;
  try {
    parsed = text ? JSON.parse(text) : undefined;
  } catch {
    /* text/calendar */
  }
  return { status: res.status(), body: parsed as T, headers: res.headers() };
}
async function api<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token = ctx.admin): Promise<T> {
  const r = await call<T>(method, path, body, token);
  if (r.status >= 400) throw new Error(`${method} ${path} → ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}
async function token(identifier: string, password: string): Promise<string> {
  const res = await ctx.api.post(`${API}/auth/login`, { data: identifier.includes("@") ? { email: identifier, password } : { username: identifier, password } });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { access_token: string }).access_token;
}

type Sub = { id: number | string; scope_kind: string; channel: string };
async function revokeAll(identifier: string, password: string): Promise<void> {
  const tk = await token(identifier, password);
  const subs = await call<Sub[] | { links?: Sub[]; items?: Sub[] }>("GET", "/calendar/subscriptions", undefined, tk);
  const list = Array.isArray(subs.body) ? subs.body : (subs.body?.links ?? subs.body?.items ?? []);
  for (const s of list) await call("DELETE", `/calendar/subscriptions/${s.id}`, undefined, tk);
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.admin = await token(ADMIN_EMAIL, ADMIN_PASSWORD);
  // the organisation's KVKK sign-off for calendar sync (REC_CAL_SIGNOFF=0 leaves it off)
  const settings = await api<{ calendar_sync_enabled: boolean; public_url: string | null }>("GET", "/calendar/admin/settings");
  ctx.syncWasOn = settings.calendar_sync_enabled;
  if (!ctx.syncWasOn) await api("PUT", "/calendar/admin/settings", { calendar_sync_enabled: true });
  // absolute links (https + webcal) need the panel's public address; this stack's own when none is set
  ctx.urlWasSet = !!settings.public_url;
  if (!ctx.urlWasSet) await api("PUT", "/calendar/admin/settings", { public_url: `http://127.0.0.1:${process.env.PW_PORT ?? 3100}` });

  // an instructor of the current term with published classes nobody is linked to yet
  const me = await api<{ current_term: { id: number } | null }>("GET", "/moderation/me");
  const termId = me.current_term!.id;
  const people = await api<{ items: { id: number; requests: number; linked_user: boolean }[] }>("GET", `/terms/${termId}/moderation/people`);
  const free = people.items.filter((p) => !p.linked_user && p.requests >= 2).sort((a, b) => a.requests - b.requests);
  ctx.instructorId = free[0]?.id ?? null;

  // Dr. Ayşe: linked to that instructor (her taught department is exportable); Dr. Mehmet: no link, no department
  const a = await api<{ id: number }>("POST", "/users", { username: AYSE.username, email: AYSE.email, firstname: "Ayşe", lastname: "T.", role: "TEACHER", password: AYSE.password });
  ctx.ayseId = a.id;
  const m = await api<{ id: number }>("POST", "/users", { username: MEHMET.username, email: MEHMET.email, firstname: "Mehmet", lastname: "T.", role: "TEACHER", password: MEHMET.password });
  ctx.mehmetId = m.id;
  for (const u of [AYSE, MEHMET]) await api("PUT", "/auth/profile", { language: "tr" }, await token(u.username, u.password));
  if (ctx.instructorId) await api("PUT", `/auth/sso/admin/users/${a.id}/instructor`, { instructor_id: ctx.instructorId });
  const opts = await api<{ scopes: { kind: string; departments?: { id: number; name: string; available?: boolean }[] }[] }>("GET", "/calendar/export/options", undefined, await token(AYSE.username, AYSE.password));
  const dep = opts.scopes.find((x) => x.kind === "department_classes")?.departments?.find((d) => d.available !== false);
  ctx.departmentId = dep?.id ?? null;
  ctx.departmentName = dep?.name ?? "";
});

test.afterAll(async () => {
  if (!ctx.api) return;
  await revokeAll(AYSE.username, AYSE.password).catch(() => undefined);
  await revokeAll(MEHMET.username, MEHMET.password).catch(() => undefined);
  if (ctx.ayseId && ctx.instructorId) await call("PUT", `/auth/sso/admin/users/${ctx.ayseId}/instructor`, { instructor_id: null });
  if (!ctx.syncWasOn) await call("PUT", "/calendar/admin/settings", { calendar_sync_enabled: false });
  if (!ctx.urlWasSet) await call("PUT", "/calendar/admin/settings", { public_url: "" });
  await ctx.api.dispose();
});

/** a feed URL (absolute on the panel's public address, or relative) on this stack's backend */
const toApi = (u: string) => u.replace(/^(https?:\/\/[^/]+)?\/api\/v1/, API);

async function openSheet(page: Page): Promise<void> {
  await page.goto("/profile#calendar");
  await page.getByTestId("cal-open").click();
  await expect(page.getByTestId("cal-sheet")).toBeVisible();
  await expect(page.getByTestId("cal-scopes")).toBeVisible();
}

async function noSideScroll(page: Page): Promise<void> {
  const r = await page.evaluate(() => ({ sw: document.scrollingElement!.scrollWidth, w: window.innerWidth }));
  expect(r.sw, JSON.stringify(r)).toBeLessThanOrEqual(r.w + 1);
}

for (const [label, device] of [
  ["1440 mouse", DESKTOP],
  ["390 touch", PHONE],
] as const) {
  test.describe(label, () => {
    test.use(device);
    const phone = label.startsWith("390");

    test(`T1 + T2 Derslerim → Takvim bağlantısı → Onayla ve ekle (${label})`, async ({ page }) => {
      test.skip(!ctx.instructorId, "no unlinked instructor with requests in the current term");
      await revokeAll(AYSE.username, AYSE.password);
      await login(page, AYSE.username, AYSE.password);
      await openSheet(page);
      // T1: focus on the heading, three scope kinds
      await expect(page.getByTestId("cal-step-heading")).toHaveText("Neyi eklemek istiyorsunuz?");
      await expect(page.getByTestId("cal-step-heading")).toBeFocused();
      await expect(page.getByTestId("cal-scope-my_classes")).toContainText("Derslerim");
      await expect(page.getByTestId("cal-scope-my_classes")).toContainText(/ders saati|yayımlanmış programdan/);
      await expect(page.locator("[data-testid^=cal-scope-department_classes]").first()).toBeVisible();
      await expect(page.getByTestId("cal-scope-my_bookings")).toBeVisible();
      if (phone) {
        const box = await page.getByTestId("cal-sheet").boundingBox();
        expect(box?.width).toBeGreaterThanOrEqual(388);
        await noSideScroll(page);
      } else {
        const box = await page.getByTestId("cal-sheet").boundingBox();
        expect(box!.width).toBeLessThanOrEqual(561);
      }
      // T2: three taps + the consent tick
      await page.getByTestId("cal-scope-my_classes").click(); // 1
      await expect(page.getByTestId("cal-refresh-times")).toBeHidden(); // refresh times under "Gelişmiş"
      await page.getByTestId("cal-channel-link").click(); // 2
      await expect(page.getByTestId("cal-step-heading")).toHaveText("Takviminize şunlar gönderilecek");
      await expect(page.getByTestId("cal-fields")).toContainText("Ders kodu ve şube");
      await expect(page.getByTestId("cal-never")).toContainText("Öğrenci bilgisi");
      const submit = page.getByTestId("cal-submit");
      const sb = await submit.boundingBox();
      expect(sb!.height).toBeGreaterThanOrEqual(phone ? 44 : 32);
      if (phone) expect(sb!.y + sb!.height).toBeGreaterThan(844 * 0.6);
      if (await page.getByTestId("cal-consent").count()) await page.getByTestId("cal-consent-tick").click();
      await submit.click(); // 3
      await expect(page.getByTestId("cal-link")).toBeVisible();
      for (const k of ["apple", "google", "outlook"]) await expect(page.getByTestId(`cal-link-${k}`)).toBeVisible();
      await expect(page.getByTestId("cal-link-note")).toContainText("Bağlantıyı açmayın, abone olun");
      // the raw addresses sit behind "Gelişmiş" (simplicity principle): closed until asked for
      await expect(page.getByTestId("cal-link-https-value")).toBeHidden();
      await page.getByTestId("cal-link-advanced-toggle").click();
      if (phone) {
        const fs = await page.getByTestId("cal-link-https-value").evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
        expect(fs).toBeGreaterThanOrEqual(16);
        await noSideScroll(page);
      }
      const https = await page.getByTestId("cal-link-https-value").inputValue();
      expect(await page.getByTestId("cal-link-apple").getAttribute("href")).toMatch(/^webcal:\/\//);
      const feed = await ctx.api.get(toApi(https));
      expect(feed.status()).toBe(200);
      expect(feed.headers()["content-type"]).toContain("text/calendar");
      const ics = await feed.text();
      expect(ics).toContain("BEGIN:VCALENDAR");
      expect(ics).toContain("BEGIN:VTIMEZONE");
      // focus stays in the sheet, never <body>
      expect(await page.evaluate(() => document.activeElement?.tagName)).not.toBe("BODY");
      await page.getByTestId("cal-finish").click();
      await expect(page.getByTestId("cal-manage-rows")).toContainText("Derslerim");
    });

    test(`T14 Kaldır: confirm, the link is a 404 afterwards, focus to the next row (${label})`, async ({ page }) => {
      test.skip(!ctx.instructorId, "no unlinked instructor with requests in the current term");
      const tk = await token(AYSE.username, AYSE.password);
      const made = await api<{ id: number | string; urls: { https: string } }>("POST", "/calendar/subscriptions", { scope_kind: "my_bookings", channel: "link" }, tk);
      await login(page, AYSE.username, AYSE.password);
      await page.goto("/profile#calendar");
      const row = page.getByTestId(`cal-row-${made.id}`);
      await expect(row).toBeVisible();
      await page.getByTestId(`cal-remove-${made.id}`).click();
      await expect(page.getByTestId("cal-remove-dialog")).toContainText("Kaldırırsanız eklenen dersler takviminizden silinir.");
      await page.getByTestId("cal-remove-confirm").click();
      await expect(row).toHaveCount(0);
      await expect.poll(() => page.evaluate(() => document.activeElement?.closest("[data-row-id]") !== null || document.activeElement?.getAttribute("data-testid") === "cal-open")).toBe(true);
      const after = await ctx.api.get(toApi(made.urls.https));
      expect(after.status()).toBe(404);
    });

    test(`T13 another department without permission: the card is closed and the API refuses (${label})`, async ({ page }) => {
      test.skip(!ctx.departmentId, "no department");
      await login(page, MEHMET.username, MEHMET.password);
      await openSheet(page);
      // not linked: Derslerim is closed with its reason
      await expect(page.getByTestId("cal-scope-my_classes")).toHaveAttribute("aria-disabled", "true");
      await expect(page.getByTestId("cal-scope-reason-my_classes")).toContainText("öğretim elemanı kaydına bağlı değil");
      // no department he may export: the department card is closed with the reason (no department list)
      const card = page.getByTestId("cal-scope-department_classes");
      await expect(card).toHaveAttribute("aria-disabled", "true");
      await expect(card).toContainText("Bu bölümün derslerini dışa aktarma yetkiniz yok.");
      await expect(page.getByTestId(`cal-scope-department_classes:${ctx.departmentId}`)).toHaveCount(0);
      const forged = await call<{ detail?: { code?: string } }>("POST", "/calendar/subscriptions", { scope_kind: "department_classes", scope_id: ctx.departmentId, channel: "link" }, await token(MEHMET.username, MEHMET.password));
      expect(forged.status).toBe(403);
      expect(forged.body.detail?.code).toBe("department_not_allowed");
      if (phone) await noSideScroll(page);
    });

    test(`CAL-07 refused account after the OAuth round trip: a Turkish sentence, never the code; one primary action (${label})`, async ({ page }) => {
      await login(page, MEHMET.username, MEHMET.password);
      await page.goto("/profile?calendar=error&provider=google&reason=account_not_verified&domain=uni.edu.tr");
      await expect(page.getByTestId("cal-not-verified")).toHaveText("Bu hesap kurumunuzun doğrulanmış hesabı değil. uni.edu.tr uzantılı hesabınızla bağlanın.");
      await expect(page.locator("body")).not.toContainText("account_not_verified");
      // the older push panel sits closed under Gelişmiş: "Takvimime ekle" is the one primary action
      const older = page.getByTestId("calendar-connections-advanced");
      if (await older.count()) await expect(older).not.toHaveAttribute("open", /.*/);
      await expect(page.getByTestId("cal-open")).toBeVisible();
      if (phone) await noSideScroll(page);
    });
  });
}

test("CAL-09 Ayarlar › Entegrasyonlar: the export block, co-instructor names off by default", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await page.goto("/settings?tab=integrations");
  const block = page.getByTestId("cal-admin-export");
  await expect(block).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("cal-admin-field-co_instructors")).not.toHaveAttribute("data-checked", /.*/);
  await expect(page.getByTestId("cal-admin-push")).toBeVisible();
});
