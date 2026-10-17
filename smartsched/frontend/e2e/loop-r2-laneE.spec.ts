/**
 * Flow loop round 2, lane E (docs/ROADMAP.md "Flow loop tickets — round 2", rounds/round-2-tickets.json) against the
 * REAL backend of a `stack.sh runs` stack, gated E2E_REAL=1:
 *
 * - T-R2-26 run report: the number after "Sorun" is the truth's broken + accepted exceptions (the headline's number)
 *   at 1440 and 390, with "Veri notları N" as a second line; the unplaced list has exactly as many rows as its count;
 *   /dashboard main.innerText has no odometer digit strip.
 * - T-R2-27 Studio on Güz: the rail reads "Tüm dönem · 14 hafta" and agrees with the sentence, also right after the
 *   term switch; the compare refusal names the reason and each run's horizon.
 * - T-R2-30 capacity and run polish: the pin template marks "sığmaz" and offers the admin reason; the move dialog
 *   disables "Taşı" on a too-small room and shows the force panel; cancel right after POST /runs → CANCELLED with the
 *   display name; focus is not on body after "Yayınla"; a planner's forced move → 403 with message_tr; the broken
 *   banner has no "week" / "day".
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19350 NEXT_PUBLIC_API_URL=http://127.0.0.1:19350 PW_PORT=19351 \
 *     npx playwright test e2e/loop-r2-laneE.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";
import { pinLanguage } from "./language";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 3, locale: "tr-TR", timezoneId: "Europe/Istanbul" };

test.describe.configure({ timeout: 300_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

interface Run {
  id: number;
  term_id: number;
  kind: string;
  horizon: string;
  status: string;
  is_active: boolean;
  horizon_params: { weeks: number[] };
  error?: string | null;
}
interface Truth {
  broken_count: number;
  exceptions_total: number;
  unplaced: number;
  unplaced_count: number;
  unplaced_list: { id: number; label: string }[];
  broken: { message: string; message_tr: string | null }[];
}
const ctx = {} as { api: APIRequestContext; admin: string; bahar: { id: number; code: string }; guz: { id: number; code: string } | null; termRun: Run | null; weekRun: Run | null; otherTermRun: Run | null };

async function call<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token = ctx.admin): Promise<{ status: number; body: T }> {
  const res = await ctx.api.fetch(`${API}${path}`, { method, data: body, headers: { Authorization: `Bearer ${token}` } });
  const text = await res.text();
  return { status: res.status(), body: (text ? JSON.parse(text) : undefined) as T };
}
async function api<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
  const r = await call<T>(method, path, body);
  if (r.status >= 400) throw new Error(`${method} ${path} → ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}
function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  return errors;
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  const res = await ctx.api.post(`${API}/auth/login`, { data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD } });
  ctx.admin = ((await res.json()) as { access_token: string }).access_token;
  const terms = await api<{ id: number; code: string }[]>("GET", "/terms");
  ctx.bahar = terms.find((t) => t.code === "2026-BAHAR") ?? terms[0];
  ctx.guz = terms.find((t) => t.code === "2026-GUZ") ?? null;
  const runs = await api<Run[]>("GET", "/runs");
  const finished = (r: Run) => ["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL"].includes(r.status) && r.kind === "COURSE";
  const bahar = runs.filter((r) => r.term_id === ctx.bahar.id && finished(r));
  ctx.termRun = bahar.filter((r) => r.horizon === "TERM").sort((a, b) => Number(b.is_active) - Number(a.is_active) || b.id - a.id)[0] ?? null;
  ctx.weekRun = bahar.filter((r) => r.horizon === "WEEK").sort((a, b) => b.id - a.id)[0] ?? null;
  ctx.otherTermRun = runs.filter((r) => r.term_id !== ctx.bahar.id && finished(r))[0] ?? null;
});
test.afterAll(async () => {
  await ctx.api.dispose();
});

/* ------------------------------------------------------------------ T-R2-26 */

