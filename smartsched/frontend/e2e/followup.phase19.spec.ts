/**
 * Phase 19 UI follow-up against the REAL backend (no mocks), gated E2E_REAL=1 (the file name ends in
 * `phase19.spec.ts`, so the config's testMatch picks it up):
 *   1. program wizard on server drafts: Taslaklarım, autosave + reload resume, per-step validation (TR texts
 *      from the server), paste preview with the code fix, cohorts from years, rooms fit, pre-check, commit
 *      "Yalnızca oluştur", the result with "Bu program için geçmiş veri yok", and the 30-day undo
 *   2. joint teaching on the real Bahar term: the section search finds MBG 014, the joint total drives the room
 *   3. moderation: person priority with its `priority.source` badge, the server "Yayından beri değişenler" list,
 *      re-solve preview with the baseline switcher and the chain, publish with "Akademisyenlere bildir"
 *   4. Taleplerim on /moderation/me for a linked and an unlinked teacher (nav entry → /moderation/me)
 *   5. learned suggestions: accept → Geri al (restore), dismiss → Geçmiş → Geri al, persistent accept with confirm
 *   6. phone 390 × 844: no sideways scroll, the compact stepper + floating footer, bottom sheets
 *
 * Backend: the real Bahar 2026 + Güz 2026 planning lists, the Bahar weekly grid, room_master.csv, the seeded
 * admin, a Bahar week-3 run and `learning-refresh`; the spec creates an empty 2027-BAHAR term itself. Run:
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:18998 NEXT_PUBLIC_API_URL=http://127.0.0.1:18998 PW_PORT=18999 \
 *     npx playwright test e2e/followup.phase19.spec.ts
 */
import { randomInt } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import { REAL, SKIP_REASON, TERM_CODE, login } from "./helpers";

test.skip(!REAL, SKIP_REASON);
test.describe.configure({ mode: "serial" });

type Term = { id: number; code: string };
type Run = { id: number; term_id: number; kind: string; horizon: string; status: string; is_active?: boolean };

async function call<T>(page: Page, method: string, path: string, body?: unknown): Promise<{ status: number; body: T }> {
  return page.evaluate(
    async ({ method, url, body }) => {
      const r = await fetch(url, { method, headers: { Accept: "application/json", "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
      return { status: r.status, body: (await r.json().catch(() => null)) as never };
    },
    { method, url: `/api/v1${path}`, body },
  );
}

const EMPTY_TERM = "2027-BAHAR";
/** a programme name is unique across terms, even after an undo archived it (backend ask), so names carry a run tag */
const RUN = Date.now().toString(36).slice(-4);
const PROGRAM_NAME = `Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans (E2E ${RUN})`;
/** The two new people, initials only (KVKK), fresh per run: the undo at the end archives them, and an archived
 * namesake is a different wizard path ("Bu kişiyi kullan", followups-ui step 7). Three initials (a name word is
 * letters only; four or more initials ending in a dot read as a note). */
const initials = () => Array.from({ length: 3 }, () => `${String.fromCharCode(65 + randomInt(26))}.`).join(" ");
const PERSON_1 = initials();
let PERSON_2 = initials();
while (PERSON_2 === PERSON_1) PERSON_2 = initials();
async function emptyTerm(page: Page): Promise<Term> {
  const terms = (await call<Term[]>(page, "GET", "/terms")).body;
  const hit = terms.find((t) => t.code === EMPTY_TERM);
  if (hit) return hit;
  const res = await call<Term>(page, "POST", "/terms", { code: EMPTY_TERM, name: "Bahar 2027", kind: "REGULAR", start_date: "2027-02-01", end_date: "2027-05-14", week_count: 14, is_active: false });
  expect(res.status, JSON.stringify(res.body)).toBe(201);
  return res.body;
}

/** the console reads the published plan: publish the newest finished Bahar week run when none is published */
async function ensurePublished(page: Page): Promise<{ term: Term; run: Run }> {
  const terms = (await call<Term[]>(page, "GET", "/terms")).body;
  const term = terms.find((t) => t.code === TERM_CODE)!;
  const runs = (await call<Run[]>(page, "GET", `/runs?term_id=${term.id}`)).body.filter((r) => r.kind === "COURSE" && r.term_id === term.id);
  const active = runs.find((r) => r.is_active);
  if (active) return { term, run: active };
  const cand = runs.filter((r) => ["OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL"].includes(r.status)).sort((a, b) => b.id - a.id).find((r) => r.horizon === "WEEK") ?? runs[0]!;
  const res = await call(page, "POST", `/runs/${cand.id}/activate`, {});
  expect(res.status, JSON.stringify(res.body)).toBe(200);
  return { term, run: cand };
}

/** MOBILE.md M-01: nothing pokes out sideways unless it sits in its own scroller */
async function noSidewaysScroll(page: Page): Promise<void> {
  const m = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const off: string[] = [];
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      if (!r.width || !r.height || cs.visibility === "hidden" || cs.position === "fixed") continue;
      if (r.right <= vw + 1 && r.left >= -1) continue;
      let p = el.parentElement;
      let contained = false;
      while (p && p !== document.body) {
        if (getComputedStyle(p).overflowX !== "visible") { contained = true; break; }
        p = p.parentElement;
      }
      if (!contained) off.push(`${el.tagName}${(el as HTMLElement).dataset.testid ? `[${(el as HTMLElement).dataset.testid}]` : ""} ${Math.round(r.left)}→${Math.round(r.right)}`);
    }
    return { sw: document.scrollingElement!.scrollWidth, vw, off: off.slice(0, 10) };
  });
  expect(m.off, JSON.stringify(m)).toEqual([]);
  expect(m.sw).toBeLessThanOrEqual(m.vw);
}

