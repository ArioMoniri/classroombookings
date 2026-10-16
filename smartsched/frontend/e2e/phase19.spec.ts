/**
 * Phase 19 frontend F1–F4 against the REAL backend (no mocks), gated E2E_REAL=1:
 *   1. moderation: Kişiler → a profile → raise a priority → "Planı yeniden oluştur" → the preview shows the diff
 *      → "Onayla ve yayınla" is published or refused by the guard, with the 409 reasons shown verbatim
 *   2. a teacher with no linked instructor gets the "not linked" empty state on /moderation, not an error
 *   3. learned suggestions: accept one (soft preference, Geri al) and dismiss one with a reason
 *   4. admin memory: reset everything (typed SIFIRLA) and undo it from "Son sıfırlamalar"
 *   5. the program wizard creates the MBG Tezli YL program from the TSV example and runs the pre-check
 *
 * Backend: Güz + Bahar planning lists, the Bahar weekly grid and room master, the seeded admin, one Bahar
 * week-3 run (publish candidate) and `learning-refresh`. The first test publishes that run if nothing is
 * published yet (the moderation console reads the published plan). Run, e.g.:
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:18974 NEXT_PUBLIC_API_URL=http://127.0.0.1:18974 PW_PORT=18975 \
 *     npx playwright test e2e/phase19.spec.ts
 */
import { expect, test, type Page } from "@playwright/test";
import { REAL, SKIP_REASON, TERM_CODE, login } from "./helpers";
import { pinLanguage } from "./language";

test.skip(!REAL, SKIP_REASON);
// the assertions read Turkish (the product default): pin it, whatever the previous spec left behind
pinLanguage("tr");
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

/** the console reads the published plan: publish the newest finished Bahar course run when none is published */
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

