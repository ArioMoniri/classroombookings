import { expect, test, type Page } from "@playwright/test";

/**
 * Real-backend flow (E2E_REAL=1; the mock is off): FastAPI on SQLite with the real Bahar workbooks
 * imported through `python -m app.cli` — see docs/testing/2026-10-08-real-backend-e2e.md.
 *
 * login → dashboard shows the backend's counts → requests inbox lists Bahar rows → rooms show A 204 (156)
 * → generate a one-week run → run report → grid of a feasible run shows events → move one event
 * (success, or the backend's conflict reason) → settings load.
 */
test.skip(process.env.E2E_REAL !== "1", "real-backend spec: set E2E_REAL=1 and start the backend");

const EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@smartsched.local";
const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "Admin-2026!";
const TERM = process.env.E2E_TERM_CODE ?? "2026-BAHAR";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel(/E-posta|E-mail/).fill(EMAIL);
  await page.getByLabel(/Şifre|Password/).fill(PASSWORD);
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("dashboard")).toBeVisible({ timeout: 30_000 });
}

/** Same-origin API calls from the page through the Next proxy (the httpOnly, Secure cookie carries the
 * JWT; Playwright's APIRequestContext does not send Secure cookies over http://127.0.0.1). */
async function api<T>(page: Page, path: string): Promise<T> {
  const res = await page.evaluate(async (url) => {
    const r = await fetch(url, { headers: { Accept: "application/json" } });
    return { status: r.status, body: (await r.json()) as unknown };
  }, `/api/v1${path}`);
  expect(res.status, `${path} → ${res.status}`).toBe(200);
  return res.body as T;
}

type Term = { id: number; code: string };
type Run = { id: number; status: string; kind: string; term_code: string | null; params: Record<string, unknown> };

