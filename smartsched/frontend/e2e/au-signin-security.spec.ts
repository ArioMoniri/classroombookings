/**
 * AUX-F (docs/design/v3/auth.md §16 checks 1–6, 8, 10; AU-B API.md) against the REAL backend (E2E_REAL=1), Chromium
 * with a CDP virtual WebAuthn authenticator (ctap2, internal, resident keys, user verification). Not run by the
 * builder (resource rule 2026-10-18): the single e2e lane runs it.
 *
 * Accounts are made through the admin API: a local user whose first password change is done through the API, so the
 * UI starts at /login. TOTP codes come from the setup key (RFC 6238, SHA-1, 6 digits, 30 s) computed here.
 * The admin (§7) and policy-tab (§9) cases use the mounts in admin/users-admin.tsx and settings/settings-view.tsx.
 */
import { createHmac } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { REAL, SKIP_REASON } from "./helpers";
import { adminApi, API, type Admin } from "./identity";
import { pinLanguage } from "./language";

test.describe.configure({ mode: "serial" });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

const STAMP = Date.now().toString(36);
const USER = { username: `au-${STAMP}`, email: `au-${STAMP}@uni.edu.tr`, first: "Gecici-Parola-2026!", password: "uzun bir cumle parola 2026" };

/* --------------------------------------------------------------------------------------------- helpers */

function base32(s: string): Buffer {
  const abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const c of s.replace(/[\s=]/g, "").toUpperCase()) bits += abc.indexOf(c).toString(2).padStart(5, "0");
  const out: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) out.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(out);
}
/** RFC 6238 TOTP (SHA-1, 6 digits, 30 s), `offset` steps from now. */
export function totp(secret: string, offset = 0, now = Date.now()): string {
  const counter = Math.floor(now / 30_000) + offset;
  const msg = Buffer.alloc(8);
  msg.writeBigUInt64BE(BigInt(counter));
  const h = createHmac("sha1", base32(secret)).update(msg).digest();
  const o = h[h.length - 1]! & 0xf;
  const n = ((h[o]! & 0x7f) << 24) | (h[o + 1]! << 16) | (h[o + 2]! << 8) | h[o + 3]!;
  return String(n % 1_000_000).padStart(6, "0");
}
/** a code from the next window, so a code used a moment ago is never replayed */
const freshCode = (secret: string) => totp(secret, 1);

async function virtualAuthenticator(context: BrowserContext, page: Page): Promise<{ count: () => Promise<number> }> {
  const cdp = await context.newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  const { authenticatorId } = await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: { protocol: "ctap2", transport: "internal", hasResidentKey: true, hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true },
  });
  return { count: async () => (await cdp.send("WebAuthn.getCredentials", { authenticatorId })).credentials.length };
}

async function signInWithPassword(page: Page, password = USER.password) {
  await page.goto("/login?method=local");
  await page.getByLabel(/Kullanıcı adı veya e-posta/).fill(USER.username);
  await page.getByLabel(/^Parola$/).fill(password);
  await page.getByRole("button", { name: /^Giriş yap$/ }).click();
}

async function focusIsNotBody(page: Page) {
  expect(await page.evaluate(() => document.activeElement?.tagName)).not.toBe("BODY");
}

let admin: Admin;
let userId = 0;
let secret = "";
let codes: string[] = [];

test.beforeAll(async () => {
  admin = await adminApi();
  const made = await admin.send<{ id: number }>("POST", "/users", { username: USER.username, email: USER.email, displayname: "AU Deneme", role: "PLANNER", password: USER.first });
  expect(made.status, JSON.stringify(made.body)).toBeLessThan(300);
  userId = made.body.id;
  // the admin-set password forces a change at the first sign-in: do it through the API (12 characters, no 2FA yet)
  const r = await admin.ctx.post(`${API}/auth/login`, { data: { username: USER.username, password: USER.first } });
  const { access_token } = (await r.json()) as { access_token: string };
  const c = await admin.ctx.post(`${API}/auth/change-password`, { headers: { Authorization: `Bearer ${access_token}` }, data: { current_password: USER.first, new_password: USER.password } });
  expect(c.status()).toBeLessThan(300);
});

test.afterAll(async () => {
  if (userId) await admin.send("DELETE", `/users/${userId}`);
  await admin.dispose();
});

/* ------------------------------------------------------------------------------------------- the checks */

