import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, FINISHED, REAL, SKIP_REASON, TERM_CODE, api, boardRun, login, numberText, type Run, type Term } from "./helpers";

/**
 * Real-backend data truth (E2E_REAL=1): FastAPI on SQLite with the real Bahar 2026 workbooks imported through
 * `python -m app.cli` (smartsched/deploy/pod-ci/gates/e2e-backend-entry.sh). Every number checked here comes
 * from the backend's own answer, read through the same Next proxy the UI uses.
 *
 * login → dashboard tiles = GET /dashboard → /requests lands on the classes review view with Bahar rows →
 * rooms show A 204 (156 seats) → the Generator Studio queues a one-week CP-SAT run that the backend finishes
 * → run report → the imported board's week has classes on the calendar → settings: users list has the admin.
 */
test.skip(!REAL, SKIP_REASON);

test("real backend: login → dashboard → classes → rooms → studio run → report → calendar → settings", async ({ page }) => {
  test.setTimeout(300_000);
  await login(page);
  await expect(page.getByTestId("dashboard")).toBeVisible({ timeout: 30_000 });

  // ---- dashboard numbers are the backend's
  const terms = await api<Term[]>(page, "/terms");
  const term = terms.find((t) => t.code === TERM_CODE);
  expect(term, `${TERM_CODE} must be imported`).toBeTruthy();
  const termId = term?.id ?? 0;
  const dash = await api<{ requests_needs_review: number; requests_total: number; sections_total: number }>(page, `/dashboard?term_id=${termId}`);
  expect(dash.requests_total).toBeGreaterThan(1000); // Bahar planning list: 1 524 requests
  const tiles = page.getByTestId("dashboard");
  await expect(tiles.getByText(numberText(dash.sections_total)).first()).toBeVisible();
  await expect(tiles.getByText(numberText(dash.requests_needs_review)).first()).toBeVisible();

  // ---- the requests inbox is the classes review view: real Bahar rows with course codes
  await page.goto("/requests");
  await expect(page).toHaveURL(/\/classes\?view=review/);
  await expect(page.getByTestId("classes")).toBeVisible();
  const rows = page.getByTestId("classes-row");
  await expect(rows.first()).toBeVisible({ timeout: 30_000 });
  expect(await rows.count()).toBeGreaterThan(5);
  await expect(rows.first()).toContainText(/[A-ZÇĞİÖŞÜ]{2,5}\s?\d{3}/);

  // ---- rooms: the room master from the weekly grid
  await page.goto("/rooms");
  await expect(page.getByTestId("rooms")).toBeVisible();
  const a204 = page.getByTestId("room-card").filter({ hasText: "A 204" }).first();
  await expect(a204).toBeVisible({ timeout: 30_000 });
  await expect(a204).toContainText("156");

  // ---- a one-week run from the Generator Studio; the backend solves it (CP-SAT) and reports
  await page.goto("/generate?step=scope");
  await expect(page.getByTestId("scope-step")).toBeVisible();
  await page.getByTestId("horizon-WEEK").click();
  await expect(page.getByTestId("save-status")).toHaveAttribute("data-state", "saved", { timeout: 15_000 });
  await page.getByTestId("rail-step-run").click();
  await expect(page.getByTestId("generate-step")).toBeVisible();
  await page.getByTestId("studio-generate").click();
  // real data: Bahar has hard-impossible classes, so the studio asks first; generate anyway
  const blocked = page.getByTestId("blocked-confirm");
  await expect(page.getByTestId("run-card").or(blocked).first()).toBeVisible({ timeout: 60_000 });
  if (await blocked.isVisible()) await page.getByTestId("blocked-confirm-cancel").click();
  const card = page.getByTestId("run-card").first();
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card).toHaveAttribute("data-status", FINISHED, { timeout: 200_000 });
  const runId = Number(/#(\d+)/.exec((await card.locator("h3").textContent()) ?? "")?.[1]);
  expect(runId, "the run card names the run").toBeGreaterThan(0);
  const run = await api<Run>(page, `/runs/${runId}`);
  expect(run.term_code).toBe(TERM_CODE);
  expect(run.horizon).toBe("WEEK");
  expect(run.status).toBe(await card.getAttribute("data-status"));

  // ---- the run report shows the backend's verdict (and the diagnoses when the data cannot be placed)
  await page.goto(`/runs/${runId}`);
  await expect(page.getByTestId("run-view")).toBeVisible();
  await expect(page.getByTestId("run-verdict")).toBeVisible({ timeout: 30_000 });
  if (run.status !== "FEASIBLE" && run.status !== "OPTIMAL") await expect(page.getByTestId("diagnosis-card").first()).toBeVisible({ timeout: 30_000 });

  // ---- the imported board on the calendar: week 3 has the planner's classes
  await page.goto(`/timetable?run=${boardRun()}&week=3`);
  await expect(page.getByTestId("calendar")).toBeVisible();
  await expect(page.getByTestId("week-label")).toContainText("3", { timeout: 30_000 });
  const events = page.getByTestId("calendar-event");
  await expect(events.first()).toBeVisible({ timeout: 30_000 });
  expect(await events.count()).toBeGreaterThan(5);

  // ---- settings load from the backend; the users tab lists the seeded admin
  await page.goto("/settings");
  await expect(page.getByTestId("settings")).toBeVisible();
  await page.getByTestId("tab-users").click();
  await expect(page.getByText(ADMIN_EMAIL).first()).toBeVisible({ timeout: 20_000 });
});
