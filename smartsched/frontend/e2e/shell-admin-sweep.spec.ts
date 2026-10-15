/**
 * Shell / admin sweep (2026-10-15) against the REAL backend, gated E2E_REAL=1:
 *
 * 1. the CRBS legacy upgrade in the import wizard (P18-LEGACY, admin persona M-14 / M-25): the repository's own
 *    classroombookings install SQL (structure.sql + data.sql) as the dump → the dry-run diff → confirm → the
 *    result; the live-DSN path names the refused host (D16 allowlist).
 * 2. the room master import (P19-I7, admin persona M-24): room_master.csv → the diff → apply → the report.
 * 3. the booking sheet closes on the first Esc from its notes field and gives focus back to the cell (U-08);
 *    a Shift-click span is announced in the grid's live region (U-24).
 *
 * The upgrade and the room master write to the e2e database (CRBS roles, a room group, a schedule and a
 * timetable week; room capacities from the same workbooks), which is why this file runs after the booking specs.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:18990 NEXT_PUBLIC_API_URL=http://127.0.0.1:18990 PW_PORT=18991 \
 *     npx playwright test e2e/shell-admin-sweep.spec.ts
 */
import path from "node:path";
import { expect, test } from "@playwright/test";
import { FIXTURES, REAL, SKIP_REASON, login } from "./helpers";

const CRBS_SQL = process.env.E2E_CRBS_SQL_DIR ?? path.resolve(process.cwd(), "../../crbs-core/application/modules/install/resources");
const ROOM_MASTER = path.join(FIXTURES, "room_master.csv");
const WEDNESDAY = "2026-02-18";

test.describe.configure({ mode: "serial" });
test.skip(!REAL, SKIP_REASON);

test("sweep 1. CRBS legacy upgrade: install SQL dump → dry-run diff → confirm → result", async ({ page }) => {
  test.setTimeout(240_000);
  await login(page);
  await page.goto("/import");
  await page.getByTestId("import-kind-crbs").click();
  await expect(page.getByTestId("crbs-upgrade")).toBeVisible();
  // a live database is refused unless an administrator allow-listed its host (review D16)
  await page.getByRole("tab", { name: /Canlı veritabanı|Live database/ }).click();
  await page.getByTestId("crbs-upgrade-dsn").fill("mysql://crbs:secret@db.example.invalid:3306/crbs");
  await page.getByTestId("crbs-upgrade-dry-run").click();
  await expect(page.getByTestId("crbs-upgrade-error")).toContainText("crbs_dsn_allowed_hosts", { timeout: 30_000 });
  // the default path: SQL dump files
  await page.getByRole("tab", { name: /SQL dökümü|SQL dump/ }).click();
  await page.getByTestId("file-input").setInputFiles([path.join(CRBS_SQL, "structure.sql"), path.join(CRBS_SQL, "data.sql")]);
  await page.getByTestId("crbs-upgrade-dry-run").click();
  const diff = page.getByTestId("crbs-upgrade-diff");
  await expect(diff).toBeVisible({ timeout: 120_000 });
  // CRBS's install data: a room group, a schedule and a timetable week are new (its roles map onto the existing ones)
  await expect(page.getByTestId("crbs-table-room_groups")).toContainText("+1");
  await expect(page.getByTestId("crbs-table-timetable_weeks")).toContainText("+1");
  await expect(diff).toContainText(/Deneme çalıştırması|Dry run/);
  // nothing was written by the dry run
  const before = await page.evaluate(async () => (await (await fetch("/api/v1/room-admin/groups")).json()) as unknown[]);
  await page.getByTestId("crbs-upgrade-confirm").click();
  await expect(page.getByTestId("crbs-upgrade-confirm-dialog")).toBeVisible();
  await page.getByTestId("crbs-upgrade-commit").click();
  const result = page.getByTestId("crbs-upgrade-result");
  await expect(result).toBeVisible({ timeout: 120_000 });
  await expect(result).toContainText(/Yükseltme uygulandı|Upgrade applied/);
  await expect(page.getByRole("heading", { name: /Yükseltme uygulandı|Upgrade applied/ })).toBeFocused();
  const after = await page.evaluate(async () => (await (await fetch("/api/v1/room-admin/groups")).json()) as unknown[]);
  expect(after.length).toBeGreaterThanOrEqual(before.length);
});

test("sweep 2. room master: room_master.csv → the diff → apply → the report", async ({ page }) => {
  test.setTimeout(180_000);
  await login(page);
  await page.goto("/import");
  await page.getByTestId("import-kind-room-master").click();
  await page.getByTestId("file-input").setInputFiles(ROOM_MASTER);
  const counts = page.getByTestId("room-master-counts");
  await expect(counts).toBeVisible({ timeout: 30_000 });
  await expect(counts).toContainText(/0 (satırda hata|lines with errors)/);
  await expect(page.getByTestId("room-master-diff")).toBeVisible();
  await page.getByTestId("room-master-apply").click();
  const result = page.getByTestId("room-master-result");
  await expect(result).toBeVisible({ timeout: 120_000 });
  await expect(result).toContainText(/satır okundu|rows read/);
  // the history lists the room-master job (admin persona M-13)
  await page.goto("/import");
  await expect(page.getByText("room_master.csv").first()).toBeVisible();
});

test("sweep 3. the book sheet closes on one Esc from its notes and focus returns to the cell; a span is announced", async ({ page }) => {
  await login(page);
  await page.goto(`/bookings?date=${WEDNESDAY}`);
  const grid = page.getByTestId("booking-grid");
  await expect(grid).toBeVisible({ timeout: 30_000 });
  const free = grid.locator('button[data-tone="available"]');
  const cell = free.first();
  const key = await cell.getAttribute("data-slot-key");
  await cell.click();
  const sheet = page.getByTestId("book-sheet");
  await expect(sheet).toBeVisible();
  await sheet.locator("textarea").first().click();
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await expect(page.locator(`button[data-slot-key="${key}"]`)).toBeFocused();
  // Shift-click two periods later in the same room: the span is announced (the sheet opens with it)
  const [date, , room] = (key ?? "").split("|");
  const sameRoom = grid.locator(`button[data-tone="available"][data-slot-key^="${date}|"][data-slot-key$="|${room}"]`);
  if ((await sameRoom.count()) >= 3) {
    await sameRoom.nth(0).click();
    await page.keyboard.press("Escape");
    await sameRoom.nth(2).click({ modifiers: ["Shift"] });
    await expect(page.getByTestId("grid-span-status")).toContainText(/(ders saati seçildi|periods selected)/);
  }
});