/** the real Bahar rows of MBG Tezli YL (bahar_derslik_planlama_listesi_v5.xlsx R182–R198), typed as Excel copies them */
const MBG_TSV = [
  "Kod\tAd\tT\tU\tL\tK\tAKTS\tSınıf",
  "MBG 598\tSeminer\t0\t0\t0\t0\t9\t1",
  "mbg532\tEpigenetik\t3\t0\t0\t3\t9\t1",
  "MBG 534\tProteomiks\t3\t0\t0\t0\t9\t1",
].join("\n");

const wizard = (page: Page) => page.getByTestId("program-wizard");
const saved = async (page: Page) => expect(page.getByTestId("save-status").first()).toHaveAttribute("data-state", "saved", { timeout: 20_000 });
/** an edit and the autosave PATCH it causes (800 ms debounce), then the saved state */
async function edit(page: Page, act: () => Promise<void>): Promise<void> {
  const patch = page.waitForResponse((r) => r.request().method() === "PATCH" && /\/program-drafts\/\d+$/.test(new URL(r.url()).pathname), { timeout: 20_000 });
  await act();
  expect((await patch).status()).toBe(200);
  await saved(page);
}

test("program wizard: a server draft from scratch, resume, validate, paste, cohorts, rooms, pre-check, create, undo", async ({ page }) => {
  test.setTimeout(300_000);
  await login(page);
  const term = await emptyTerm(page);
  await page.goto("/programs/new");
  const landing = page.getByTestId("wizard-landing");
  await expect(landing.getByRole("heading", { name: "Taslaklarım" })).toBeVisible();
  // no demo data anywhere: no example button, and the term list is the real one
  await expect(landing.getByText(/örneğiyle/)).toHaveCount(0);
  await landing.getByTestId("wizard-term").selectOption(String(term.id));
  await landing.getByTestId("wizard-start").click();
  await expect(page).toHaveURL(/\/programs\/new\/\d+\?step=program/);
  const draftId = Number(/\/programs\/new\/(\d+)/.exec(page.url())![1]);
  await expect(wizard(page).getByText(`Taslak · ${EMPTY_TERM} dönemine henüz hiçbir şey yazılmadı`)).toBeVisible();

  // step 1: the server's Turkish validation under the field, then the fix
  await expect(page.getByTestId("rail-program")).toHaveAttribute("data-status", "error");
  await edit(page, () => page.getByTestId("wizard-prefix").fill("MBĞ"));
  await expect(wizard(page).getByText("Ders kodlarında Türkçe harf kullanılmıyor")).toBeVisible();
  await page.getByTestId("wizard-next").click();
  await expect(page.getByTestId("error-summary")).toBeFocused();
  await expect(page.getByTestId("error-summary")).toContainText("Program adı gerekli");
  await page.getByTestId("wizard-prefix").fill("MBG");
  await page.getByTestId("wizard-faculty").fill("Fen Bilimleri Enstitüsü");
  await edit(page, () => page.getByTestId("wizard-program-name").fill(PROGRAM_NAME));
  await expect(page.getByTestId("rail-program")).toHaveAttribute("data-status", "ok");

  // autosave is on the server: a reload resumes the same values on the same step
  await page.reload();
  await expect(page.getByTestId("wizard-program-name")).toHaveValue(PROGRAM_NAME);
  const draft = await call<{ payload: { program: { prefix: string } }; version: number }>(page, "GET", `/program-drafts/${draftId}`);
  expect(draft.body.payload.program.prefix).toBe("MBG");

  // step 2: paste from Excel → server preview with the code fix → insert
  await page.getByTestId("wizard-next").click();
  await expect(page).toHaveURL(/step=courses/);
  await page.getByTestId("wizard-paste").click();
  const paste = page.getByTestId("paste-dialog");
  await paste.getByTestId("paste-text").fill(MBG_TSV);
  await paste.getByTestId("paste-read").click();
  await expect(paste.getByTestId("paste-preview")).toContainText("MBG 532");
  await expect(paste.getByText("Ders kodu 'mbg532' → MBG 532 olarak düzeltildi.")).toBeVisible();
  await expect(paste.getByTestId("paste-count")).toContainText("3 satır eklenecek");
  await edit(page, () => paste.getByTestId("paste-insert").click());
  await expect(page.getByTestId("course-row")).toHaveCount(3);
  // the seminar is 0+0+0: a warning from the server, never a blocker
  await expect(wizard(page).getByText(/MBG 598: T\+U\+L = 0/)).toBeVisible();

  // step 3: sections with the real Bahar enrolments
  await page.getByTestId("rail-sections").click();
  const enrol = page.getByTestId("section-enrolment");
  await expect(enrol).toHaveCount(3);
  await edit(page, async () => {
    for (const [i, n] of [[0, 120], [1, 80], [2, 75]] as const) await enrol.nth(i).fill(String(n));
  });

  // step 4: instructors: two new people (initials only) and one left unassigned (a warning)
  await page.getByTestId("rail-instructors").click();
  const pick = page.getByTestId("section-instructor");
  await pick.first().fill(PERSON_1);
  await page.getByTestId("wizard-new-person").click();
  await expect(page.getByTestId("picked-instructor").first()).toContainText(PERSON_1);
  await edit(page, async () => {
    await pick.first().fill(PERSON_2);
    await page.getByTestId("wizard-new-person").click();
  });
  await expect(wizard(page).getByText(`Yeni kişi: ${PERSON_1}`)).toBeVisible();
  await expect(wizard(page).getByText(/öğretim elemanı atanmadı/)).toHaveCount(1);
  await expect(page.getByTestId("rail-instructors")).toHaveAttribute("data-status", "warning");

  // step 5: cohorts from the years
  await page.getByTestId("rail-cohorts").click();
  await expect(page.getByTestId("cohorts-empty")).toBeVisible();
  await edit(page, () => page.getByTestId("cohorts-build").click());
  await expect(page.getByTestId("cohort")).toHaveCount(1);
  await expect(page.getByTestId("cohort").locator("input").first()).toHaveValue("MBG 1. sınıf");
  await expect(wizard(page).getByText(/kohort için en az \d+ gün gerekir/)).toBeVisible();

  // step 6: weekly patterns (Bahar: Cum 14.20 / Sal 11.00 / Cum 10.10) and the live room fit
  await page.getByTestId("rail-rooms").click();
  const courses = page.getByTestId("pattern-course");
  await expect(courses).toHaveCount(3);
  for (const [i, start, day] of [[0, "14:20", 5], [1, "11:00", 2], [2, "10:10", 5]] as const) {
    const c = courses.nth(i);
    await c.getByTestId("pattern-start").selectOption(start);
    for (const d of [1, 2, 3, 4, 5]) if (d !== day) await c.getByTestId(`day-${d}`).click();
  }
  await expect(courses.nth(0).getByTestId("fit-line")).toContainText(/120 öğrenci · \d+ oda sığar: .*A 207 \(120\)/);
  await edit(page, () => courses.nth(1).getByTestId("pattern-preferred").fill("C 504"));
  await expect(courses.nth(1).getByText(/C 504 \(40\) 80 öğrenciye yetmez/)).toBeVisible();

  // step 7: the program-scoped pre-check (rolled back on the server) with the rooms that fit
  await page.getByTestId("rail-constraints").click();
  await page.getByTestId("precheck-run").click();
  const pre = page.getByTestId("precheck-result");
  await expect(pre).toBeVisible({ timeout: 60_000 });
  await expect(pre).toContainText(/Ön kontrol: \d+ engel, \d+ uyarı/);
  await expect(page.getByTestId("precheck-rooms")).toContainText("A 207 (120)");

  // step 8: the summary, "Bu program için geçmiş veri yok", then "Yalnızca oluştur"
  await page.getByTestId("rail-generate").click();
  await expect(page.getByTestId("generate-summary")).toBeVisible();
  await expect(page.getByTestId("wizard-no-history")).toHaveText("Bu program için geçmiş veri yok");
  await expect(page.getByText("Oluştur ve dönemi çöz")).toBeVisible(); // 2027-BAHAR has no published plan
  await page.getByTestId("generate-mode-only").check();
  await page.getByTestId("generate-open").click();
  const confirm = page.getByTestId("generate-confirm");
  await expect(confirm).toContainText(`${EMPTY_TERM} dönemine 1 program, 3 ders, 3 şube, 1 kohort`);
  await confirm.getByTestId("generate-go").click();
  const done = page.getByTestId("wizard-committed");
  await expect(done).toHaveAttribute("data-status", "committed", { timeout: 60_000 });
  await expect(done).toContainText(`Program oluşturuldu · ${EMPTY_TERM}`);
  await expect(done.getByTestId("undo-panel")).toContainText("tarihine kadar geri alınabilir");
  await expect(done.getByTestId("wizard-no-history")).toBeVisible();
  // the rows exist in the term now (one transaction)
  const secs = await call<{ items: unknown[] }>(page, "GET", `/sections?term_id=${term.id}&limit=50`);
  expect(secs.body.items.length).toBe(3);

  // Oluşturulanlar lists it; the draft page is the result screen with the undo
  await page.goto("/programs/new");
  await expect(page.getByTestId("committed-list").getByTestId("draft-row").filter({ hasText: `(E2E ${RUN})` })).toBeVisible();
  await page.goto(`/programs/new/${draftId}`);
  await page.getByTestId("undo-open").click();
  await page.getByTestId("undo-confirm").getByTestId("undo-go").click();
  await expect(page.getByTestId("wizard-committed")).toHaveAttribute("data-status", "undone");
  await expect(page.getByTestId("undo-result")).toContainText("3 şube");
  const after = await call<{ items: unknown[] }>(page, "GET", `/sections?term_id=${term.id}&limit=50`);
  expect(after.body.items.length).toBe(0);
});

