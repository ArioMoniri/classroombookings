/**
 * VO-06 / VO-08 on a real stack: the mic in the chat panel, studio "write it", the upload panel's paste tab and the
 * admin guard bench, with Chromium's fake microphone, at 1440 (mouse) and 390 × 844 (touch, tr-TR, Europe/Istanbul).
 *
 *  1. chat (desktop): first use shows the consent sheet (provider + region), Kabul et ve başla records the consent,
 *     click to start, click to stop, the transcript is in the box (selected, focused, "Sesle girildi"), nothing is
 *     sent until the user edits and presses send; the streamed answer comes from the text stub.
 *  2. the real transcription path: the clip goes as the raw body (audio/webm;codecs=opus) to the real backend, whose
 *     fake Deepgram key fails → "Ses yazıya dökülemedi…" (provider_error), the box untouched.
 *  3. a spoken injection lands in the box, and the chat endpoint refuses it on send (the guard runs on send).
 *  4. write-it and the paste tab: the transcript goes into their boxes.
 *  5. phone: press and hold in the chat tab, release → transcript; M-01 / M-02 / M-03 on the voice controls and the
 *     consent sheet; focus never on <body>.
 *  6. site policy `microphone=()` → "Bu sitede mikrofon kullanımı kapalı. Yöneticinize bildirin."; a browser
 *     without the grant → "Mikrofon izni verilmedi…".
 *  7. voice off → no mic anywhere.
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:<api> PW_PORT=<web> VO_STUB_PORT=19792 npx playwright test vo-mounts
 */
import type http from "node:http";
import { chromium, expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";
import { API, DESKTOP, FAKE_MIC, PHONE, SPOKEN, SPOKEN_INJECTION, blockMicByPolicy, ctxFor, focusNotOnBody, hold, m01, m02m03, setupText, setupVoice, startTextStub, stubTranscript } from "./vo-setup";

const STUB_PORT = Number(process.env.VO_STUB_PORT ?? 19792);
const BASE = `http://127.0.0.1:${process.env.PW_PORT ?? 3100}`;
test.describe.configure({ mode: "serial", timeout: 180_000 });
test.skip(!REAL, SKIP_REASON);

let stub: http.Server | null = null;
let runId = 0;
let browser: Browser;

test.beforeAll(async () => {
  stub = await startTextStub(STUB_PORT);
  const admin = await ctxFor(ADMIN_EMAIL, ADMIN_PASSWORD);
  await setupVoice(admin);
  await setupText(admin, STUB_PORT);
  // a fresh first use: the admin has not agreed to voice yet
  await admin.delete(`${API}/me/consents/voice`);
  const runs = (await (await admin.get(`${API}/runs`)).json()) as { id: number }[] | { items: { id: number }[] };
  runId = (Array.isArray(runs) ? runs : runs.items)[0]!.id;
  await admin.dispose();
  browser = await chromium.launch({ args: FAKE_MIC });
});

test.afterAll(async () => {
  await browser?.close();
  await new Promise<void>((resolve) => (stub ? stub.close(() => resolve()) : resolve()));
});

async function open(opts: typeof DESKTOP | typeof PHONE, grant = true): Promise<{ ctx: BrowserContext; page: Page }> {
  const ctx = await browser.newContext({ ...opts, baseURL: BASE, permissions: grant ? ["microphone"] : [] });
  const page = await ctx.newPage();
  await login(page);
  return { ctx, page };
}

const chatBox = (page: Page) => page.getByTestId("chat-panel").locator("textarea").first();
const chatMic = (page: Page) => page.getByTestId("voice-mic-chat").getByTestId("voice-mic");

test("1. chat at 1440: consent first, click to start / stop, transcript in the box, never sent until the user sends", async () => {
  const { ctx, page } = await open(DESKTOP);
  const calls = await stubTranscript(page, SPOKEN);
  await page.goto(`/runs/${runId}`);
  const mic = chatMic(page);
  await expect(mic).toBeVisible({ timeout: 90_000 });
  await expect(mic).toHaveAccessibleName("Sesle yaz");
  await mic.click();
  const sheet = page.getByTestId("voice-consent");
  await expect(sheet).toBeVisible();
  await expect(sheet).toContainText("Deepgram");
  await expect(sheet).toContainText("ses kaydı saklanmaz");
  await expect(page.getByTestId("voice-consent-accept")).toBeFocused();
  await page.screenshot({ path: test.info().outputPath("chat-consent-1440.png") });
  await page.getByTestId("voice-consent-accept").click();
  await expect(page.getByTestId("voice-mic-chat")).toHaveAttribute("data-phase", "recording", { timeout: 15_000 });
  await expect(mic).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("voice-level")).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("chat-recording-1440.png") });
  await hold(page, 1800);
  await mic.click();
  const box = chatBox(page);
  await expect(box).toHaveValue(SPOKEN, { timeout: 15_000 });
  await expect(box).toBeFocused();
  expect(await box.evaluate((el: HTMLTextAreaElement) => [el.selectionStart, el.selectionEnd])).toEqual([0, SPOKEN.length]);
  await expect(page.getByTestId("voice-chip")).toHaveText("Sesle girildi");
  expect(calls).toHaveLength(1);
  expect(calls[0]!.url).toContain("feature=chat");
  expect(calls[0]!.url).toContain("lang=tr");
  expect(calls[0]!.type).toMatch(/^audio\/webm/);
  expect(calls[0]!.bytes).toBeGreaterThan(500);
  // nothing was sent: no user turn in the list yet
  await expect(page.getByTestId("chat-panel")).not.toContainText("Tamam, B-204");
  await page.screenshot({ path: test.info().outputPath("chat-inserted-1440.png") });
  // edit, then send with Enter: the stub's answer streams in
  await box.press("End");
  await box.type(" olsun");
  await expect(page.getByTestId("voice-chip")).toHaveCount(0);
  await box.press("Enter");
  await expect(page.getByTestId("chat-panel")).toContainText("Tamam, B-204", { timeout: 60_000 });
  await focusNotOnBody(page);
  await ctx.close();
});

