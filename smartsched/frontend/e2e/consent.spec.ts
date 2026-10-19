/**
 * Consent gates in the UI (consent-ui 2026-10-16) against the REAL backend (no mocked API), gated E2E_REAL=1, on the
 * real Bahar 2026 data:
 *
 * 1. My bookings: with the calendar-sync sign-off on (this spec signs off through the API and puts it back) and no
 *    `calendar_sync` consent, "Bağlantı oluştur" opens the inline consent step (focus on it); "Rıza ver ve devam et"
 *    gives the consent and makes the link. The consent is then withdrawn through the API while the page is open
 *    (another tab), so the stale screen sends a reset and the backend's real 409 `consent_required` is shown with its
 *    TR sentence and a link to `grant_path`, which opens Profil › Gizlilik.
 * 2. Profil › Takvim aktarımı: Google is configured with a dummy client and the panel's public URL (both restored); "Bağlan" asks for the
 *    consent first, then the browser goes to the backend's Google authorize URL (the provider page itself is stubbed:
 *    no real Google round trip).
 * 3. Admin › KVKK › Yapay zekâ: `kvkk.ai_personal_default` is switched to `excluded` in the two-option control; a teacher
 *    who never gave the AI consent reads on Gizlilik that they are kept out and why; giving it changes the text. The
 *    setting is put back.
 * 4. KVKK queue: a leaver with a push-calendar connection whose stored grant cannot be decrypted (seeded straight into
 *    the e2e SQLite DB, E2E_DB; the same state a rotated APP_SECRET leaves) asks for erasure; completing it shows
 *    `result.failures[]` (grant_unreadable, events_not_removed, TR) and `result.calendar[]` (revoke state) in the
 *    result panel. Skipped without E2E_DB.
 * 5. Phone 390 × 844 (touch): the consent step on My bookings and Admin › KVKK › Yapay zekâ have no sideways scroll;
 *    their buttons / options are ≥ 44 px.
 *
 *   E2E_REAL=1 E2E_DB=/path/e2e.db E2E_API_URL=http://127.0.0.1:19024 NEXT_PUBLIC_API_URL=http://127.0.0.1:19024 \
 *     PW_PORT=19025 npx playwright test e2e/consent.spec.ts
 */
import { spawnSync } from "node:child_process";
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const DB = process.env.E2E_DB ?? "";
const STAMP = Date.now().toString(36);
const TEACHER = { username: `cs.hoca.${STAMP}`, email: `cs.hoca.${STAMP}@uni.edu.tr`, password: "Ogretmen-2026!" };
const LEAVER = { username: `cs.ayrilan.${STAMP}`, email: `cs.ayrilan.${STAMP}@uni.edu.tr`, password: "Ogretmen-2026!" };
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
const GOOGLE_CLIENT = `e2e-consent-${STAMP}.apps.googleusercontent.com`;

test.describe.configure({ mode: "serial", timeout: 180_000 });
test.skip(!REAL, SKIP_REASON);

const ctx = {} as { api: APIRequestContext; token: string; teacherToken: string; teacherId: number; restore: { sync?: boolean; google?: boolean; publicUrl?: boolean; aiDefault?: string } };