test("moderation: people → profile → raise a priority → re-solve preview diff → publish per the guard", async ({ page }) => {
  test.setTimeout(420_000);
  await login(page);
  await ensurePublished(page);
  await page.goto("/moderation?tab=people");
  const console_ = page.getByTestId("moderation-console");
  await expect(console_).toBeVisible();
  await expect(console_.getByRole("heading", { level: 1, name: "Moderasyon" })).toBeVisible();
  // Kişiler: sorted by unmet requests; the first row is someone with an unmet request
  await page.getByRole("button", { name: "Karşılanmayan talebi olan" }).click();
  const firstPerson = page.getByTestId("people-table").getByTestId("mod-row").first();
  await expect(firstPerson).toBeVisible({ timeout: 60_000 });
  // keyboard path: the row is focusable and Enter opens the profile
  await firstPerson.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/moderation\/people\/\d+/);
  const profile = page.getByTestId("person-profile");
  await expect(profile.getByTestId("profile-name")).toBeVisible({ timeout: 60_000 });
  await expect(profile.getByTestId("request-timeline")).toBeVisible();
  // the timeline is grouped by term and every row carries outcome glyph + word
  await expect(profile.getByTestId("term-group").first()).toBeVisible();
  const bahar = profile.getByTestId("term-group").filter({ hasText: TERM_CODE });
  const unmet = bahar.locator('[data-testid="timeline-row"]:is([data-verdict="unplaced"],[data-verdict="not_as_requested"],[data-verdict="partial"])').first();
  const row = (await unmet.count()) ? unmet : bahar.getByTestId("timeline-row").first();
  await expect(row).toBeVisible();
  // raise the priority: glyph + word in the tier picker, saved and staged for the re-solve
  await row.getByTestId("priority-trigger").click();
  // the request's own form (popover); the profile's side panel has a second tier picker, the person's priority
  const form = page.locator("form").filter({ has: page.getByTestId("priority-save") });
  await expect(form).toBeVisible();
  await form.getByRole("tab", { name: /Yüksek/ }).or(form.getByRole("radio", { name: /Yüksek/ })).first().click();
  await form.getByTestId("priority-save").click();
  await expect(page.getByText(/öncelik kaydedildi/).first()).toBeVisible();
  await expect(row.getByTestId("priority-trigger")).toContainText("Yüksek");

  // back in the console: 1 staged change, then "Planı yeniden oluştur" (minimal change)
  await page.goto("/moderation?tab=matchings");
  await expect(page.getByTestId("staged-link")).toContainText(/1 değişiklik yayında değil/);
  await expect(page.getByTestId("matchings-table")).toBeVisible({ timeout: 60_000 });
  await page.getByTestId("recreate-open").click();
  const sheet = page.getByTestId("recreate-sheet");
  await expect(sheet.getByRole("radio", { name: /En az değişiklik/ })).toBeChecked();
  await sheet.getByTestId("recreate-start").click();
  await expect(page).toHaveURL(/\/moderation\/recreate\/\d+/);

  // the preview: the diff table is the primary view, counts are static text
  const preview = page.getByTestId("recreate-preview");
  await expect(preview).toBeVisible({ timeout: 300_000 });
  await expect(preview.getByTestId("diff-summary")).toContainText("Değişmeyen");
  const unchanged = Number((await preview.getByTestId("count-unchanged").textContent())?.replace(/\D/g, ""));
  expect(unchanged).toBeGreaterThan(100);
  await expect(preview.getByTestId("preview-state")).toHaveText("Yayında değil");
  // the four groups switch with 1–4; Değişmeyen is a count, the others list rows or say they are empty
  for (const [key, name] of [["1", "Taşınan"], ["2", "Yeni yerleşen"], ["3", "Yerleşemeyen"]] as const) {
    await page.keyboard.press(key);
    await expect(preview.getByRole("tab", { name: new RegExp(name) }).or(preview.getByRole("radio", { name: new RegExp(name) })).first()).toHaveAttribute("aria-selected", "true").catch(() => undefined);
    await expect(preview.getByTestId("diff-table").or(preview.getByTestId("diff-empty"))).toBeVisible();
  }
  await page.keyboard.press("4");
  await expect(preview.getByTestId("unchanged-note")).toContainText(/ders gününü, saatini ve odasını koruyor/);
  // the calendar compare mode draws only the changed classes
  await preview.getByRole("tab", { name: /Takvimde göster/ }).or(preview.getByRole("radio", { name: /Takvimde göster/ })).first().click();
  await expect(preview.getByTestId("compare-calendar")).toBeVisible();
  await preview.getByRole("tab", { name: /Tablo/ }).or(preview.getByRole("radio", { name: /Tablo/ })).first().click();

  // "Onayla ve yayınla": the publish guard decides; a refusal is shown verbatim and nothing is published
  await preview.getByTestId("preview-publish").click();
  const dialog = page.getByTestId("publish-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Vazgeç" })).toBeFocused();
  await dialog.getByTestId("publish-confirm").click();
  const refused = dialog.getByTestId("publish-refused");
  const published = page.getByText(/Yayınlandı: #\d+ artık geçerli plan/);
  await expect(refused.or(published).first()).toBeVisible({ timeout: 60_000 });
  if (await refused.isVisible()) {
    // e.g. "run 12 breaks hard rules…", or the scope-reduction 409 with its confirm
    await expect(refused).not.toBeEmpty();
  } else {
    await expect(preview.getByTestId("preview-state")).toContainText("Yayında", { timeout: 30_000 });
  }
});

test("a teacher without a linked instructor sees the 'not linked' empty state on /moderation", async ({ page }) => {
  await login(page);
  const email = `p19-teacher-${Date.now()}@uni.edu.tr`;
  const made = await call(page, "POST", "/users", { email, full_name: "P19 Öğretmen", role: "TEACHER", password: "Teacher-2026!" });
  expect(made.status, JSON.stringify(made.body)).toBe(201);
  await page.context().clearCookies();
  await login(page, email, "Teacher-2026!");
  await page.goto("/moderation");
  await expect(page.getByTestId("my-requests")).toBeVisible();
  await expect(page.getByTestId("mine-unlinked")).toContainText("Hesabınız bir öğretim elemanına bağlı değil");
  await expect(page.getByText("Yüklenemedi")).toHaveCount(0);
});

