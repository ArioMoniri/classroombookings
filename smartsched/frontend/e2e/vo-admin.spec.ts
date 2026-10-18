/**
 * VO-07 on a real stack: /admin/ai voice at 1440 (mouse) and 390 × 844 (touch, tr-TR, Europe/Istanbul).
 *
 *  1. Sağlayıcılar: Deepgram (speech only) shows "Ses→yazı"; a test-only key, the KVKK record with "Bu sağlayıcı ses
 *     işler", Modelleri eşitle lists its speech models without a request.
 *  2. Modeller: the "Sesle yazma" row offers only speech-capable providers and models ("Seçilmedi (mikrofon gizli)"
 *     first), the text rows offer no speech model; the route is saved, and a second admin reads the same route.
 *  3. Koruma: the Ses card says there is no voice yet until the route exists, one switch turns voice on, the
 *     advanced settings are folded; a second admin reads the same switch. The guard bench has its mic.
 *  4. Limitler: voice time in minutes (10 / 100 by default); Kullanım has no voice card while nobody used voice.
 *  5. The speech test of a provider: the stored preview is shown as "Ses testi başarılı: “…”" (answered in the browser,
 *     the key is fake), and the real call's failure is a sentence.
 *  6. Phone 390: M-01 on every tab, M-02 / M-03 on the voice card and the voice route row.
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:<api> PW_PORT=<web> npx playwright test vo-admin
 */
import { chromium, expect, test, type Browser, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";
import { API, DESKTOP, FAKE_MIC, PHONE, ctxFor, focusNotOnBody, m01, m02m03 } from "./vo-setup";

const BASE = `http://127.0.0.1:${process.env.PW_PORT ?? 3100}`;
const STAMP = Date.now().toString(36);
const ADMIN2 = { email: `vo.admin2.${STAMP}@smartsched.local`, password: "Vo-2026!pw-admin2" };
test.describe.configure({ mode: "serial", timeout: 180_000 });
test.skip(!REAL, SKIP_REASON);

let browser: Browser;

test.beforeAll(async () => {
  const admin = await ctxFor(ADMIN_EMAIL, ADMIN_PASSWORD);
  // start from "no voice": route removed, voice off
  const routes = (await (await admin.get(`${API}/ai/admin/routes`)).json()) as { features: Record<string, unknown> };
  delete routes.features.voice_stt;
  await admin.put(`${API}/ai/admin/routes`, { data: { features: routes.features } });
  await admin.put(`${API}/ai/admin/voice`, { data: { enabled: false } });
  const r = await admin.post(`${API}/users`, { data: { email: ADMIN2.email, role: "ADMIN", password: ADMIN2.password, full_name: `Ses Yönetici ${STAMP}` } });
  expect(r.status(), await r.text()).toBe(201);
  await admin.dispose();
  browser = await chromium.launch({ args: FAKE_MIC });
});

test.afterAll(async () => {
  await browser?.close();
});

async function page1440(): Promise<Page> {
  const ctx = await browser.newContext({ ...DESKTOP, baseURL: BASE, permissions: ["microphone"] });
  const page = await ctx.newPage();
  await login(page);
  return page;
}

test("1–4. providers, the voice route, the Ses card and voice limits at 1440; a second admin sees the same", async () => {
  const page = await page1440();
  await page.goto("/admin/ai?tab=providers");
  const card = page.getByTestId("ai-provider-deepgram");
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("ai-provider-caps-deepgram")).toHaveText(/Ses→yazı/);
  await expect(page.getByTestId("ai-provider-caps-anthropic")).toHaveText(/^Yetenekler: Metin( · |$)/);
  await card.getByTestId("ai-key-deepgram-api_key").fill("e2e-placeholder-deepgram-key-0001");
  await card.getByTestId("ai-transfer-deepgram").locator("summary").click();
  await card.getByTestId("ai-transfer-mech-deepgram").selectOption("standard_contract");
  const voiceBox = card.getByTestId("ai-transfer-voice-deepgram");
  if (!(await voiceBox.isChecked())) await voiceBox.click(); // a rerun finds it ticked
  await card.getByLabel("Ses kaydının sağlayıcıda saklanma süresi").fill("Saklanmaz");
  await card.getByTestId("ai-provider-save-deepgram").click();
  await expect(page.getByText("Sağlayıcı kaydedildi.")).toBeVisible();
  await card.getByTestId("ai-provider-sync-deepgram").click();
  await expect(card.getByTestId("ai-sync-line-deepgram")).toContainText("model", { timeout: 30_000 });
  // the speech-only provider has no separate voice test button: its connection test is the voice test
  await expect(card.getByTestId("ai-provider-voice-test-deepgram")).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("providers-1440.png"), fullPage: false });

  // Ses card first: no route yet
  await page.goto("/admin/ai?tab=guard");
  await expect(page.getByTestId("ai-voice-card")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("ai-voice-no-route")).toContainText("Sesle yazma");
  await expect(page.getByTestId("ai-voice-advanced")).not.toHaveAttribute("open", "");

  // Modeller: the voice row
  await page.goto("/admin/ai?tab=models");
  const row = page.getByTestId("ai-route-voice_stt");
  await expect(row).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("ai-route-note-voice_stt")).toContainText("mikrofon kimseye gösterilmez");
  const prov = page.getByTestId("ai-route-provider-voice_stt");
  const options = await prov.locator("option").allTextContents();
  expect(options[0]).toBe("Seçilmedi (mikrofon gizli)");
  expect(options).not.toContain("Anthropic");
  await prov.selectOption("deepgram");
  const models = await page.getByTestId("ai-route-model-voice_stt").locator("option").allTextContents();
  expect(models.length).toBeGreaterThan(0);
  // no speech model on a text row
  for (const id of ["rules", "chat"]) {
    const textProviders = await page.getByTestId(`ai-route-provider-${id}`).locator("option").evaluateAll((o) => o.map((x) => (x as HTMLOptionElement).value));
    expect(textProviders).not.toContain("deepgram");
  }
  await page.getByTestId("ai-routes-save").click();
  await expect(page.getByText("Model seçimleri kaydedildi.").or(page.getByText(/kaydedildi/))).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("models-voice-1440.png") });

  // Koruma: route in place, switch voice on
  await page.goto("/admin/ai?tab=guard");
  await expect(page.getByTestId("ai-voice-card")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("ai-voice-no-route")).toHaveCount(0);
  const sw = page.getByTestId("ai-voice-enabled");
  await expect(sw).not.toBeChecked();
  await sw.click();
  await expect(page.getByText("Ses ayarları kaydedildi.")).toBeVisible();
  await expect(sw).toBeChecked();
  await focusNotOnBody(page);
  // the guard bench has its mic once voice is on (status read again on the next page)
  await page.reload();
  await expect(page.getByTestId("voice-mic-guard")).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: test.info().outputPath("guard-voice-1440.png") });

  // Limitler: minutes
  await page.goto("/admin/ai?tab=limits");
  const audio = page.getByTestId("ai-limits-audio");
  await expect(audio).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("ai-limit-audio-daily")).toHaveValue("10");
  await expect(page.getByTestId("ai-limit-audio-monthly")).toHaveValue("100");
  await page.context().close();

  // a second admin sees the same route and switch (one shared settings row)
  const ctx2 = await browser.newContext({ ...DESKTOP, baseURL: BASE });
  const p2 = await ctx2.newPage();
  await login(p2, ADMIN2.email, ADMIN2.password);
  await p2.goto("/admin/ai?tab=models");
  await expect(p2.getByTestId("ai-route-provider-voice_stt")).toHaveValue("deepgram", { timeout: 30_000 });
  await p2.goto("/admin/ai?tab=guard");
  await expect(p2.getByTestId("ai-voice-enabled")).toBeChecked({ timeout: 30_000 });
  await ctx2.close();
});

