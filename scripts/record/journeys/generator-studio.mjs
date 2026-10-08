// Journey 2: Generator Studio end to end — scope → classes → rules (plain-language rule) → pre-check
// (apply a fix) → generate → result.
import { tr } from "./_shared.mjs";
import { pick } from "../lib/recorder.mjs";

export default {
  id: "generator-studio",
  title: "Generator Studio end to end",
  db: "seeded",
  role: "admin",
  verified: false,
  async setup({ page }) {
    await page.goto("/generate");
    await page.getByTestId("generate").waitFor({ timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    const goto = async (s) => rec.click(await pick(page, [page.getByTestId(`rail-step-${s}`), page.getByTestId(`tab-step-${s}`)]));
    await rec.step(tr(ctx, "Choose what to schedule: one week of courses", "Ne planlanacağını seçin: bir haftalık dersler"), async () => {
      await goto("scope");
      await rec.frame(page.getByTestId("scope-step"), { dwell: 600 });
      const week = page.getByTestId("scope-horizon").getByRole("radio").first();
      if (await week.isVisible().catch(() => false)) await rec.click(week);
    });
    await rec.step(tr(ctx, "Review the classes that will be placed", "Yerleştirilecek dersleri gözden geçirin"), async () => {
      await goto("classes");
      await rec.type(page.getByTestId("class-search"), "ACU", { delay: 90 });
      await rec.frame(page.getByTestId("class-table"), { dwell: 1200 });
    });
    await rec.step(tr(ctx, "Write a rule in plain language", "Kuralı düz bir cümleyle yazın"), async () => {
      await goto("rules");
      await rec.type(page.getByTestId("nl-input"), tr(ctx, "No classes on Friday after 16:00 for first-year students", "Birinci sınıflara cuma 16:00'dan sonra ders konmasın"), { delay: 40 });
      await rec.click(page.getByTestId("nl-analyse"));
      const accept = await pick(page, [page.getByTestId("tray-accept"), page.getByTestId("review-accept")], { timeout: 60_000 });
      await rec.click(accept);
    });
    await rec.step(tr(ctx, "The pre-check finds problems and offers fixes", "Ön kontrol sorunları bulur ve düzeltme önerir"), async () => {
      await goto("check");
      const fix = page.getByTestId("fix-button").first();
      await fix.waitFor({ timeout: 60_000 }).catch(() => undefined);
      if (await fix.isVisible().catch(() => false)) await rec.click(fix);
      else await rec.frame(page.getByTestId("check-step"), { dwell: 1200 });
    });
    await rec.step(tr(ctx, "Generate: the solver builds the timetable", "Oluştur: çözücü ders programını kurar"), async () => {
      await goto("generate");
      await rec.click(await pick(page, [page.getByTestId("bar-generate"), page.getByTestId("summary-generate"), page.getByTestId("inline-generate")]));
      await page.getByTestId("run-result").waitFor({ timeout: 180_000 });
      await rec.frame(page.getByTestId("run-result"), { dwell: 1800 });
    }, { hold: 1600, poster: true });
  },
};