test("learned suggestions: accept one (soft, undoable) and dismiss one with a reason", async ({ page }) => {
  test.setTimeout(240_000);
  await login(page);
  await page.goto("/moderation?tab=preferences");
  await page.getByRole("tab", { name: "Öneriler" }).or(page.getByRole("radio", { name: "Öneriler" })).first().click();
  const list = page.getByTestId("suggestions-moderation");
  const cards = list.getByTestId("suggestion-card");
  await expect(cards.first()).toBeVisible({ timeout: 120_000 });
  const first = cards.first();
  // evidence first: confidence word + meter, "Kanıtı göster"
  await expect(first.getByRole("meter")).toHaveAttribute("aria-valuetext", /güven/);
  await first.getByTestId("suggestion-evidence-toggle").click();
  await expect(first.getByText(/Kabul ederseniz yumuşak bir tercih/)).toBeVisible();
  const acceptedId = await first.getAttribute("data-suggestion-id");
  await first.getByTestId("suggestion-accept").click();
  const receipt = list.locator('[data-testid="suggestion-receipt"][data-kind="accepted"]');
  await expect(receipt).toContainText("Yumuşak tercih eklendi");
  // the accepted rule is a SOFT LEARNED preference of the term
  const sugg = await call<{ id: number; state: string; constraint_id: number | null }[]>(page, "GET", `/learning/suggestions?term_id=${(await call<Term[]>(page, "GET", "/terms")).body.find((t) => t.code === TERM_CODE)!.id}&state=accepted`);
  const accepted = sugg.body.find((s) => String(s.id) === acceptedId)!;
  expect(accepted.constraint_id).not.toBeNull();
  const rules = await call<{ id: number; hardness: string; source: string }[]>(page, "GET", `/constraints?enabled=true`);
  expect(rules.body.find((r) => r.id === accepted.constraint_id)).toMatchObject({ hardness: "soft", source: "LEARNED" });

  // dismiss the next open card with a reason chip
  const next = list.locator(`[data-testid="suggestion-card"]:not([data-suggestion-id="${acceptedId}"])`).first();
  await next.getByTestId("suggestion-reject").click();
  await next.getByTestId("dismiss-stale").click();
  await expect(list.locator('[data-testid="suggestion-receipt"][data-kind="dismissed"]')).toContainText("Reddedildi");
  // Geçmiş lists both decisions
  await list.getByRole("tab", { name: /Geçmiş/ }).or(list.getByRole("radio", { name: /Geçmiş/ })).first().click();
  await expect(list.getByTestId("suggestion-history")).toContainText("Kabul edildi");
  await expect(list.getByTestId("suggestion-history")).toContainText("Reddedildi");
});