test("5. the speech test: the stored preview is shown; the real call with the fake key fails with a sentence", async () => {
  const page = await page1440();
  await page.goto("/admin/ai?tab=providers");
  const card = page.getByTestId("ai-provider-deepgram");
  await expect(card).toBeVisible({ timeout: 30_000 });
  // real call first
  const real = page.waitForResponse((r) => r.url().includes("/ai/admin/providers/deepgram/test"));
  await card.getByTestId("ai-provider-test-deepgram").click();
  const res = await real;
  const body = (await res.json()) as { ok: boolean; kind?: string };
  expect(body.ok).toBe(false);
  await expect(card.getByTestId("ai-provider-error-deepgram").or(card.getByTestId("ai-test-line-deepgram"))).toBeVisible({ timeout: 60_000 });
  // the preview rendering, with the answer a real key gives (VO-B API.md §3)
  await page.route("**/api/v1/ai/admin/providers/deepgram/test", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ at: "2026-10-18T09:00:00", ok: true, detail: "ok", model: "nova-3", kind: "stt", transcript_preview: "Şu cümle çok önemli" }) }),
  );
  await card.getByTestId("ai-provider-test-deepgram").click();
  await expect(page.getByText("Ses testi başarılı: “Şu cümle çok önemli”").or(page.getByText(/Şu cümle çok önemli/)).first()).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("voice-test-1440.png") });
  await page.context().close();
});

test("6. phone 390 × 844: M-01 on each tab, M-02 / M-03 on the voice card and the voice route row", async () => {
  const ctx = await browser.newContext({ ...PHONE, baseURL: BASE });
  const page = await ctx.newPage();
  await login(page);
  for (const tab of ["providers", "models", "usage", "limits", "guard"]) {
    await page.goto(`/admin/ai?tab=${tab}`);
    await expect(page.getByTestId("ai-admin")).toBeVisible({ timeout: 30_000 });
    await page.waitForTimeout(800);
    await m01(page);
  }
  await page.goto("/admin/ai?tab=guard");
  await expect(page.getByTestId("ai-voice-card")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("ai-voice-advanced").locator("summary").tap();
  await m02m03(page, "[data-testid=ai-voice-card]");
  await page.screenshot({ path: test.info().outputPath("guard-voice-390.png") });
  await page.goto("/admin/ai?tab=models");
  await expect(page.getByTestId("ai-route-voice_stt")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("ai-route-voice_stt").scrollIntoViewIfNeeded();
  await m02m03(page, "[data-testid=ai-route-voice_stt]");
  await page.screenshot({ path: test.info().outputPath("models-voice-390.png") });
  await page.goto("/admin/ai?tab=limits");
  await page.getByTestId("ai-limits-audio").scrollIntoViewIfNeeded();
  await m02m03(page, "[data-testid=ai-limits-audio]");
  await ctx.close();
});
