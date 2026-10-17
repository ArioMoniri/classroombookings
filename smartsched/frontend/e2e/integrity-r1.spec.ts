/**
 * Round-1 hard-rule integrity (docs/testing/flows/rounds/round-1-admin.md, round-1-staff.md) on the real e2e backend
 * (Bahar 2026 workbooks + room master, the seeded week-3 runs and the full-term solver run):
 *
 *  1. R1-M-04 / R1-M-02: a week run's report never says "hiçbir kural bozulmadı" next to accepted exceptions; its
 *     publish confirm asks for the scope tick up front and publishes (no "başka biri değiştirdi" toast).
 *  2. R1-M-06 / R1-M-05: an administrator forces a move onto a taken room from the timetable's move dialog with a
 *     written reason; the timetable banner and the run report then name the broken rule with that reason; undo
 *     brings hard 100 back.
 *  3. R1-M-10: a week run against the full-term run: no metric with data on one side only reads "B daha iyi".
 *  4. R1-M-12: a week clicked while the previous scope save is still in flight survives the answer and a reload.
 *  5. R1-M-03: the impossible hard pin (ING 302, 100 students -> B 201, 30 seats) is refused with the one sentence.
 */
import { expect, test, type Page } from "@playwright/test";
import { REAL, SKIP_REASON, api, login } from "./helpers";

test.skip(!REAL, SKIP_REASON);

type TermRow = { id: number; code: string };
type RunRow = { id: number; term_id: number; kind: string; horizon: string; status: string; label: string | null; is_active: boolean; hard_score: number | null; stats: Record<string, unknown> };

async function useTerm(page: Page, code: string): Promise<TermRow> {
  const terms = await api<TermRow[]>(page, "/terms");
  const term = terms.find((t) => t.code === code)!;
  await page.evaluate((id) => {
    const raw = localStorage.getItem("smartsched.ui");
    const cur = raw ? (JSON.parse(raw) as { state?: Record<string, unknown>; version?: number }) : {};
    localStorage.setItem("smartsched.ui", JSON.stringify({ ...cur, state: { ...(cur.state ?? {}), termId: id } }));
  }, term.id);
  return term;
}