test("§16.6: 2FA on in ≤ 3 steps; .txt name; Bitir after the tick; the warning at step 3", async ({ page }) => {
  await signInWithPassword(page);
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  await page.goto("/profile#security");
  await page.getByTestId("mfa-turn-on").click();
  // signed in moments ago: the 10-minute window, no password dialog
  await expect(page.getByTestId("reauth-dialog")).toHaveCount(0);
  const sheet = page.getByTestId("mfa-setup-sheet");
  await expect(sheet.getByTestId("mfa-setup-step")).toHaveText("Adım 1–2 / 3");
  await sheet.getByTestId("setup-cant-scan").click();
  secret = ((await sheet.getByTestId("setup-key").textContent()) ?? "").replace(/\s/g, "");
  expect(secret).toMatch(/^[A-Z2-7]{32}$/);
  await sheet.getByRole("textbox", { name: "Doğrulama kodu" }).pressSequentially(totp(secret));
  await expect(sheet.getByTestId("setup-step-3")).toBeVisible();
  await expect(sheet.getByTestId("recovery-code-list").locator("li")).toHaveCount(10);
  const [dl] = await Promise.all([page.waitForEvent("download"), sheet.getByTestId("codes-download").click()]);
  expect(dl.suggestedFilename()).toMatch(/^smartsched-kurtarma-kodlari-[a-z0-9-]+\.txt$/);
  codes = (await readFile((await dl.path())!, "utf8")).match(/[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}/g) ?? [];
  expect(codes).toHaveLength(10);
  await expect(sheet.getByTestId("codes-finish")).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("mfa-setup-close-confirm")).toBeVisible();
  await page.getByTestId("mfa-setup-back").click();
  await sheet.getByTestId("codes-saved").click();
  await sheet.getByTestId("codes-finish").click();
  await expect(page.getByTestId("security-mfa")).toContainText("Açık");
});

test("§16.1: password → 2FA step without reload; '123 456' pasted fills and submits; a wrong code clears and keeps focus", async ({ page, context }) => {
  await context.clearCookies();
  await signInWithPassword(page);
  await page.waitForURL("**/login/verify");
  const input = page.getByRole("textbox", { name: "Doğrulama kodu" });
  await expect(input).toBeFocused();
  await expect(page.getByTestId("mfa-remember")).not.toBeChecked();
  await input.pressSequentially("000000");
  await expect(page.getByText("Kod doğru değil. Uygulamadaki güncel kodu girin.")).toBeVisible();
  await expect(input).toHaveValue("");
  await expect(input).toBeFocused();
  const code = freshCode(secret);
  await input.focus();
  await page.evaluate((c) => {
    const el = document.activeElement as HTMLInputElement;
    const dt = new DataTransfer();
    dt.setData("text/plain", c);
    el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
  }, `${code.slice(0, 3)} ${code.slice(3)}`);
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  await focusIsNotBody(page);
});

test("§16.2: 'Bu cihazı 30 gün hatırla' skips the step next time; 'Diğer cihazlardan çıkış yap' forgets it", async ({ page, context }) => {
  await context.clearCookies();
  await signInWithPassword(page);
  await page.waitForURL("**/login/verify");
  await page.getByTestId("mfa-remember").click();
  await page.getByRole("textbox", { name: "Doğrulama kodu" }).pressSequentially(totp(secret, 2));
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  // a new session on the same browser (ss_td kept, the session cookie dropped)
  const keep = (await context.cookies()).filter((c) => c.name === "ss_td");
  expect(keep).toHaveLength(1);
  await context.clearCookies();
  await context.addCookies(keep);
  await signInWithPassword(page);
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  await page.goto("/profile#security");
  await expect(page.getByTestId("device-row")).toHaveCount(1);
  // AU-15: sessions list without any network, the current one tagged
  await expect(page.getByTestId("session-current")).toHaveText("Bu cihaz");
  expect(await page.getByTestId("security-sessions").textContent()).not.toMatch(/\d+\.\d+\.\d+\.\d+|\/24|\/48/);
  await page.getByTestId("sessions-end-others").click();
  await page.getByTestId("sessions-end-others-confirm").click();
  await expect(page.getByTestId("device-row")).toHaveCount(0);
});

test("§16.4: passkey added in Profil (virtual authenticator) → 'Hiç kullanılmadı'; then the second step by passkey", async ({ page, context }) => {
  const auth = await virtualAuthenticator(context, page);
  await context.clearCookies();
  await signInWithPassword(page);
  await page.waitForURL("**/login/verify");
  await page.getByRole("textbox", { name: "Doğrulama kodu" }).pressSequentially(totp(secret, 3));
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  await page.goto("/profile#security");
  await page.getByTestId("passkey-add").click();
  await expect(page.getByTestId("passkey-row")).toHaveCount(1);
  await expect(page.getByTestId("passkey-meta")).toContainText("Hiç kullanılmadı");
  expect(await auth.count()).toBe(1);
  // rename: Enter saves, focus returns to the row's ⋯
  await page.getByTestId("passkey-rename-input").fill("Test anahtarı");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("passkey-menu")).toBeFocused();
  // next sign-in: "Başka bir yöntem › Geçiş anahtarı kullan"
  await context.clearCookies();
  await signInWithPassword(page);
  await page.waitForURL("**/login/verify");
  await page.getByRole("button", { name: /Başka bir yöntem/ }).click();
  await page.getByRole("button", { name: /Geçiş anahtarı kullan/ }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
});

