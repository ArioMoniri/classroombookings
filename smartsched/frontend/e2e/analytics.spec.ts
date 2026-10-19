/**
 * Planning analytics UI on the REAL backend (no mocks): scenario comparison, utilisation heatmaps and invigilator
 * assignment. The backend has the real Bahar 2026 workbooks + room master and the real 2026 Final board and exam
 * list, with solver runs made by the CLI (`python -m app.cli solve …`):
 *   "Bahar 3. hafta (A)"                                        week 3, published
 *   "Bahar 3. hafta, en yoğun derslik çarşamba kapalı (B)"      week 3 again with A's busiest room closed on Wednesday
 *   "Final (A)"                                                 the Final exam run
 * Run (see playwright.config.ts): E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:<api> PW_PORT=<web> npx playwright test analytics
 */
import { expect, test, type Page } from "@playwright/test";
import { api, login, pinTerm, REAL, SKIP_REASON } from "./helpers";

test.skip(!REAL, SKIP_REASON);

type RunRow = { id: number; label: string | null; kind: string; term_id: number; status: string };
type TermRow = { id: number; code: string };

async function runByLabel(page: Page, label: string): Promise<RunRow> {
  const runs = await api<RunRow[]>(page, "/runs");
  const run = runs.find((r) => r.label === label);
  expect(run, `run "${label}" (made by the CLI on the e2e backend)`).toBeTruthy();
  return run!;
}

/** the term every page works on (the shell's persisted term switcher) */
async function useTerm(page: Page, code: string) {
  const terms = await api<TermRow[]>(page, "/terms");
  const term = terms.find((t) => t.code === code)!;
  await pinTerm(page, term.id);
  return term;
}

async function csvOk(page: Page, href: string | null) {
  expect(href).toBeTruthy();
  // what the download link does: a same-origin GET through the proxy with the session cookie
  const res = await page.evaluate(async (url) => {
    const r = await fetch(url);
    return { status: r.status, type: r.headers.get("content-type") ?? "", disposition: r.headers.get("content-disposition") ?? "", body: await r.text() };
  }, href!);
  expect(res.status).toBe(200);
  expect(res.type).toContain("text/csv");
  expect(res.disposition).toContain("attachment");
  expect(res.body.split("\n").length).toBeGreaterThan(1);
}

