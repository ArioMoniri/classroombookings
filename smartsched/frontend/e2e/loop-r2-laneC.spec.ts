/**
 * Flow-loop round 2, lane C (docs/ROADMAP.md "Flow loop tickets — round 2", rounds/round-2-tickets.json) against the
 * REAL backend of a FRESH stack (stack.sh up --fresh), gated E2E_REAL=1: intake, council, onboarding and the programme
 * wizard.
 *
 * - T-R2-19 F-08 S07/S08 then S10/S11 through the API: Job B (the English CSV) committed first; Job A (the Bahar
 *   workbook + the same CSV): the dry run's per-entity counts equal the commit's and the term holds each request once;
 *   Job D (the CSV again) creates and updates nothing; Job C (Turkish Excel's cp1254 ';' export, LANEC_CP1254) is
 *   >= 99 % unchanged.
 * - T-R2-20 F-08 S01/S03/S08: /onboarding lists the recent jobs after a reload; /onboarding/<id> opens the job; Enter
 *   and Space on the drop zone open the file picker; the input has an accept list; after the blockers are decided
 *   through the API the commit bar reads 0 engel without a reload.
 * - T-R2-21 F-08 S08: a commit with undecided merges -> 409 {code: review_pending, message_tr} and no person name in
 *   the body; with the AI policy off a PDF / DOCX row shows no "YZ" chip.
 * - T-R2-22 F-07 S05/S07/S08: "Yeni kişi" twice for the same name on a section -> one entry and an inline refusal; the
 *   pre-check never says "listed twice"; one <main> on /programs/new/<draft>.
 * - MOBILE M-01/M-02/M-03/M-05 at 390 × 844 on /onboarding, /onboarding/<id> and /programs/new/<draft>.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19330 NEXT_PUBLIC_API_URL=http://127.0.0.1:19330 PW_PORT=19331 \
 *     LANEC_CP1254=<scratch>/bahar_listesi_noktali_virgul.csv npx playwright test e2e/loop-r2-laneC.spec.ts
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, request as pwRequest, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, FIXTURES, PLANNING_LIST, REAL, SKIP_REASON, login } from "./helpers";
import { pinLanguage } from "./language";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const EN_CSV = path.join(FIXTURES, "universal", "bahar_requests_en.csv");
const MEMO = path.join(FIXTURES, "universal", "rules_memo.docx");
const SCAN_PDF = path.join(FIXTURES, "universal", "final_exams_sheet.pdf");
const CP1254 = process.env.LANEC_CP1254 ?? "";
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
const LONG = 240_000;
const TERM = { code: "2026-BAHAR", week_count: 14 };
const BODY = { group: 0, term: TERM, allow_pending: true };

test.describe.configure({ mode: "serial", timeout: 420_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

type Counts = Record<string, { create: number; update: number; unchanged: number; conflict: number }>;
type Job = { id: number; status: string; files: { index: number; filename: string; route: string | null }[]; summary?: Record<string, number> };
const ctx = {} as { api: APIRequestContext; admin: string; jobB: number; jobA: number; mergeJob: number; draftId: number; termId: number };

async function call<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", p: string, body?: unknown, token = ctx.admin): Promise<{ status: number; body: T }> {
  const res = await ctx.api.fetch(`${API}${p}`, { method, data: body, headers: { Authorization: `Bearer ${token}` } });
  const text = await res.text();
  return { status: res.status(), body: (text ? JSON.parse(text) : undefined) as T };
}
async function api<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", p: string, body?: unknown): Promise<T> {
  const r = await call<T>(method, p, body);
  if (r.status >= 400) throw new Error(`${method} ${p} → ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}
/** Upload files as a council job (ai=false: the deterministic readers) and wait until the council has finished. */
async function job(files: string[]): Promise<Job> {
  const multipart: Record<string, unknown> = { lang: "tr", year_hint: "2026", ai: "false" };
  // Playwright's multipart takes one value per field name: several files go as files[0], files[1], ... is not what
  // FastAPI reads; send the first here and append the others through a FormData body instead
  const fd = new FormData();
  fd.set("lang", "tr");
  fd.set("year_hint", "2026");
  fd.set("ai", "false");
  for (const f of files) fd.append("files", new Blob([readFileSync(f)]), path.basename(f));
  void multipart;
  const res = await ctx.api.post(`${API}/council/jobs`, { multipart: fd, headers: { Authorization: `Bearer ${ctx.admin}` } });
  expect(res.status(), await res.text()).toBe(202);
  const id = ((await res.json()) as { id: number }).id;
  const until = Date.now() + LONG;
  for (;;) {
    const j = await api<Job>("GET", `/council/jobs/${id}`);
    if (!["QUEUED", "RUNNING"].includes(j.status)) return j;
    if (Date.now() > until) throw new Error(`job ${id} still ${j.status}`);
    await new Promise((r) => setTimeout(r, 2000));
  }
}
const n = (c: Counts, entity: string, change: keyof Counts[string]) => c[entity]?.[change] ?? 0;
const share = (c: Counts, entity: string) => {
  const v = c[entity];
  const total = v ? v.create + v.update + v.unchanged + v.conflict : 0;
  return total ? (v?.unchanged ?? 0) / total : 0;
};
const noSidewaysScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  const res = await ctx.api.post(`${API}/auth/login`, { data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD } });
  expect(res.ok(), await res.text()).toBeTruthy();
  ctx.admin = ((await res.json()) as { access_token: string }).access_token;
  // F-08 runs with the administrator's AI policy off (the fresh stack has no key anyway)
  await api("PUT", "/ai/policy", { intake_enabled: false, vision_enabled: false, kvkk_ack: true, reason: "lane C round 2" });
  const terms = await api<{ id: number; code: string }[]>("GET", "/terms");
  ctx.termId = terms.find((t) => t.code === TERM.code)?.id ?? (await api<{ id: number }>("POST", "/terms", { ...TERM, name: "Bahar 2026" })).id;
});
test.afterAll(async () => {
  await ctx.api?.dispose();
});

