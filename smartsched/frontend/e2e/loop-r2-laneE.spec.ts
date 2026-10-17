/**
 * Flow loop round 2, lane E (docs/ROADMAP.md "Flow loop tickets — round 2", rounds/round-2-tickets.json) against the
 * REAL backend of a `stack.sh runs` stack, gated E2E_REAL=1:
 *
 * - T-R2-26 run report: the number after "Sorun" is the truth's broken + accepted exceptions (the headline's number)
 *   at 1440 and 390, with "Veri notları N" as a second line; the unplaced list has exactly as many rows as its count;
 *   /dashboard main.innerText has no odometer digit strip.
 * - T-R2-27 Studio on Güz: the rail reads "Tüm dönem · 14 hafta" and agrees with the sentence, also right after the
 *   term switch; the compare refusal names the reason and each run's horizon.
 * - T-R2-28 phone timetable / classes: MOBILE M-02 clean with the inspector open; "Taşı…" and "Kilitle" (44 px) in the
 *   sheet footer inside the bottom 40 %; an open-filters trigger opens the filters sheet; document.title is never a
 *   day name; at 1440 the second Tab from the page start reaches "Izgaraya geç".
 * - T-R2-29 Studio steps 2–3 and /settings?tab=solver on the phone: M-02 clean, 16 px inputs, the solver's default
 *   weights (never 0) under "Ağırlık"; GET /runs/<id>/export?weeks=4 is named -hafta4.
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
/** MOBILE.md M-02 (touch targets ≥ 44 px or a 44 px hit area), for the elements in view. */
const M02 = () => {
  const SEL = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=checkbox],[role=radio],[role=switch],[role=menuitem],[role=option],[role=slider],[tabindex]:not([tabindex="-1"])';
  const hits = (el: Element, x: number, y: number) => { const t = document.elementFromPoint(x, y); return !!t && (t === el || el.contains(t)); };
  const bad: { el: string; w: number; h: number }[] = [];
  for (const el of document.querySelectorAll<HTMLElement>(SEL)) {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === "hidden" || el.closest('[aria-hidden="true"],[inert]')) continue;
    if (el.checkVisibility && !el.checkVisibility()) continue;
    if (r.width <= 1 && r.height <= 1 && el !== document.activeElement) continue;
    if (el.tagName === "A" && cs.display === "inline" && /^(P|LI|TD|SPAN|DD)$/.test(el.parentElement?.tagName ?? "")) continue;
    let w = r.width, h = r.height;
    const lab = (el as HTMLInputElement).labels?.[0]; if (lab) { const l = lab.getBoundingClientRect(); w = Math.max(w, l.width); h = Math.max(h, l.height); }
    if (w >= 44 && h >= 44) continue;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const VW = document.documentElement.clientWidth, VH = document.documentElement.clientHeight;
    const inView = cy > 22 && cy < VH - 22 && cx > 22 && cx < VW - 22;
    if (!inView) continue;
    if ([[cx - 22, cy], [cx + 21, cy], [cx, cy - 22], [cx, cy + 21]].every(([x, y]) => hits(el, x, y))) continue;
    bad.push({ el: (el.dataset.testid || el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40), w: Math.round(w), h: Math.round(h) });
  }
  return bad;
};
async function m02All(page: Page): Promise<{ el: string; w: number; h: number }[]> {
  const out: { el: string; w: number; h: number }[] = [];
  const vh = await page.evaluate(() => document.documentElement.clientHeight);
  const total = await page.evaluate(() => Math.min(8000, Math.max(document.documentElement.scrollHeight, ...[...document.querySelectorAll("main *")].map((e) => e.scrollHeight))));
  for (let y = 0; y <= total; y += Math.round(vh * 0.8)) {
    await page.evaluate((y) => { window.scrollTo(0, y); document.querySelectorAll("main, main *, [role=dialog] *").forEach((e) => { if (e.scrollHeight > e.clientHeight + 4) e.scrollTop = y; }); }, y);
    await page.waitForTimeout(150);
    out.push(...(await page.evaluate(M02)));
  }
  return out.filter((x, i, arr) => arr.findIndex((y) => JSON.stringify(y) === JSON.stringify(x)) === i);
}
async function assertTouch(page: Page): Promise<void> {
  const s = await page.evaluate(() => ({ coarse: matchMedia("(pointer: coarse)").matches, hover: matchMedia("(hover: none)").matches, touch: navigator.maxTouchPoints }));
  expect(s, "touch emulation is on (MOBILE.md: assertTouch)").toEqual({ coarse: true, hover: true, touch: expect.any(Number) });
  expect(s.touch).toBeGreaterThan(0);
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
  // leave the Studio drafts on the scope step: the server remembers the last step per term and user, and another spec's
  // "/generate then select Bahar" expects the scope step
  for (const term of [ctx.bahar, ctx.guz].filter((t): t is { id: number; code: string } => !!t)) {
    const draft = await call<{ version: number; last_step: string | null }>("GET", `/terms/${term.id}/studio?kind=COURSE`);
    if (draft.status === 200 && draft.body.last_step && draft.body.last_step !== "scope") {
      await call("PUT", `/terms/${term.id}/studio`, { version: draft.body.version, kind: "COURSE", last_step: "scope" });
    }
  }
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
  // the headline and the KPI are one number: the exceptions it lists (plus the broken rules, when a forced move left one)
  const hero = await page.getByTestId("run-hero").innerText();
  if (summary.truth.broken_count) expect(hero).toContain(`${summary.truth.broken_count} kesin kural bozuk`);
  else expect(hero).toContain(`${want} kabul edilmiş istisna`);
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

/* ------------------------------------------------------------------ T-R2-28 */

test("T-R2-28 · phone timetable: M-02 clean, Taşı… / Kilitle in the sheet footer within the bottom 40 %, a filters sheet, no day-name title", async ({ browser }) => {
  test.skip(!ctx.termRun, "no finished Bahar term run");
  const phoneCtx = await browser.newContext(PHONE);
  const phone = await phoneCtx.newPage();
  await login(phone);
  const titles = new Set<string>();
  const poll = setInterval(() => void phone.evaluate(() => document.title).then((t) => titles.add(t)).catch(() => undefined), 40);
  await phone.goto(`/timetable?run=${ctx.termRun!.id}&week=3`);
  await phone.getByTestId("calendar-mobile").waitFor({ timeout: 60_000 });
  await phone.waitForTimeout(2500);
  clearInterval(poll);
  expect([...titles].filter((t) => /^(Pazartesi|Salı|Çarşamba|Perşembe|Cuma|Cumartesi|Pazar)$/.test(t))).toEqual([]);
  await assertTouch(phone);
  expect(await m02All(phone)).toEqual([]);
  // the filters: a trigger on the agenda view opens the desktop filters in a sheet
  await expect(phone.getByTestId("open-filters")).toBeVisible();
  await phone.getByTestId("open-filters").click();
  await expect(phone.getByTestId("filters-sheet")).toBeVisible();
  await expect(phone.getByTestId("calendar-sidebar")).toBeVisible();
  await phone.keyboard.press("Escape");
  await expect(phone.getByTestId("filters-sheet")).toBeHidden();
  // the inspector sheet: both actions in the footer, 44 px, inside the bottom 40 %
  await phone.evaluate(() => window.scrollTo(0, 0));
  await phone.getByTestId("calendar-event").first().click();
  await expect(phone.getByTestId("class-inspector")).toBeVisible({ timeout: 20_000 });
  const vh = phone.viewportSize()!.height;
  for (const tid of ["inspector-move", "inspector-lock"]) {
    const b = (await phone.getByTestId(tid).boundingBox())!;
    expect(b.height, tid).toBeGreaterThanOrEqual(44);
    expect(b.y, `${tid} in the bottom 40 %`).toBeGreaterThanOrEqual(0.6 * vh - 1);
    expect(b.y + b.height).toBeLessThanOrEqual(vh);
  }
  await expect(phone.getByTestId("inspector-lock")).toHaveText(/Kilitle|Kilidi aç/);
  await expect(phone.getByTestId("inspector-move")).toHaveText("Taşı…");
  expect(await phone.evaluate(M02)).toEqual([]);
  await phoneCtx.close();
});

test("T-R2-28 · /classes on the phone is M-02 clean; at 1440 the second Tab reaches Izgaraya geç", async ({ page, browser }) => {
  test.skip(!ctx.termRun, "no finished Bahar term run");
  const phoneCtx = await browser.newContext(PHONE);
  const phone = await phoneCtx.newPage();
  await login(phone);
  await phone.goto(`/classes?run=${ctx.termRun!.id}`);
  await phone.getByTestId("classes").waitFor({ timeout: 60_000 });
  await phone.waitForTimeout(3000);
  await assertTouch(phone);
  expect(await m02All(phone)).toEqual([]);
  await phoneCtx.close();

  await login(page);
  await page.goto(`/timetable?run=${ctx.termRun!.id}&week=3`);
  await page.getByTestId("time-grid").waitFor({ timeout: 60_000 });
  await page.waitForTimeout(500);
  await page.keyboard.press("Tab");
  await expect.poll(() => page.evaluate(() => document.activeElement?.textContent?.trim())).toBe("İçeriğe atla");
  await page.keyboard.press("Tab");
  await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute("data-testid"))).toBe("skip-to-grid");
  await expect(page.getByTestId("skip-to-grid")).toHaveText("Izgaraya geç");
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute("data-testid"))).toBe("time-grid");
});

