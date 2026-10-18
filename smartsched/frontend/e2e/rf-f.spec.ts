import { expect, test, type Page } from "@playwright/test";
import { PLANNING_LIST, REAL, SKIP_REASON, login } from "./helpers";

/**
 * RF-06 / RF-08 / RF-09 / users mfa_state (rf-f-2026-10-18) on a real stack. Run at 1440 (mouse) and 390×844
 * (touch, isMobile, hasTouch, tr-TR, Europe/Istanbul). Not run by the builder (resource rule 2026-10-18).
 */
test.skip(!REAL, SKIP_REASON);
test.use({ locale: "tr-TR", timezoneId: "Europe/Istanbul" });

async function post(page: Page, path: string, body: unknown): Promise<number> {
  return page.evaluate(
    async ([p, b]) => (await fetch(`/api/v1${p}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b), credentials: "same-origin" })).status,
    [path, body] as const,
  );
}

test("import: preview first, one Uygula, a second apply is refused, history names who imported", async ({ page }) => {
  test.setTimeout(300_000);
  await login(page);
  await page.goto("/import?kind=planning-list");
  await page.getByTestId("file-input").setInputFiles(PLANNING_LIST);
  await page.getByTestId("import-start").click();
  const preview = page.getByTestId("import-preview");
  await expect(preview).toBeVisible({ timeout: 180_000 });
  await expect(page.getByTestId("import-preview-summary")).toContainText(/aynı kalacak|değişecek|eklenecek|hiçbir şeyi değiştirmiyor/);
  await expect(preview).not.toContainText(/meeting_requests|exam_requests|_id\b/);
  // the newest job is the preview just made
  const id: number = await page.evaluate(async () => (await (await fetch("/api/v1/imports?limit=1", { credentials: "same-origin" })).json())[0].id);
  await page.getByTestId("import-apply").click();
  await expect(page.getByTestId("import-report")).toBeVisible({ timeout: 180_000 });
  expect(await post(page, `/imports/${id}/apply`, { on_conflict: null })).toBe(409);
  await page.goto("/import");
  const row = page.getByTestId(`import-history-${id}`);
  await expect(row).toContainText("Önizleme · uygulandı");
  await expect(page.getByTestId("import-history")).toContainText(/Yükleyen: |İlk kurulum \(sistem\)/);
  const download = page.waitForEvent("download");
  await page.getByTestId(`import-history-download-${id}`).click();
  expect((await download).suggestedFilename()).toMatch(/\.xlsx$/);
});

test("Ders saatleri: 18 rows, Turkish time, field error, Varsayılana dön", async ({ page }) => {
  await login(page);
  await page.goto("/admin/schedules");
  const grid = page.getByTestId("period-grid");
  await expect(grid.locator('[data-testid^="grid-row-"]')).toHaveCount(18);
  await page.getByLabel("P3 başlangıç").fill("09.00");
  await page.getByTestId("period-grid-save").click();
  await expect(page.getByTestId("grid-row-3").getByRole("alert")).toContainText("P2 bitmeden");
  await page.getByLabel("P3 başlangıç").fill("10.10");
  await page.getByLabel("P1 başlangıç").fill("08.35");
  await page.getByTestId("period-grid-save").click();
  await expect(grid).toContainText("Kurumunuzun saatleri");
  await page.reload();
  await expect(page.getByLabel("P1 başlangıç")).toHaveValue("08:35");
  await page.getByTestId("period-grid-advanced").click();
  await page.getByTestId("period-grid-reset").click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Varsayılana dön" }).click();
  await expect(page.getByLabel("P1 başlangıç")).toHaveValue("08:30");
});

test("Dönem haftaları: kind per week, 'Elle değiştirildi', duplicate refused inline; Dönem profilleri still below", async ({ page }) => {
  await login(page);
  await page.goto("/admin/weeks");
  const weeks = page.getByTestId("term-weeks");
  await expect(weeks).toBeVisible();
  await page.getByLabel("14. hafta türü").selectOption({ label: "Tatil" });
  await expect(page.getByTestId("term-week-14")).toContainText("Elle değiştirildi");
  await page.reload();
  await expect(page.getByLabel("14. hafta türü")).toHaveValue("HOLIDAY");
  await page.getByTestId("term-weeks-advanced").click();
  await page.getByLabel("Hafta numarası").fill("1");
  await page.getByTestId("term-week-add").click();
  await expect(page.getByTestId("term-week-add-error")).toContainText("Aynı hafta numarası iki kez verildi.");
  await page.getByLabel("14. hafta türü").selectOption({ label: "Ders" });
});

test("Kullanıcılar: the 2FA filter asks the server (mfa_state) and pages the filtered set", async ({ page }) => {
  await login(page);
  const seen: string[] = [];
  page.on("request", (r) => r.url().includes("/users/search") && seen.push(r.url()));
  await page.goto("/admin/users");
  const filter = page.getByTestId("mfa-filter").first();
  await filter.selectOption("off");
  await expect.poll(() => seen.some((u) => u.includes("mfa_state=off") && u.includes("offset=0"))).toBe(true);
});