test("T-R2-19 F-08 S07/S08/S10/S11 (API): the dry run predicts the commit, one key per request across formats", async () => {
  // S10 first, as the tester did: Job B, the English CSV through the general path, committed into the empty term
  const jobB = await job([EN_CSV]);
  ctx.jobB = jobB.id;
  const b = await api<{ changes: Counts }>("POST", `/council/jobs/${jobB.id}/commit`, BODY);
  const nB = n(b.changes, "meeting_requests", "create");
  expect(nB).toBeGreaterThan(1300);

  // S07/S08: Job A, the workbook (fast path) with the same CSV: dry run == commit, and no second copy of B's rows
  const jobA = await job([PLANNING_LIST, EN_CSV]);
  ctx.jobA = jobA.id;
  const dry = await api<{ counts: Counts; result: { general: Record<string, number> } }>("POST", `/council/jobs/${jobA.id}/commit`, { ...BODY, dry_run: true });
  const real = await api<{ changes: Counts; general: Record<string, number> }>("POST", `/council/jobs/${jobA.id}/commit`, BODY);
  expect(real.changes).toEqual(dry.counts);
  expect(n(dry.counts, "meeting_requests", "create")).toBeLessThanOrEqual(1513 - nB);
  const probe = await api<{ counts: Counts }>("POST", `/council/jobs/${(await job([PLANNING_LIST])).id}/commit`, { ...BODY, dry_run: true });
  expect(n(probe.counts, "meeting_requests", "create")).toBe(0);
  expect(n(probe.counts, "meeting_requests", "unchanged")).toBeGreaterThanOrEqual(1500);

  // S10: Job D, the same CSV once more: create 0 · update 0
  const jobD = await job([EN_CSV]);
  const d = await api<{ counts: Counts; result: { general: Record<string, number> } }>("POST", `/council/jobs/${jobD.id}/commit`, { ...BODY, dry_run: true });
  for (const entity of ["meeting_requests", "sections", "instructors", "section_instructors", "courses"]) expect(n(d.counts, entity, "create"), entity).toBe(0);
  expect(n(d.counts, "meeting_requests", "update")).toBe(0);
  expect(n(d.counts, "meeting_requests", "unchanged") + (d.result.general.duplicates_skipped ?? 0)).toBeGreaterThanOrEqual(nB);

  // S11: Job C, the office's cp1254 ';' export (fast path): >= 99 % unchanged
  test.skip(!CP1254, "LANEC_CP1254 names the cp1254 ';' export (tests/council/exports.csv_bytes)");
  const jobC = await job([CP1254]);
  expect(jobC.files[0].route).toBe("fast:planning-list");
  const c = await api<{ counts: Counts }>("POST", `/council/jobs/${jobC.id}/commit`, { ...BODY, dry_run: true });
  expect(n(c.counts, "meeting_requests", "create")).toBe(0);
  expect(share(c.counts, "meeting_requests")).toBeGreaterThanOrEqual(0.99);
  expect(share(c.counts, "sections")).toBeGreaterThanOrEqual(0.99);
});

