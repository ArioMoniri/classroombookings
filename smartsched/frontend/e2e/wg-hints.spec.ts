/**
 * WG-07 feature hints against the REAL backend (E2E_REAL=1). The test accounts are created after the wave-3 release,
 * so the admin switch "Herkese ipucu göster" (hints_for_all, "new accounts included") is turned on for this file and
 * put back afterwards.
 *
 * - Staff, desktop: after the sheet is closed for good, the next sign-in auto-shows the quick-reserve hint as a
 *   non-modal popover on the nav entry (focus stays put); "Anladım" persists: another browser shows nothing.
 * - A staff account never gets the admin hints (payload, and no strip on /admin/ai).
 * - Admin: the /admin/ai strip once (role=status); after "Anladım" a reload shows nothing.
 * - Phone: the quick-reserve hint is an inline card at the top of /bookings, 44 px buttons.
 */
import { expect, test } from "@playwright/test";
import { REAL, SKIP_REASON } from "./helpers";
import { pinLanguage } from "./language";
import { DESKTOP, PHONE, adminApi, m02, makeTeacher, settings, signIn, welcomeOf, type Api, type Person } from "./wg-helpers";

test.describe.configure({ mode: "serial", timeout: 240_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

let api: Api;
let before: Record<string, unknown> | null = null;
test.beforeAll(async () => {
  api = await adminApi();
  before = ((await api.json<{ settings: Record<string, unknown> }>("GET", "/welcome/settings")).settings ?? null) as Record<string, unknown> | null;
  await settings(api, { hints: true, hints_for_all: true });
});
test.afterAll(async () => {
  if (before) await settings(api, { hints: before.hints ?? true, hints_for_all: before.hints_for_all ?? false });
  await api.ctx.dispose();
});

/** Close the first-sign-in sheet for good through the API (the person's own event). */
async function dismissSheet(p: Person) {
  await api.json("POST", "/welcome/events", { guide_key: "sheet", event: "dismissed" }, await api.tokenFor(p.username));
}

test("staff desktop: the quick-reserve popover once, non-modal; 'Anladım' holds on another browser", async ({ browser }) => {
  const p = await makeTeacher(api, "wg.hint.st");
  await dismissSheet(p);
  const w = await welcomeOf(api, p);
  expect(w.hints.map((h) => h.key)).toContain("hint.quick_reserve");
  expect(w.hints.map((h) => h.key)).not.toContain("hint.admin_ai");
  const { context, page } = await signIn(browser, p, DESKTOP);
  await page.goto("/bookings");
  const pop = page.getByTestId("hint-quick_reserve");
  await expect(pop).toBeVisible({ timeout: 20_000 });
  await expect(pop).toHaveAttribute("role", "dialog");
  await expect(pop).toHaveAttribute("aria-modal", "false");
  expect(await page.evaluate(() => !!document.activeElement?.closest('[data-testid="hint-quick_reserve"]'))).toBe(false);
  await expect(page.getByTestId("new-badge-quick_reserve")).toBeVisible();
  await page.getByTestId("hint-dismiss-quick_reserve").click();
  await expect(pop).toBeHidden();
  await context.close();
  const again = await signIn(browser, p, DESKTOP);
  await again.page.goto("/bookings");
  await again.page.waitForLoadState("networkidle");
  await again.page.waitForTimeout(1500);
  await expect(again.page.getByTestId("hint-quick_reserve")).toHaveCount(0);
  await expect(again.page.getByTestId("new-badge-quick_reserve")).toHaveCount(0);
  await again.context.close();
});

test("a staff account never sees admin hints", async ({ browser }) => {
  const p = await makeTeacher(api, "wg.hint.no");
  await dismissSheet(p);
  const w = await welcomeOf(api, p);
  for (const k of ["hint.admin_ai", "hint.admin_ops", "hint.admin_integrations"]) expect(w.hints.map((h) => h.key)).not.toContain(k);
  const { context, page } = await signIn(browser, p, DESKTOP);
  await page.goto("/admin/ai");
  await expect(page.getByText("Bu sayfaya erişiminiz yok").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("hint-admin_ai")).toHaveCount(0);
  await context.close();
});

test("admin: the /admin/ai strip once; after 'Anladım' a reload shows nothing", async ({ browser }) => {
  const username = `wg.hint.ad.${Date.now().toString(36)}`;
  const admin = await api.json<{ id: number }>("POST", "/users", { username, email: `${username}@uni.edu.tr`, firstname: "Fatih", lastname: "Bey", role: "ADMIN", password: "Rehber-2026!" });
  const p = { id: admin.id, username, email: `${username}@uni.edu.tr`, password: "Rehber-2026!" };
  await dismissSheet(p);
  const { context, page } = await signIn(browser, p, DESKTOP);
  await page.goto("/admin/ai");
  const strip = page.getByTestId("hint-admin_ai");
  await expect(strip).toBeVisible({ timeout: 20_000 });
  await expect(strip).toHaveAttribute("role", "status");
  await expect(strip).toContainText("Yeni: Yapay zekâ ayarları.");
  await page.getByTestId("hint-dismiss-admin_ai").click();
  await expect(strip).toBeHidden();
  await page.reload();
  await page.waitForLoadState("networkidle");
  await expect(page.getByTestId("hint-admin_ai")).toHaveCount(0);
  await context.close();
});

test("phone: the quick-reserve hint is an inline card at the top of /bookings", async ({ browser }) => {
  const p = await makeTeacher(api, "wg.hint.ph");
  await dismissSheet(p);
  const { context, page } = await signIn(browser, p, PHONE);
  await page.goto("/bookings");
  const card = page.getByTestId("hint-quick_reserve");
  await expect(card).toBeVisible({ timeout: 20_000 });
  await expect(card).toHaveAttribute("role", "status");
  expect(await m02(page, '[data-testid="hint-quick_reserve"]')).toEqual([]);
  await page.getByTestId("hint-try-quick_reserve").tap();
  await page.waitForURL(/\/reserve/);
  await context.close();
});
