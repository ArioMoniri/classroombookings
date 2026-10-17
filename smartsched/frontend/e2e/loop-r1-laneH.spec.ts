/**
 * Flow loop round 1, lane H (docs/ROADMAP.md "Flow loop tickets — round 1", rounds/round-1-tickets.json) against the
 * REAL backend, gated E2E_REAL=1, with NO Anthropic key on the stack. The ticket checks a builder can run in a browser:
 *
 * - T-R1-46 Studio › Kurallar without a key: the Turkish nursing chip opens the "Belirli saatten sonra ders olmasın"
 *   template with both "Hemşirelik" programmes ticked, "1. sınıf" and 17:30; the reach is > 0 and the related
 *   (master's) programmes are offered; a saved template rule keeps the programme's capital letters and says "Şablon".
 * - T-R1-47 Studio › Kapsam: switching the term never shows "0 derslikte"; Güz (14 weeks, 2 dated rows) reads
 *   "14 hafta" with the note about the dated rows; the reach badge prints "%…", never "… %".
 * - T-R1-48 run report: a cancelled run reads "İptal edildi" (by whom, when) and none of "karşılandı" / "İhlal yok";
 *   the "Sorun" KPI is the same number at 1440 and 390; main.innerText has no "0 1 2 3 4 5 6 7 8 9" odometer digits;
 *   the publish sheet names a single week as "3. hafta".
 * - T-R1-49 timetable: from the top of /timetable the second Tab reaches "Izgaraya geç" and Enter lands on the grid; the move
 *   dialog offers "Başlangıç haftası"; the sidebar's "Yerleşmeyenler (n)" equals the run's API unplaced count; the
 *   inspector's history says "Çalıştırma #".
 * - T-R1-50 program wizard: with "Yalnızca oluştur" the button reads "Oluştur"; the undo check is never called on the
 *   generate step (no 409 in the console).
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19250 NEXT_PUBLIC_API_URL=http://127.0.0.1:19250 PW_PORT=19251 \
 *     npx playwright test e2e/loop-r1-laneH.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";
import { pinLanguage } from "./language";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 3, locale: "tr-TR", timezoneId: "Europe/Istanbul" };

test.describe.configure({ mode: "serial", timeout: 300_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

interface Run {
  id: number;
  term_id: number;
  term_code: string;
  kind: string;
  horizon: string;
  status: string;
  is_active: boolean;
  horizon_params: { weeks: number[] };
  stats: Record<string, unknown>;
}
const ctx = {} as { api: APIRequestContext; admin: string; bahar: { id: number; code: string }; guz: { id: number; code: string }; hasGuz: boolean; weekRun: Run | null; termRun: Run | null; cancelled: number | null };

async function call<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<{ status: number; body: T }> {
  const res = await ctx.api.fetch(`${API}${path}`, { method, data: body, headers: { Authorization: `Bearer ${ctx.admin}` } });
  const text = await res.text();
  return { status: res.status(), body: (text ? JSON.parse(text) : undefined) as T };
}
async function api<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
  const r = await call<T>(method, path, body);
  if (r.status >= 400) throw new Error(`${method} ${path} → ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}
async function noKey(): Promise<boolean> {
  const s = await api<{ anthropic_api_key_masked?: string | null }>("GET", "/settings");
  return !s.anthropic_api_key_masked;
}
function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`console: ${m.text()}`);
  });
  return errors;
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  const res = await ctx.api.post(`${API}/auth/login`, { data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD } });
  ctx.admin = ((await res.json()) as { access_token: string }).access_token;
  const terms = await api<{ id: number; code: string }[]>("GET", "/terms");
  ctx.bahar = terms.find((t) => t.code === "2026-BAHAR") ?? terms[0];
  ctx.guz = terms.find((t) => t.code === "2026-GUZ") ?? terms[0];
  ctx.hasGuz = terms.some((t) => t.code === "2026-GUZ");
  const runs = await api<Run[]>("GET", `/runs?term_id=${ctx.bahar.id}`);
  const finished = runs.filter((r) => ["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL"].includes(r.status) && r.kind === "COURSE");
  ctx.weekRun = finished.filter((r) => r.horizon === "WEEK").sort((a, b) => b.id - a.id)[0] ?? null;
  ctx.termRun = finished.filter((r) => r.horizon === "TERM").sort((a, b) => Number(b.is_active) - Number(a.is_active) || b.id - a.id)[0] ?? null;
  ctx.cancelled = null;
});

test.afterAll(async () => {
  await ctx.api.dispose();
});

test("T-R1-46 · the nursing chip opens the pre-filled template without an AI key; the saved rule keeps its capitals and says Şablon", async ({ page }) => {
  test.skip(!(await noKey()), "the stack has an Anthropic key: the chip then fills the composer (F-09 S03 AI path)");
  const errors = trackErrors(page);
  await login(page);
  await page.goto("/generate");
  await page.getByTestId("scope-step").waitFor();
  await page.locator("#scope-term").selectOption(String(ctx.bahar.id));
  await page.getByTestId("rail-step-rules").click();
  await page.getByTestId("rules-step").waitFor();
  await expect(page.getByTestId("no-key")).toContainText("YZ");
  const chip = page.getByTestId("example-chip").filter({ hasText: "Hemşirelik" });
  await expect(chip).toHaveAttribute("data-opens", "template");
  await chip.click();
  await page.getByTestId("rule-builder").waitFor();
  await expect(page.locator('[data-testid="template-gallery"] h2').first()).toHaveText("Belirli saatten sonra ders olmasın");
  await expect(page.getByTestId("builder-programmes")).toContainText("Hemşirelik, Hemşirelik (İngilizce) · 1. sınıf");
  await expect(page.getByTestId("applies-year")).toHaveValue("1");
  const ticked = await page.locator('[data-testid="applies-programmes"] input:checked').evaluateAll((els) => els.map((e) => e.parentElement?.textContent?.trim()));
  expect(ticked).toEqual(["Hemşirelik", "Hemşirelik (İngilizce)"]);
  await expect(page.locator('[data-testid="rule-builder"] p.text-base')).toContainText("17:30");
  // one rule reaches both programmes' year-1 classes (23 on the real Bahar list), with the master's programmes offered
  const reach = page.locator('[data-testid="rule-builder"] [data-testid="affected-count"]');
  await expect(reach).toHaveText(/^[1-9]\d* derse uygulanıyor$/);
  await expect(page.getByTestId("related-programmes")).toContainText("Yüksek Lisans");
  // the percentage never reads "x %" (T-R1-47)
  await expect(page.locator('[data-testid="rule-builder"] [data-testid="affected-count"] + span, [data-testid="rule-builder"] .rounded-full').first()).not.toContainText(/\d %\)/);
  await page.getByTestId("builder-add").click();
  await expect(page.locator("[data-sonner-toast]").first()).toContainText("Kural eklendi");
  const card = page.locator('[data-testid="rules-step"] article').filter({ hasText: "17:30" }).first();
  await expect(card).toContainText("Hemşirelik (İngilizce)");
  await expect(card).toContainText("Şablon");
  await expect(card).not.toContainText("hemşirelik (ingilizce)");
  // tidy up: delete the rule we added
  const rules = await api<{ id: number; kind: string; params: Record<string, unknown> }[]>("GET", `/constraints?term_id=${ctx.bahar.id}`);
  for (const r of rules.filter((x) => x.kind === "day_window" && JSON.stringify(x.params).includes("hemşirelik"))) await api("DELETE", `/constraints/${r.id}`);
  expect(errors.filter((e) => !/favicon|ResizeObserver/.test(e))).toEqual([]);
});

test("T-R1-47 · switching the term never shows 0 derslikte; Güz reads 14 hafta with its dated rows", async ({ page }) => {
  // the Güz term comes with `stack.sh up` and with the e2e gate seed (e2e-backend-entry.sh imports the Güz grid +
  // planning list); the skip stays as the fallback for a Bahar-only backend
  test.skip(!ctx.hasGuz, "no 2026-GUZ term on this backend (stack.sh up and e2e-backend-entry.sh import it)");
  await login(page);
  await page.goto("/generate");
  await page.getByTestId("scope-step").waitFor();
  const sel = page.locator("#scope-term");
  await sel.selectOption(String(ctx.bahar.id));
  await expect(page.getByTestId("scope-sentence")).toContainText("derslikte");
  await sel.selectOption(String(ctx.guz.id));
  const seen: string[] = [];
  const t0 = Date.now();
  while (Date.now() - t0 < 2000) {
    seen.push(await page.getByTestId("scope-sentence").innerText());
    await page.waitForTimeout(50);
  }
  expect(seen.filter((x) => /\b0 derslikte/.test(x))).toEqual([]);
  await page.getByTestId("horizon-TERM").click();
  await expect(page.getByTestId("scope-sentence")).toContainText("14 hafta boyunca");
  await expect(page.getByTestId("scope-term-weeks")).toContainText("Dönem 14 hafta; bunların 2 tanesinin tarihi girilmiş.");
  await sel.selectOption(String(ctx.bahar.id));
});

test("T-R1-48 · a cancelled run reads İptal edildi and claims nothing", async ({ page }) => {
  const errors = trackErrors(page);
  // a run that is cancelled right away (the planner's "İptal" on the run card)
  const started = await call<{ run_id: number }>("POST", "/runs", { term_id: ctx.bahar.id, kind: "COURSE", horizon: "WEEK", horizon_params: { weeks: [3] }, params: { time_limit_s: 60 } });
  expect(started.status, JSON.stringify(started.body)).toBe(202);
  const id = started.body.run_id;
  const cancel = await call("POST", `/runs/${id}/cancel`);
  expect([200, 409]).toContain(cancel.status);
  const run = await api<Run & { error?: string | null }>("GET", `/runs/${id}`);
  test.skip(run.status !== "CANCELLED", `run ${id} finished before the cancel (${run.status})`);
  ctx.cancelled = id;
  await login(page);
  await page.goto(`/runs/${id}`);
  const verdict = page.getByTestId("run-verdict");
  await expect(verdict).toHaveAttribute("data-state", "cancelled");
  await expect(verdict).toContainText("İptal edildi");
  // who stopped it, named as the rest of the UI names people (R2-M-17: display name, else username, else e-mail)
  const me = await api<{ full_name?: string | null; username?: string | null; email: string }>("GET", "/auth/me");
  await expect(page.getByTestId("run-cancelled-by")).toContainText(me.full_name?.trim() || me.username?.trim() || ADMIN_EMAIL);
  const hero = await page.getByTestId("run-hero").innerText();
  expect(hero).not.toMatch(/karşılandı|İhlal yok|hiçbir kural bozulmadı/);
  const main = await page.locator("main").innerText();
  expect(main).not.toMatch(/İhlal yok|Bütün tercihler karşılandı/);
  await expect(page.getByTestId("run-publish")).toHaveCount(0);
  expect(errors.filter((e) => !/favicon|ResizeObserver/.test(e))).toEqual([]);
});

test("T-R1-48 · the Sorun KPI is one server-side number at 1440 and 390; no odometer digits; one week reads 3. hafta", async ({ page, browser }) => {
  test.skip(!ctx.weekRun, "no finished Bahar week run on this stack (stack.sh runs)");
  const r = ctx.weekRun!;
  await login(page);
  await page.goto(`/runs/${r.id}`);
  const kpi = page.locator('[data-testid^="kpi-Sorun"]');
  await expect(kpi).toBeVisible();
  // the number settles once the summary is in
  await page.waitForTimeout(1500);
  const desktop = (await kpi.innerText()).trim();
  expect(desktop).toMatch(/^\d+$/);
  const main = await page.locator("main").innerText();
  expect(main).not.toContain("0 1 2 3 4 5 6 7 8 9");
  expect(main.replace(/\s+/g, "")).not.toContain("0123456789");
  // the publish confirm: a one-week run says "3. hafta", never "3. haftalar"
  await page.getByTestId("run-publish").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(`${r.horizon_params.weeks[0]}. hafta`);
  await expect(dialog).not.toContainText(`${r.horizon_params.weeks[0]}. haftalar`);
  await page.keyboard.press("Escape");

  const phoneCtx = await browser.newContext(PHONE);
  const phone = await phoneCtx.newPage();
  await login(phone);
  await phone.goto(`/runs/${r.id}`);
  const kpiPhone = phone.locator('[data-testid^="kpi-Sorun"]');
  await expect(kpiPhone).toBeVisible();
  await phone.waitForTimeout(1500);
  expect((await kpiPhone.innerText()).trim()).toBe(desktop);
  await phoneCtx.close();
});

test("T-R1-49 · skip link to the grid, Başlangıç haftası in the move dialog, one unplaced count, Çalıştırma # in the history", async ({ page }) => {
  test.skip(!ctx.termRun, "no finished Bahar term run on this stack (stack.sh runs)");
  const r = ctx.termRun!; // its classes span the term, so the move dialog offers the week scopes
  const week = 3;
  await login(page);
  await page.goto(`/timetable?run=${r.id}&week=${week}`);
  await page.getByTestId("time-grid").waitFor();
  // two Tabs from the top: the shell's "İçeriğe atla", then the calendar's own skip link, which T-R2-28 (lane E) portals
  // right after it as the second Tab stop (round 2 sweeper 3: the old path pressed Enter on the shell link first and
  // then tabbed up to 4 times, which no longer meets the link)
  await page.keyboard.press("Tab");
  await expect.poll(() => page.evaluate(() => document.activeElement?.textContent?.trim())).toBe("İçeriğe atla");
  await page.keyboard.press("Tab");
  await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute("data-testid"))).toBe("skip-to-grid");
  await expect(page.getByTestId("skip-to-grid")).toHaveText("Izgaraya geç");
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute("data-testid"))).toBe("time-grid");
  // the sidebar's unplaced count is the run's API number
  const unplacedApi = Number(((r.stats.truth as { unplaced?: number } | undefined)?.unplaced ?? r.stats.unplaced ?? Number(r.stats.events_total) - Number(r.stats.placed)) || 0);
  const sidebar = page.getByTestId("calendar-sidebar");
  if (await sidebar.isVisible()) {
    await expect(sidebar).toContainText(`Yerleşmeyenler (${unplacedApi})`);
    // the sidebar names the run's term, whatever the shell's working term is (R1-S-26)
    const terms = await api<{ id: number; name: string }[]>("GET", "/terms");
    await expect(sidebar.getByTestId("sidebar-term")).toHaveText(terms.find((t) => t.id === r.term_id)?.name ?? "");
  }
  // open a class, then its move dialog: the scope "from" needs a start-week select
  const chip = page.getByTestId("calendar-event").first();
  await chip.click();
  await expect(page.getByTestId("class-inspector")).toBeVisible();
  const history = page.getByTestId("class-inspector");
  await expect(history).not.toContainText(/Run #\d/);
  await page.getByTestId("inspector-move").click();
  const dialog = page.getByTestId("move-dialog");
  await expect(dialog).toBeVisible();
  const from = dialog.getByTestId("move-scope-from");
  if (await from.count()) {
    await from.locator("input").check();
    await expect(dialog.getByTestId("move-from-week")).toBeVisible();
    await expect(dialog).toContainText("Başlangıç haftası");
    // the day / start / start-week selects are design-system selects (16 px and 44 px on phones: the phone pass measures M-03)
    await expect(dialog.getByTestId("move-day")).toBeVisible();
  }
  await page.keyboard.press("Escape");
});

test("T-R1-50 · Yalnızca oluştur reads Oluştur, and no undo check (409) fires on the generate step", async ({ page }) => {
  const errors = trackErrors(page);
  const stamp = Date.now().toString(36).slice(-4).toUpperCase();
  // a course-code prefix is 2–4 capital letters
  const prefix = `L${String.fromCharCode(65 + (Date.now() % 26))}${String.fromCharCode(65 + (Math.floor(Date.now() / 26) % 26))}`;
  const course = (n: number, name: string) => ({
    key: `c${n}`,
    code: `${prefix} 10${n}`,
    name,
    t: 2,
    u: 0,
    l: 0,
    credits: "2",
    ects: 4,
    year: 1,
    mode: "Yüz yüze",
    sections: [{ key: `s${n}`, label: "1", enrolment: 20 + n, instructors: [{ name: n === 3 ? "Lale Hoca" : "Hasan Hoca" }] }],
    pattern: { theoryBlocks: [2], weeklyHours: null, days: [n], start: "09:20", weeks: "1-14" },
    room: { capacity: null, tags: [], building: "", preferred: "" },
  });
  const payload = {
    program: { facultyName: "Lane H Enstitüsü", name: `Lane H Test Programı ${stamp}`, level: "masterThesis", evening: false, prefix, years: 1 },
    courses: [course(1, "Deneme Bir"), course(2, "Deneme İki"), course(3, "Deneme Üç")],
    cohorts: [{ key: "y1", label: "LH 1. sınıf", year: 1, compulsory: ["c1", "c2", "c3"] }],
    rules: { window: { enabled: false, earliest: 1, latest: 11, hard: false }, sameRoom: true },
  };
  const draft = await api<{ id: number }>("POST", "/program-drafts", { term_id: ctx.guz.id, payload });
  await login(page);
  await page.goto(`/programs/new/${draft.id}?step=generate`);
  await page.getByTestId("generate-open").waitFor();
  await page.getByText("Yalnızca oluştur", { exact: false }).first().click();
  await expect(page.getByTestId("generate-open")).toHaveText("Oluştur");
  await expect(page.getByTestId("generate-open")).not.toHaveText(/çöz/);
  await page.waitForTimeout(1000);
  expect(errors.filter((e) => /409|undo/.test(e))).toEqual([]);
  // tidy: delete the draft (never committed)
  await call("DELETE", `/program-drafts/${draft.id}`);
});