test("T-R2-26 · Sorun = broken + accepted exceptions at 1440 and 390; Veri notları on a second line; the unplaced list is complete", async ({ page, browser }) => {
  test.skip(!ctx.termRun, "no finished Bahar term run on this stack (stack.sh runs)");
  const r = ctx.termRun!;
  const summary = await api<{ truth: Truth; data_issues: { issues: number } }>("GET", `/runs/${r.id}/summary`);
  const want = summary.truth.broken_count + summary.truth.exceptions_total;
  expect(summary.truth.unplaced_list.length).toBe(summary.truth.unplaced_count);
  expect(summary.truth.unplaced_list.length).toBe(summary.truth.unplaced);
  const errors = trackErrors(page);
  await login(page);
  await page.goto(`/runs/${r.id}`);
  const kpi = page.locator('[data-testid^="kpi-Sorun"]');
  await expect(kpi).toHaveText(String(want), { timeout: 20_000 });
  // the summary (planner check + data issues) takes ~8 s on a loaded 4-core host: the page shows the stored truth
  // first and settles once the fresh summary is in
  await expect(page.getByTestId("kpi-data-notes")).toHaveText(`Veri notları ${new Intl.NumberFormat("tr-TR").format(summary.data_issues.issues)}`, { timeout: 45_000 });
  await expect(page.getByTestId("tab-report")).toContainText(String(want));
  // the headline and the KPI are one number
  const hero = await page.getByTestId("run-hero").innerText();
  expect(hero).toContain(`${want} kabul edilmiş istisna`);
  const list = page.getByTestId("unplaced-list");
  await expect(list).toBeVisible({ timeout: 45_000 });
  expect(await list.locator("li").count()).toBe(summary.truth.unplaced_count);
  await expect(page.getByTestId("unplaced-list-count")).toHaveText(String(summary.truth.unplaced_count));
  expect((await page.locator("main").innerText()).replace(/\s+/g, "")).not.toContain("0123456789");

  const phoneCtx = await browser.newContext(PHONE);
  const phone = await phoneCtx.newPage();
  await login(phone);
  await phone.goto(`/runs/${r.id}`);
  await expect(phone.locator('[data-testid^="kpi-Sorun"]')).toHaveText(String(want), { timeout: 20_000 });
  await expect(phone.getByTestId("unplaced-list")).toBeVisible({ timeout: 45_000 });
  expect(await phone.getByTestId("unplaced-list").locator("li").count()).toBe(summary.truth.unplaced_count);
  await phoneCtx.close();
  expect(errors).toEqual([]);
});

test("T-R2-26 · /dashboard has no odometer digit strip in main.innerText at 1440 and 390", async ({ page, browser }) => {
  await login(page);
  await page.goto("/dashboard");
  await page.locator("main h1, main h2").first().waitFor();
  await page.waitForTimeout(1500);
  const main = await page.locator("main").innerText();
  expect(main).not.toContain("0 1 2 3 4 5 6 7 8 9");
  expect(main.replace(/\s+/g, "")).not.toContain("0123456789");
  const phoneCtx = await browser.newContext(PHONE);
  const phone = await phoneCtx.newPage();
  await login(phone);
  await phone.goto("/dashboard");
  await phone.waitForTimeout(1500);
  expect((await phone.locator("main").innerText()).replace(/\s+/g, "")).not.toContain("0123456789");
  await phoneCtx.close();
});

/* ------------------------------------------------------------------ T-R2-27 */

test("T-R2-27 · the Studio rail and sentence agree on Güz's 14 weeks, also right after the term switch", async ({ page }) => {
  test.skip(!ctx.guz, "no 2026-GUZ term on this backend");
  await login(page);
  await page.goto("/generate");
  await page.getByTestId("scope-step").waitFor();
  const sel = page.locator("#scope-term");
  await sel.selectOption(String(ctx.bahar.id));
  await expect(page.getByTestId("scope-sentence")).toContainText("derslikte", { timeout: 60_000 });
  await page.getByTestId("horizon-TERM").click();
  await sel.selectOption(String(ctx.guz!.id));
  const rail = page.locator('[data-testid="rail-step-scope"]');
  const seen: string[] = [];
  const t0 = Date.now();
  while (Date.now() - t0 < 2500) {
    seen.push((await rail.innerText()).replace(/\s+/g, " "));
    await page.waitForTimeout(50);
  }
  // never "2 hafta" (the dated rows) while the term settles: either counting or the term's weeks
  expect(seen.filter((x) => /\b2 hafta\b/.test(x))).toEqual([]);
  await expect(rail).toContainText("Tüm dönem · 14 hafta", { timeout: 60_000 });
  await expect(page.getByTestId("scope-sentence")).toContainText("14 hafta boyunca", { timeout: 60_000 });
});