test("joint teaching on the real Bahar term: MBG 534 with MBG 014, the joint total sizes the room, commit minimal → moderation preview", async ({ page }) => {
  test.setTimeout(420_000);
  await login(page);
  const { term } = await ensurePublished(page);
  await page.goto("/programs/new");
  await page.getByTestId("wizard-term").selectOption(String(term.id));
  await page.getByTestId("wizard-start").click();
  await expect(page).toHaveURL(/\/programs\/new\/\d+/);
  const draftId = Number(/\/programs\/new\/(\d+)/.exec(page.url())![1]);
  await page.getByTestId("wizard-faculty").fill("Fen Bilimleri Enstitüsü");
  await edit(page, () => page.getByTestId("wizard-program-name").fill(`MBG Tezsiz YL (E2E ortak ders ${RUN})`));
  await page.getByTestId("rail-courses").click();
  // an existing catalogue course is reused as is
  await page.getByTestId("wizard-existing-course").fill("MBG 534");
  await edit(page, () => page.getByRole("option").filter({ hasText: "MBG 534" }).first().getByRole("button").click());
  await expect(page.getByTestId("course-row")).toHaveCount(1);
  await page.getByTestId("rail-sections").click();
  await edit(page, () => page.getByTestId("section-enrolment").fill("10"));
  // "Ortak ders": the code typed any way finds MBG 014 (lisans) in this term
  await page.getByTestId("joint-search").fill("mbg014");
  const opt = page.getByTestId("joint-option").filter({ hasText: "MBG 014" }).first();
  await expect(opt).toBeVisible({ timeout: 20_000 });
  await edit(page, () => opt.click());
  await expect(page.getByTestId("joint-links")).toContainText("MBG 014");
  await expect(page.getByTestId("joint-total")).toHaveText("Ortak toplam: 85 öğrenci");
  await page.getByTestId("rail-rooms").click();
  const c = page.getByTestId("pattern-course").first();
  await expect(c.getByTestId("fit-line")).toContainText("85 öğrenci");
  await edit(page, async () => {
    await c.getByTestId("pattern-start").selectOption("10:10");
    for (const d of [1, 2, 3, 4]) await c.getByTestId(`day-${d}`).click();
  });
  // the server joins the joint section's meetings: the pre-check reports the merge
  await page.getByTestId("rail-constraints").click();
  await page.getByTestId("precheck-run").click();
  await expect(page.getByTestId("precheck-result")).toBeVisible({ timeout: 60_000 });
  // commit with the minimal-change re-solve of the published plan: lands in the moderation preview
  await page.getByTestId("rail-generate").click();
  await expect(page.getByText("Oluştur ve mevcut plana ekle")).toBeVisible();
  await page.getByTestId("generate-mode-solve").check();
  await page.getByTestId("generate-open").click();
  await page.getByTestId("generate-confirm").getByTestId("generate-go").click();
  await expect(page).toHaveURL(/\/moderation\/recreate\/\d+/, { timeout: 60_000 });
  await expect(page.getByTestId("recreate-preview")).toBeVisible({ timeout: 240_000 });
  await expect(page.getByTestId("chain")).toContainText("#");
  // back on the draft: the result screen with the undo and the server's blockers (if any), never a dead button
  await page.goto(`/programs/new/${draftId}`);
  const panel = page.getByTestId("undo-panel");
  await expect(panel).toContainText("geri alınabilir");
  const blockers = await panel.getByTestId("undo-blockers").count();
  if (blockers) await expect(page.getByTestId("undo-open")).toBeDisabled();
  else {
    await page.getByTestId("undo-open").click();
    await page.getByTestId("undo-confirm").getByTestId("undo-go").click();
    await expect(page.getByTestId("wizard-committed")).toHaveAttribute("data-status", "undone");
  }
});