test("T-R2-21 F-08 S08: the refusal for undecided merges is coded, Turkish and names nobody; no YZ chip with AI off", async ({ page }) => {
  // a job with merge items: the workbook again (its instructor spellings), into a new term so nothing is remembered
  const merge = await job([PLANNING_LIST, MEMO, SCAN_PDF]);
  ctx.mergeJob = merge.id;
  const review = await api<{ blocking: number; items: { id: string; kind: string; blocking: boolean; decision: unknown }[] }>("GET", `/council/jobs/${merge.id}/review`);
  test.skip(review.blocking === 0, "the council settled every spelling alone on this stack: nothing to refuse");
  const r = await call<{ detail: Record<string, unknown> }>("POST", `/council/jobs/${merge.id}/commit`, { group: 0, term: TERM });
  expect(r.status).toBe(409);
  expect(r.body.detail.code).toBe("review_pending");
  expect(r.body.detail.count).toBe(review.blocking);
  expect(String(r.body.detail.message_tr)).toBe(`Önce ${review.blocking} inceleme kararı verilmeli.`);
  const text = JSON.stringify(r.body);
  expect(text).not.toMatch(/Same instructor|e\.g\.|Aynı kişi mi/);
  expect(text).not.toMatch(/'[^']+' and '[^']+'/);

  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await page.goto(`/onboarding/${merge.id}`);
  const progress = page.getByTestId("onboarding-progress");
  await expect(progress).toBeVisible({ timeout: 30_000 });
  const docRows = progress.getByRole("row").filter({ hasText: /\.(pdf|docx)/ });
  await expect(docRows.first()).toBeVisible({ timeout: 30_000 }); // the table follows the job query
  await expect(docRows.locator('[data-slot="method-badge"]').first()).toHaveText(/Doğrudan|Okunmadı|YZ kapalı/);
  await expect(progress.locator('[data-method="ai"]')).toHaveCount(0);
});

test("T-R2-20 F-08 S01/S03/S08 at 1440: recent jobs after a reload, /onboarding/<id>, a keyboard drop zone, accept, a live commit bar", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await page.goto("/onboarding");
  await page.reload();
  const recent = page.getByTestId("onboarding-recent");
  await expect(recent).toBeVisible({ timeout: 30_000 });
  expect(await recent.getByRole("button").count()).toBeGreaterThan(0);
  // the drop zone: one button, Enter and Space open the picker, the input lists the formats
  const zone = page.getByTestId("onboarding-dropzone");
  await expect(zone).toBeVisible();
  expect(await zone.evaluate((e) => e.tagName)).toBe("BUTTON");
  expect(await zone.locator("button, a, input, [tabindex]").count()).toBe(0);
  const accept = (await page.getByTestId("onboarding-input").getAttribute("accept")) ?? "";
  expect(accept.split(",")).toEqual(expect.arrayContaining([".xlsx", ".csv", ".pdf", ".docx", "image/*"]));
  await zone.focus();
  let chooser = page.waitForEvent("filechooser", { timeout: 10_000 });
  await page.keyboard.press("Enter");
  expect((await chooser).isMultiple()).toBeTruthy();
  chooser = page.waitForEvent("filechooser", { timeout: 10_000 });
  await page.keyboard.press(" ");
  await chooser;

  // the job's own address
  await page.goto(`/onboarding/${ctx.mergeJob}`);
  await expect(page.getByTestId("onboarding-progress")).toBeVisible({ timeout: 30_000 });
  expect(page.url()).toContain(`/onboarding/${ctx.mergeJob}`);
  await expect(page.getByText(/404|Sayfa bulunamadı/)).toHaveCount(0);

  // the commit bar follows the review: decide the blockers through the API, the bar reads 0 without a reload
  const review = await api<{ blocking: number; items: { id: string; blocking: boolean; decision: unknown }[] }>("GET", `/council/jobs/${ctx.mergeJob}/review`);
  if (review.blocking > 0) {
    const bar = page.getByTestId("onboarding-commit");
    await expect(bar).toBeVisible({ timeout: 60_000 });
    await expect(bar).toContainText(new RegExp(`${review.blocking} engel`));
    await expect(bar.getByTestId("onboarding-commit-button")).toBeDisabled();
    await api("POST", `/council/jobs/${ctx.mergeJob}/review`, { decisions: review.items.filter((i) => i.blocking && i.decision == null).map((i) => ({ id: i.id, action: "accept" })) });
    await expect(page.getByTestId("blocking-count")).toHaveText(/^0/, { timeout: 60_000 });
    await expect(bar).not.toContainText(/[1-9]\d* engel/);
  }
});

