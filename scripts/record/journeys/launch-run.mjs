// Launch video, chapters 2-4: a real solver run of the whole Güz term. The run page says every hard rule was kept,
// the report explains each class that could not be placed and what would fix it, and the planner publishes it.
// The setup needs a finished, not yet published full-term run: it takes the newest one, or starts one through the
// public API (POST /runs, what the Generate button sends; 4 min) when every term run is already published.
// Steps (story.mjs cuts them by index): 0 open the run, 1 verdict, 2 report, 3 a fix, 4 publish dialog, 5 published.
import { api, termId, tr } from "./_shared.mjs";

const OK = ["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL"];

export default {
  id: "launch-run",
  title: "Solver run: every hard rule kept, the report, publish",
  db: "seeded",
  role: "admin",
  verified: false,
  async setup({ page }) {
    const tid = await termId(page, process.env.REC_RUN_TERM ?? "2026-GUZ");
    const list = async () => ((await api(page, `/runs?term_id=${tid}`)).data ?? []).filter((r) => r.kind === "COURSE" && OK.includes(r.status)).sort((a, b) => (a.horizon === "TERM" ? 0 : 1) - (b.horizon === "TERM" ? 0 : 1));
    // a solver run (an imported board is a run too, label "Grid import: …"), finished, not the published one
    // hard score 100 = every hard rule held (a run that breaks one cannot be published: publish_guard)
    let run = (await list()).find((r) => !r.is_active && (r.placed ?? 0) > 0 && (r.hard_score ?? 0) >= 100 && !/^Grid import/i.test(r.label ?? ""));
    if (!run) {
      const made = await api(page, "/runs", { method: "POST", body: { term_id: tid, kind: "COURSE", horizon: "TERM", label: "Güz full term", horizon_params: {}, params: { time_limit_s: Number(process.env.REC_RUN_LIMIT ?? 240) } } });
      if (made.status >= 400) throw new Error(`POST /runs: ${made.status} ${JSON.stringify(made.data)}`);
      const id = made.data.run_id;
      for (;;) {
        const r = (await api(page, `/runs/${id}`)).data;
        if (!["QUEUED", "RUNNING", "PENDING"].includes(r?.status)) break;
        await page.waitForTimeout(5000);
      }
      run = { id };
    }
    this.runId = run.id;
    await page.goto("/runs");
    await page.getByTestId("runs").waitFor({ timeout: 30_000 });
    await page.waitForLoadState("networkidle").catch(() => undefined);
  },
  async run(rec, ctx) {
    const { page } = rec;
    const view = page.getByTestId("run-view");
    await rec.step(tr(ctx, "A real solver run on the autumn term's data", "Gerçek veriyle tüm güz dönemi için bir çözücü çalıştırması"), async () => {
      const link = page.locator(`a[href$="/runs/${this.runId}"]`).first();
      await rec.click(link, { after: 300 });
      await view.waitFor({ timeout: 30_000 });
      await page.waitForLoadState("networkidle").catch(() => undefined);
    }, { hold: 300 });
    await rec.step(tr(ctx, "Hard rules held: every exception is one the planning list asked for, named and counted", "Her katı kural korunur: çakışma yok, küçük derslik yok, aynı anda iki ders yok"), async () => {
      await rec.frame(page.getByTestId("run-verdict"), { dwell: 1500 });
      const kpi = page.locator('[data-testid^="kpi-"]').first();
      if (await kpi.isVisible().catch(() => false)) await rec.frame(kpi, { dwell: 900 });
    }, { hold: 500, poster: true });
    await rec.step(tr(ctx, "The report lists each class that could not be placed, and why", "Rapor yerleşmeyen her dersi ve nedenini listeler"), async () => {
      const tab = page.getByTestId("tab-report");
      if (await tab.isVisible().catch(() => false)) await rec.click(tab, { after: 700 });
      const sec = page.getByTestId("unplaced-section");
      if (await sec.isVisible().catch(() => false)) await rec.frame(sec, { dwell: 1200 });
      await rec.frame(page.getByTestId("diagnosis-card").first(), { dwell: 1300 });
    }, { hold: 300 });
    await rec.step(tr(ctx, "Each comes with concrete fixes: a free room and time, and what else would move", "Ve neyin düzelteceğini: daha büyük derslik, başka gün, bölme"), async () => {
      const opt = page.getByTestId("diagnosis-fix-option").first();
      if (await opt.isVisible().catch(() => false)) await rec.click(opt, { after: 900 });
      else await rec.frame(page.getByTestId("diagnosis-card").first(), { dwell: 1200 });
    }, { hold: 600 });
    await rec.step(tr(ctx, "Publish: the dialog says what is left out before anyone sees the plan", "Yayınlayın: plan görünmeden önce neyin dışarıda kaldığı söylenir"), async () => {
      const btn = page.getByTestId("run-publish");
      await rec.click(btn, { after: 800 });
      for (const id of ["publish-partial-ack", "publish-scope-ack"]) {
        const box = page.getByTestId(id);
        if (await box.isVisible().catch(() => false)) await rec.click(box, { after: 500 });
      }
      const confirm = page.locator('[data-testid="publish-confirm"], [data-testid="publish-confirm-reduction"]').first();
      await rec.click(confirm, { after: 300 });
    }, { hold: 200 });
    await rec.step(tr(ctx, "Published: bookings, calendars and the dashboard now follow this plan", "Yayınlandı: rezervasyonlar, takvimler ve pano artık bu planı izler"), async () => {
      await page.getByTestId("run-published").waitFor({ timeout: 60_000 });
      await rec.frame(page.getByTestId("run-published"), { dwell: 1600 });
    }, { hold: 600 });
  },
};
