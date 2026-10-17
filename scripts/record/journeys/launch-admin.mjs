// Launch video, chapter 7: what an administrator runs the platform with (wave 3): the AI console (providers and
// models chosen by admins, token usage per user with limits, the guardrails) and the operations panel (service
// health, the error log). The page change in the middle happens off camera (Recorder.cut).
import { tr } from "./_shared.mjs";

export default {
  id: "launch-admin",
  title: "Admin: the AI usage console and the operations panel",
  db: "seeded",
  role: "admin",
  verified: false,
  async setup({ page }) {
    await page.goto("/admin/ai");
    await page.getByTestId("ai-admin").waitFor({ timeout: 30_000 });
    await page.waitForLoadState("networkidle").catch(() => undefined);
  },
  async run(rec, ctx) {
    const { page } = rec;
    await rec.step(tr(ctx, "Admins pick the AI provider and model for each feature, and see who used how many tokens", "Yöneticiler her özellik için sağlayıcıyı ve modeli seçer, kimin ne kadar token kullandığını görür"), async () => {
      await rec.frame(page.getByTestId("ai-overview"), { dwell: 900 });
      await rec.click(page.getByTestId("ai-tab-limits"), { after: 900 });
      await rec.frame(page.getByTestId("ai-limits"), { dwell: 1100 });
    }, { hold: 300 });
    await rec.step(tr(ctx, "Guardrails keep the models on scheduling: injection and off-topic requests are refused", "Korumalar modelleri planlamada tutar: enjeksiyon ve konu dışı istekler reddedilir"), async () => {
      await rec.click(page.getByTestId("ai-tab-guard"), { after: 900 });
      await rec.frame(page.getByTestId("ai-guard"), { dwell: 1300 });
    }, { hold: 300 });
    await rec.cut(async () => {
      await page.goto("/admin/ops");
      await page.getByTestId("ops-panel").waitFor({ timeout: 30_000 });
      await page.waitForLoadState("networkidle").catch(() => undefined);
    });
    await rec.step(tr(ctx, "The operations panel: service health, metrics and the error log in one place", "Operasyon paneli: servis sağlığı, metrikler ve hata kaydı tek yerde"), async () => {
      await rec.frame(page.locator('[data-testid^="ops-card-"]').first(), { dwell: 1100 });
      const errors = page.getByTestId("ops-errors");
      if (await errors.isVisible().catch(() => false)) await rec.frame(errors, { dwell: 1300 });
    }, { hold: 900, poster: true });
  },
};