test("2. the real transcription path: raw webm to the backend, the fake provider key gives the provider-error sentence", async () => {
  const { ctx, page } = await open(DESKTOP);
  const seen: { status: number; type: string }[] = [];
  page.on("response", (r) => {
    if (r.url().includes("/api/v1/ai/voice/transcribe")) seen.push({ status: r.status(), type: r.request().headers()["content-type"] ?? "" });
  });
  await page.goto(`/runs/${runId}`);
  const mic = chatMic(page);
  await expect(mic).toBeVisible({ timeout: 90_000 });
  await mic.click();
  await expect(page.getByTestId("voice-mic-chat")).toHaveAttribute("data-phase", "recording", { timeout: 15_000 });
  await hold(page, 1500);
  await mic.click();
  const err = page.getByTestId("voice-mic-chat").getByTestId("voice-error");
  await expect(err).toBeVisible({ timeout: 90_000 });
  expect(seen[0]?.type).toMatch(/^audio\/webm/);
  expect(seen[0]?.status, "the backend accepted the clip and the provider failed").toBe(502);
  await expect(err).toHaveText("Ses yazıya dökülemedi. Tekrar deneyin ya da yazarak devam edin.");
  await expect(chatBox(page)).toHaveValue("");
  await focusNotOnBody(page);
  await ctx.close();
});

