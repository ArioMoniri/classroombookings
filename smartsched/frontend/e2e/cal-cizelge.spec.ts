import { expect, test, type Page } from "@playwright/test";
import { compareRoomCodes } from "../src/components/timetable/model/room-sort";
import { REAL, SKIP_REASON, api, ensureBookingSetup, fillDate, login, solverRun } from "./helpers";

/**
 * Owner report 2026-11-02 on Çizelge, against the REAL backend (playwright.config.ts):
 *   1. the free slot's "+" opens quick-create on Rezervasyon and books (a click; before, only a drag did anything)
 *   2. the room columns sort by natural code or capacity, remembered per user
 *   3. the inspector shows the room's capacity and its exam capacity
 *   4. "Yeni dönem oluştur…" in a term dropdown creates the term and selects it
 *   5. the imported-board notice on Gözetmen ataması offers the linked exam runs and Oluştur › Sınav
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx playwright test e2e/cal-cizelge.spec.ts
 */
test.skip(!REAL, SKIP_REASON);
test.describe.configure({ mode: "serial" });
test.use({ viewport: { width: 1440, height: 900 }, timezoneId: "Europe/Istanbul" });

async function send<T>(page: Page, method: "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<{ status: number; body: T }> {
  return page.evaluate(
    async ({ method, url, body }) => {
      const r = await fetch(url, { method, headers: { Accept: "application/json", "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
      const text = await r.text();
      return { status: r.status, body: (text ? JSON.parse(text) : null) as T };
    },
    { method, url: `/api/v1${path}`, body },
  );
}

async function openBoard(page: Page) {
  // Tuesday of week 3 (17 Şubat): after the e2e booking clock (Monday 16 Şubat 08:00), so its slots are bookable
  await page.goto(`/timetable?run=${solverRun()}&lens=board&board=day&week=3&day=2`);
  await expect(page.getByTestId("time-grid")).toBeVisible({ timeout: 60_000 });
}

test("1. a click on a free slot's + opens quick-create on Rezervasyon, and it books", async ({ page }) => {
  await ensureBookingSetup();
  await login(page);
  await openBoard(page);
  // an evening slot (P16–P18) of a room column: free on the run and, at that hour, on the published board
  const cells = page.locator('[data-testid="grid-drop-cell"][data-free="true"][data-period="17"]');
  await expect(cells.first()).toBeAttached();
  const cell = cells.first();
  await cell.scrollIntoViewIfNeeded();
  const room = await cell.getAttribute("data-room-id");
  await cell.hover();
  await expect(cell.locator('[data-slot="free-plus"]')).toBeVisible();
  await cell.click();
  const panel = page.getByTestId("quick-create");
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId("booking-slot")).toHaveAttribute("data-room-id", room ?? "");
  await expect(panel.getByTestId("booking-slot")).toHaveAttribute("data-period", "17");
  // the click opens on Rezervasyon (its button only renders on that tab)
  const book = panel.getByTestId("booking-create");
  await expect(book).toBeEnabled({ timeout: 15_000 });
  const created = page.waitForResponse((r) => r.url().includes("/api/v1/bookings") && r.request().method() === "POST");
  await book.click();
  const res = await created;
  expect(res.status(), await res.text()).toBeLessThan(300);
  await expect(panel).toBeHidden();
  const id = ((await res.json()) as { id?: number; bookings?: { id: number }[] }).id;
  if (id) await send(page, "POST", `/bookings/${id}/cancel`, { scope: "one", reason: "e2e cal-cizelge cleanup" });
});

test("1b. a click on a class still opens its inspector, never quick-create", async ({ page }) => {
  await login(page);
  await openBoard(page);
  const chip = page.getByTestId("calendar-event").first();
  await chip.click();
  await expect(page.getByTestId("class-inspector")).toBeVisible();
  await expect(page.getByTestId("quick-create")).toHaveCount(0);
});

test("2. room order: natural code by default, capacity on demand, remembered after a reload", async ({ page }) => {
  await login(page);
  await openBoard(page);
  const sort = page.getByTestId("room-sort");
  await expect(sort).toHaveValue("code-asc");
  const heads = () => page.locator('[data-testid="time-grid"] [role="columnheader"]').evaluateAll((els) => els.map((e) => e.getAttribute("aria-label") ?? ""));
  const codes = (await heads()).map((h) => h.split(",")[0]!.trim());
  expect(codes.length).toBeGreaterThan(3);
  expect([...codes].sort(compareRoomCodes)).toEqual(codes);
  await sort.selectOption("cap-desc");
  const seats = (await heads()).map((h) => Number(/,\s*(\d+)/.exec(h)?.[1] ?? NaN));
  expect(seats.every((n) => Number.isFinite(n))).toBe(true);
  expect([...seats].sort((a, b) => b - a)).toEqual(seats);
  await page.reload();
  await expect(page.getByTestId("time-grid")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("room-sort")).toHaveValue("cap-desc");
  await page.getByTestId("room-sort").selectOption("code-asc");
  await expect(page.getByTestId("room-sort")).toHaveValue("code-asc");
});

test("3. the inspector shows the room's capacity and exam capacity", async ({ page }) => {
  await login(page);
  await openBoard(page);
  await page.getByTestId("calendar-event").first().click();
  const seats = page.getByTestId("inspector-room-seats");
  await expect(seats).toBeVisible();
  await expect(seats).toHaveText(/\d+.*\d+/);
  // the column header names the exam capacity too
  const head = await page.locator('[data-testid="time-grid"] [role="columnheader"]').first().getAttribute("aria-label");
  expect(head).toMatch(/\d+.*\d+/);
});

test("4. Yeni dönem oluştur… in Hedef dönem creates the term and selects it", async ({ page }) => {
  await login(page);
  await page.goto("/import?kind=planning-list");
  const select = page.locator("select#term");
  await expect(select).toBeVisible({ timeout: 30_000 });
  // the terms are in: the select holds one of them
  await expect.poll(() => select.evaluate((el: HTMLSelectElement) => /^\d+$/.test(el.value) && !el.selectedOptions[0]?.disabled), { timeout: 30_000 }).toBe(true);
  const before = await select.inputValue();
  await select.selectOption("__new_term__");
  const dialog = page.getByTestId("term-create-dialog");
  await expect(dialog).toBeVisible();
  // the select keeps the term it had until one is created
  await expect(select).toHaveValue(before);
  const code = `E2E-CZ-${Date.now().toString(36)}`.toUpperCase().slice(0, 32);
  await dialog.getByTestId("term-create-code").fill(code);
  await dialog.getByTestId("term-create-kind-FINAL").click();
  await fillDate(dialog.getByTestId("term-create-start"), "2031-06-02");
  await fillDate(dialog.getByTestId("term-create-end"), "2031-06-22");
  const created = page.waitForResponse((r) => /\/api\/v1\/terms$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
  await dialog.getByTestId("term-create-save").click();
  const res = await created;
  expect(res.status(), await res.text()).toBe(201);
  const term = (await res.json()) as { id: number; code: string; kind?: string };
  try {
    await expect(dialog).toBeHidden();
    await expect(select).toHaveValue(String(term.id));
    const terms = await api<{ id: number; code: string; kind: string }[]>(page, "/terms");
    expect(terms.find((x) => x.id === term.id)).toMatchObject({ code, kind: "FINAL" });
  } finally {
    await send(page, "DELETE", `/terms/${term.id}`);
  }
});

type RunRow = { id: number; term_id: number; term_code: string | null; kind: string; status: string; label: string | null; params?: { source?: string } | null };
const STAFFABLE = new Set(["OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL"]);

test("5. an imported board on Gözetmen ataması: switch to a linked exam run, or start Oluştur › Sınav for the term", async ({ page }) => {
  await login(page);
  const runs = await api<RunRow[]>(page, "/runs");
  const exams = runs.filter((r) => r.kind === "EXAM" && STAFFABLE.has(r.status));
  const isBoard = (r: RunRow) => r.params?.source === "GRID_IMPORT" || /^grid import/i.test(r.label ?? "");
  const finalBoard = exams.find((r) => r.term_code === "2026-FINAL" && isBoard(r));
  const linked = exams.find((r) => r.term_code === "2026-FINAL" && !isBoard(r));
  test.skip(!finalBoard || !linked, "the Final board and its exam run are seeded by e2e-seed-analytics.py");

  await page.goto(`/exams/invigilation?run=${finalBoard!.id}`);
  const notice = page.getByTestId("invig-board-run");
  await expect(notice).toBeVisible({ timeout: 30_000 });
  const switchTo = notice.locator(`[data-testid="invig-switch-run"][data-run-id="${linked!.id}"]`);
  await expect(switchTo).toBeVisible();
  await switchTo.click();
  await expect(page).toHaveURL(new RegExp(`run=${linked!.id}`));
  await expect(page.getByTestId("invig-board-run")).toHaveCount(0);

  // a term whose only exam run is its board: the notice offers Oluştur › Sınav on that term
  const lonely = exams.find((r) => isBoard(r) && !exams.some((x) => x.term_id === r.term_id && !isBoard(x)));
  test.skip(!lonely, "every term with a board has a linked exam run on this stack");
  await page.goto(`/exams/invigilation?run=${lonely!.id}`);
  await expect(page.getByTestId("invig-no-linked")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("invig-start-exam").click();
  await expect(page).toHaveURL(/\/generate\?kind=EXAM/);
  await expect(page.locator("select#scope-term")).toHaveValue(String(lonely!.term_id), { timeout: 30_000 });
});