/* ------------------------------------------------------------------ T-R2-29 */

test("T-R2-29 · Studio steps 2–3 and the solver tab on the phone: M-02 clean, 16 px inputs, real default weights under Ağırlık", async ({ browser }) => {
  const phoneCtx = await browser.newContext(PHONE);
  const phone = await phoneCtx.newPage();
  await login(phone);
  await phone.goto("/generate");
  await phone.getByTestId("scope-step").waitFor({ timeout: 60_000 });
  await phone.locator("#scope-term").selectOption(String(ctx.bahar.id));
  await expect(phone.getByTestId("scope-sentence")).toContainText("derslikte", { timeout: 60_000 });
  await phone.getByTestId("step-next").click();
  await phone.getByTestId("classes-step").waitFor({ timeout: 60_000 });
  await phone.waitForTimeout(2500);
  await assertTouch(phone);
  expect(await m02All(phone)).toEqual([]);
  await phone.getByTestId("step-next").click();
  await phone.getByTestId("rules-step").waitFor({ timeout: 60_000 });
  await phone.waitForTimeout(2000);
  await assertTouch(phone);
  expect(await m02All(phone)).toEqual([]);

  await phone.goto("/settings?tab=solver");
  await phone.getByTestId("solver-weights").waitFor({ timeout: 60_000 });
  await phone.waitForTimeout(1000);
  await assertTouch(phone);
  expect(await m02All(phone)).toEqual([]);
  const inputs = await phone.evaluate(() => [...document.querySelectorAll<HTMLInputElement>("main input")].filter((i) => i.checkVisibility()).map((i) => ({ id: i.id || i.type, fs: parseFloat(getComputedStyle(i).fontSize) })));
  expect(inputs.length).toBeGreaterThanOrEqual(3);
  expect(inputs.filter((i) => i.fs < 16)).toEqual([]);
  const weights = await phone.locator('[data-testid^="weight-"]').allInnerTexts();
  expect(weights.length).toBe(6);
  expect(weights.filter((w) => Number(w) === 0)).toEqual([]);
  await expect(phone.getByTestId("solver-weights").locator("thead")).toContainText("Ağırlık");
  await expect(phone.getByTestId("solver-weights").locator("thead")).not.toContainText(/\bw\b/);
  await phoneCtx.close();
});

