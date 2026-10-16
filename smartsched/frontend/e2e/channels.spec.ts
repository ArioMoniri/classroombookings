/**
 * Notification channels, admin + Profile flows that need no external provider (REAL backend, E2E_REAL=1):
 * write-only secrets, KVKK sign-off gate, VAPID generation, WhatsApp Web risk acknowledgement, Teams allowlist
 * refusal, the delivery log, and on Profile the Telegram deep link (+ polling), the SMS code round trip (wrong
 * code), and the narrow-scope push service worker. Every fake credential is built at run time; nothing is sent
 * to a real provider (the outbox may try and fail, which is the backend's business).
 */
import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import { login, REAL, SKIP_REASON } from "./helpers";
import { adminApi, type Admin } from "./identity";

test.describe.configure({ mode: "serial" });
test.skip(!REAL, SKIP_REASON);

let admin: Admin;
const KINDS = ["webpush", "telegram", "whatsapp_web", "sms", "teams"] as const;
const SIGNOFF = { signed: true, legal_basis: "e2e: Kurula bildirilen standart sözleşme", officer: "e2e KVKK sorumlusu" };

test.beforeAll(async () => {
  admin = await adminApi();
});

test.afterAll(async () => {
  for (const k of KINDS) await admin.send("PUT", `/channels/admin/${k}`, { enabled: false, kvkk_signoff: { signed: false } });
  await admin.send("PUT", "/channels/admin/telegram", { secrets: { bot_token: null } });
  await admin.send("PUT", "/channels/admin/sms", { secrets: { account_sid: null, auth_token: null } });
  await admin.send("PUT", "/channels/admin/whatsapp_web", { risk_ack: false });
  await admin.dispose();
});

async function openChannels(page: Page) {
  await page.goto("/settings?tab=channels");
  await expect(page.getByTestId("channels-admin")).toBeVisible();
}

async function expand(page: Page, kind: string) {
  const toggle = page.getByTestId(`channel-toggle-${kind}`);
  if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
}

test("admin: every channel is listed and off; secrets are write-only", async ({ page }) => {
  await login(page);
  await openChannels(page);
  for (const k of ["webpush", "telegram", "whatsapp", "whatsapp_web", "sms", "teams", "slack"]) await expect(page.getByTestId(`channel-${k}`)).toBeVisible();
  await expand(page, "telegram");
  const fake = ["e2e", "bot", randomUUID().replace(/-/g, "")].join("_");
  await page.getByTestId("secret-telegram-bot_token").fill(fake);
  await page.getByTestId("channel-save-telegram").click();
  await expect(page.getByTestId("secret-set-telegram-bot_token")).toBeVisible();
  // the value never comes back: not in the API, not in the page
  const api = await admin.get<{ channels: { kind: string; secrets: Record<string, boolean> }[] }>("/channels/admin");
  expect(api.channels.find((c) => c.kind === "telegram")?.secrets.bot_token).toBe(true);
  expect(JSON.stringify(api)).not.toContain(fake);
  expect(await page.content()).not.toContain(fake);
});

test("admin: Web Push needs keys, a contact and the KVKK sign-off before it sends", async ({ page }) => {
  await login(page);
  await openChannels(page);
  await expand(page, "webpush");
  const gen = page.getByTestId("vapid-generate");
  if (await gen.isVisible()) await gen.click();
  await expect(page.getByTestId("channel-webpush").getByText(/Bu sunucuda oluşturuldu|Generated on this server/)).toBeVisible();
  await expand(page, "webpush");
  await page.locator("#webpush-contact").fill("bilgi-islem@ornek.edu.tr");
  await page.getByTestId("channel-save-webpush").click();
  await expand(page, "webpush");
  await page.getByTestId("channel-enable-webpush").click();
  await expect(page.getByTestId("channel-missing-webpush")).toContainText(/KVKK/);
  await expand(page, "webpush");
  await page.getByTestId("kvkk-basis-webpush").fill(SIGNOFF.legal_basis);
  await page.getByTestId("kvkk-officer-webpush").fill(SIGNOFF.officer);
  await page.getByTestId("kvkk-sign-webpush").click();
  await expect(page.getByTestId("channel-webpush")).toContainText(/Gönderiyor|Sending/);
});