test("3. a spoken injection lands in the box and is refused on send", async () => {
  const { ctx, page } = await open(DESKTOP);
  await stubTranscript(page, SPOKEN_INJECTION);
  await page.goto(`/runs/${runId}`);
  const mic = chatMic(page);
  await expect(mic).toBeVisible({ timeout: 90_000 });
  await mic.click();
  await hold(page, 1200);
  await mic.click();
  const box = chatBox(page);
  await expect(box).toHaveValue(SPOKEN_INJECTION, { timeout: 15_000 });
  const refused = page.waitForResponse((r) => /\/chat(\/stream)?$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
  await box.press("Enter");
  expect((await refused).status()).toBe(422);
  await expect(page.getByTestId("chat-panel")).not.toContainText("Tamam, B-204");
  await page.screenshot({ path: test.info().outputPath("chat-injection-1440.png") });
  await focusNotOnBody(page);
  await ctx.close();
});

test("4. studio write-it and the paste tab: the transcript goes into their boxes", async () => {
  const { ctx, page } = await open(DESKTOP);
  await stubTranscript(page, "Hemşirelik dersleri B blokta olsun");
  await page.goto("/generate");
  await page.getByTestId("scope-step").waitFor({ timeout: 60_000 });
  await page.getByTestId("rail-step-rules").click();
  await page.getByTestId("rules-step").waitFor();
  const writeMic = page.getByTestId("voice-mic-rules").first().getByTestId("voice-mic");
  await expect(writeMic).toBeVisible();
  await writeMic.click();
  await hold(page, 1200);
  await writeMic.click();
  await expect(page.getByTestId("rule-composer-input")).toHaveValue("Hemşirelik dersleri B blokta olsun", { timeout: 15_000 });
  await expect(page.getByTestId("rule-composer-input")).toBeFocused();
  await expect(page.getByTestId("nl-analyse")).toBeEnabled();
  await page.screenshot({ path: test.info().outputPath("write-it-1440.png") });
  // the paste tab of the upload panel
  if (!(await page.getByTestId("upload-panel").isVisible())) await page.getByTestId("add-upload").click();
  await page.getByTestId("upload-panel").getByRole("tab", { name: "Metin yapıştır" }).click();
  const paste = page.getByTestId("upload-panel").getByRole("textbox", { name: "Metin yapıştır" });
  const pasteMic = page.getByTestId("upload-panel").getByTestId("voice-mic");
  await pasteMic.click();
  await hold(page, 1200);
  await pasteMic.click();
  await expect(paste).toHaveValue("Hemşirelik dersleri B blokta olsun", { timeout: 15_000 });
  await expect(paste).toBeFocused();
  await ctx.close();
});

test("5. phone 390 × 844: press and hold in the chat tab, release → transcript; M-01 / M-02 / M-03; focus never on body", async () => {
  const { ctx, page } = await open(PHONE);
  await stubTranscript(page, SPOKEN);
  await page.goto(`/runs/${runId}`);
  await page.getByRole("tab", { name: "Sohbet" }).click();
  const mic = chatMic(page);
  await expect(mic).toBeVisible({ timeout: 90_000 });
  const box = await mic.boundingBox();
  expect(box!.width).toBeGreaterThanOrEqual(44);
  expect(box!.height).toBeGreaterThanOrEqual(44);
  await m01(page);
  await m02m03(page, "[data-testid=voice-mic-chat]");
  const fs = await chatBox(page).evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  expect(fs, "the chat box is 16 px on the phone (no zoom on focus)").toBeGreaterThanOrEqual(16);
  // press and hold with a touch pointer (CDP touch events drive pointerdown / pointerup with pointerType touch)
  const cdp = await ctx.newCDPSession(page);
  const x = box!.x + box!.width / 2;
  const y = box!.y + box!.height / 2;
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] });
  await expect(page.getByTestId("voice-mic-chat")).toHaveAttribute("data-phase", "recording", { timeout: 15_000 });
  await expect(page.getByTestId("voice-hold-hint")).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("chat-hold-390.png") });
  await m01(page);
  await page.waitForTimeout(1500);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await expect(chatBox(page)).toHaveValue(SPOKEN, { timeout: 15_000 });
  await expect(chatBox(page)).toBeFocused();
  await page.screenshot({ path: test.info().outputPath("chat-inserted-390.png") });
  await m01(page);
  // slide left cancels: nothing more is uploaded
  const before = await chatBox(page).inputValue();
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] });
  await expect(page.getByTestId("voice-mic-chat")).toHaveAttribute("data-phase", "recording", { timeout: 15_000 });
  await page.waitForTimeout(600);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: x - 120, y }] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await expect(page.getByTestId("voice-mic-chat")).toHaveAttribute("data-phase", "idle");
  await expect(chatBox(page)).toHaveValue(before);
  await focusNotOnBody(page);
  await ctx.close();
});

test("5b. phone: the consent sheet is a bottom sheet with 44 px actions", async () => {
  const admin = await ctxFor(ADMIN_EMAIL, ADMIN_PASSWORD);
  await admin.delete(`${API}/me/consents/voice`);
  await admin.dispose();
  const { ctx, page } = await open(PHONE);
  await page.goto(`/runs/${runId}`);
  await page.getByRole("tab", { name: "Sohbet" }).click();
  await chatMic(page).tap();
  const sheet = page.getByTestId("voice-consent");
  await expect(sheet).toBeVisible();
  const r = await sheet.boundingBox();
  expect(Math.round(r!.y + r!.height)).toBeGreaterThanOrEqual(844 - 40); // anchored at the bottom
  await m01(page);
  await m02m03(page, "[data-testid=voice-consent]");
  await page.screenshot({ path: test.info().outputPath("consent-390.png") });
  await page.getByTestId("voice-consent-later").tap();
  await expect(sheet).toHaveCount(0);
  await expect(chatMic(page)).toBeFocused();
  // agree for the remaining tests
  await chatMic(page).tap();
  await page.getByTestId("voice-consent-accept").tap();
  await expect(page.getByTestId("voice-mic-chat")).toHaveAttribute("data-phase", /recording|starting/, { timeout: 15_000 });
  await page.getByTestId("voice-cancel").tap();
  await ctx.close();
});