test("T-R2-29 · a weeks-filtered export of a term run is named -haftaN", async () => {
  test.skip(!ctx.termRun, "no finished Bahar term run");
  const res = await ctx.api.fetch(`${API}/runs/${ctx.termRun!.id}/export?weeks=4`, { headers: { Authorization: `Bearer ${ctx.admin}` } });
  expect(res.status()).toBe(200);
  expect(res.headers()["content-disposition"]).toContain(`smartsched-run${ctx.termRun!.id}-hafta4.xlsx`);
  const plain = await ctx.api.fetch(`${API}/runs/${ctx.termRun!.id}/export`, { headers: { Authorization: `Bearer ${ctx.admin}` } });
  expect(plain.headers()["content-disposition"]).toContain(`smartsched-run${ctx.termRun!.id}.xlsx`);
});

/* ------------------------------------------------------------------ T-R2-30 (F-10 S06) */

test("T-R2-30 · a forced capacity break reads Turkish on the timetable banner and in the truth (no 'week' / 'day'); the move is undone", async ({ page }) => {
  // on the unpublished week run: its one week makes the undo exact, and the published run's truth stays as it was
  test.skip(!ctx.weekRun, "no finished Bahar week run");
  const run = ctx.weekRun!.id;
  const week = ctx.weekRun!.horizon_params.weeks[0] ?? 3;
  const asg = await api<{ id: number; day: number; start_period: number; end_period: number; room_ids: number[]; size: number | null; capacity: number | null }[]>("GET", `/runs/${run}/assignments?week=${week}`);
  const big = [...asg].filter((a) => a.size).sort((a, b) => (b.size ?? 0) - (a.size ?? 0))[0];
  const rooms = await api<{ id: number; capacity: number; is_bookable: boolean }[]>("GET", "/rooms");
  const small = rooms.filter((r) => r.is_bookable && r.capacity > 0 && r.capacity < (big.size ?? 0) / 2).sort((a, b) => a.capacity - b.capacity)[0];
  test.skip(!small, "no room small enough for a capacity break");
  const move = (room_ids: number[], force: boolean) =>
    call<{ detail?: unknown; applied?: number }>("POST", `/runs/${run}/assignments/bulk-move`, { force, reason: force ? "lane E banner check" : undefined, moves: [{ aid: big.id, day: big.day, start_period: big.start_period, end_period: big.end_period, room_ids, scope: "all" }] });
  // the room may be taken at this slot: try the smallest free one
  let forced: Awaited<ReturnType<typeof move>> | null = null;
  for (const r of rooms.filter((r) => r.is_bookable && r.capacity > 0 && r.capacity < (big.size ?? 0) / 2).sort((a, b) => a.capacity - b.capacity).slice(0, 6)) {
    forced = await move([r.id], true);
    if (forced.status === 200) break;
  }
  expect(forced?.status, JSON.stringify(forced?.body ?? forced)).toBe(200);
  try {
    const s = await api<{ truth: Truth }>("GET", `/runs/${run}/summary`);
    expect(s.truth.broken_count).toBeGreaterThan(0);
    for (const b of s.truth.broken) {
      expect(b.message_tr, b.message).toBeTruthy();
      expect(b.message_tr!).not.toMatch(/\b(week|day)\b/);
    }
    await login(page);
    await page.goto(`/timetable?run=${run}&week=${week}`);
    const banner = page.getByTestId("run-broken-banner");
    await expect(banner).toBeVisible({ timeout: 60_000 });
    const text = await banner.innerText();
    expect(text).not.toMatch(/\b(week|day)\b/);
    expect(text).toMatch(/kesin kural/);
  } finally {
    const back = await move(big.room_ids, false);
    expect(back.status, JSON.stringify(back.body ?? back)).toBe(200);
  }
});