async function call<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token = ctx.token): Promise<{ status: number; body: T }> {
  const res = await ctx.api.fetch(`${API}${path}`, { method, data: body, headers: { Authorization: `Bearer ${token}` } });
  const text = await res.text();
  let parsed: unknown = undefined;
  try {
    parsed = text ? JSON.parse(text) : undefined;
  } catch {
    parsed = text;
  }
  return { status: res.status(), body: parsed as T };
}
async function api<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token = ctx.token): Promise<T> {
  const r = await call<T>(method, path, body, token);
  if (r.status >= 400) throw new Error(`${method} ${path} → ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}
async function loginToken(identifier: string, password: string): Promise<string> {
  const body = identifier.includes("@") ? { email: identifier, password } : { username: identifier, password };
  const res = await ctx.api.post(`${API}/auth/login`, { data: body });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { access_token: string }).access_token;
}
async function ackNotice(token: string): Promise<void> {
  const me = await api<{ notice: { id: number } | null; needs_ack: boolean }>("GET", "/me/privacy", undefined, token);
  if (me.needs_ack && me.notice) await api("POST", "/me/privacy/ack", { notice_id: me.notice.id }, token);
}
async function syncConsent(token = ctx.teacherToken): Promise<{ required: boolean; granted: boolean }> {
  return (await api<{ consent: { required: boolean; granted: boolean } }>("GET", "/calendar/sync", undefined, token)).consent;
}
/** M-01: no sideways scroll on the layout viewport */
async function noSideScroll(page: Page): Promise<void> {
  const m = await page.evaluate(() => ({ sw: document.scrollingElement!.scrollWidth, vw: document.documentElement.clientWidth }));
  expect(m.sw, `scrollWidth ${m.sw} > ${m.vw}`).toBeLessThanOrEqual(m.vw + 1);
}
async function signInAs(page: Page, id: string, password: string): Promise<void> {
  await page.goto("about:blank");
  await page.context().clearCookies();
  await login(page, id, password);
}

test.beforeAll(async ({}, testInfo) => {
  ctx.api = await pwRequest.newContext();
  ctx.token = await loginToken(ADMIN_EMAIL, ADMIN_PASSWORD);
  ctx.restore = {};
  // the calendar-sync KVKK sign-off (the gate only applies while it is on) and a configured Google client
  const integrations = await api<{ calendar_sync_enabled: boolean; public_url: string | null; google: { configured: boolean } }>("GET", "/calendar/admin/settings");
  // a push provider is configured only with a public URL (its redirect URI is built from it)
  if (!integrations.public_url) {
    ctx.restore.publicUrl = false;
    await api("PUT", "/calendar/admin/settings", { public_url: new URL(String(testInfo.project.use.baseURL)).origin });
  }
  if (!integrations.calendar_sync_enabled) {
    ctx.restore.sync = false;
    await api("PUT", "/calendar/admin/settings", { calendar_sync_enabled: true });
  }
  if (!integrations.google.configured) {
    ctx.restore.google = false;
    await api("PUT", "/calendar/admin/settings", { google_client_id: GOOGLE_CLIENT, google_client_secret: `e2e-secret-${STAMP}` });
  }
  const settings = await api<Record<string, unknown>>("GET", "/settings");
  ctx.restore.aiDefault = String(settings["kvkk.ai_personal_default"] ?? "included");
  if (ctx.restore.aiDefault !== "included") await api("PUT", "/settings", { extra: { "kvkk.ai_personal_default": "included" } });
  const teacher = await api<{ id: number }>("POST", "/users", { username: TEACHER.username, email: TEACHER.email, firstname: "Rıza", lastname: "Deneme", role: "TEACHER", password: TEACHER.password });
  ctx.teacherId = teacher.id;
  ctx.teacherToken = await loginToken(TEACHER.username, TEACHER.password);
  for (const token of [ctx.token, ctx.teacherToken]) await ackNotice(token);
  expect(await syncConsent()).toMatchObject({ required: true, granted: false });
});

test.afterAll(async () => {
  if (ctx.restore?.aiDefault) await call("PUT", "/settings", { extra: { "kvkk.ai_personal_default": ctx.restore.aiDefault } });
  if (ctx.restore?.google === false) await call("PUT", "/calendar/admin/settings", { google_client_id: "", google_client_secret: "" });
  if (ctx.restore?.publicUrl === false) await call("PUT", "/calendar/admin/settings", { public_url: "" });
  if (ctx.restore?.sync === false) await call("PUT", "/calendar/admin/settings", { calendar_sync_enabled: false });
  await ctx.api?.dispose();
});

test("1. My bookings: the consent step before the first link; a 409 consent_required links to Gizlilik", async ({ page }) => {
  await signInAs(page, TEACHER.username, TEACHER.password);
  await page.goto("/my-bookings");
  const panel = page.getByTestId("calendar-sync");
  await panel.getByTestId("sync-create").click();
  const step = panel.getByTestId("calendar-consent-step");
  await expect(step).toBeVisible();
  await expect(step).toBeFocused();
  await expect(step).toContainText("Takvim eşitleme için rızanız gerekiyor");
  await expect(step).toContainText("açık rızanızdır (KVKK)");
  await expect(step.getByRole("link", { name: "Gizlilik bölümüne git" })).toHaveAttribute("href", "/profile#privacy");
  // nothing was asked yet: "Şimdi değil" leaves the consent and the links alone
  await step.getByTestId("calendar-consent-cancel").click();
  await expect(step).toHaveCount(0);
  expect((await syncConsent()).granted).toBe(false);
  await panel.getByTestId("sync-create").click();
  await panel.getByTestId("calendar-consent-grant").click();
  const url = panel.getByTestId("sync-url-mine");
  await expect(url).toHaveValue(/\/calendar\/feeds\/.+\/mine\.ics$/);
  await expect(panel.getByTestId("calendar-consent-step")).toHaveCount(0);
  expect((await syncConsent()).granted).toBe(true);

  // withdrawn in another tab (the API here) while this page still believes it is given: the reset is refused
  await api("DELETE", "/me/consents/calendar_sync", undefined, ctx.teacherToken);
  await panel.getByTestId("sync-reset").click();
  await page.getByRole("alertdialog", { name: /sıfırlansın mı/ }).getByRole("button", { name: /sıfırla/i }).click();
  const refused = panel.getByTestId("calendar-consent-refused");
  await expect(refused).toContainText('Bunun için "Takvimimle eşitleme (Google / Microsoft)" rızanız gerekir.');
  const link = refused.getByTestId("calendar-consent-link");
  await expect(link).toHaveAttribute("href", "/profile#privacy");
  await link.click();
  await page.waitForURL(/\/profile#privacy$/);
  const privacy = page.getByTestId("privacy-section");
  await expect(privacy).toBeVisible();
  await expect(privacy.getByTestId("consent-switch-calendar_sync")).not.toBeChecked();
});

test("2. Profil › Takvim aktarımı: Connect asks for the consent, then goes to the provider", async ({ page }) => {
  expect((await syncConsent()).granted).toBe(false);
  // the provider's own page is not part of SmartSched: a stub answers so the hand-off URL can be read
  await page.route("https://accounts.google.com/**", (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><title>Google stub</title><p>stub</p>" }));
  await signInAs(page, TEACHER.username, TEACHER.password);
  await page.goto("/profile");
  const section = page.getByTestId("calendar-connections");
  await expect(section.getByTestId("calendar-connections-consent")).toContainText("Bağlanırken önce takvim eşitleme rızanız istenir");
  await section.getByTestId("calendar-connect-google").click();
  const step = section.getByTestId("calendar-consent-google");
  await expect(step).toBeVisible();
  expect((await syncConsent()).granted).toBe(false);
  await step.getByTestId("calendar-consent-grant").click();
  await page.waitForURL(/^https:\/\/accounts\.google\.com\//);
  const target = new URL(page.url());
  expect(target.searchParams.get("client_id")).toBe(GOOGLE_CLIENT);
  expect(target.searchParams.get("code_challenge_method")).toBe("S256");
  expect((await syncConsent()).granted).toBe(true);
});

test("3. Admin › KVKK: ai_personal_default = excluded; Gizlilik says who is kept out of AI requests and why", async ({ page }) => {
  await signInAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/kvkk?tab=ai");
  const card = page.getByTestId("kvkk-ai-default");
  await expect(card.getByTestId("kvkk-ai-included")).toBeChecked();
  await expect(card.getByTestId("kvkk-ai-option-included")).toContainText("Kayıtlı ayar");
  await expect(card.getByTestId("kvkk-ai-option-excluded")).toContainText("verene kadar dışarıda tutulur");
  await expect(card.getByTestId("kvkk-ai-save")).toBeDisabled();
  await card.getByTestId("kvkk-ai-option-excluded").click();
  await card.getByTestId("kvkk-ai-save").click();
  await expect(page.getByText("Kaydedildi. Herkesin Gizlilik sayfası artık yeni anlamı açıklıyor.")).toBeVisible();
  await expect(card.getByTestId("kvkk-ai-option-excluded")).toContainText("Kayıtlı ayar");
  expect((await api<Record<string, unknown>>("GET", "/settings"))["kvkk.ai_personal_default"]).toBe("excluded");
  // the server answer is what the screen says (the backend audits the change)
  const me = await api<{ ai_personal_default: string; ai_excluded: boolean }>("GET", "/me/privacy", undefined, ctx.teacherToken);
  expect(me).toMatchObject({ ai_personal_default: "excluded", ai_excluded: true });

  await signInAs(page, TEACHER.username, TEACHER.password);
  await page.goto("/profile#privacy");
  const row = page.getByTestId("consent-ai_personal");
  await expect(row.getByTestId("consent-ai-state")).toHaveAttribute("data-excluded", "true");
  await expect(row.getByTestId("consent-ai-state")).toContainText("Şu an: yapay zekâ isteklerinin dışındasınız");
  await expect(row.getByTestId("consent-ai-text")).toContainText("Bu rızayı vermediğiniz ve kurumunuz bunu hayır saydığı için dışarıdasınız");
  await row.getByTestId("consent-switch-ai_personal").click();
  await expect(row.getByTestId("consent-ai-state")).toHaveAttribute("data-excluded", "false");
  await expect(row.getByTestId("consent-ai-text")).toContainText("Bu rızayı verdiğiniz için dahilsiniz");
  // withdrawing it (AI changes only what is sent from now on: no confirmation) names the withdrawal as the reason
  await row.getByTestId("consent-switch-ai_personal").click();
  await expect(row.getByTestId("consent-ai-text")).toContainText("Bu rızayı geri aldığınız için dışarıdasınız");

  // back to the default for the specs after this one
  await api("PUT", "/settings", { extra: { "kvkk.ai_personal_default": "included" } });
  expect((await api<{ ai_excluded: boolean }>("GET", "/me/privacy", undefined, ctx.teacherToken)).ai_excluded).toBe(true);
});

test("4. KVKK queue: an erasure whose calendar grant cannot be read lists the failures and the calendar outcome", async ({ page }) => {
  test.skip(!DB, "set E2E_DB to the e2e backend's SQLite file: the unreadable grant is seeded there (no real provider in e2e)");
  const leaver = await api<{ id: number }>("POST", "/users", { username: LEAVER.username, email: LEAVER.email, firstname: "Ayrılan", lastname: "Takvimli", role: "TEACHER", password: LEAVER.password });
  const leaverToken = await loginToken(LEAVER.username, LEAVER.password);
  // a Google connection whose stored grant is not decryptable (what a rotated APP_SECRET leaves) with one pushed event
  const seed = spawnSync(
    "python3",
    [
      "-I",
      "-c",
      [
        "import sqlite3, sys, datetime",
        "db = sqlite3.connect(sys.argv[1]); uid = int(sys.argv[2]); now = datetime.datetime.utcnow().isoformat(sep=' ')",
        "cur = db.execute(\"INSERT INTO calendar_connections (user_id, provider, account_email, calendar_id, access_token_enc, refresh_token_enc, status, created_at) VALUES (?, 'google', ?, 'primary', 'not-a-fernet-token', 'not-a-fernet-token', 'ACTIVE', ?)\", (uid, sys.argv[3], now))",
        "db.execute(\"INSERT INTO calendar_event_links (connection_id, booking_id, calendar_id, external_id, synced_at) VALUES (?, 990001, 'primary', 'e2e-event-1', ?)\", (cur.lastrowid, now))",
        "db.commit()",
      ].join("\n"),
      DB,
      String(leaver.id),
      LEAVER.email,
    ],
    { encoding: "utf8" },
  );
  expect(seed.status, seed.stderr).toBe(0);
  const erase = await api<{ id: number }>("POST", "/me/data-requests", { kind: "erase", note: "Kurumdan ayrıldım (takvim bağlı)" }, leaverToken);

  await signInAs(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/kvkk?tab=requests");
  const row = page.getByTestId(`dsr-${erase.id}`);
  await row.getByTestId(`dsr-complete-${erase.id}`).click();
  await page.getByTestId("dsr-dialog").getByTestId("dsr-confirm").click();
  const failures = page.getByTestId("dsr-failures");
  await expect(failures).toContainText("2 adım ilginizi bekliyor");
  await expect(failures).toContainText("Silme tamamlandı; takvim sağlayıcısındaki şu adımlar bitmedi.");
  const unreadable = failures.getByTestId("dsr-failure-google-grant_unreadable");
  await expect(unreadable).toContainText("Google Takvim");
  await expect(unreadable).toContainText("silindi ama sağlayıcıda iptal edilemedi");
  await expect(unreadable).toContainText("grant_unreadable");
  await expect(failures.getByTestId("dsr-failure-google-events_not_removed")).toContainText("1 etkinlik silinemedi");
  const cal = page.getByTestId("dsr-calendar-google");
  await expect(cal).toHaveAttribute("data-revoke", "unreadable");
  await expect(cal).toContainText("1 etkinliğin 0 tanesi silindi · 1 tanesi silinemedi · saklanan yetki okunamadı");
  await expect(page.getByTestId("dsr-result").getByTestId("dsr-partial")).toBeVisible();
  // the stored answer reopens the same panel from the Done list
  await page.getByTestId("dsr-result").getByRole("button", { name: "Kapat" }).click();
  await expect(failures).toHaveCount(0);
  await page.getByTestId("dsr-filter-done").click();
  await page.getByTestId(`dsr-${erase.id}`).getByRole("button", { name: "Silinenleri göster" }).click();
  await expect(page.getByTestId("dsr-failures")).toContainText("grant_unreadable");
});

test("5. phone: the consent step and Admin › KVKK › Yapay zekâ fit 390 px with 44 px targets", async ({ browser }) => {
  // the teacher gave the consent in test 2: withdraw it so the step appears again
  if ((await syncConsent()).granted) await api("DELETE", "/me/consents/calendar_sync", undefined, ctx.teacherToken);
  const c = await browser.newContext(PHONE);
  const p = await c.newPage();
  await login(p, TEACHER.username, TEACHER.password);
  await p.goto("/my-bookings");
  const panel = p.getByTestId("calendar-sync");
  await panel.getByTestId("sync-create").click();
  const step = panel.getByTestId("calendar-consent-step");
  await expect(step).toBeVisible();
  await noSideScroll(p);
  for (const id of ["calendar-consent-grant", "calendar-consent-cancel"]) {
    const box = await step.getByTestId(id).boundingBox();
    expect(box!.height, id).toBeGreaterThanOrEqual(44);
  }
  await c.clearCookies();
  await login(p, ADMIN_EMAIL, ADMIN_PASSWORD);
  await p.goto("/admin/kvkk?tab=ai");
  await expect(p.getByTestId("kvkk-ai-default")).toBeVisible();
  await noSideScroll(p);
  for (const v of ["included", "excluded"]) {
    const box = await p.getByTestId(`kvkk-ai-option-${v}`).boundingBox();
    expect(box!.height, v).toBeGreaterThanOrEqual(44);
  }
  const save = await p.getByTestId("kvkk-ai-save").boundingBox();
  expect(save!.height).toBeGreaterThanOrEqual(44);
  await c.close();
});