type MatchingRow = { request_id: number; label: string; section_id: number; instructors: { id: number; name: string }[]; priority: { value: number; source: string } };
const TEACHER = { email: "akademisyen.p19@smartsched.local", password: "Flow-2026!pw" };
const UNLINKED = { email: "personel.p19@smartsched.local", password: "Flow-2026!pw" };

async function ensureUser(page: Page, u: { email: string; password: string }, fullName: string): Promise<number> {
  const list = await call<{ id: number; email: string | null }[] | { items: { id: number; email: string | null }[] }>(page, "GET", "/users?limit=500");
  const rows = Array.isArray(list.body) ? list.body : list.body.items;
  const hit = rows.find((r) => r.email === u.email);
  if (hit) return hit.id;
  const res = await call<{ id: number }>(page, "POST", "/users", { email: u.email, full_name: fullName, role: "TEACHER", password: u.password });
  expect(res.status, JSON.stringify(res.body)).toBe(201);
  return res.body.id;
}

let person: { id: number; name: string; label: string } | null = null;

test("moderation: person priority with its source badge, server changes list, re-solve preview with baseline + chain, publish with Akademisyenlere bildir", async ({ page }) => {
  test.setTimeout(480_000);
  await login(page);
  const { term } = await ensurePublished(page);
  // the academician of the flow: the first person in the published plan with a default-priority request
  const m = await call<{ items: MatchingRow[] }>(page, "GET", `/terms/${term.id}/moderation/matchings?check=false&limit=5000`);
  const row = m.body.items.find((x) => x.instructors.length === 1 && x.priority.source === "default")!;
  person = { id: row.instructors[0]!.id, name: row.instructors[0]!.name, label: row.label };
  // the teacher login linked to that instructor record (F-05 S00), and the term is the current one
  const uid = await ensureUser(page, TEACHER, "A. P.");
  expect((await call(page, "PUT", `/auth/sso/admin/users/${uid}/instructor`, { instructor_id: person.id })).status).toBe(200);
  expect((await call(page, "PUT", `/terms/${term.id}`, { is_active: true })).status).toBe(200);
  await ensureUser(page, UNLINKED, "P. U.");

  // person priority on the profile: Yüksek + note
  await page.goto(`/moderation/people/${person.id}`);
  const form = page.getByTestId("person-priority");
  await expect(form).toBeVisible({ timeout: 60_000 });
  await form.getByRole("radio", { name: /Yüksek/ }).or(form.getByRole("tab", { name: /Yüksek/ })).first().click();
  await form.getByRole("textbox").fill("akreditasyon");
  await form.getByTestId("person-priority-save").click();
  await expect(page.getByText(/öncelik kaydedildi \(\d+ talep\)/).first()).toBeVisible();
  const ov = await call<{ items: { subject_id: number; priority: number; note: string }[] }>(page, "GET", `/terms/${term.id}/moderation/priorities?subject=person`);
  expect(ov.body.items.find((o) => o.subject_id === person!.id)).toMatchObject({ priority: 1, note: "akreditasyon" }); // Yüksek = 1 (backend moderation.PRIORITY_TIERS)

  // the server-side staged list: every browser sees it
  await page.goto("/moderation?tab=matchings");
  const link = page.getByTestId("staged-link");
  await expect(link).toContainText(/değişiklik yayında değil/, { timeout: 60_000 });
  await link.click();
  await expect(page.getByTestId("changes-list")).toContainText("kişi önceliği Yüksek");
  await page.keyboard.press("Escape");
  // the matching inherits it: priority.source = person (badge "· kişi")
  await page.getByTestId("chip-all").click();
  await page.getByTestId("moderation-search").fill(person.label);
  await page.getByTestId("matchings-table").getByTestId("mod-row").first().click();
  const insp = page.getByTestId("matching-inspector");
  await expect(insp.getByTestId("priority-source").first()).toHaveAttribute("data-source", "person");
  await expect(insp.getByTestId("person-priority").first()).toBeVisible();
  await page.keyboard.press("Escape");

  // re-solve preview: the changes come from the server; the preview names its baseline and chain
  await page.getByTestId("recreate-open").click();
  const sheet = page.getByTestId("recreate-sheet");
  await expect(sheet.getByTestId("changes-list")).toContainText("kişi önceliği Yüksek");
  await sheet.getByTestId("recreate-start").click();
  await expect(page).toHaveURL(/\/moderation\/recreate\/\d+/);
  const preview = page.getByTestId("recreate-preview");
  await expect(preview).toBeVisible({ timeout: 300_000 });
  await expect(preview).toContainText(/Yeni çözüm ← yayındaki plan #\d+/);
  await expect(page.getByTestId("baseline-select")).toBeVisible();
  await expect(page.getByTestId("chain")).toContainText(/Zincir: #\d+ ← #\d+/);

  // publish: the dialog says who gets the digest; the guard may still refuse (shown verbatim)
  const publish = page.getByTestId("preview-publish");
  await expect(publish).toBeEnabled({ timeout: 30_000 });
  await publish.click();
  const dialog = page.getByTestId("publish-dialog");
  const notify = dialog.getByTestId("notify-people");
  await expect(notify).toContainText("Akademisyenlere bildir");
  await expect(notify.getByTestId("notify-list").or(notify.getByText(/bildirim gitmez/))).toBeVisible();
  await dialog.getByTestId("publish-confirm").click();
  await expect(page.getByText(/artık geçerli plan/).or(dialog.getByTestId("publish-refused")).first()).toBeVisible({ timeout: 60_000 });
});

test("Taleplerim: the teacher's nav entry opens /moderation/me with their own requests; an unlinked account gets the plain explanation", async ({ browser }) => {
  test.setTimeout(180_000);
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await login(page, TEACHER.email, TEACHER.password);
  const nav = page.getByRole("link", { name: "Taleplerim" }).first();
  await expect(nav).toHaveAttribute("href", "/moderation/me");
  await nav.click();
  await expect(page).toHaveURL(/\/moderation\/me/);
  const mine = page.getByTestId("my-requests");
  await expect(mine.getByRole("heading", { level: 1, name: "Taleplerim" })).toBeVisible();
  await expect(mine.getByTestId("mine-table")).toBeVisible({ timeout: 60_000 });
  // own requests only (Q11): the API says the same
  const me = await call<{ instructor_id: number; visibility: string }>(page, "GET", "/moderation/me");
  expect(me.body.visibility).toBe("own");
  await mine.getByTestId("mine-history").click();
  await expect(page).toHaveURL(new RegExp(`/moderation/people/${me.body.instructor_id}`));
  // no edit controls for an academician
  await expect(page.getByTestId("person-priority")).toHaveCount(0);
  await ctx.close();

  const ctx2 = await browser.newContext();
  const p2 = await ctx2.newPage();
  await login(p2, UNLINKED.email, UNLINKED.password);
  await p2.goto("/moderation/me");
  await expect(p2.getByTestId("mine-unlinked")).toContainText("Hesabınız bir öğretim elemanına bağlı değil");
  await ctx2.close();
});

test("learned suggestions: accept → Geri al restores; dismiss → Geçmiş → Geri al; persistent accept asks first", async ({ page }) => {
  test.setTimeout(180_000);
  await login(page);
  const { term } = await ensurePublished(page);
  // suggestions are priors over the extracted evidence: run the extraction for the term first (idempotent; the same
  // as `python -m app.cli learning-refresh`, which the gate's backend does not run)
  const refreshed = await call<{ priors?: unknown }>(page, "POST", "/learning/refresh", { term_id: term.id });
  expect(refreshed.status, JSON.stringify(refreshed.body)).toBe(200);
  await page.goto("/moderation?tab=preferences");
  await page.getByRole("radio", { name: "Öneriler" }).or(page.getByRole("tab", { name: "Öneriler" })).first().click();
  const list = page.getByTestId("suggestions-moderation");
  const cards = list.getByTestId("suggestion-card");
  await expect(cards.first()).toBeVisible({ timeout: 60_000 });
  const first = Number(await cards.first().getAttribute("data-suggestion-id"));

  // accept for this term, then undo: the suggestion is open again and its rule is switched off
  await cards.first().getByTestId("suggestion-accept").click();
  await expect(list.getByTestId("suggestion-receipt").first()).toContainText("Yumuşak tercih eklendi");
  await list.getByTestId("suggestion-undo").first().click();
  await expect(list.locator(`[data-testid="suggestion-card"][data-suggestion-id="${first}"]`)).toBeVisible();
  const open1 = await call<{ id: number; state: string }[]>(page, "GET", `/learning/suggestions?term_id=${term.id}&state=all&limit=500`);
  expect(open1.body.find((s) => s.id === first)?.state).toBe("open");

  // dismiss without a reason, then Geçmiş → Geri al
  const second = list.locator(`[data-testid="suggestion-card"][data-suggestion-id="${first}"]`);
  await second.getByTestId("suggestion-reject").click();
  await second.getByTestId("dismiss-skip").click();
  await expect(list.getByTestId("suggestion-receipt").first()).toContainText("Reddedildi");
  await list.getByRole("radio", { name: /Geçmiş/ }).or(list.getByRole("tab", { name: /Geçmiş/ })).first().click();
  const hist = list.getByTestId("history-row").filter({ has: page.locator('[data-testid="history-undo"]') }).first();
  await expect(hist).toHaveAttribute("data-state", "dismissed");
  await hist.getByTestId("history-undo").click();
  await list.getByRole("radio", { name: /Bekleyen/ }).or(list.getByRole("tab", { name: /Bekleyen/ })).first().click();
  await expect(list.locator(`[data-testid="suggestion-card"][data-suggestion-id="${first}"]`)).toBeVisible();

  // persistent (planning.admin): the confirm explains it is never applied by itself
  const card = list.locator(`[data-testid="suggestion-card"][data-suggestion-id="${first}"]`);
  await card.getByRole("button", { name: "Ağırlık seç" }).click();
  await page.getByTestId("suggestion-accept-persistent").click();
  const confirm = page.getByTestId("persistent-confirm");
  await expect(confirm).toContainText("Hiçbir zaman kendiliğinden uygulanmaz");
  await confirm.getByTestId("persistent-go").click();
  await expect(list.getByTestId("suggestion-receipt").first()).toContainText("Kalıcı tercih olarak eklendi");
  const acc = await call<{ id: number; state: string; scope: string | null }[]>(page, "GET", `/learning/suggestions?term_id=${term.id}&state=all&limit=500`);
  expect(acc.body.find((s) => s.id === first)).toMatchObject({ state: "accepted", scope: "persistent" });
  await list.getByTestId("suggestion-undo").first().click();
  await expect(card).toBeVisible();
});

test("phone 390 × 844: the wizard's compact stepper and floating footer, moderation sheets, no sideways scroll", async ({ browser }) => {
  test.setTimeout(240_000);
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" });
  const page = await ctx.newPage();
  await login(page);
  const term = await emptyTerm(page);
  const d = await call<{ id: number }>(page, "POST", "/program-drafts", { term_id: term.id, payload: { program: { name: "Mobil kontrol (E2E)", faculty_name: "Fen Bilimleri Enstitüsü", prefix: "MBG" } }, step: "program" });
  expect(d.status).toBe(201);
  await page.goto("/programs/new");
  await noSidewaysScroll(page);
  for (const step of ["program", "courses", "sections", "instructors", "cohorts", "rooms", "constraints", "generate"]) {
    await page.goto(`/programs/new/${d.body.id}?step=${step}`);
    await expect(page.getByTestId("wizard-stepper")).toBeVisible();
    await expect(page.getByTestId("wizard-rail")).toBeHidden();
    await noSidewaysScroll(page);
  }
  // the step list is a bottom sheet with every step's status
  await page.getByTestId("stepper-open").click();
  await expect(page.getByTestId("stepper-sheet")).toBeVisible();
  await page.getByTestId("stepper-sheet").getByTestId("rail-courses").click();
  await expect(page).toHaveURL(/step=courses/);
  // the footer capsule: 44 px controls within thumb reach
  const next = page.getByTestId("wizard-next");
  const box = (await next.boundingBox())!;
  expect(box.height).toBeGreaterThanOrEqual(44);
  expect(box.y + box.height).toBeLessThanOrEqual(844);
  await page.getByTestId("wizard-paste").click();
  await expect(page.getByTestId("paste-dialog")).toHaveAttribute("data-variant", "sheet");
  await page.keyboard.press("Escape");

  for (const url of ["/moderation?tab=people", "/moderation/me", ...(person ? [`/moderation/people/${person.id}`] : [])]) {
    await page.goto(url);
    await page.waitForLoadState("networkidle");
    await noSidewaysScroll(page);
  }
  if (person) {
    await expect(page.getByTestId("person-priority")).toBeVisible();
  }
  await page.goto("/moderation?tab=matchings");
  await page.getByTestId("staged-link").click();
  await expect(page.getByTestId("changes-sheet")).toHaveAttribute("data-variant", "sheet");
  await ctx.close();
});
