// From empty to a timetable: import the planning office's two real Bahar 2026 workbooks (weekly room grid,
// then the planning list), generate one week in the Generator Studio, and open the run report.
// Needs `scripts/record/stack.sh up --fresh` (admin + an empty 2026-BAHAR term). Waits for the import jobs
// and the solver are cut from the video (Recorder.cut); the captions say so.
import { FIXTURES, tr } from "./_shared.mjs";

const WEEK = 3;
const files = [
  { kind: "weekly-grid", file: "bahar_derslikler_takvimi_2026.xlsx", en: "Import the weekly room grid workbook", tr: "Haftalık derslik takvimini içe aktarın" },
  { kind: "planning-list", file: "bahar_derslik_planlama_listesi_v5.xlsx", en: "Then the planning list with every section", tr: "Ardından tüm şubeleri içeren planlama listesini" },
];

export default {
  id: "import-generate",
  title: "Import the planning files, generate a week, read the report",
  db: "fresh",
  role: "admin",
  verified: "2026-10-08 against the Liquid Glass v2 UI and the real backend",
  async setup({ page }) {
    await page.goto("/import");
    await page.getByTestId("import").waitFor({ timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    for (const [i, f] of files.entries()) {
      if (i > 0) {
        await page.goto("/import");
        await page.getByTestId(`import-kind-${f.kind}`).waitFor();
      }
      await rec.step(tr(ctx, f.en, f.tr), async () => {
        await rec.click(page.getByTestId(`import-kind-${f.kind}`));
        const drop = page.getByTestId("import-dropzone");
        await rec.moveOnto(drop);
        await page.getByTestId("file-input").setInputFiles(`${FIXTURES}/${f.file}`);
        await rec.frame(drop, { dwell: 900 });
        await rec.click(page.getByTestId("import-start"));
        await rec.cut(() => page.getByTestId("import-report").waitFor({ timeout: 180_000 }));
      });
      await rec.step(tr(ctx, "The import report: rows read, rows skipped and why", "İçe aktarma raporu: okunan, atlanan satırlar ve nedenleri"), async () => {
        await rec.frame(page.getByTestId("import-report"), { dwell: 1800 });
      }, { zoom: false, hold: 600 });
    }
    await rec.step(tr(ctx, "Generator Studio: plan week 3 of the term", "Oluşturma Stüdyosu: dönemin 3. haftasını planlayın"), async () => {
      await rec.click(page.getByTestId("nav-generate"));
      await page.getByTestId("scope-step").waitFor({ timeout: 30_000 });
      await rec.click(page.getByTestId("horizon-WEEK"));
      const week = page.getByTestId(`week-${WEEK}`);
      if (await week.isVisible().catch(() => false)) await rec.click(week);
      await rec.frame(page.getByTestId("scope-sentence"), { dwell: 1200 });
    });
    await rec.step(tr(ctx, "The pre-check warns before solving: some classes cannot fit", "Ön kontrol çözmeden önce uyarır: bazı dersler sığamaz"), async () => {
      await rec.click(page.getByTestId("summary-generate"));
      const anyway = page.getByRole("button", { name: /generate anyway|yine de oluştur/i });
      if (await anyway.waitFor({ timeout: 6_000 }).then(() => true, () => false)) {
        await rec.frame(page.getByRole("dialog").or(page.getByRole("alertdialog")).first(), { dwell: 1800 });
        await rec.click(anyway);
      }
    });
    await rec.step(tr(ctx, "Generate anyway to get the full diagnosis (solving time skipped)", "Yine de oluşturun, tam tanı için (çözüm süresi atlandı)"), async () => {
      await rec.cut(() => page.getByTestId("run-open-report").first().waitFor({ timeout: 300_000 }));
      await rec.frame(page.getByTestId("run-result").first(), { dwell: 1500 });
    });
    await rec.step(tr(ctx, "The run report: every placed class keeps every hard rule", "Çalıştırma raporu: yerleşen her ders tüm zorunlu kurallara uyar"), async () => {
      await rec.click(page.getByTestId("run-open-report").first());
      await page.getByTestId("run-hero").waitFor({ timeout: 30_000 });
      await rec.frame(page.getByTestId("run-hero"), { dwell: 2000 });
    }, { hold: 600, poster: true });
    await rec.step(tr(ctx, "What could not be placed is listed with the reason and fixes", "Yerleşemeyenler nedeni ve düzeltmeleriyle listelenir"), async () => {
      const card = page.getByTestId("diagnosis-card").first();
      await card.scrollIntoViewIfNeeded();
      await rec.frame(card, { dwell: 2200 });
    }, { hold: 1200 });
  },
};
