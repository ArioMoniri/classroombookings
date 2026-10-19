/**
 * Wave 3b, lane W3-IDP: several identity providers on a real stack with a local mock OpenID Connect issuer
 * (e2e/w3-idp-mock-issuer.py on 127.0.0.1:19712, Keycloak-shaped; nothing leaves the machine).
 *
 *  1. Admin, desktop 1440: Ayarlar › Kimlik sağlayıcıları › "Sağlayıcı ekle" › Keycloak; the guided setup shows the
 *     redirect URI built from the public URL with "Kopyala"; the issuer pasted with NBSP is discovered (check rows);
 *     the secret becomes "kayıtlı" (never shown again); "Kendi hesabımla dene" runs the real flow in a popup and the
 *     claims come back; "Etkinleştir" turns it on; the row says Bağlı with "Son değişiklik".
 *  2. Invitation for Keycloak; /login?invite=… shows only the Keycloak button; the invited person signs in through
 *     the mock issuer and lands in the panel.
 *  3. /login shows the Keycloak button plus the password door; a provider error (`domain`) reads in Turkish.
 *  4. Phone 390 × 844 touch: no sideways scroll, the provider button ≥ 44 px, inputs ≥ 16 px.
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:19710 PW_PORT=19711 npx playwright test w3-idp
 */
import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import { expect, request as pwRequest, test, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const WEB = `http://127.0.0.1:${process.env.PW_PORT ?? 3100}`;
const ISSUER_PORT = Number(process.env.W3_IDP_ISSUER_PORT ?? 19712);
const ISSUER = `http://localhost:${ISSUER_PORT}/realms/uni`;
const STAMP = Date.now().toString(36);
const INVITED = `davetli.${STAMP}@uni.edu.tr`;
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };

test.describe.configure({ mode: "serial", timeout: 240_000 });
test.skip(!REAL, SKIP_REASON);

let issuer: ChildProcess | null = null;
let inviteLink = "";

test.beforeAll(async () => {
  // W3_IDP_EXTERNAL=1: the caller already runs the issuer (pod CI e2e-real.sh: a sidecar in the backend's network)
  if (!process.env.W3_IDP_EXTERNAL) {
    const py = process.env.W3_IDP_PYTHON ?? path.resolve(process.cwd(), "../backend/.venv/bin/python");
    issuer = spawn(py, ["-I", path.resolve(process.cwd(), "e2e/w3-idp-mock-issuer.py"), String(ISSUER_PORT)], { stdio: "ignore" });
    await new Promise((r) => setTimeout(r, 1500));
  }
  // the panel's public URL (the redirect URI is built from it)
  const ctx = await pwRequest.newContext();
  const tok = (await (await ctx.post(`${API}/auth/login`, { data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD } })).json()) as { access_token: string };
  const r = await ctx.put(`${API}/calendar/admin/settings`, { data: { public_url: WEB }, headers: { Authorization: `Bearer ${tok.access_token}` } });
  expect(r.ok()).toBeTruthy();
  // idempotent reruns: earlier Keycloak providers of this spec are switched off and deleted
  const auth = { Authorization: `Bearer ${tok.access_token}` };
  const list = (await (await ctx.get(`${API}/auth/sso/admin/providers`, { headers: auth })).json()) as { providers: { id: number; kind: string; enabled: boolean }[] };
  for (const p of list.providers.filter((x) => x.kind === "oidc")) {
    if (p.enabled) await ctx.put(`${API}/auth/sso/admin/providers/${p.id}`, { data: { enabled: false }, headers: auth });
    await ctx.delete(`${API}/auth/sso/admin/providers/${p.id}`, { headers: auth });
  }
  await ctx.dispose();
});

test.afterAll(() => {
  issuer?.kill();
});

