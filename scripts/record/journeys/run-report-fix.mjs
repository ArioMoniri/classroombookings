// Journey 3: read the run report and apply a suggested fix to one diagnosis.
import { findRun, termId, tr } from "./_shared.mjs";

export default {
  id: "run-report-fix",
  title: "Read the run report and apply a fix",
  db: "seeded",
  role: "admin",
  verified: false,
  async setup({ page, termCode }) {
    const tid = await termId(page, termCode);
    // a run with diagnoses: a solver run of week 3 (best-effort partial on the real data)
    let run = await findRun(page, tid, { statuses: ["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL", "INFEASIBLE"], withDiagnoses: true });
    if (!run) throw new Error("no run with diagnoses: create one first (README: POST /runs week 3) or record generator-studio");
    this.runId = run.id;
    await page.goto(`/runs/${run.id}`);
    await page.getByTestId("run-view").waitFor({ timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    await rec.step(tr(ctx, "The run report explains what could not be placed, and why", "Çalıştırma raporu neyin neden yerleşmediğini açıklar"), async () => {
      const tab = page.getByTestId("tab-report");
      if (await tab.isVisible().catch(() => false)) await rec.click(tab);
      await rec.frame(page.getByTestId("diagnosis-card").first(), { dwell: 1800 });
    });
    await rec.step(tr(ctx, "Pick a suggestion and apply it", "Bir öneri seçip uygulayın"), async () => {
      const card = page.getByTestId("diagnosis-card").filter({ has: page.getByTestId("diagnosis-apply") }).first();
      const option = card.getByTestId("diagnosis-fix-option").first();
      if (await option.isVisible().catch(() => false)) await rec.click(option);
      await rec.click(card.getByTestId("diagnosis-apply"));
      await page.locator("[data-sonner-toast]").first().waitFor({ timeout: 30_000 }).catch(() => undefined);
    }, { hold: 1600, poster: true });
  },
};