test("T-R2-27 · the compare refusal names the reason and each run's horizon", async () => {
  test.skip(!ctx.termRun, "no finished Bahar term run");
  const a = ctx.termRun!;
  if (ctx.weekRun) {
    // different horizons of one term and kind compare on their common weeks
    const ok = await call<{ scope?: { differs: boolean } }>("GET", `/analytics/compare?a=${a.id}&b=${ctx.weekRun.id}`);
    expect(ok.status).toBe(200);
    expect(ok.body.scope?.differs).toBe(true);
  }
  const other = ctx.otherTermRun;
  test.skip(!other, "no finished run of another term");
  const r = await call<{ detail: { code: string; tr: string; en: string } }>("GET", `/analytics/compare?a=${a.id}&b=${other!.id}`);
  expect(r.status).toBe(422);
  expect(r.body.detail.code).toBe("compare_scope");
  expect(r.body.detail.tr).toContain("dönemleri farklı");
  expect(r.body.detail.tr).toContain("tüm dönem");
  expect(r.body.detail.tr).toContain(`#${a.id}`);
  expect(r.body.detail.tr).not.toContain("aynı dönemin aynı türden çalıştırmaları değil");
});

/* ------------------------------------------------------------------ T-R2-30 */

test("T-R2-30 · the pin template marks 'sığmaz' for B 201 with ING 302 and offers the admin reason", async ({ page }) => {
  await login(page);
  await page.goto("/generate");
  await page.getByTestId("scope-step").waitFor();
  await page.locator("#scope-term").selectOption(String(ctx.bahar.id));
  await page.getByTestId("rail-step-rules").click();
  await page.getByTestId("rules-step").waitFor();
  await page.getByTestId("add-template").click();
  const tpl = page.getByTestId("template-always_in_room");
  await tpl.waitFor({ timeout: 15_000 });
  await tpl.click();
  await page.getByTestId("rule-builder").waitFor();
  // the course: ING 302 (100 students); the course picker shows each meeting's day and time
  const courseBox = page.locator('[data-testid="rule-builder"] input[aria-label="Ara: Ders"]');
  await courseBox.fill("ING 302");
  const course = page.locator('[data-testid^="course-option-"]').first();
  await expect(course).toContainText(/P\d|\d\d:\d\d/);
  await course.locator("input").check();
  // the room: B 201 (30 seats) → sığmaz
  const roomBox = page.locator('[data-testid="rule-builder"] input[aria-label="Ara: Derslik"]');
  await roomBox.fill("B 201");
  const room = page.locator('[data-testid^="room-option-"]').filter({ hasText: "B 201" }).first();
  await expect(room).toContainText(/sığmaz \(\d+ > 30\)/);
  await room.locator("input").check();
  await expect(page.getByTestId("builder-too-small")).toContainText("sığmaz");
  await expect(page.getByTestId("builder-reason")).toBeVisible();
  await expect(page.getByTestId("builder-add")).toBeDisabled();
  await page.keyboard.press("Escape");
});