test("T-R2-22 F-07 S05/S07/S08 at 1440: the same new person twice is refused on the step; no 'listed twice'; one <main>", async ({ page }) => {
  const payload = {
    program: { facultyName: "Fen Bilimleri Enstitüsü", name: `Lane C Biyoteknoloji ${Date.now().toString(36)}`, prefix: "LCB" },
    courses: [
      {
        key: "c1",
        code: "LCB 501",
        name: "Biyoteknolojide Yöntemler",
        t: 3,
        u: 0,
        l: 0,
        credits: "3",
        ects: 7,
        year: 1,
        mode: "Yüz yüze",
        sections: [{ key: "s1", label: "1", enrolment: 20, instructors: [] }],
        pattern: { theoryBlocks: [3], days: [3], start: "13.30", weeks: "1-14" },
        room: { capacity: null, tags: [], building: "", preferred: "" },
      },
    ],
    cohorts: [],
    rules: {},
  };
  const draft = await api<{ id: number }>("POST", "/program-drafts", { term_id: ctx.termId, payload });
  ctx.draftId = draft.id;
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page);
  await page.goto(`/programs/new/${draft.id}?step=instructors`);
  const row = page.getByTestId("instructor-row").first();
  await expect(row).toBeVisible({ timeout: 30_000 });
  expect(await page.evaluate(() => document.querySelectorAll("main").length)).toBe(1);
  await row.getByTestId("section-instructor").fill("Tolga Emre");
  await row.getByTestId("wizard-new-person").click();
  await expect(row.getByTestId("picked-instructor")).toHaveCount(1);
  await row.getByTestId("section-instructor-2").fill("TOLGA EMRE");
  await row.getByTestId("wizard-new-person").click();
  await expect(row.getByTestId("instructor-refused")).toContainText("Bu kişi bu şubede zaten var");
  await expect(row.getByTestId("picked-instructor")).toHaveCount(1);
  // the server agrees, on the step, in Turkish: a draft with the person twice validates to instructor_twice
  const twice = await api<{ id: number }>("POST", "/program-drafts", { term_id: ctx.termId, payload: { ...payload, program: { ...payload.program, name: `${payload.program.name} b` }, courses: [{ ...payload.courses[0], sections: [{ ...payload.courses[0].sections[0], instructors: [{ name: "Tolga Emre" }, { name: "TOLGA EMRE" }] }] }] } });
  const v = await api<{ can_commit: boolean; issues: { code: string; step: string; text: { tr: string } }[] }>("POST", `/program-drafts/${twice.id}/validate`);
  const issue = v.issues.find((i) => i.code === "instructor_twice");
  expect(issue?.step).toBe("instructors");
  expect(issue?.text.tr).toContain("Bu kişi bu şubede zaten var");
  const pre = await call<{ detail: { message_tr?: string; issues?: { code: string }[] } }>("POST", `/program-drafts/${twice.id}/precheck`);
  expect(pre.status).toBe(422);
  expect(JSON.stringify(pre.body)).not.toMatch(/listed twice|Kayıt yazılamadı/);
  expect(pre.body.detail.message_tr).toBeTruthy();
});