test("6. the site policy blocks the microphone; a browser without the grant says permission denied", async () => {
  // policy: Permissions-Policy microphone=() on the documents (the nginx / Caddy header before VO-05)
  for (const opts of [DESKTOP, PHONE]) {
    const ctx = await browser.newContext({ ...opts, baseURL: BASE, permissions: ["microphone"] });
    await blockMicByPolicy(ctx);
    const page = await ctx.newPage();
    await login(page);
    await page.goto(`/runs/${runId}`);
    if (opts === PHONE) await page.getByRole("tab", { name: "Sohbet" }).click();
    await chatMic(page).click();
    const err = page.getByTestId("voice-mic-chat").getByTestId("voice-error");
    await expect(err).toHaveText("Bu sitede mikrofon kullanımı kapalı. Yöneticinize bildirin.");
    await expect(err).toHaveAttribute("data-code", "policy_blocked");
    await page.screenshot({ path: test.info().outputPath(`policy-${opts.viewport.width}.png`) });
    await focusNotOnBody(page);
    await ctx.close();
  }
  // the VO-05 edge header microphone=(self) (nginx default.conf:108, Caddyfile:24; no nginx binary on this host, so
  // the header is put on the documents here): getUserMedia works and the recording starts
  {
    const ctx = await browser.newContext({ ...DESKTOP, baseURL: BASE, permissions: ["microphone"] });
    await ctx.route("**/*", async (route) => {
      if (route.request().resourceType() !== "document") return route.continue();
      const res = await route.fetch();
      await route.fulfill({ response: res, headers: { ...res.headers(), "permissions-policy": "camera=(), microphone=(self), geolocation=(), payment=(), usb=(), interest-cohort=()" } });
    });
    const page = await ctx.newPage();
    await login(page);
    await page.goto(`/runs/${runId}`);
    expect(await page.evaluate(() => (document as unknown as { featurePolicy?: { allowsFeature(f: string): boolean } }).featurePolicy?.allowsFeature("microphone"))).toBe(true);
    await chatMic(page).click();
    await expect(page.getByTestId("voice-mic-chat")).toHaveAttribute("data-phase", "recording", { timeout: 15_000 });
    await page.getByTestId("voice-cancel").click();
    await ctx.close();
  }
  // no grant: a browser without the fake-UI flag answers the prompt with "Block"
  const plain = await chromium.launch({ args: ["--use-fake-device-for-media-stream"] });
  const ctx = await plain.newContext({ ...DESKTOP, baseURL: BASE });
  const page = await ctx.newPage();
  await login(page);
  await page.goto(`/runs/${runId}`);
  await chatMic(page).click();
  const err = page.getByTestId("voice-mic-chat").getByTestId("voice-error");
  await expect(err).toContainText("Mikrofon izni verilmedi.", { timeout: 15_000 });
  await expect(err).toContainText("Mikrofon › İzin ver");
  await page.screenshot({ path: test.info().outputPath("denied-1440.png") });
  await focusNotOnBody(page);
  await plain.close();
});

test("7. voice off: no mic on any surface", async () => {
  const admin = await ctxFor(ADMIN_EMAIL, ADMIN_PASSWORD);
  await admin.put(`${API}/ai/admin/voice`, { data: { enabled: false } });
  const { ctx, page } = await open(DESKTOP);
  await page.goto(`/runs/${runId}`);
  await expect(chatBox(page)).toBeVisible({ timeout: 90_000 });
  await page.waitForResponse((r) => r.url().includes("/ai/voice/status")).catch(() => undefined);
  await page.waitForTimeout(500);
  await expect(page.getByTestId("voice-mic")).toHaveCount(0);
  await admin.put(`${API}/ai/admin/voice`, { data: { enabled: true } });
  await admin.dispose();
  await ctx.close();
});
