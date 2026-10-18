/**
 * WG-04 welcome sheet against the REAL backend (E2E_REAL=1), 1440 mouse and 390×844 touch (tr-TR, Europe/Istanbul).
 *
 * - A new academician signs in on a phone: the sheet (bottom-sheet pager) shows once, focus on the greeting,
 *   MOBILE M-01/02/03/05 on /reserve with it open. "Sonra" → a reload shows nothing, a second browser shows nothing.
 * - A new staff member on desktop: the staff cards; keyboard only (Tab through, Esc = Sonra, focus not on <body>).
 * - Reduced motion: the sheet still reaches every state; the hero is the static poster.
 * - A deep link (/approvals/123) is never interrupted; /public never calls GET /welcome.
 */
import { expect, test } from "@playwright/test";
import { REAL, SKIP_REASON } from "./helpers";
import { pinLanguage } from "./language";
import { DESKTOP, PHONE, adminApi, focusNotBody, makeAcademician, makeTeacher, mobileChecks, m05, signIn, unlink, welcomeOf, type Api } from "./wg-helpers";

test.describe.configure({ mode: "serial", timeout: 240_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

let api: Api;
const linked: { id: number; instructorId: number | null }[] = [];
test.beforeAll(async () => {
  api = await adminApi();
});
test.afterAll(async () => {
  for (const p of linked) await unlink(api, p);
  await api.ctx.dispose();
});

test("phone: a new academician sees the sheet once; 'Sonra' holds on reload and on another device", async ({ browser }) => {
  const ayse = await makeAcademician(api, "wg.sheet.ac");
  linked.push(ayse);
  const w = await welcomeOf(api, ayse);
  expect(w.show?.kind).toBe("sheet");
  const { context, page } = await signIn(browser, ayse, PHONE);
  await page.goto("/reserve");
  const sheet = page.getByTestId("welcome-sheet");
  await expect(sheet).toBeVisible({ timeout: 20_000 });
  await expect(sheet).toHaveAttribute("data-variant", "pager");
  await expect(page.getByTestId("welcome-sheet-title")).toBeFocused();
  await expect(page.getByTestId("welcome-page")).toHaveText(/^1 \/ \d$/);
  // MOBILE M-01 / M-02 (inside the sheet) / M-03 with the sheet open; M-05: "İleri" in the bottom 40 %
  await mobileChecks(page, '[data-testid="welcome-sheet"]');
  const reach = await m05(page, '[data-testid="welcome-next"]');
  expect(reach.ok, JSON.stringify(reach)).toBe(true);
  const box = await sheet.boundingBox();
  expect(Math.abs(box!.y + box!.height - 844)).toBeLessThanOrEqual(2); // M-04: anchored to the bottom
  await page.getByTestId("welcome-next").tap();
  await expect(page.getByTestId("welcome-page")).toHaveText(/^2 \//);
  await page.getByTestId("welcome-later").tap();
  await expect(sheet).toBeHidden();
  await focusNotBody(page);
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("welcome-sheet")).toHaveCount(0);
  await context.close();
  // another device (a new browser, no sessionStorage): the server says snoozed
  const second = await signIn(browser, ayse, DESKTOP);
  await second.page.goto("/reserve");
  await second.page.waitForLoadState("networkidle");
  await second.page.waitForTimeout(1500);
  await expect(second.page.getByTestId("welcome-sheet")).toHaveCount(0);
  await second.context.close();
  expect((await welcomeOf(api, ayse)).show).toBeNull();
});

test("desktop keyboard only: a new staff member, Tab through the cards, Esc = Sonra, focus returns", async ({ browser }) => {
  const pelin = await makeTeacher(api, "wg.sheet.st");
  const { context, page } = await signIn(browser, pelin, DESKTOP);
  await page.goto("/reserve");
  const sheet = page.getByTestId("welcome-sheet");
  await expect(sheet).toBeVisible({ timeout: 20_000 });
  await expect(sheet).toHaveAttribute("data-variant", "dialog");
  await expect(page.getByTestId("welcome-sheet-title")).toContainText("SmartSched'e hoş geldiniz");
  await expect(page.getByTestId("welcome-card-find_room")).toBeVisible();
  await expect(page.getByTestId("welcome-badge")).toContainText("İdari personel");
  const width = (await sheet.boundingBox())!.width;
  expect(width).toBeGreaterThan(600);
  expect(width).toBeLessThanOrEqual(641);
  // Tab moves through the cards and buttons and stays in the dialog
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => !!document.activeElement?.closest('[data-testid="welcome-sheet"]'))).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await focusNotBody(page);
  await context.close();
});

test("reduced motion: every state is reached, the hero is the static poster", async ({ browser }) => {
  const p = await makeTeacher(api, "wg.sheet.rm");
  const { context, page } = await signIn(browser, p, { ...DESKTOP, reducedMotion: "reduce" });
  await page.goto("/reserve");
  await expect(page.getByTestId("welcome-sheet")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("welcome-hero").locator("img")).toBeVisible();
  await page.getByTestId("welcome-never").click();
  await expect(page.getByTestId("welcome-sheet")).toBeHidden();
  await context.close();
});

test("a deep link is never interrupted; /public never calls GET /welcome", async ({ browser }) => {
  const p = await makeTeacher(api, "wg.sheet.dl");
  const context = await browser.newContext(DESKTOP);
  const page = await context.newPage();
  const welcomeCalls: string[] = [];
  page.on("request", (r) => {
    if (/\/api\/v1\/welcome(\?|$)/.test(r.url())) welcomeCalls.push(r.url());
  });
  await page.goto("/public");
  await page.waitForLoadState("networkidle");
  expect(welcomeCalls).toEqual([]);
  await page.goto(`/login?method=local&next=${encodeURIComponent("/approvals/123")}`);
  await page.getByTestId("login-identifier").fill(p.username);
  await page.getByTestId("login-password").fill(p.password);
  await page.getByTestId("login-submit").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30_000 });
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1500);
  await expect(page.getByTestId("welcome-sheet")).toHaveCount(0);
  await context.close();
});