test("T-R2-30 · the move dialog disables Taşı on a Sığmaz room and explains in the force panel", async ({ page }) => {
  test.skip(!ctx.termRun, "no finished Bahar term run");
  // the biggest class of week 3 (MAT 112 §1, 180 students on the real Bahar list): most rooms are too small for it
  const asg = await api<{ id: number; size: number | null }[]>("GET", `/runs/${ctx.termRun!.id}/assignments?week=3`);
  const big = [...asg].sort((a, b) => (b.size ?? 0) - (a.size ?? 0))[0];
  await login(page);
  await page.goto(`/timetable?run=${ctx.termRun!.id}&week=3&sel=${big.id}`);
  await page.getByTestId("time-grid").waitFor();
  await expect(page.getByTestId("class-inspector")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("inspector-move").click();
  const dialog = page.getByTestId("move-dialog");
  await expect(dialog).toBeVisible();
  const small = dialog.locator('[data-testid="free-room"][data-status="too_small"]').first();
  await expect(small).toBeVisible({ timeout: 30_000 });
  await small.click();
  await expect(dialog.getByTestId("move-confirm")).toBeDisabled();
  await expect(dialog.getByTestId("move-force-panel")).toBeVisible();
  await expect(dialog).toContainText(/sığmaz/);
  await expect(dialog.getByTestId("move-server-ok")).toHaveCount(0);
  await page.keyboard.press("Escape");
});

test("T-R2-30 · cancel right after POST /runs → CANCELLED by the display name; a planner's forced move → 403 with message_tr", async () => {
  const created = await api<{ run_id: number }>("POST", "/runs", { term_id: ctx.bahar.id, kind: "COURSE", horizon: "WEEK", horizon_params: { weeks: [3] }, params: { time_limit_s: 20 }, label: "lane E cancel" });
  const c = await call<Run>("POST", `/runs/${created.run_id}/cancel`);
  expect(c.status).toBe(200);
  expect(c.body.status).toBe("CANCELLED");
  const me = await api<{ full_name: string | null; email: string }>("GET", "/auth/me");
  expect(c.body.error).toBe(`cancelled by ${me.full_name || me.email}`);
  expect(c.body.error).not.toContain("@");
  const again = await call<{ detail: { message_tr?: string } }>("POST", `/runs/${created.run_id}/cancel`);
  expect(again.status).toBe(409);
  expect(again.body.detail.message_tr).toContain("çalıştırması");
  // a planner may not force a move: 403 with a Turkish sentence
  const email = "planner.lane-e@smartsched.local";
  const users = await api<{ id: number; email: string }[] | { items: { id: number; email: string }[] }>("GET", "/users?q=planner.lane-e");
  const list = Array.isArray(users) ? users : users.items;
  if (!list.some((u) => u.email === email)) await api("POST", "/users", { email, full_name: "P. L.", role: "PLANNER", password: "Flow-2026!pw" });
  const login = await ctx.api.post(`${API}/auth/login`, { data: { email, password: "Flow-2026!pw" } });
  expect(login.status()).toBe(200);
  const planner = ((await login.json()) as { access_token: string }).access_token;
  test.skip(!ctx.termRun, "no finished Bahar term run");
  const asg = await api<{ id: number; day: number; start_period: number; end_period: number; room_ids: number[] }[]>("GET", `/runs/${ctx.termRun!.id}/assignments?week=3&day=1`);
  const a = asg[0];
  const forced = await call<{ detail: { message?: string; message_tr?: string } }>("POST", `/runs/${ctx.termRun!.id}/assignments/bulk-move`, { force: true, reason: "lane E test", moves: [{ aid: a.id, day: a.day, start_period: a.start_period, end_period: a.end_period, room_ids: a.room_ids, scope: "all" }] }, planner);
  expect(forced.status).toBe(403);
  expect(forced.body.detail.message_tr).toContain("yöneticilere açık");
});

test("T-R2-30 · focus stays off body after Yayınla; the republished run is restored", async ({ page }) => {
  test.skip(!ctx.termRun, "no finished Bahar term run");
  const runs = await api<Run[]>("GET", `/runs?term_id=${ctx.bahar.id}`);
  const other = runs.filter((r) => r.kind === "COURSE" && r.horizon === "TERM" && !r.is_active && ["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL"].includes(r.status)).sort((a, b) => a.id - b.id)[0];
  test.skip(!other, "no second publishable Bahar term run");
  const active = ctx.termRun!.is_active ? ctx.termRun!.id : null;
  await login(page);
  await page.goto(`/runs/${other!.id}`);
  const publish = page.getByTestId("run-publish");
  await expect(publish).toBeVisible({ timeout: 20_000 });
  await publish.click();
  const dialog = page.getByRole("dialog");
  for (const tid of ["publish-partial-ack", "publish-scope-ack", "publish-forced-ack"]) {
    const box = dialog.getByTestId(tid);
    if (await box.count()) await box.click();
  }
  await dialog.getByRole("button", { name: /^Yayınla$|Haftaları kaldırarak yayımla/ }).last().click();
  await expect(page.locator("[data-sonner-toast]").first()).toContainText("artık yayımlanan program", { timeout: 20_000 });
  await expect.poll(() => page.evaluate(() => document.activeElement?.tagName)).not.toBe("BODY");
  await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute("data-testid"))).toBe("run-published");
  if (active) await api("POST", `/runs/${active}/activate`, { confirm_scope_reduction: true, confirm_forced_breaks: true });
});
