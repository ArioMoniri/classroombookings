/**
 * Intake (P19 I1-I5) on the owner's real Bahar 2026 workbooks, against the real backend (E2E_REAL=1):
 *
 *   1. the planning list (bahar_derslik_planlama_listesi_v5.xlsx; the 16 376-column refusal is fixed, so it must be
 *      accepted) through the stepper Dosyalar › İnceleme › Fark › Kaydet: the three instructor merges decided, the
 *      Fark dry run with "keep" and with "take" (the request carries the choice), then the commit into 2026-BAHAR;
 *   2. the same file again: every merge decided in 1 comes back "remembered" (intake memory) with its suggestion;
 *   3. the general path forced: the unmapped column is decided, and a re-upload shows that mapping remembered; then
 *      "Hatırlanan kararlar" on the onboarding page lists that file's signature, the whole signature is forgotten after
 *      a confirm (the API no longer lists it) and the toast's Geri al brings it back;
 *   4. the weekly board (bahar_derslikler_takvimi_2026.xlsx): Fark reads the dry run's `result.baseline_run` (the
 *      baseline import run the schedule map goes to and its counts); the Kaydet target "Yazma" (skip) and "Başka
 *      çalıştırma" (another run of the term) change the dry run's request and answer; Kaydet with the baseline run
 *      shows its counts, and "Re-solve keeping this board" opens the run's dialog, where a relaxation policy is
 *      chosen and a child run of the baseline run is queued (then cancelled and removed again).
 *
 * The AI rows path (pdf / docx / images through the model) needs an Anthropic API key and an administrator's AI
 * switch; it is skipped unless E2E_ANTHROPIC_KEY_CONFIGURED=1 says the backend has one.
 */
import path from "node:path";
import { expect, test, type Page, type Request } from "@playwright/test";
import { FIXTURES, PLANNING_LIST, REAL, SKIP_REASON, TERM_CODE, api, login, pickSegment, type Term } from "./helpers";

const BOARD = path.join(FIXTURES, "bahar_derslikler_takvimi_2026.xlsx");
const LONG = 180_000;

test.describe.configure({ mode: "serial" });
test.skip(!REAL, SKIP_REASON);

async function startJob(page: Page, file: string, opts: { general?: boolean } = {}) {
  await page.goto("/onboarding");
  const drop = page.getByTestId("onboarding-drop");
  await expect(drop).toBeVisible();
  await page.getByTestId("onboarding-input").setInputFiles(file);
  await expect(drop).toContainText(path.basename(file));
  // deterministic path: no file content to the model (no key is configured on the e2e backend anyway)
  const ai = drop.getByRole("checkbox", { name: "Anahtar tanımlıysa yapay zekâ modelini kullan" });
  await ai.uncheck();
  if (opts.general) await drop.getByRole("checkbox", { name: /Her dosyayı kurulla oku/ }).check();
  await page.getByTestId("onboarding-start").click();
  await expect(page.getByTestId("onboarding-review")).toBeVisible({ timeout: LONG });
  await expect(page.getByRole("alert").filter({ hasText: /fail|başarısız|reddedil|refused/i })).toHaveCount(0);
}

const currentStep = (page: Page) => page.getByTestId("onboarding-steps").locator("[aria-current=step]");
const jsonBody = (r: Request) => (r.postDataJSON() ?? {}) as Record<string, unknown>;
const commitRequest = (page: Page, dry: boolean) =>
  page.waitForRequest((r) => r.method() === "POST" && /\/council\/jobs\/\d+\/commit$/.test(r.url()) && jsonBody(r).dry_run === dry, { timeout: LONG });

async function fillTerm(page: Page) {
  const terms = await api<(Term & { name: string })[]>(page, "/terms");
  const term = terms.find((t) => t.code === TERM_CODE);
  expect(term, `term ${TERM_CODE} is imported`).toBeTruthy();
  const commit = page.getByTestId("onboarding-commit");
  await commit.getByTestId("term-code").fill(TERM_CODE);
  // the existing term's own name, so the commit changes nothing about the term itself
  await commit.getByRole("textbox").nth(1).fill(term!.name);
  return commit;
}