test("real backend: login → dashboard → requests → rooms → run → grid → move → settings", async ({ page }) => {
  test.setTimeout(240_000);
  await login(page);
  const req = page;

  // ---- dashboard numbers are the backend's (no mock, no client-side composition)
  const terms = await api<Term[]>(req, "/terms");
  const term = terms.find((t) => t.code === TERM) ?? terms[0];
  expect(term, "a term must be imported").toBeTruthy();
  const dash = await api<{ requests_needs_review: number; requests_total: number; sections_total: number; term: Term }>(req, `/dashboard?term_id=${term.id}`);
  expect(dash.requests_total).toBeGreaterThan(1000); // Bahar list: 1 529 rows
  // tiles animate to the value; accept plain (1271) or tr-TR grouped (1.271) rendering
  const num = (n: number) => new RegExp(`^(${n}|${new Intl.NumberFormat("tr-TR").format(n).replace(".", "\\.")})$`);
  const tiles = page.getByTestId("dashboard");
  await expect(tiles.getByText(num(dash.sections_total)).first()).toBeVisible();
  await expect(tiles.getByText(num(dash.requests_needs_review)).first()).toBeVisible();

  // ---- requests inbox: real Bahar rows (course codes, Turkish programme names)
  await page.goto("/requests");
  await expect(page.getByTestId("requests")).toBeVisible();
  const rows = page.getByTestId("request-row");
  await expect(rows.first()).toBeVisible({ timeout: 20_000 });
  expect(await rows.count()).toBeGreaterThan(5);
  await expect(rows.first()).toContainText(/[A-ZÇĞİÖŞÜ]{2,5}\s?\d{3}/);

  // ---- rooms: the room master from the weekly grid
  await page.goto("/rooms");
  await expect(page.getByTestId("rooms")).toBeVisible();
  const a204 = page.getByTestId("room-card").filter({ hasText: "A 204" }).first();
  await expect(a204).toBeVisible({ timeout: 20_000 });
  await expect(a204).toContainText("156");

  // ---- generate a one-week run through the UI; the backend solves it (CP-SAT) and reports
  await page.goto("/generate");
  await expect(page.getByTestId("generate")).toBeVisible();
  await page.getByTestId("horizon-WEEK").click();
  await page.getByTestId("generate-submit").click();
  await expect(page).toHaveURL(/\/runs\/\d+/, { timeout: 30_000 });
  const runId = Number(/\/runs\/(\d+)/.exec(page.url())?.[1]);
  await expect(page.getByTestId("run-view")).toBeVisible();
  await expect
    .poll(async () => (await api<Run>(req, `/runs/${runId}`)).status, { timeout: 150_000, intervals: [2_000] })
    .not.toMatch(/QUEUED|RUNNING/);
  const run = await api<Run>(req, `/runs/${runId}`);
  expect(run.term_code).toBe(term.code);
  await page.reload();
  if (run.status === "INFEASIBLE") {
    // real data: the planner's own fixed times clash; the report explains why
    await expect(page.getByTestId("diagnosis-card").first()).toBeVisible({ timeout: 20_000 });
  } else {
    await expect(page.getByTestId("tab-grid")).toBeVisible();
  }

  // ---- grid of a feasible run (this one if feasible, else the imported published board)
  const runs = await api<Run[]>(req, `/runs?term_id=${term.id}`);
  const feasible = ["FEASIBLE", "OPTIMAL"].includes(run.status) ? run : runs.find((r) => r.kind === "COURSE" && ["FEASIBLE", "OPTIMAL"].includes(r.status));
  expect(feasible, "a feasible COURSE run (solver or imported board)").toBeTruthy();
  await page.goto(`/runs/${feasible?.id ?? 1}?tab=grid`);
  await expect(page.getByTestId("day-grid")).toBeVisible({ timeout: 30_000 });
  const events = page.locator("[data-testid='day-grid'] [data-assignment-id]");
  await expect(events.first()).toBeVisible({ timeout: 30_000 });
  expect(await events.count()).toBeGreaterThan(5);

  // ---- move one event via the event sheet: success toast, or the backend's conflict reason
  const movable = page.locator("[data-testid='day-grid'] [data-assignment-id][data-status='ok']").first();
  await movable.click();
  await expect(page.getByTestId("event-sheet")).toBeVisible();
  const moveBtn = page.getByTestId("sheet-move");
  if (await moveBtn.isEnabled()) {
    await moveBtn.click();
    await expect(page.getByTestId("move-dialog")).toBeVisible();
    // look for a slot the client-side preview accepts (weekend first); the backend re-checks it
    const confirm = page.getByTestId("move-confirm");
    search: for (const day of ["7", "6", "5"]) {
      await page.getByLabel(/Yeni gün|New day/).selectOption(day);
      for (const start of ["1", "13", "15", "10", "4"]) {
        await page.getByLabel(/Başlangıç saati|Start period/).selectOption(start).catch(() => undefined);
        if (await confirm.isEnabled()) break search;
      }
    }
    if (await confirm.isEnabled()) {
      const moved = page.waitForResponse((r) => r.url().includes("/move") && r.request().method() === "POST");
      await confirm.click();
      const res = await moved;
      expect([200, 409]).toContain(res.status());
      const body = (await res.json()) as { ok: boolean; conflicts: { message: string }[]; assignment: { is_locked: boolean; origin: string } | null };
      if (body.ok) expect(body.assignment).toMatchObject({ is_locked: true, origin: "MANUAL" });
      else expect(body.conflicts[0]?.message).toBeTruthy();
      await expect(page.locator("[data-sonner-toast]").first()).toBeVisible();
    } else {
      // the client-side preview already shows why the slot is not free
      await expect(page.getByTestId("move-preview")).toBeVisible();
      await page.keyboard.press("Escape");
    }
  }

  // ---- settings load from the backend (masked key state, users list for admins)
  await page.goto("/settings");
  await expect(page.getByTestId("settings")).toBeVisible();
  await page.getByTestId("tab-users").click();
  await expect(page.getByText(EMAIL).first()).toBeVisible({ timeout: 20_000 });
});