test("admin: WhatsApp Web bridge needs the risk acknowledgement; no bridge URL keeps QR off", async ({ page }) => {
  await login(page);
  await openChannels(page);
  await expand(page, "whatsapp_web");
  await expect(page.getByTestId("bridge-panel")).toContainText(/WhatsApp/);
  await page.getByTestId("bridge-ack").click();
  await page.getByTestId("bridge-ack-save").click();
  await expand(page, "whatsapp_web");
  await expect(page.getByTestId("bridge-connect")).toBeDisabled();
});

test("admin: a Teams target outside the vendor allowlist is refused with the reason", async ({ page }) => {
  // the e2e database imports rooms and courses but no departments: make one for this check and remove it after
  const existing = await admin.get<{ id: number }[]>("/departments");
  const made = existing.length ? null : await admin.send<{ id: number }>("POST", "/departments", { name: `e2e bölüm ${randomUUID().slice(0, 6)}` });
  if (made && made.status >= 400) throw new Error(`department: ${made.status}`);
  try {
    await login(page);
    await openChannels(page);
    await expand(page, "teams");
    const target = page.getByTestId("targets-teams");
    const select = target.locator("select");
    await expect.poll(() => select.locator("option").count()).toBeGreaterThan(1);
    await select.selectOption({ index: 1 });
    await target.locator("input").fill("https://example.com/hook");
    await target.getByRole("button", { name: /Ekle|Add/ }).click();
    await expect(target.getByRole("alert")).toBeVisible();
  } finally {
    if (made) await admin.send("DELETE", `/departments/${made.body.id}`);
  }
});

test("admin: the delivery log renders", async ({ page }) => {
  await login(page);
  await openChannels(page);
  await expect(page.getByTestId("channel-deliveries")).toBeVisible();
});

test("profile: Telegram deep link and the waiting state (no bot needed)", async ({ page }) => {
  await admin.send("PUT", "/channels/admin/telegram", { secrets: { bot_token: ["e2e", "bot", randomUUID().slice(0, 8)].join("_") }, options: { bot_username: "SmartSchedE2eBot", update_mode: "webhook" }, kvkk_signoff: SIGNOFF, enabled: true });
  await login(page);
  await page.goto("/profile");
  await page.getByTestId("channel-link-telegram").click();
  await page.getByTestId("telegram-start").click();
  const link = page.getByTestId("telegram-deeplink");
  await expect(link).toHaveAttribute("href", /^https:\/\/t\.me\/SmartSchedE2eBot\?start=[A-Za-z0-9_-]{16,}$/);
  await expect(page.getByTestId("linker-telegram").getByRole("status")).toBeVisible();
});

test("profile: SMS phone → code → a wrong code is refused", async ({ page }) => {
  const r = await admin.send("PUT", "/channels/admin/sms", { options: { provider: "twilio", from_number: "+905321112233" }, secrets: { account_sid: ["e2e", "sid", randomUUID().slice(0, 8)].join("-"), auth_token: ["e2e", "tok", randomUUID().slice(0, 8)].join("-") }, kvkk_signoff: SIGNOFF, enabled: true });
  expect(r.status, JSON.stringify(r.body)).toBeLessThan(400);
  await login(page);
  await page.goto("/profile");
  await page.getByTestId("channel-link-sms").click();
  await page.getByTestId("sms-phone").fill("0532 111 22 33");
  await page.getByTestId("sms-send-code").click();
  await expect(page.getByTestId("linker-sms").getByRole("status")).toBeVisible();
  await page.getByTestId("sms-code").fill("000000");
  await page.getByTestId("sms-verify").click();
  await expect(page.getByTestId("linker-sms").getByRole("alert")).toBeVisible();
});

test("profile: the push worker registers only on the action, with the narrow /push-sw/ scope", async ({ page, context, baseURL }) => {
  await context.grantPermissions(["notifications"], { origin: baseURL });
  await login(page);
  await page.goto("/profile");
  expect(await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length)).toBe(0);
  await page.getByTestId("channel-link-webpush").click();
  await page.getByTestId("push-subscribe").click();
  // the push service may be unreachable from the test runner: success or a clear error, never a hang
  await expect(page.getByTestId("linker-webpush").getByRole("alert").or(page.getByTestId("linked-webpush"))).toBeVisible({ timeout: 30_000 });
  const scopes = await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).map((r) => new URL(r.scope).pathname));
  expect(scopes).toEqual(["/push-sw/"]);
  expect(await page.evaluate(() => navigator.serviceWorker.controller)).toBeNull();
});