test("Bahar planning list: Dosyalar › İnceleme › Fark (keep / take) › Kaydet", async ({ page }) => {
  test.setTimeout(6 * 60_000);
  await login(page);
  await page.goto("/onboarding");
  await expect(currentStep(page)).toHaveText(/Dosyalar/);
  await startJob(page, PLANNING_LIST);

  // İnceleme: the instructor spellings the council could not settle alone block the commit until decided
  await expect(currentStep(page)).toHaveText(/İnceleme/);
  const merges = page.locator('[data-testid^="review-merge:"]');
  await expect(merges.first()).toBeVisible();
  const count = await merges.count();
  expect(count).toBeGreaterThan(0);
  for (let i = 0; i < count; i++) {
    const row = merges.nth(i);
    const decision = i === count - 1 ? "Reddet" : "Onayla";
    await row.getByRole("button", { name: decision }).click();
    await expect(row.getByText(i === count - 1 ? "reject" : "accept", { exact: true })).toBeVisible({ timeout: 30_000 });
  }
  await expect(page.getByTestId("blocking-count")).toHaveText(/^0/, { timeout: 30_000 });
  await expect(currentStep(page)).toHaveText(/Fark/);

  // Fark: the same writer in a rolled-back transaction, first keeping planner corrections, then taking the file's
  const commit = await fillTerm(page);
  await expect(commit.getByTestId("onboarding-baseline-preview")).toHaveCount(0); // a planning list is no schedule map
  await expect(commit.getByTestId("onboarding-baseline-target")).toHaveCount(0);
  let req = commitRequest(page, true);
  await commit.getByTestId("onboarding-diff-button").click();
  expect(jsonBody(await req).on_conflict).toBe("keep");
  const diff = commit.getByTestId("onboarding-diff");
  await expect(diff).toBeVisible({ timeout: LONG });
  await expect(diff.getByRole("row", { name: /meeting_requests/ })).toBeVisible();
  await pickSegment(page, "Dosyadakini al", commit);
  await expect(diff).toHaveCount(0); // a changed choice drops the old diff
  req = commitRequest(page, true);
  await commit.getByTestId("onboarding-diff-button").click();
  expect(jsonBody(await req).on_conflict).toBe("take");
  await expect(commit.getByTestId("onboarding-diff")).toBeVisible({ timeout: LONG });

  // Kaydet with "keep" (the default a coordinator saves with)
  await pickSegment(page, "Düzeltmeyi koru", commit);
  req = commitRequest(page, false);
  await commit.getByTestId("onboarding-commit-button").click();
  expect(jsonBody(await req).on_conflict).toBe("keep");
  await expect(commit.getByTestId("onboarding-result")).toContainText(`${TERM_CODE} dönemine yazıldı`, { timeout: LONG });
  await expect(currentStep(page)).toHaveText(/Kaydet/);
});

test("re-upload of the planning list: the merge decisions come back remembered", async ({ page }) => {
  test.setTimeout(4 * 60_000);
  await login(page);
  await startJob(page, PLANNING_LIST);
  const merges = page.locator('[data-testid^="review-merge:"]');
  await expect(merges.first()).toBeVisible();
  const count = await merges.count();
  for (let i = 0; i < count; i++) {
    const memory = merges.nth(i).getByTestId("review-remembered");
    await expect(memory).toContainText(/tarihli \d+ numaralı işten hatırlandı/);
    await expect(memory).toContainText("Yine de karar vermeniz gerekiyor.");
  }
  // the suggestion is offered, never applied by itself: one click applies it
  const first = merges.first();
  await first.getByRole("button", { name: "Öneriyi uygula" }).click();
  await expect(first.getByText("accept", { exact: true })).toBeVisible({ timeout: 30_000 });
});

