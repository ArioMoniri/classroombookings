// Journey 1: import the planning files (weekly grid, then the planning list) into an empty term.
// Needs `scripts/record/stack.sh up --fresh` (admin + empty 2026-BAHAR term, no data).
import { FIXTURES, tr } from "./_shared.mjs";
import { pick } from "../lib/recorder.mjs";

const files = [
  { kind: "weekly-grid", file: "bahar_derslikler_takvimi_2026.xlsx", en: "Upload the weekly room grid", tr: "Haftalık derslik takvimini yükleyin" },
  { kind: "planning-list", file: "bahar_derslik_planlama_listesi_v5.xlsx", en: "Then the planning list with every section", tr: "Ardından tüm şubeleri içeren planlama listesini" },
];

export default {
  id: "import-planning",
  title: "Import the planning files",
  db: "fresh",
  role: "admin",
  verified: false,
  async setup({ page }) {
    await page.goto("/import");
    await page.getByTestId("import").waitFor({ timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    for (const [i, f] of files.entries()) {
      if (i > 0) {
        await page.goto("/import");
        await page.getByTestId("import").waitFor();
      }
      await rec.step(tr(ctx, f.en, f.tr), async () => {
        await rec.click(await pick(page, [page.getByTestId(`import-kind-${f.kind}`), page.getByRole("button", { name: f.kind === "weekly-grid" ? /takvim|grid/i : /planlama|planning/i })]));
        const drop = await pick(page, [page.getByTestId("dropzone"), page.getByRole("button", { name: /dosya|file/i })]);
        await rec.moveOnto(drop);
        await page.getByTestId("file-input").setInputFiles(`${FIXTURES}/${f.file}`);
        await rec.frame(drop, { dwell: 900 });
        await rec.click(page.getByTestId("import-start"));
      });
      await rec.step(tr(ctx, "SmartSched reads the workbook and reports what it found", "SmartSched dosyayı okur ve bulduklarını raporlar"), async () => {
        // the import job runs in the background (≈15 s per workbook on the real fixtures)
        await page.getByText(/tamamlandı|completed|done|bitti/i).first().waitFor({ timeout: 120_000 });
        await rec.frame(page.getByTestId("import"), { dwell: 1500 });
      }, { hold: 1600, poster: i === 1 });
    }
  },
};