async function send(page: Page, method: string, path: string, body?: unknown): Promise<{ status: number; body: Record<string, unknown> }> {
  return page.evaluate(
    async ({ method, url, body }) => {
      const r = await fetch(url, { method, headers: { Accept: "application/json", "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
      return { status: r.status, body: (await r.json().catch(() => ({}))) as Record<string, unknown> };
    },
    { method, url: `/api/v1${path}`, body },
  );
}

async function runs(page: Page, termId: number): Promise<RunRow[]> {
  return api<RunRow[]>(page, `/runs?term_id=${termId}&limit=200`);
}

test.describe.configure({ mode: "serial" });

test.describe("round-1 hard-rule integrity", () => {
  test("1. week run: the verdict names its exceptions, the publish confirm asks for the scope", async ({ page }) => {
    test.setTimeout(180_000);
    await login(page);
    const term = await useTerm(page, "2026-BAHAR");
    const all = await runs(page, term.id);
    // a seeded week-3 run that is not the published one yet (a rerun on the same stack takes the other)
    const week = all.find((r) => r.kind === "COURSE" && r.horizon === "WEEK" && !r.is_active && (r.label ?? "").startsWith("Bahar 3. hafta") && ["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL"].includes(r.status));
    expect(week, "an unpublished seeded week-3 run").toBeTruthy();
    await page.goto(`/runs/${week!.id}`);
    const verdict = page.getByTestId("run-verdict");
    await expect(verdict).toBeVisible({ timeout: 30_000 });
    const summary = await api<{ truth: { verdict: string; headline: { tr: string } } }>(page, `/runs/${week!.id}/summary`);
    if (summary.truth.verdict !== "clean") await expect(verdict).not.toContainText("hiçbir kural bozulmadı");
    await expect(verdict).toContainText(summary.truth.headline.tr.split(" · ")[0]);
    if (summary.truth.verdict !== "clean") await expect(page.locator("body")).not.toContainText("Yerleşen her ders bütün kurallara uyuyor");

    await page.getByTestId("run-publish").click();
    const scope = page.getByTestId("publish-scope-reduction");
    await expect(scope).toBeVisible();
    const confirm = page.getByTestId("publish-confirm");
    await expect(confirm).toBeDisabled();
    if (await page.getByTestId("publish-partial-ack").isVisible()) await page.getByTestId("publish-partial-ack").click();
    await page.getByTestId("publish-scope-ack").click();
    await expect(confirm).toBeEnabled();
    await confirm.click();
    await expect(page.getByTestId("run-published")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Bu kaydı bu arada başka biri değiştirdi")).toHaveCount(0);
    const after = await api<RunRow>(page, `/runs/${week!.id}`);
    expect(after.is_active).toBe(true);
  });

  test("2. an administrator forces a move with a reason; the banner and the report name the break; undo restores", async ({ page }) => {
    test.setTimeout(240_000);
    await login(page);
    const term = await useTerm(page, "2026-BAHAR");
    const edit = Number(process.env.E2E_EDIT_RUN ?? 0) || (await runs(page, term.id)).find((r) => r.label === "e2e: Bahar 3. hafta (takvim düzenlemeleri)")!.id;
    const hardBefore = (await api<RunRow>(page, `/runs/${edit}`)).hard_score;
    const overridesBefore = ((await api<RunRow>(page, `/runs/${edit}`)).stats.forced_overrides as unknown[] | undefined)?.length ?? 0;
    // the busiest room of week 3: its classes have taken rooms around them in the finder
    const idx = await api<{ rooms: { id: number; name: string }[]; assignments: { rooms: number[]; weeks: number[] }[] }>(page, `/runs/${edit}/calendar-index`);
    const load = new Map<number, number>();
    for (const a of idx.assignments) if (a.weeks.includes(3)) for (const r of a.rooms) load.set(r, (load.get(r) ?? 0) + 1);
    const room = [...load.entries()].sort((x, y) => y[1] - x[1])[0][0];
    await page.goto(`/timetable?run=${edit}&week=3&lens=week&subject=room:${room}`);
    const chips = page.locator(`[data-testid=calendar-event][data-room-id="${room}"]`);
    await expect(chips.first()).toBeVisible({ timeout: 45_000 });
    const insp = page.getByTestId("class-inspector");
    const dialog = page.getByTestId("move-dialog");
    let forced = false;
    const n = Math.min(10, await chips.count());
    for (let i = 0; i < n && !forced; i++) {
      await chips.nth(i).click();
      await expect(insp).toBeVisible();
      await insp.getByTestId("inspector-move").click();
      await expect(dialog).toBeVisible();
      const busy = dialog.locator("[data-testid=free-room][data-status=busy]").first();
      if (!(await busy.waitFor({ state: "visible", timeout: 15_000 }).then(() => true, () => false))) {
        await page.keyboard.press("Escape");
        continue;
      }
      await busy.click();
      const panel = dialog.getByTestId("move-force-panel");
      await expect(panel).toBeVisible({ timeout: 15_000 });
      const force = dialog.getByTestId("move-force");
      await expect(force).toBeDisabled();
      await dialog.getByTestId("move-force-reason").fill("Bölüm başkanı onayı, tek seferlik");
      await expect(force).toBeEnabled();
      await force.click();
      await expect(dialog).toBeHidden({ timeout: 30_000 });
      forced = true;
    }
    expect(forced, "a class with a taken room in the finder").toBe(true);
    // the run names the break with the reason: the timetable banner and the report
    await expect.poll(async () => ((await api<RunRow>(page, `/runs/${edit}`)).stats.forced_overrides as unknown[] | undefined)?.length ?? 0, { timeout: 30_000 }).toBe(overridesBefore + 1);
    expect((await api<RunRow>(page, `/runs/${edit}`)).hard_score ?? 100).toBeLessThan(100);
    const banner = page.getByTestId("run-broken-banner");
    await expect(banner).toBeVisible({ timeout: 30_000 });
    await expect(banner).toContainText("Bölüm başkanı onayı, tek seferlik");
    const report = await page.context().newPage();
    await report.goto(`/runs/${edit}`);
    await expect(report.getByTestId("run-verdict")).toHaveAttribute("data-state", "broken", { timeout: 30_000 });
    await expect(report.getByTestId("verdict-broken")).toContainText("Bölüm başkanı onayı");
    await report.close();
    // undo (Ctrl+Z on the timetable): the forced placement goes away, the override stops counting, hard 100 again
    await page.getByTestId("calendar-title").click();
    await page.keyboard.press("ControlOrMeta+z");
    await expect.poll(async () => (await api<RunRow>(page, `/runs/${edit}`)).hard_score, { timeout: 30_000 }).toBe(hardBefore);
    if (hardBefore === 100) await expect(banner).toBeHidden({ timeout: 30_000 });
  });

  test("3. a week run against the full-term run is never 'B daha iyi' on data it does not have", async ({ page }) => {
    test.setTimeout(120_000);
    await login(page);
    const term = await useTerm(page, "2026-BAHAR");
    const all = await runs(page, term.id);
    const termRun = [...all].reverse().find((r) => r.kind === "COURSE" && r.horizon === "TERM" && ["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL"].includes(r.status) && r.label === "e2e: Bahar full term");
    const week = all.find((r) => r.label === "Bahar 3. hafta (B)" || r.label?.startsWith("Bahar 3. hafta, en yoğun"));
    expect(termRun && week, "the full-term run and a week-3 run").toBeTruthy();
    await page.goto(`/runs/compare?a=${termRun!.id}&b=${week!.id}`);
    await expect(page.getByTestId("compare-headline")).toContainText("Kapsamlar farklı", { timeout: 60_000 });
    for (const key of ["placed", "unplaced", "objective"]) {
      await expect(page.locator(`[data-testid="compare-metric"][data-key="${key}"]`)).toHaveAttribute("data-verdict", "incomparable");
    }
    await expect(page.locator('[data-testid="compare-metric"][data-verdict="incomparable"]').first()).toContainText("karşılaştırılamaz");
  });

  test("4. the Studio keeps a week clicked while the previous save is in flight (R1-M-12)", async ({ page }) => {
    test.setTimeout(240_000);
    await login(page);
    const term = await useTerm(page, "2026-BAHAR");
    const draft = await api<{ version: number }>(page, `/terms/${term.id}/studio`);
    const put = await send(page, "PUT", `/terms/${term.id}/studio`, { version: draft.version, horizon: "WEEK", horizon_params: { weeks: [6] } });
    expect(put.status).toBe(200);
    // every draft save answers 1.2 s late, so the second click lands while the first request is in flight
    await page.route(`**/api/v1/terms/${term.id}/studio`, async (route) => {
      if (route.request().method() === "PUT") await new Promise((res) => setTimeout(res, 1200));
      await route.continue();
    });
    await page.goto("/generate?step=scope");
    await expect(page.getByTestId("week-6")).toHaveAttribute("aria-pressed", "true", { timeout: 45_000 });
    await page.getByTestId("week-4").click();
    const firstSave = page.waitForRequest((r) => r.url().includes(`/terms/${term.id}/studio`) && r.method() === "PUT");
    await firstSave;
    await page.getByTestId("week-3").click(); // while the week-4 save is in flight
    await expect(page.getByTestId("save-status")).toHaveAttribute("data-state", "saved", { timeout: 90_000 });
    await expect(page.getByTestId("week-3")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("week-4")).toHaveAttribute("aria-pressed", "false");
    await page.unroute(`**/api/v1/terms/${term.id}/studio`);
    await expect.poll(async () => (await api<{ scope: { horizon_params: { weeks?: number[] } } }>(page, `/terms/${term.id}/studio`)).scope.horizon_params.weeks, { timeout: 20_000 }).toEqual([3]);
    await page.reload();
    await expect(page.getByTestId("week-3")).toHaveAttribute("aria-pressed", "true", { timeout: 45_000 });
    await expect(page.getByTestId("week-6")).toHaveAttribute("aria-pressed", "false");
  });

  test("5. the impossible hard pin is refused with the one sentence (R1-M-03)", async ({ page }) => {
    await login(page);
    const term = await useTerm(page, "2026-BAHAR");
    const classes = await api<{ items: { id: number; course_code: string | null; day: number | null; start_period: number | null; enrolment: number | null }[] }>(page, `/terms/${term.id}/studio/classes?limit=2000`);
    const ing = classes.items.find((c) => (c.course_code ?? "").replace(/\s/g, "") === "ING302" && c.day === 1 && c.start_period === 3 && c.enrolment === 100);
    const rooms = await api<{ id: number; code: string }[]>(page, "/rooms");
    const b201 = rooms.find((r) => r.code === "B201");
    test.skip(!ing || !b201, "the ING 302 row of the Bahar list");
    const res = await send(page, "POST", "/constraints", { term_id: term.id, kind: "room_pin", params: { event_ids: [ing!.id], room_ids: [b201!.id] }, hardness: "hard", weight: 5 });
    expect(res.status).toBe(422);
    expect((res.body.detail as { message_tr: string }).message_tr).toBe("100 öğrenci 30 kişilik B 201'e sığmaz");
  });
});