test.describe("planning analytics", () => {
  test("scenario comparison from the runs list: headline, verdicts, class changes, rooms, rules, CSV", async ({ page }) => {
    await login(page);
    const a = await runByLabel(page, "Bahar 3. hafta (A)");
    const b = await runByLabel(page, "Bahar 3. hafta, en yoğun derslik çarşamba kapalı (B)");
    await useTerm(page, "2026-BAHAR");
    await page.goto("/runs");
    await page.getByTestId("runs-compare").click();
    const dialog = page.getByTestId("compare-entry-dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByTestId("compare-pick-a").selectOption(String(a.id));
    await dialog.getByTestId("compare-pick-b").selectOption(String(b.id));
    await dialog.getByTestId("compare-apply").click();
    await page.waitForURL(new RegExp(`/runs/compare\\?a=${a.id}&b=${b.id}`));

    // the backend's own headline and both runs by their real labels
    await expect(page.getByTestId("compare-headline")).toContainText(`#${b.id}, #${a.id} ile karşılaştırıldı`);
    await expect(page.getByTestId("compare-run-a")).toContainText("Bahar 3. hafta (A)");
    await expect(page.getByTestId("compare-run-b")).toContainText("çarşamba kapalı");
    // every metric has a verdict word next to its numbers (never colour alone)
    const metrics = page.getByTestId("compare-metric");
    expect(await metrics.count()).toBeGreaterThanOrEqual(8);
    await expect(metrics.filter({ has: page.locator('[data-verdict="same"]') }).first()).toContainText("aynı");
    await expect(page.locator('[data-testid="compare-metric"][data-key="hard_score"]')).toContainText("100");

    // classes: moved by default, then the classes only A placed (the closed room's Wednesday classes)
    const rows = page.getByTestId("compare-class-row");
    await expect(rows.first()).toBeVisible();
    await page.getByTestId("compare-filter-only_in_a").click();
    await expect(rows.first()).toHaveAttribute("data-bucket", "only_in_a");
    await expect(rows.first()).toContainText("yerleşmedi");
    await csvOk(page, await page.getByTestId("compare-csv-classes").getAttribute("href"));

    // room utilisation: rooms whose use changed, each linking to its room page
    await page.getByTestId("compare-tab-rooms").click();
    await expect(page.getByTestId("compare-rooms-total")).toContainText("Doluluk A");
    const room = page.getByTestId("compare-room-row").first();
    await expect(room).toBeVisible();
    await expect(room.locator("a[href^='/rooms/']")).toHaveCount(1);

    // rules: the soft penalties side by side
    await page.getByTestId("compare-tab-rules").click();
    await expect(page.getByTestId("compare-rule-row").first()).toBeVisible();
    await csvOk(page, await page.getByTestId("compare-csv-rules").getAttribute("href"));
  });

  test("room heatmap: live board by building, keyboard drill-down, rooms linking to the room page, CSV", async ({ page }) => {
    await login(page);
    await useTerm(page, "2026-BAHAR");
    await page.goto("/analytics/heatmap");
    await expect(page.getByTestId("heat-overall")).toContainText("Genel doluluk");
    await expect(page.getByTestId("heat-source-note")).toContainText("Yayındaki program: #");
    await expect(page.getByTestId("heat-legend")).toContainText("Önceden dolu");

    const overview = page.getByTestId("heat-overview");
    const cells = overview.getByRole("gridcell");
    expect(await cells.count()).toBeGreaterThanOrEqual(5 * 8); // all rooms + 4 buildings, 7 days + total
    // one tab stop; arrows move and the readout repeats the counts
    await cells.first().focus();
    await page.keyboard.press("ArrowDown");
    await expect(page.getByTestId("heat-overview-readout")).toContainText("A blok");
    await expect(page.getByTestId("heat-overview-readout")).toContainText("dolu");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/g=A/);
    await expect(page.getByTestId("heat-detail-title")).toContainText("A blok");
    const roomLink = page.getByTestId("heat-rooms").getByTestId("heat-room-link").first();
    await expect(roomLink).toHaveAttribute("href", /^\/rooms\/\d+$/);
    await csvOk(page, await page.getByTestId("heat-csv").getAttribute("href"));

    // one run instead of the live board, grouped by room type, whole term
    await page.getByTestId("heat-source-run").click();
    await expect(page).toHaveURL(/source=run/);
    await page.getByTestId("heat-group").selectOption("room_type");
    await expect(page.getByTestId("heat-source-note")).toContainText("Çalıştırma #");
    await expect(page.getByTestId("heat-overview").getByRole("rowheader").nth(1)).not.toHaveText("");
  });

  test("instructor load: matrix, sortable people, a person's week", async ({ page }) => {
    await login(page);
    await useTerm(page, "2026-BAHAR");
    const a = await runByLabel(page, "Bahar 3. hafta (A)");
    await page.goto(`/analytics/heatmap?tab=instructors&source=run&run=${a.id}`);
    await expect(page.getByTestId("instructors-heat")).toContainText(`Çalıştırma #${a.id}`);
    await expect(page.getByTestId("ins-matrix").getByRole("gridcell").first()).toBeVisible();
    const rows = page.getByTestId("ins-row");
    await expect(rows.first()).toBeVisible();
    const first = (await rows.first().innerText()).split("\n")[0]!;
    await page.getByRole("columnheader", { name: /Periyot\/hafta/ }).click(); // ascending now
    await expect(rows.first()).not.toContainText(first);
    await rows.first().click();
    await expect(page.getByTestId("ins-person")).toBeVisible();
    await expect(page.getByTestId("ins-person-grid").getByRole("gridcell").first()).toBeVisible();
  });

  test("phone 390 px: heatmap and comparison scroll inside their frames, never the page", async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    await login(page);
    await useTerm(page, "2026-BAHAR");
    const a = await runByLabel(page, "Bahar 3. hafta (A)");
    const b = await runByLabel(page, "Bahar 3. hafta, en yoğun derslik çarşamba kapalı (B)");
    for (const path of ["/analytics/heatmap?g=A", `/runs/compare?a=${a.id}&b=${b.id}`, "/exams/invigilation"]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      const [sw, iw] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
      expect(sw, `${path} has no page-level horizontal scroll`).toBeLessThanOrEqual(iw);
    }
    await ctx.close();
  });

  test("invigilation: pool with unavailability, run, diagnoses, lock, reassign, re-run keeping locks, publish, roster", async ({ page }) => {
    test.setTimeout(900_000);
    await login(page);
    const exam = await runByLabel(page, "Final (A)");
    await useTerm(page, "2026-FINAL");
    await page.goto(`/exams/invigilation?run=${exam.id}&tab=pool`);

    // pool: a research assistant who cannot invigilate on the first Final morning
    const name = `Arş. Gör. Deniz Kaya ${Date.now() % 100000}`;
    await page.getByTestId("pool-add").click();
    const form = page.getByTestId("pool-form");
    await form.getByTestId("pool-name").fill(name);
    await form.getByTestId("pool-kind").selectOption("ASSISTANT");
    await form.getByTestId("pool-max_per_day").fill("2");
    await form.getByTestId("pool-unavail-add").click();
    const row = form.getByTestId("pool-unavail-row").first();
    await row.getByTestId("pool-unavail-date").fill("01.06.2026");
    await row.getByTestId("pool-unavail-date").press("Enter");
    await form.getByTestId("pool-save").click();
    await expect(form).toBeHidden();
    const member = page.getByTestId("pool-row").filter({ hasText: name });
    await expect(member).toContainText("Araştırma görevlisi");
    await expect(member).toContainText("01.06.2026");

    // a plan with the default rules (a short time budget for the test)
    await page.getByTestId("invig-tab-plans").click();
    await page.getByTestId("invig-new").click();
    const plan = page.getByTestId("invig-form");
    await expect(plan.getByTestId("invig-param-students_per_invigilator")).toHaveValue("40");
    await expect(plan.getByTestId("invig-param-max_per_day")).toHaveValue("3");
    await plan.getByTestId("invig-advanced").click();
    await plan.getByTestId("invig-param-time_limit_s").fill("3");
    await plan.getByTestId("invig-param-label").fill("e2e varsayılan kurallar");
    await plan.getByTestId("invig-form-submit").click();
    await expect(plan).toBeHidden();
    const detail = page.getByTestId("invig-plan");
    await expect(detail).toHaveAttribute("data-status", /^(OPTIMAL|FEASIBLE|INFEASIBLE)$/, { timeout: 240_000 });
    await expect(page.getByTestId("invig-headline")).toContainText("salon-oturum");
    await expect(page.getByTestId("invig-counts")).toContainText("846");
    await expect(page.getByTestId("invig-diagnosis")).toBeVisible();

    // lock one duty, then hand another to a free candidate (shown with the reasons of everyone who is not free)
    const duty = page.getByTestId("invig-duty").first();
    await duty.getByTestId("invig-lock").click();
    await expect(page.getByTestId("invig-duty").first()).toHaveAttribute("data-locked", "true");
    await page.getByTestId("invig-duty").nth(1).getByTestId("invig-reassign").click();
    const dlg = page.getByTestId("invig-reassign-dialog");
    // every person is checked against every hard rule of the post (about 0.3 s on the real Final since 80780f2)
    await expect(dlg.getByTestId("invig-cand").first()).toBeVisible({ timeout: 30_000 });
    await dlg.getByTestId("invig-cand").first().check();
    await dlg.getByTestId("invig-reassign-reason").fill("e2e: elle değişiklik");
    await dlg.getByTestId("invig-reassign-ok").click();
    await expect(dlg).toBeHidden({ timeout: 120_000 });
    await expect(page.getByTestId("invig-duty").nth(1)).toHaveAttribute("data-locked", "true");
    await expect(page.getByTestId("invig-duty").nth(1)).toContainText("elle");

    // roster CSV of this plan
    await csvOk(page, await page.getByTestId("invig-roster-csv").getAttribute("href"));

    // re-run: a child plan that keeps both locked duties
    await page.getByTestId("invig-rerun").click();
    // the re-run starts from the parent's parameters (the 3 s budget set above)
    await expect(plan).toContainText("yeniden çalıştır");
    if (!(await plan.getByTestId("invig-param-time_limit_s").isVisible())) await plan.getByTestId("invig-advanced").click();
    await expect(plan.getByTestId("invig-param-time_limit_s")).toHaveValue("3");
    await plan.getByTestId("invig-form-submit").click();
    await expect(detail).toContainText("planından", { timeout: 30_000 });
    await expect(detail).toHaveAttribute("data-status", /^(OPTIMAL|FEASIBLE|INFEASIBLE)$/, { timeout: 240_000 });
    type Detail = { parent_plan_id: number | null; posts: { assigned: { post_key: string; person_key: string; is_locked: boolean }[] }[] };
    const child = Number(new URL(page.url()).searchParams.get("plan"));
    const kept = await api<Detail>(page, `/invigilation/plans/${child}`);
    expect(kept.parent_plan_id).toBeTruthy();
    const parent = await api<Detail>(page, `/invigilation/plans/${kept.parent_plan_id}`);
    const locks = (d: Detail) => d.posts.flatMap((p) => p.assigned).filter((x) => x.is_locked).map((x) => `${x.post_key}>${x.person_key}`).sort();
    expect(locks(parent)).toHaveLength(2); // the locked duty and the reassigned (manual, locked) one
    expect(locks(kept)).toEqual(locks(parent));

    // publish the re-run
    await page.getByTestId("invig-publish").click();
    await page.getByTestId("invig-confirm-ok").click();
    await expect(page.getByTestId("invig-published")).toBeVisible();

    // the pool row goes again
    await page.getByTestId("invig-tab-pool").click();
    await page.getByTestId("pool-row").filter({ hasText: name }).getByTestId("pool-delete").click();
    await page.getByTestId("pool-delete-ok").click();
    await expect(page.getByTestId("pool-row").filter({ hasText: name })).toHaveCount(0);
  });

  /**
   * batch-2 UI (self-contained: its own pool members and plans, all removed at the end). The real progress of a
   * default-rule plan (phase + the backend's percentage; while solving, the time against the limit), then a plan
   * with the instructor pool off and one staff member leaves posts short; a second member added afterwards is free
   * for them, and "Gözetmen ekle" fills one by hand: MANUAL, locked, the brief re-scored and the post's shortage
   * shown as resolved. On a phone the picker is a bottom sheet and nothing scrolls sideways.
   */
  test("invigilation: real progress, then Gözetmen ekle fills a short post by hand (resolved), phone 390 px", async ({ page, browser }) => {
    test.setTimeout(600_000);
    await login(page);
    const exam = await runByLabel(page, "Final (A)");
    const term = await useTerm(page, "2026-FINAL");
    const stamp = Date.now() % 100000;
    const made = { pool: [] as number[], plans: [] as number[] };
    type Brief = { id: number; status: string; counts: { filled: number | null; missing: number | null }; progress?: { phase: string; pct: number | null } };
    type Detail = Brief & { posts: { key: string; missing: number; required: number; assigned: { person_key: string; origin: string; is_locked: boolean }[] }[]; diagnosis: { code: string; post_keys?: string[]; resolved?: boolean }[] };
    try {
      // 1 · progress: a default-rule plan with a 15 s budget, opened while it runs
      const run = await send<{ plan_id: number }>(page, "POST", "/invigilation/plans", { exam_run_id: exam.id, label: `e2e batch2 ilerleme ${stamp}`, params: { time_limit_s: 15 } });
      made.plans.push(run.plan_id);
      await page.goto(`/exams/invigilation?run=${exam.id}&plan=${run.plan_id}`);
      const detail = page.getByTestId("invig-plan");
      const running = page.getByTestId("invig-running");
      // the backend's own phase and percentage; while CP-SAT runs the percentage stays at 30 and the time moves
      await expect(running).toHaveAttribute("data-phase", "solving", { timeout: 30_000 });
      await expect(page.getByTestId("invig-phase")).toHaveText("Çözülüyor");
      await expect(page.getByTestId("invig-progress")).toHaveAttribute("aria-valuenow", "30");
      const meter = page.getByTestId("invig-solve-time");
      await expect(meter).toHaveAttribute("aria-valuemax", "15");
      const t0 = Number(await meter.getAttribute("aria-valuenow"));
      await expect.poll(async () => Number(await meter.getAttribute("aria-valuenow")), { timeout: 10_000 }).toBeGreaterThan(t0);
      await expect(page.getByTestId("invig-plan-item").filter({ hasText: `e2e batch2 ilerleme ${stamp}` })).toContainText("Çözülüyor · %30");
      await expect(detail).toHaveAttribute("data-status", /^(OPTIMAL|FEASIBLE|INFEASIBLE)$/, { timeout: 240_000 });
      const done = await api<Brief[]>(page, `/invigilation/plans?exam_run_id=${exam.id}`);
      expect(done.find((p) => p.id === run.plan_id)?.progress).toEqual({ phase: "done", pct: 100 });

      // 2 · a short plan: instructors off, one staff member in the pool
      const first = await send<{ id: number }>(page, "POST", "/invigilation/pool", { full_name: `Arş. Gör. e2e Bir ${stamp}`, kind: "ASSISTANT", term_id: term.id });
      made.pool.push(first.id);
      const shortRun = await send<{ plan_id: number }>(page, "POST", "/invigilation/plans", { exam_run_id: exam.id, label: `e2e batch2 eksik ${stamp}`, params: { time_limit_s: 3, instructor_pool: "none" } });
      made.plans.push(shortRun.plan_id);
      await expect.poll(async () => (await api<Brief[]>(page, `/invigilation/plans?exam_run_id=${exam.id}`)).find((p) => p.id === shortRun.plan_id)?.status, { timeout: 240_000 }).toMatch(/^(INFEASIBLE|FEASIBLE|OPTIMAL)$/);
      // a second member joins after the solve: free for the short posts
      const name = `Arş. Gör. e2e İki ${stamp}`;
      const second = await send<{ id: number; person_key: string }>(page, "POST", "/invigilation/pool", { full_name: name, kind: "ASSISTANT", term_id: term.id });
      made.pool.push(second.id);
      const before = await api<Detail>(page, `/invigilation/plans/${shortRun.plan_id}`);
      // a post one invigilator short whose shortage diagnoses name only it: filling it resolves them
      const target = before.posts.find((p) => {
        if (p.missing !== 1) return false;
        const ds = before.diagnosis.filter((d) => d.post_keys?.includes(p.key));
        return ds.length > 0 && ds.every((d) => d.post_keys!.length === 1);
      });
      expect(target, "a post one invigilator short on the real Final").toBeTruthy();

      await page.goto(`/exams/invigilation?run=${exam.id}&plan=${shortRun.plan_id}&post=${encodeURIComponent(target!.key)}`);
      const card = page.locator(`[data-testid="invig-post"][data-post="${target!.key}"]`);
      await expect(card).toHaveAttribute("data-missing", "1");
      await card.getByTestId("invig-add").click();
      const dlg = page.getByTestId("invig-reassign-dialog");
      await expect(dlg).toContainText("salonuna gözetmen ekle");
      await expect(dlg).not.toContainText("dakika");
      await dlg.getByTestId("invig-cand-search").fill(`e2e İki ${stamp}`);
      await dlg.getByRole("radio", { name }).check({ timeout: 30_000 });
      await dlg.getByTestId("invig-reassign-reason").fill("e2e: eksik salon elle dolduruldu");
      await dlg.getByTestId("invig-reassign-ok").click();
      await expect(dlg).toBeHidden({ timeout: 30_000 });
      await expect(card).toHaveAttribute("data-missing", "0");
      await expect(card.getByTestId("invig-duty").filter({ hasText: name })).toContainText("elle");
      await expect(card.getByTestId("invig-add")).toHaveCount(0);
      // the diagnoses come back with the shortage resolved, in a group of their own
      await expect(page.locator('[data-testid="invig-diag-group"][data-resolved="true"]').first()).toContainText("giderildi");

      const after = await api<Detail>(page, `/invigilation/plans/${shortRun.plan_id}`);
      expect(after.counts.filled).toBe((before.counts.filled ?? 0) + 1);
      const duty = after.posts.find((p) => p.key === target!.key)!.assigned.find((d) => d.person_key === second.person_key);
      expect(duty).toMatchObject({ origin: "MANUAL", is_locked: true });
      expect(after.diagnosis.filter((d) => d.post_keys?.includes(target!.key)).every((d) => d.resolved === true)).toBe(true);

      // 3 · phone 390 px: the picker is a bottom sheet; nothing scrolls sideways
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
      const phone = await ctx.newPage();
      await login(phone);
      await useTerm(phone, "2026-FINAL");
      const other = after.posts.find((p) => p.missing > 0)!;
      await phone.goto(`/exams/invigilation?run=${exam.id}&plan=${shortRun.plan_id}&post=${encodeURIComponent(other.key)}`);
      const pcard = phone.locator(`[data-testid="invig-post"][data-post="${other.key}"]`);
      await pcard.getByTestId("invig-add").click();
      const sheet = phone.getByTestId("invig-reassign-dialog");
      await expect(sheet).toHaveAttribute("data-variant", "sheet");
      await expect(sheet.getByTestId("invig-cand").or(sheet.getByTestId("invig-cand-none")).first()).toBeVisible({ timeout: 30_000 });
      const [sw, iw] = await phone.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
      expect(sw).toBeLessThanOrEqual(iw);
      await ctx.close();
    } finally {
      for (const id of made.plans) await send(page, "DELETE", `/invigilation/plans/${id}`).catch(() => undefined);
      for (const id of made.pool) await send(page, "DELETE", `/invigilation/pool/${id}`).catch(() => undefined);
    }
  });
});

/** a write through the same-origin proxy with the session cookie (what the UI does) */
async function send<T = unknown>(page: Page, method: "POST" | "DELETE", path: string, body?: unknown): Promise<T> {
  const res = await page.evaluate(
    async ([m, url, b]) => {
      const r = await fetch(url as string, { method: m as string, headers: { Accept: "application/json", "Content-Type": "application/json" }, body: b === undefined ? undefined : JSON.stringify(b) });
      return { status: r.status, body: (await r.json().catch(() => null)) as unknown };
    },
    [method, `/api/v1${path}`, body] as const,
  );
  if (res.status >= 400) throw new Error(`${method} ${path} → ${res.status} ${JSON.stringify(res.body)}`);
  return res.body as T;
}
