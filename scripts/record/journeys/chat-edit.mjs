// Journey 5: edit the timetable by chat (needs an Anthropic API key in Settings → AI, or the
// backend's ANTHROPIC_API_KEY). Proposal → apply.
import { findRun, termId, tr } from "./_shared.mjs";

export default {
  id: "chat-edit",
  title: "Chat edit",
  db: "seeded",
  role: "admin",
  verified: false,
  requires: ["AI key configured in the backend (Settings → AI)"],
  async setup({ page, termCode }) {
    const tid = await termId(page, termCode);
    const run = await findRun(page, tid);
    if (!run) throw new Error("no feasible COURSE run");
    await page.goto(`/runs/${run.id}`);
    await page.getByTestId("chat-panel").first().waitFor({ timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    const panel = page.getByTestId("chat-panel").first();
    await rec.step(tr(ctx, "Ask for a change in your own words", "Değişikliği kendi cümlelerinizle isteyin"), async () => {
      await rec.type(panel.getByTestId("chat-input"), tr(ctx, "Move ACU244 to Friday morning, same room if possible", "ACU244'ü cuma sabahına al, mümkünse aynı derslikte"), { delay: 38 });
      await rec.click(panel.getByTestId("chat-send"));
    });
    await rec.step(tr(ctx, "The assistant proposes a checked change", "Asistan kontrol edilmiş bir değişiklik önerir"), async () => {
      const card = panel.getByTestId("proposal-card").first();
      await card.waitFor({ timeout: 120_000 });
      await rec.frame(card, { dwell: 1800 });
    });
    await rec.step(tr(ctx, "Apply it, or undo with one click", "Uygulayın, ya da tek tıkla geri alın"), async () => {
      await rec.click(panel.getByTestId("proposal-apply").first());
      await panel.getByTestId("proposal-undo").first().waitFor({ timeout: 30_000 }).catch(() => undefined);
    }, { hold: 1600, poster: true });
  },
};
