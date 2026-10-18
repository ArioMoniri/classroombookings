/**
 * WG-08 Yönetim › Karşılama rehberi against the REAL backend (E2E_REAL=1), 1440 mouse and 390×844 touch.
 *
 * - Switching "Karşılama rehberi" off hides the sheet for a fresh academician (the switch is put back).
 * - A Turkish title edit for academicians is what a fresh academician sees; "show again" re-shows it with
 *   "Güncellendi" to someone who had closed it.
 * - A teacher gets the no-access page.
 * - Tamamlanma: one card per audience, small groups say "5'ten az".
 * - Phone: MOBILE M-01/02/03 on /admin/welcome (all three tabs), 16 px inputs in the text editor.
 * The academician texts are put back to the product copy afterwards.
 */
import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON } from "./helpers";
import { pinLanguage } from "./language";
import { DESKTOP, PHONE, adminApi, makeAcademician, makeTeacher, mobileChecks, settings, signIn, unlink, type Api } from "./wg-helpers";

test.describe.configure({ mode: "serial", timeout: 300_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

let api: Api;
const linked: { id: number; instructorId: number | null }[] = [];
const ADMIN = { username: ADMIN_EMAIL, password: ADMIN_PASSWORD };
const TITLE = "Kampüse hoş geldiniz, {ad}";

test.beforeAll(async () => {
  api = await adminApi();
});
test.afterAll(async () => {
  await settings(api, { sheet: true }).catch(() => undefined);
  const c = await api.json<{ version: number }>("GET", "/welcome/content/academician").catch(() => null);
  if (c) await api.call("PUT", "/welcome/content/academician", { version: c.version, fields: { tr: { title: "" } }, reshow: false });
  for (const p of linked) await unlink(api, p);
  await api.ctx.dispose();
});

test("a teacher gets the no-access page", async ({ browser }) => {
  const p = await makeTeacher(api, "wg.adm.t");
  const { context, page } = await signIn(browser, p, DESKTOP);
  await page.goto("/admin/welcome");
  await expect(page.getByText("Bu sayfaya erişiminiz yok").first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("welcome-admin")).toHaveCount(0);
  await context.close();
});

test("switching the sheet off hides it for a fresh academician", async ({ browser }) => {
  const admin = await signIn(browser, ADMIN, DESKTOP);
  await admin.page.goto("/admin/welcome");
  const sw = admin.page.getByTestId("welcome-switch-sheet");
  await expect(sw).toBeVisible({ timeout: 20_000 });
  if ((await sw.getAttribute("aria-checked")) === "true") await sw.click();
  await expect(sw).toHaveAttribute("aria-checked", "false");
  await expect.poll(async () => ((await api.json<{ settings: { sheet: boolean } }>("GET", "/welcome/settings")).settings.sheet)).toBe(false);
  const ac = await makeAcademician(api, "wg.adm.off");
  linked.push(ac);
  const { context, page } = await signIn(browser, ac, DESKTOP);
  await page.goto("/reserve");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1500);
  await expect(page.getByTestId("welcome-sheet")).toHaveCount(0);
  await context.close();
  await sw.click();
  await expect(sw).toHaveAttribute("aria-checked", "true");
  await admin.context.close();
});

test("a Turkish title edit reaches academicians; 'show again' re-shows it with 'Güncellendi'", async ({ browser }) => {
  // someone who already closed the sheet
  const earlier = await makeAcademician(api, "wg.adm.old", "Deniz");
  linked.push(earlier);
  await api.json("POST", "/welcome/events", { guide_key: "sheet", event: "shown" }, await api.tokenFor(earlier.username));
  await api.json("POST", "/welcome/events", { guide_key: "sheet", event: "completed" }, await api.tokenFor(earlier.username));

  const admin = await signIn(browser, ADMIN, DESKTOP);
  await admin.page.goto("/admin/welcome?tab=texts");
  const field = admin.page.getByTestId("welcome-text-academician-title-tr");
  await expect(field).toBeVisible({ timeout: 20_000 });
  await field.fill(TITLE);
  await admin.page.getByTestId("welcome-save").click();
  const confirm = admin.page.getByRole("alertdialog");
  await expect(confirm).toContainText("Kaydedince bu kitleye rehber yeniden gösterilsin mi?");
  await confirm.getByTestId("welcome-reshow").click();
  await confirm.getByRole("button", { name: "Kaydet" }).click();
  await expect(admin.page.getByTestId("welcome-last-change")).toContainText("Son değişiklik:", { timeout: 15_000 });
  await admin.context.close();

  const fresh = await makeAcademician(api, "wg.adm.new", "Ayşe");
  linked.push(fresh);
  const a = await signIn(browser, fresh, DESKTOP);
  await a.page.goto("/reserve");
  await expect(a.page.getByTestId("welcome-sheet-title")).toHaveText("Kampüse hoş geldiniz, Ayşe", { timeout: 20_000 });
  await a.context.close();

  const b = await signIn(browser, earlier, DESKTOP);
  await b.page.goto("/reserve");
  await expect(b.page.getByTestId("welcome-sheet")).toBeVisible({ timeout: 20_000 });
  await expect(b.page.getByTestId("welcome-updated")).toHaveText("Güncellendi");
  await b.context.close();
});

test("Tamamlanma: one card per audience; small groups say '5'ten az'", async ({ browser }) => {
  const admin = await signIn(browser, ADMIN, DESKTOP);
  await admin.page.goto("/admin/welcome?tab=stats");
  await expect(admin.page.getByTestId("welcome-stats-academician")).toBeVisible({ timeout: 20_000 });
  for (const a of ["admin", "planner", "viewer", "dept_admin", "approver", "staff"]) await expect(admin.page.getByTestId(`welcome-stats-${a}`)).toBeVisible();
  const stats = await api.json<{ audiences: { audience: string; small_group: boolean }[] }>("GET", "/welcome/stats?days=30");
  const small = stats.audiences.find((r) => r.small_group);
  if (small) await expect(admin.page.getByTestId(`welcome-stats-${small.audience}`)).toContainText("5'ten az");
  await admin.page.getByTestId("welcome-days-7").click();
  await expect(admin.page.getByTestId("welcome-stats-academician")).toBeVisible();
  await admin.context.close();
});

test("phone: MOBILE M-01/02/03 on every tab of /admin/welcome", async ({ browser }) => {
  const { context, page } = await signIn(browser, ADMIN, PHONE);
  for (const tab of ["general", "texts", "stats"]) {
    await page.goto(`/admin/welcome?tab=${tab}`);
    await expect(page.getByTestId("welcome-admin")).toBeVisible({ timeout: 20_000 });
    if (tab === "general") await page.getByTestId("welcome-advanced").tap();
    if (tab === "texts") await page.getByTestId("welcome-cards-toggle").tap();
    await mobileChecks(page, "main");
  }
  await context.close();
});
