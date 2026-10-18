/**
 * WG-06 "Başlarken" checklist + Help against the REAL backend (E2E_REAL=1).
 *
 * - Desktop: the sidebar pill "Başlarken n / N" opens the 420 px panel; a booking made through /reserve ticks
 *   "İlk rezervasyonunuzu yapın" after a refetch (the server computes it), with no client event.
 * - Help › Turu yeniden başlat reopens the sheet (user menu); ⌘K lists the same command.
 * - Phone: the first row of "Daha" opens the full-screen list (64 px rows); M-01/02/03 on the Daha tab and the list.
 */
import { expect, test, type Page } from "@playwright/test";
import { REAL, SKIP_REASON } from "./helpers";
import { pinLanguage } from "./language";
import { DESKTOP, PHONE, adminApi, makeTeacher, mobileChecks, signIn, type Api } from "./wg-helpers";

test.describe.configure({ mode: "serial", timeout: 240_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

let api: Api;
test.beforeAll(async () => {
  api = await adminApi();
});
test.afterAll(async () => {
  await api.ctx.dispose();
});

async function closeSheet(page: Page) {
  const sheet = page.getByTestId("welcome-sheet");
  // locator.isVisible() does not wait (its timeout is ignored): the sheet opened after the check and covered the pill
  // (e2e lane 2026-10-18); wait for it like a web-first assertion
  if (await sheet.waitFor({ state: "visible", timeout: 15_000 }).then(() => true, () => false)) {
    await page.getByTestId("welcome-later").click();
    await expect(sheet).toBeHidden();
  }
}

/** A real booking through /reserve (the quick reserve's three taps: the slot is preselected, pick a room, Rezerve et). */
async function bookThroughReserve(page: Page): Promise<boolean> {
  await page.goto("/reserve");
  await expect(page.getByTestId("quick-reserve")).toBeVisible({ timeout: 20_000 });
  const room = page.getByTestId("qr-rooms").locator('[role=radio][data-action="book"]').first();
  if (!(await room.waitFor({ state: "visible", timeout: 10_000 }).then(() => true, () => false))) return false;
  await room.click();
  await page.getByTestId("qr-submit").click();
  await expect(page.getByTestId("qr-receipt-title")).toHaveText("Rezerve edildi", { timeout: 20_000 });
  return true;
}

test("desktop: the pill and panel; a booking ticks 'İlk rezervasyonunuzu yapın' after a refetch; Help › restart reopens the sheet", async ({ browser }) => {
  const p = await makeTeacher(api, "wg.check.st");
  const { context, page } = await signIn(browser, p, DESKTOP);
  await page.goto("/reserve");
  await closeSheet(page);
  const pill = page.getByTestId("checklist-pill");
  await expect(pill).toBeVisible();
  await expect(pill).toHaveAccessibleName(/^Başlarken, \d adımdan \d tanesi tamam$/);
  await pill.click();
  const panel = page.getByTestId("checklist-panel").first();
  await expect(panel).toBeVisible();
  await expect(page.getByTestId("checklist-progress").first()).toHaveAttribute("role", "progressbar");
  const row = page.getByTestId("checklist-item-first_booking").first();
  await expect(row).toHaveAttribute("data-done", "false");
  await page.keyboard.press("Escape");
  const booked = await bookThroughReserve(page);
  test.skip(!booked, "no bookable room for the quick reserve on this stack");
  await page.reload();
  await pill.click();
  await expect(page.getByTestId("checklist-item-first_booking").first()).toHaveAttribute("data-done", "true", { timeout: 15_000 });
  await page.keyboard.press("Escape");
  // Help › Turu yeniden başlat
  await page.locator('aside [data-testid="user-menu"]').click();
  await page.getByTestId("help-restart-tour").click();
  await expect(page.getByTestId("welcome-sheet")).toBeVisible({ timeout: 10_000 });
  await page.getByTestId("welcome-later").click();
  // ⌘K has the same command
  await page.keyboard.press("Control+k");
  await page.keyboard.type(">tur");
  await expect(page.getByText("Turu yeniden başlat").first()).toBeVisible();
  await context.close();
});

test("phone: the first row of 'Daha' is the checklist; the full-screen list; MOBILE checks", async ({ browser }) => {
  const p = await makeTeacher(api, "wg.check.ph");
  const { context, page } = await signIn(browser, p, PHONE);
  await page.goto("/reserve");
  await closeSheet(page);
  await page.getByTestId("open-drawer").tap();
  const row = page.getByTestId("drawer-checklist");
  await expect(row).toBeVisible();
  expect((await row.boundingBox())!.height).toBeGreaterThanOrEqual(88);
  await mobileChecks(page, '[role="dialog"]');
  await row.tap();
  const list = page.getByTestId("checklist-sheet");
  await expect(list).toBeVisible({ timeout: 10_000 });
  const first = list.locator('[data-testid^="checklist-item-"] a').first();
  expect((await first.boundingBox())!.height).toBeGreaterThanOrEqual(63);
  await mobileChecks(page, '[data-testid="checklist-sheet"]');
  await first.tap();
  await expect(list).toBeHidden();
  await context.close();
});
