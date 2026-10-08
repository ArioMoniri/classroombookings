// Generator Studio: add a rule from a template (a sentence with blanks), then let the pre-check find
// problems in the real data and apply one of its fixes.
// Plain-language rules ("write it in your own words") need an Anthropic API key in Settings → AI; the
// recording stack has none, so this journey uses the template path, which works without AI.
import { tr } from "./_shared.mjs";

export default {
  id: "studio-rule-fix",
  title: "Generator Studio: add a rule, then fix what the pre-check finds",
  db: "seeded",
  role: "admin",
  verified: "2026-10-08 against the Liquid Glass v2 UI and the real backend",
  async setup({ page }) {
    await page.goto("/generate");
    await page.getByTestId("generate").waitFor({ timeout: 30_000 });
    await page.getByTestId("rail-step-rules").click();
    await page.getByTestId("rules-step").waitFor({ timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    const gallery = page.getByTestId("template-gallery");
    await rec.step(tr(ctx, "Rules are sentences: start from a template", "Kurallar birer cümledir: bir şablonla başlayın"), async () => {
      await rec.click(page.getByTestId("add-template"));
      await gallery.waitFor();
      await rec.click(gallery.getByTestId("template-same_room_every_week"));
      await gallery.getByTestId("rule-builder").waitFor();
    });
    await rec.step(tr(ctx, "Fill in the blanks; the preview counts the classes it affects", "Boşlukları doldurun; önizleme etkilenen dersleri sayar"), async () => {
      await rec.frame(gallery.getByTestId("rule-builder"), { dwell: 1800 });
      await rec.click(gallery.getByTestId("builder-add"));
      await gallery.waitFor({ state: "hidden", timeout: 20_000 });
      await rec.frame(page.getByTestId("rule-group-must"), { dwell: 1200 });
    });
    await rec.step(tr(ctx, "The pre-check tests the plan against the data before solving", "Ön kontrol, çözmeden önce planı verilerle sınar"), async () => {
      await rec.click(page.getByTestId("rail-step-check"));
      await page.getByTestId("check-step").waitFor();
      const done = page.locator("[data-testid=check-step] [data-testid=readiness]:not([data-readiness=checking]):not([data-readiness=unknown])");
      // the automatic check after a change does not always start (see the hand-off): ask for one
      if (!(await done.waitFor({ timeout: 4_000 }).then(() => true, () => false))) {
        await rec.click(page.getByTestId("recheck"));
        await rec.cut(() => done.waitFor({ timeout: 180_000 }));
      }
      await rec.frame(page.getByTestId("check-step"), { dwell: 1400 });
    }, { zoom: false });
    await rec.step(tr(ctx, "Each problem names the classes involved and offers fixes", "Her sorun ilgili dersleri adlandırır ve düzeltme önerir"), async () => {
      const card = page.getByTestId("issue-card").filter({ has: page.getByTestId("fix-button") }).first();
      await card.scrollIntoViewIfNeeded();
      await rec.frame(card, { dwell: 1500 });
      await rec.click(card.getByTestId("fix-button").first());
      await page.locator("[data-sonner-toast]").first().waitFor({ timeout: 30_000 }).catch(() => undefined);
      await rec.wait(1200);
    }, { hold: 1500, poster: true });
  },
};