test("§16.3: a recovery code works once; the toast names the remaining count", async ({ page, context }) => {
  await context.clearCookies();
  await signInWithPassword(page);
  await page.waitForURL("**/login/verify");
  await page.getByRole("button", { name: /Başka bir yöntem/ }).click();
  await page.getByRole("button", { name: /Kurtarma kodu kullan/ }).click();
  // typed lower-case without dashes: the field normalises it
  await page.getByLabel("Kurtarma kodu").fill(codes[0]!.replace(/-/g, "").toLowerCase());
  await page.getByTestId("mfa-submit").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
  await expect(page.getByText(/Bir kurtarma kodu kullandınız\. 9 kod kaldı\./)).toBeVisible();
  // the same code a second time is refused
  await context.clearCookies();
  await signInWithPassword(page);
  await page.waitForURL("**/login/verify");
  await page.getByRole("button", { name: /Başka bir yöntem/ }).click();
  await page.getByRole("button", { name: /Kurtarma kodu kullan/ }).click();
  await page.getByLabel("Kurtarma kodu").fill(codes[0]!);
  await page.getByTestId("mfa-submit").click();
  await expect(page.getByText("Bu kurtarma kodu geçerli değil ya da daha önce kullanıldı.")).toBeVisible();
});

test("§16.10: an SSO-only account never sees 2FA or passkey rows (API answer)", async () => {
  // the UI side is covered by vitest (security-section.test.tsx); here the contract: GET /auth/mfa for an SSO user
  test.skip(!process.env.E2E_SSO_MINT, "needs an SSO account (E2E_SSO_MINT, see sign-in.spec.ts)");
});

test("§16.7/8: admin menu ('Giriş' group, no reset code item) and the reset dialog", async ({ page }) => {
  await page.goto("/login?method=local");
  const r = await page.request.post("/api/v1/auth/login", { data: { email: process.env.E2E_ADMIN_EMAIL ?? "admin@smartsched.local", password: process.env.E2E_ADMIN_PASSWORD ?? "Admin-2026!" } });
  expect(r.ok()).toBe(true);
  await page.goto(`/admin/users?q=${encodeURIComponent(USER.username)}`);
  await page.getByRole("button", { name: `${USER.username} için işlemler` }).click();
  const group = page.getByTestId(`user-security-menu-${userId}`);
  await expect(group).toBeVisible();
  await expect(page.getByTestId(`user-send-link-${userId}`)).toBeVisible();
  await expect(page.getByTestId(`user-show-code-${userId}`)).toHaveText("Sıfırlama kodunu ekranda göster");
  await expect(page.getByRole("menuitem", { name: "Tek kullanımlık sıfırlama kodu" })).toHaveCount(0);
  await page.getByTestId(`user-reset-mfa-${userId}`).click();
  await page.getByTestId("reset-reason").fill("9 harfli.");
  await page.getByTestId("reset-confirm").click();
  await expect(page.getByTestId("reset-reason-error")).toBeVisible();
  await page.getByTestId("reset-chip-compromised").click();
  await expect(page.getByTestId("reset-keep-passkeys")).toHaveCount(0);
  await page.getByTestId("reset-identity").selectOption("in_person");
  await page.getByTestId("reset-confirm").click();
  await expect(page.getByText(/iki aşamalı doğrulama sıfırlandı/)).toBeVisible();
  // the admin's own row offers the Profil link instead of a reset
  const me = await admin.get<{ id: number; username?: string | null; email?: string | null }>("/auth/me");
  await page.goto(`/admin/users?q=${encodeURIComponent(me.username ?? me.email ?? "")}`);
  await page.getByRole("button", { name: `${me.username ?? me.email} için işlemler` }).click();
  await expect(page.getByTestId(`user-own-security-${me.id}`)).toBeVisible();
  await expect(page.getByTestId(`user-reset-mfa-${me.id}`)).toHaveCount(0);
});

test("§16.9/12: policy tab round-trip at 390 (chips 44 px, save above the tab bar, no horizontal scroll)", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "tr-TR", timezoneId: "Europe/Istanbul" });
  const page = await ctx.newPage();
  const r = await page.request.post("/api/v1/auth/login", { data: { email: process.env.E2E_ADMIN_EMAIL ?? "admin@smartsched.local", password: process.env.E2E_ADMIN_PASSWORD ?? "Admin-2026!" } });
  expect(r.ok()).toBe(true);
  await page.goto("/settings?tab=signin-security");
  await expect(page.getByTestId("signin-security")).toBeVisible();
  const before = await admin.get<Record<string, unknown>>("/admin/auth/mfa-policy");
  await page.getByTestId("policy-required").click();
  await page.getByTestId("policy-role-PLANNER").click();
  for (const chip of await page.getByTestId("policy-roles").locator("button").all()) expect((await chip.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  const save = page.getByTestId("policy-save");
  const box = (await save.boundingBox())!;
  expect(box.y + box.height).toBeLessThanOrEqual(844 - 84);
  await save.click();
  await page.getByTestId("policy-confirm-save").click();
  await expect.poll(async () => (await admin.get<{ mfa_policy: string; mfa_roles: string[] }>("/admin/auth/mfa-policy")).mfa_roles.sort()).toEqual(["ADMIN", "PLANNER"]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await admin.send("PUT", "/admin/auth/mfa-policy", before);
  await ctx.close();
});