test("forced general path: a column mapping decision is remembered for the same file signature", async ({ page }) => {
  test.setTimeout(6 * 60_000);
  await login(page);
  await startJob(page, PLANNING_LIST, { general: true });
  const mapping = page.locator('[data-testid^="review-map:"]').first();
  await expect(mapping).toBeVisible();
  // the column the analysis could not map (a yes / no flag) stays unused: accept it as it is
  await mapping.getByRole("button", { name: "Onayla" }).click();
  await expect(mapping.getByText("accept", { exact: true })).toBeVisible({ timeout: 60_000 });

  await startJob(page, PLANNING_LIST, { general: true });
  const again = page.locator('[data-testid^="review-map:"]').first();
  await expect(again).toBeVisible();
  await expect(again.getByTestId("review-remembered")).toContainText(/tarihli \d+ numaralı işten hatırlandı/);
  // nothing is committed here: the general path into a term the fast path filled would add duplicate requests

  // Hatırlanan kararlar (onboarding, before a new upload): the file's layout signature, its rows, forget all + undo
  type Mem = { total: number; items: { id: number; signature: string; kind: string; context: { file?: string } }[] };
  const before = await api<Mem>(page, "/council/memory?kind=intake_mapping");
  const row = before.items.find((i) => i.context.file === path.basename(PLANNING_LIST));
  expect(row, "the planning list's column mapping is remembered").toBeTruthy();
  const sig = row!.signature;
  const n = (await api<Mem>(page, `/council/memory?signature=${sig}`)).total;
  await page.goto("/onboarding");
  const panel = page.getByTestId("intake-memory");
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId("intake-memory-section-layout")).toContainText("Dosya düzenleri");
  const group = panel.locator(`[data-testid="intake-memory-group"][data-signature="${sig}"]`);
  await expect(group).toContainText(path.basename(PLANNING_LIST));
  await group.getByTestId("intake-memory-group-toggle").click();
  await expect(group.getByTestId("intake-memory-row").filter({ hasText: /\d+\. sütun/ }).first()).toBeVisible();
  await expect(group.getByTestId("intake-memory-row")).toHaveCount(n);
  await group.getByTestId("intake-memory-forget-group").click();
  const confirm = page.getByTestId("intake-memory-confirm");
  await expect(confirm).toContainText(`${n} karar unutulacak`);
  const del = page.waitForRequest((r) => r.method() === "DELETE" && r.url().includes(`/council/memory?signature=${sig}`));
  await confirm.getByTestId("intake-memory-confirm-button").click();
  await del;
  await expect(group).toHaveCount(0, { timeout: 30_000 });
  expect((await api<Mem>(page, `/council/memory?signature=${sig}`)).total).toBe(0);
  // the forget is a learning reset of scope intake: the toast's Geri al (administrators) restores it
  await page.locator("[data-sonner-toast]").getByRole("button", { name: "Geri al" }).click();
  await expect(group).toBeVisible({ timeout: 30_000 });
  expect((await api<Mem>(page, `/council/memory?signature=${sig}`)).total).toBe(n);
});