async function noSideways(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

test("admin sets up Keycloak with the guided setup and a real test login (1440)", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page);
  await page.goto("/settings?tab=sso");
  await page.getByTestId("idp-add").click();
  await page.getByTestId("idp-preset-oidc-keycloak").click();
  const wizard = page.getByTestId("idp-wizard");
  await expect(wizard).toBeVisible();
  await expect(page.getByTestId("idp-changed")).toContainText("Son değişiklik:");
  await page.getByTestId("idp-preset-next").click();
  // step 2: the values to paste, from the public URL
  await expect(page.locator("[data-testid=idp-copy-redirect_uri] input")).toHaveValue(`${WEB}/api/v1/auth/sso/keycloak/callback`);
  await expect(page.getByTestId("idp-copy-redirect_uri-copy")).toBeVisible();
  await page.getByTestId("idp-console-next").click();
  // step 3: paste the values (NBSP and trailing spaces as copied from a console)
  await page.getByTestId("idp-issuer").fill(` ${ISSUER} `);
  await page.getByTestId("idp-client").fill("smartsched-e2e");
  await page.getByTestId("idp-secret").fill("e2e-fake-secret");
  await page.getByTestId("idp-values-save").click();
  await expect(page.getByTestId("idp-check-issuer")).toHaveAttribute("data-ok", "true");
  await expect(page.getByTestId("idp-secret-set")).toContainText("kayıtlı");
  await expect(page.getByText("e2e-fake-secret")).toHaveCount(0);
  await page.getByTestId("idp-values-next").click();
  // step 4: the real flow in a popup
  const popupPromise = page.waitForEvent("popup");
  await page.getByTestId("idp-test-login").click();
  const popup = await popupPromise;
  await popup.waitForURL(/test-done\?ok=1/, { timeout: 30_000 });
  await expect(popup.locator("h1")).toContainText("Test girişi tamamlandı");
  await popup.close();
  const result = page.getByTestId("idp-test-result");
  await expect(result).toHaveAttribute("data-ok", "true", { timeout: 15_000 });
  await expect(result).toContainText("ayse.yilmaz@uni.edu.tr");
  // step 5: enable for invited people only (the OIDC default)
  await page.getByTestId("idp-test-next").click();
  await expect(page.getByTestId("idp-invite-only")).toBeChecked();
  await page.getByTestId("idp-enable").click();
  const row = page.getByTestId("idp-row-keycloak");
  await expect(row).toContainText("Bağlı", { timeout: 15_000 });
  await expect(row).toContainText("Son değişiklik:");
  // an invitation for Keycloak
  await page.getByTestId("inv-email").fill(INVITED);
  await page.getByTestId("inv-provider").selectOption("keycloak");
  await page.getByTestId("inv-send").click(); // no SMTP on the stack: copy the link instead
  await page.getByTestId("inv-submit").click();
  const link = page.getByTestId("inv-created");
  await expect(link).toBeVisible();
  inviteLink = (await link.locator("input, pre").first().evaluate((el) => (el instanceof HTMLInputElement ? el.value : el.textContent ?? ""))).trim();
  expect(inviteLink).toContain("/login?invite=");
  // focus stays on the page, never on <body>
  expect(await page.evaluate(() => document.activeElement?.tagName)).not.toBe("BODY");
});

test("the invited person sees only the Keycloak button and signs in through it", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "tr-TR", timezoneId: "Europe/Istanbul" });
  const page = await ctx.newPage();
  await page.goto(inviteLink.replace(/^https?:\/\/[^/]+/, WEB));
  await expect(page.getByTestId("signin-invite")).toBeVisible();
  const btn = page.getByTestId("login-sso-keycloak");
  await expect(btn).toBeVisible();
  await expect(btn).toContainText("Keycloak ile giriş yap");
  await expect(page.getByTestId("login-sso-microsoft")).toHaveCount(0);
  await btn.click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30_000 });
  const me = await page.evaluate(async () => (await fetch("/api/v1/auth/me")).json());
  expect(me.email).toBe(INVITED);
  await ctx.close();
});

test("/login lists the provider beside the password door; provider errors read in Turkish", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "tr-TR" });
  const page = await ctx.newPage();
  await page.goto("/login");
  await expect(page.getByTestId("login-sso-keycloak")).toBeVisible();
  await expect(page.getByTestId("login-disclosure")).toBeVisible();
  await page.goto("/login?error=domain&provider=keycloak");
  await expect(page.getByTestId("signin-error-domain")).toContainText("izin verdiği bir e-posta alan adı");
  await ctx.close();
});

test("phone 390 × 844: buttons ≥ 44 px, inputs ≥ 16 px, no sideways scroll", async ({ browser }) => {
  const ctx = await browser.newContext(PHONE);
  const page = await ctx.newPage();
  await page.goto("/login");
  const btn = page.getByTestId("login-sso-keycloak");
  await expect(btn).toBeVisible();
  expect((await btn.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
  await noSideways(page);
  await login(page);
  await page.goto("/settings?tab=sso");
  await expect(page.getByTestId("identity-providers-panel")).toBeVisible();
  await noSideways(page);
  const fonts = await page.locator("[data-testid=identity-providers-panel] input:visible:not([type=file]):not([type=checkbox]):not([type=radio])").evaluateAll((els) => els.map((e) => parseFloat(getComputedStyle(e).fontSize)));
  expect(fonts.length).toBeGreaterThan(0);
  expect(Math.min(...fonts)).toBeGreaterThanOrEqual(16);
  const setup = page.getByTestId("idp-setup-keycloak");
  expect((await setup.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
  await setup.click();
  await expect(page.getByTestId("idp-wizard")).toBeVisible();
  await noSideways(page);
  await ctx.close();
});