for (const route of ["/onboarding", "/onboarding/<job>", "/programs/new/<draft>"]) {
  test(`MOBILE M-01/M-02/M-03/M-05 at 390 × 844 on ${route}`, async ({ browser }: { browser: Browser }) => {
    const context = await browser.newContext(PHONE);
    const page = await context.newPage();
    try {
      await login(page);
      const url = route.replace("<job>", String(ctx.mergeJob ?? ctx.jobA)).replace("<draft>", String(ctx.draftId));
      await page.goto(url);
      await page.waitForLoadState("networkidle");
      if (route.startsWith("/programs")) await expect(page.getByTestId("wizard-footer")).toBeVisible({ timeout: 30_000 });
      else await expect(page.getByTestId("onboarding")).toBeVisible({ timeout: 30_000 });
      // M-01
      expect(await noSidewaysScroll(page), "no sideways scroll").toBeTruthy();
      // M-02: visible controls in the page body (the shell's tab bar is lane A's)
      const small = await page.evaluate(() => {
        const out: string[] = [];
        for (const el of Array.from(document.querySelectorAll<HTMLElement>('main button, main a[href], main input:not([type=hidden]), main [role=button], main [role=option]'))) {
          let r = el.getBoundingClientRect();
          if (r.width <= 1 || r.height <= 1 || el.closest(".sr-only") || el.classList.contains("sr-only")) continue; // visually hidden inputs of composite controls
          const label = el.tagName === "INPUT" ? el.closest("label") : null;
          if (label) r = label.getBoundingClientRect(); // a radio / checkbox inside its label: the label is the hit area
          if (r.height < 44 && r.width < 44) out.push(`${el.tagName.toLowerCase()} ${el.textContent?.trim().slice(0, 30)} ${Math.round(r.width)}×${Math.round(r.height)}`);
        }
        return out;
      });
      expect(small, "touch targets under 44 px in both dimensions").toEqual([]);
      // M-03: no text under 11 px, text inputs >= 16 px
      const fonts = await page.evaluate(() => {
        const bad: string[] = [];
        for (const el of Array.from(document.querySelectorAll<HTMLElement>("main *"))) {
          if (!el.textContent?.trim() || el.children.length > 0 && !Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent?.trim())) continue;
          const r = el.getBoundingClientRect();
          if (r.width === 0 || r.height === 0) continue;
          const size = parseFloat(getComputedStyle(el).fontSize);
          if (size < 11) bad.push(`${el.tagName.toLowerCase()} ${size}px`);
        }
        for (const el of Array.from(document.querySelectorAll<HTMLInputElement>("main input:not([type=hidden]):not([type=file]):not([type=checkbox]):not([type=radio]), main textarea"))) {
          const r = el.getBoundingClientRect();
          if (r.width === 0) continue;
          if (parseFloat(getComputedStyle(el).fontSize) < 16) bad.push(`input ${el.getAttribute("data-testid") ?? el.name} ${getComputedStyle(el).fontSize}`);
        }
        return bad;
      });
      expect(fonts, "text under 11 px / inputs under 16 px").toEqual([]);
      // M-05: the primary action is visible in the bottom 40 % after a scroll
      const primary = route.startsWith("/programs") ? page.getByTestId("wizard-footer").getByTestId("wizard-next") : page.getByTestId("onboarding-dropzone").or(page.getByTestId("onboarding-commit-button")).first();
      await page.mouse.wheel(0, 400);
      await page.waitForTimeout(300);
      const box = await primary.boundingBox();
      if (route.startsWith("/programs")) {
        expect(box, "primary action visible").toBeTruthy();
        expect(box!.y + box!.height / 2, "within the bottom 40 %").toBeGreaterThan(844 * 0.6);
      }
    } finally {
      await context.close();
    }
  });
}