/* ------------------------------------------------------------------ round 3 follow-up (loop-r3-laneE-2026-10-17) */

test("R3-M-05 · phone filters: a full-width bottom sheet, 16 px search, 44 px targets, a sticky show action; the search filters the agenda", async ({ browser }) => {
  test.skip(!ctx.termRun, "no finished Bahar term run");
  const phoneCtx = await browser.newContext(PHONE);
  const phone = await phoneCtx.newPage();
  await login(phone);
  await phone.goto(`/timetable?run=${ctx.termRun!.id}&week=3`);
  await phone.getByTestId("calendar-mobile").waitFor({ timeout: 60_000 });
  await phone.waitForTimeout(1500);
  const before = await phone.locator('[data-testid="calendar-mobile"] [data-testid="calendar-event"]').count();
  expect(before).toBeGreaterThan(1);
  await phone.getByTestId("open-filters").click();
  const sheet = phone.getByTestId("filters-sheet");
  await expect(sheet).toBeVisible();
  await phone.waitForTimeout(600);
  await assertTouch(phone);
  const vp = phone.viewportSize()!;
  const box = (await sheet.boundingBox())!;
  expect(box.width).toBeGreaterThanOrEqual(vp.width - 1); // full width (M-04)
  expect(box.y + box.height).toBeGreaterThanOrEqual(vp.height - 1); // anchored to the bottom
  const search = phone.getByTestId("calendar-search");
  expect(await search.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16);
  // M-02 inside the sheet, every scroll step of its body
  const bad: unknown[] = [];
  const body = phone.locator('[data-testid="filters-sheet"] [data-testid="calendar-sidebar"]');
  const total = await body.evaluate((el) => el.scrollHeight);
  for (let y = 0; y <= total; y += 300) {
    await body.evaluate((el, y) => (el.scrollTop = y), y);
    await phone.waitForTimeout(120);
    bad.push(...(await phone.evaluate(M02)));
  }
  expect(bad.filter((b, i, a) => a.findIndex((x) => JSON.stringify(x) === JSON.stringify(b)) === i)).toEqual([]);
  // the primary action: sticky in the bottom 40 %
  const apply = (await phone.getByTestId("filters-apply").boundingBox())!;
  expect(apply.y).toBeGreaterThanOrEqual(0.6 * vp.height - 1);
  expect(apply.height).toBeGreaterThanOrEqual(44);
  // the search filters the day list: one course of the agenda
  const first = (await phone.locator('[data-testid="calendar-mobile"] [data-testid="calendar-event"] span.font-semibold').first().innerText()).trim();
  const code = (first.match(/^[A-ZÇĞİÖŞÜ]{2,5} \d{3}/) ?? [""])[0];
  test.skip(!code, `no course code in the first chip's name (${first})`);
  await search.fill(code);
  await expect(phone.getByTestId("filters-apply")).not.toHaveText(new RegExp(`^${before} `));
  await search.press("Enter");
  await expect(sheet).toBeHidden();
  const after = await phone.locator('[data-testid="calendar-mobile"] [data-testid="calendar-event"]').count();
  expect(after).toBeGreaterThan(0);
  expect(after).toBeLessThan(before);
  await expect.poll(() => phone.evaluate(() => document.activeElement?.getAttribute("data-testid"))).toBe("calendar-event");
  await expect(phone.getByTestId("filters-count")).toBeVisible();
  // no match: the day list says why
  await phone.getByTestId("open-filters").click();
  await phone.getByTestId("calendar-search").fill("zzzz yok");
  await phone.getByTestId("filters-apply").click();
  await expect(phone.getByTestId("calendar-mobile")).toContainText("Bu filtrelerle gösterilecek ders yok.");
  await phoneCtx.close();
});