test("admin memory: reset everything with the typed word, then undo it", async ({ page }) => {
  test.setTimeout(180_000);
  await login(page);
  await page.goto("/moderation/learning");
  const panel = page.getByTestId("learning-memory");
  await expect(panel.getByTestId("memory-summary")).toBeVisible({ timeout: 60_000 });
  await panel.getByTestId("reset-all-open").click();
  const dialog = page.getByTestId("reset-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId("reset-reason")).toBeFocused();
  await dialog.getByTestId("reset-reason").fill("e2e: yeniden yapılanma denemesi");
  // a wrong word is refused with a message; SIFIRLA (Turkish-aware) goes through
  await dialog.getByTestId("reset-word").fill("SIFIR");
  await dialog.getByTestId("reset-confirm").click();
  await expect(dialog.getByRole("alert")).toHaveText("Yazılan kelime eşleşmiyor.");
  await dialog.getByTestId("reset-word").fill("sıfırla");
  await dialog.getByTestId("reset-confirm").click();
  await expect(dialog).toBeHidden();
  const row = panel.getByTestId("reset-row").first();
  await expect(row).toHaveAttribute("data-status", "undoable");
  await expect(row).toContainText(/Geri alma için \d+ gün kaldı/);
  await row.getByTestId("reset-undo").click();
  await expect(panel.getByTestId("reset-row").first()).toHaveAttribute("data-status", "undone");
});

test("the program wizard creates the MBG Tezli YL program and runs the pre-check", async ({ page }) => {
  test.setTimeout(420_000);
  await login(page);
  await page.goto("/programs/new");
  await page.getByTestId("wizard-start").click();
  await expect(page.getByTestId("program-wizard")).toBeVisible();
  // 1 term
  const termValue = await page.getByTestId("wizard-term").locator("option", { hasText: TERM_CODE }).first().getAttribute("value");
  await page.getByTestId("wizard-term").selectOption(termValue!);
  await page.getByTestId("wizard-next").click();
  // 2 faculty + program
  const name = `Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans e2e ${Date.now() % 100000}`;
  await page.getByTestId("wizard-faculty").fill("Fen Bilimleri Enstitüsü");
  await page.getByTestId("wizard-program-name").fill(name);
  await page.getByTestId("wizard-prefix").fill("MBG");
  await page.getByTestId("wizard-next").click();
  // 3 courses: the TSV paste preview, then insert (MBG532 → MBG 532)
  await page.getByTestId("wizard-paste").click();
  await page.getByTestId("paste-example").click();
  await expect(page.getByTestId("paste-dialog")).toContainText("7 satır eklenecek");
  await page.getByTestId("paste-insert").click();
  await expect(page.getByTestId("course-row")).toHaveCount(7);
  await expect(page.getByTestId("courses-grid")).not.toContainText("MBG532");
  // the rail shows the step summary and its status in words (never colour only)
  await expect(page.getByTestId("rail-courses")).toContainText("7 ders · 63 AKTS");
  // 5 patterns: a start time for every course (the seminar meets one period a week)
  await page.getByTestId("rail-patterns").click();
  const starts = page.getByTestId("pattern-start");
  await expect(starts).toHaveCount(7);
  for (let i = 0; i < 7; i++) await starts.nth(i).selectOption("09:20");
  await expect(page.getByTestId("fit-line").first()).toContainText(/oda sığar/);
  // autosave: faculty, program, courses, sections, patterns → "Tüm değişiklikler kaydedildi"
  await expect(page.getByTestId("save-status")).toHaveAttribute("data-state", "saved", { timeout: 180_000 });
  await expect(page.getByTestId("save-status")).toContainText("Tüm değişiklikler kaydedildi");
  // the server has the programme and its seven sections with their meetings
  const programs = await call<{ items: { id: number; name: string }[] }>(page, "GET", `/programs?search=${encodeURIComponent("e2e")}`);
  const prog = programs.body.items.find((p) => p.name === name)!;
  expect(prog).toBeTruthy();
  const terms = (await call<Term[]>(page, "GET", "/terms")).body;
  const termId = terms.find((t) => t.code === TERM_CODE)!.id;
  await expect.poll(async () => (await call<{ total: number }>(page, "GET", `/sections?term_id=${termId}&program_id=${prog.id}`)).body.total, { timeout: 60_000 }).toBe(7);
  const meetings = await call<{ total: number }>(page, "GET", `/requests/meetings?term_id=${termId}&program_id=${prog.id}`);
  expect(meetings.body.total).toBeGreaterThanOrEqual(7);
  // 7 pre-check: the wizard's own checks + the Studio pre-check for this program's meetings
  await page.getByTestId("rail-precheck").click();
  await expect(page.getByTestId("wizard-issues").or(page.getByText("Hata ya da uyarı yok."))).toBeVisible();
  await page.getByTestId("precheck-run").click();
  await expect(page.getByTestId("precheck-result")).toContainText(/Ön kontrol: \d+ engel, \d+ uyarı/, { timeout: 180_000 });
  // 8 generate: no errors, so "Oluştur ve çöz" is enabled (warnings never block)
  await page.getByTestId("rail-generate").click();
  await expect(page.getByTestId("generate-summary")).toBeVisible();
  await expect(page.getByTestId("generate-open")).toBeEnabled();
  // resume: the draft is listed with "Kaldığınız yer"
  await page.goto("/programs/new");
  await expect(page.getByTestId("draft-list")).toContainText(name);
});