test("weekly board: the schedule map goes to the baseline run; a re-solve keeps it with a relaxation policy", async ({ page }) => {
  test.setTimeout(14 * 60_000);
  await login(page);
  await startJob(page, BOARD);
  await expect(page.getByTestId("blocking-count")).toHaveText(/^0/);
  const commit = await fillTerm(page);
  const preview = commit.getByTestId("onboarding-baseline-preview");
  await expect(preview).toBeVisible();
  await expect(preview).toHaveAttribute("data-state", "pending");
  const target = commit.getByTestId("onboarding-baseline-target");
  await expect(target).toHaveAttribute("data-mode", "auto");

  // Fark: the dry run says which run the map goes to (the term's baseline run, existing or new) and its counts
  let dry = commitRequest(page, true);
  await commit.getByTestId("onboarding-diff-button").click();
  expect(jsonBody(await dry).baseline).toEqual({ mode: "auto" });
  await expect(preview).toHaveAttribute("data-state", /^(existing|new)$/, { timeout: LONG });
  await expect(preview).toContainText(/temel çalıştırma/);
  await expect(preview).toContainText("Talebe bağlı");

  // Kaydet target "Yazma": the dry run writes no schedule map
  await pickSegment(page, "Yazma", target);
  await expect(preview).toHaveAttribute("data-state", "pending"); // a changed choice drops the old diff
  dry = commitRequest(page, true);
  await commit.getByTestId("onboarding-diff-button").click();
  expect(jsonBody(await dry).baseline).toEqual({ mode: "skip" });
  await expect(preview).toHaveAttribute("data-state", "skip", { timeout: LONG });
  await expect(preview).toContainText(/Program haritası yazılmayacak \([\d.]+ ders girişi atlanır\)/);

  // "Başka çalıştırma": another finished COURSE run of the term (the e2e full-term solve), dry run only
  await pickSegment(page, "Başka çalıştırma", target);
  const select = target.getByTestId("baseline-target-run");
  await expect(select).toBeVisible({ timeout: 30_000 });
  const other = Number(await select.inputValue());
  expect(other).toBeGreaterThan(0);
  dry = commitRequest(page, true);
  await commit.getByTestId("onboarding-diff-button").click();
  expect(jsonBody(await dry).baseline).toEqual({ mode: "run", run_id: other });
  await expect(preview).toHaveAttribute("data-state", "target", { timeout: LONG });
  await expect(preview).toContainText(`#${other} numaralı çalıştırmasına`);

  // Kaydet with the baseline run (the default)
  await pickSegment(page, "Temel çalıştırma", target);
  const req = commitRequest(page, false);
  await commit.getByTestId("onboarding-commit-button").click();
  expect(jsonBody(await req).baseline).toEqual({ mode: "auto" });
  const result = commit.getByTestId("onboarding-baseline-result");
  await expect(result).toBeVisible({ timeout: LONG });
  await expect(result).toContainText(/Temel çalıştırma #\d+ (oluşturuldu|güncellendi)/);
  const baselineId = Number((await result.getByTestId("onboarding-baseline-open").getAttribute("href"))?.split("/").pop());
  const created = /oluşturuldu/.test((await result.textContent()) ?? "");
  let childId: number | null = null;
  try {
    const baseline = await api<{ params: { source?: string; sources?: { file?: string }[] }; label: string }>(page, `/runs/${baselineId}`);
    expect(baseline.params.source).toBe("COUNCIL_BASELINE");
    expect(baseline.params.sources?.map((s) => s.file)).toContain(path.basename(BOARD));

    await result.getByTestId("onboarding-baseline-resolve").click();
    await page.waitForURL(new RegExp(`/runs/${baselineId}\\?resolve=1`));
    await expect(page.getByTestId("baseline-run-card")).toContainText(path.basename(BOARD));
    const dialog = page.getByTestId("resolve-run");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("İçe aktarılan programı koruyarak çöz");
    await pickSegment(page, "Önce en çok ders", dialog);
    await expect(dialog.getByTestId("resolve-relax-desc")).toContainText("Önce en çok ders yerleşir");
    const post = page.waitForRequest((r) => r.method() === "POST" && /\/api\/v1\/runs$/.test(r.url()));
    await dialog.getByTestId("resolve-run-start").click();
    expect(jsonBody(await post)).toMatchObject({ parent_run_id: baselineId, kind: "COURSE", params: { stability: true, relaxation_policy: "most_classes_first" } });
    await page.waitForURL((u) => /\/runs\/\d+$/.test(u.pathname) && !u.pathname.endsWith(`/${baselineId}`), { timeout: 30_000 });
    childId = Number(new URL(page.url()).pathname.split("/").pop());
    const child = await api<{ parent_run_id: number; params: { relaxation_policy?: string } }>(page, `/runs/${childId}`);
    expect(child.parent_run_id).toBe(baselineId);
    expect(child.params.relaxation_policy).toBe("most_classes_first");
  } finally {
    // leave the e2e backend as the other specs expect it: no extra solver run, no baseline run this spec made
    await page.evaluate(
      async ({ child, base, drop }) => {
        if (child) await fetch(`/api/v1/runs/${child}`, { method: "DELETE" });
        if (drop && base) await fetch(`/api/v1/runs/${base}`, { method: "DELETE" });
      },
      { child: childId, base: baselineId, drop: created },
    );
  }
});

test("AI rows: the exam sheet printed to PDF is read by the model and every row waits for a decision", async ({ page }) => {
  test.skip(process.env.E2E_ANTHROPIC_KEY_CONFIGURED !== "1", "AI rows path skipped: no Anthropic API key is configured on the e2e backend (set E2E_ANTHROPIC_KEY_CONFIGURED=1 on a backend with a key and Settings › AI intake on)");
  test.setTimeout(8 * 60_000);
  await login(page);
  await page.goto("/onboarding");
  // final_exams_sheet.pdf: one real sheet of the owner's final-exam list printed to PDF (tests/fixtures/universal)
  await page.getByTestId("onboarding-input").setInputFiles(path.join(FIXTURES, "universal", "final_exams_sheet.pdf"));
  await page.getByTestId("onboarding-start").click();
  const rows = page.getByTestId("onboarding-rows");
  await expect(rows).toBeVisible({ timeout: LONG });
  await expect(rows.getByTestId("rows-pending")).toContainText(/\d+ satır bekliyor/);
  await expect(rows.getByTestId("council-row").first()).toBeVisible();
});