test("R1-S-26 · at 1440 and 1024 the overlay sidebar leaves its toggle uncovered and Esc closes it", async ({ browser }) => {
  test.skip(!ctx.termRun, "no finished Bahar term run");
  for (const width of [1440, 1024]) {
    const c = await browser.newContext({ viewport: { width, height: 900 }, locale: "tr-TR" });
    const page = await c.newPage();
    await login(page);
    await page.goto(`/timetable?run=${ctx.termRun!.id}&week=3`);
    await page.getByTestId("calendar-toolbar").waitFor({ timeout: 60_000 });
    const toggle = page.getByTestId("sidebar-toggle");
    if (await page.getByTestId("calendar-sidebar").isVisible()) await toggle.click();
    await expect(page.getByTestId("calendar-sidebar")).toBeHidden();
    await toggle.click();
    await expect(page.getByTestId("calendar-sidebar")).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    // the toggle is not covered: a click at its centre reaches it, and it closes the sidebar
    const free = await toggle.evaluate((el) => { const r = el.getBoundingClientRect(); const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return t === el || el.contains(t); });
    expect(free, `${width}: toggle uncovered`).toBe(true);
    await toggle.click();
    await expect(page.getByTestId("calendar-sidebar")).toBeHidden();
    // Esc closes it (also with focus in its search) and focus returns to the toggle
    await toggle.click();
    await page.getByTestId("calendar-search").focus();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("calendar-sidebar")).toBeHidden();
    await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute("data-testid"))).toBe("sidebar-toggle");
    await c.close();
  }
});

test("R2-S-08 · /classes view tabs and the inspector's Yerleşimi açıkla are 44 px on the phone; R3-S-06 the solver save is sticky", async ({ browser }) => {
  test.skip(!ctx.termRun, "no finished Bahar term run");
  const phoneCtx = await browser.newContext(PHONE);
  const phone = await phoneCtx.newPage();
  await login(phone);
  await phone.goto(`/classes?run=${ctx.termRun!.id}`);
  await phone.getByTestId("view-tabs").waitFor({ timeout: 60_000 });
  await phone.waitForTimeout(1500);
  await assertTouch(phone);
  const tabs = await phone.locator('[data-testid="view-tabs"] [role="tab"]').evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
  expect(tabs.filter((h) => h < 44)).toEqual([]);
  expect(await m02All(phone)).toEqual([]);
  // the timetable inspector's "Yerleşimi açıkla"
  await phone.goto(`/timetable?run=${ctx.termRun!.id}&week=3`);
  await phone.getByTestId("calendar-mobile").waitFor({ timeout: 60_000 });
  await phone.locator('[data-testid="calendar-mobile"] [data-testid="calendar-event"]').first().click();
  const why = phone.getByTestId("explain-placement");
  await expect(why).toBeVisible({ timeout: 20_000 });
  expect((await why.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  // the solver save: in the bottom 40 % and free at every scroll (M-05)
  await phone.goto("/settings?tab=solver");
  const save = phone.getByTestId("save-solver");
  await save.waitFor({ timeout: 60_000 });
  const vh = phone.viewportSize()!.height;
  for (const y of [0, 400, 1e6]) {
    await phone.evaluate((y) => window.scrollTo(0, y), y);
    await phone.waitForTimeout(150);
    const b = (await save.boundingBox())!;
    const free = await save.evaluate((el) => { const r = el.getBoundingClientRect(); const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return t === el || el.contains(t); });
    expect(b.y, `scroll ${y}`).toBeGreaterThanOrEqual(0.6 * vh - 1);
    expect(b.y + b.height).toBeLessThanOrEqual(vh);
    expect(b.height).toBeGreaterThanOrEqual(44);
    expect(free, `scroll ${y}`).toBe(true);
  }
  await phoneCtx.close();
});
