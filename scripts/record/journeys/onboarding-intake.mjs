// Onboarding (universal intake) on an empty instance: drop the real Final 2026 exam planning workbook, the
// structured readers detect what it is and propose a term (AI off), review what needs a decision, commit.
// The two term planning lists (Bahar, Güz) are refused by onboarding's size guard on this build ("16376 columns,
// limit 1024": their sheets declare a full-width range), so the exam planning list is the one that goes through.
// Needs `scripts/record/stack.sh up --fresh`. KVKK: the review names instructors ("Same instructor?"), so the
// review answer is held until the database is masked (maskBeforeShowing); the wait is cut from the video.
// No camera zoom: the page scrolls through the drop zone, the review and the commit, and every camera move on top of
// a scroll would cost the GIF a few MB.
import { FIXTURES, maskBeforeShowing, tr } from "./_shared.mjs";

const FILE = "final_planlama_listesi_2026_v2.xlsx";

export default {
  id: "onboarding-intake",
  title: "Onboarding: drop a planning workbook, review, commit",
  db: "fresh",
  // Playwright's own video: Chrome's screencast stalls while a large workbook is uploaded and imported (no frames for
  // half a minute, then a burst), which breaks the clock mapping of the cuts
  capture: "video",
  role: "admin",
  verified: "2026-10-15 on the real backend (snapshot 6c4b790)",
  async setup({ page }) {
    await maskBeforeShowing(page, "**/api/v1/council/jobs/*/review", () => true);
    await page.goto("/onboarding");
    await page.getByTestId("onboarding-drop").waitFor({ timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    const drop = page.getByTestId("onboarding-drop");
    await rec.step(tr(ctx, "Drop the planning office's workbook; AI off, structured readers only", "Planlama ofisinin çalışma kitabını bırakın; yapay zekâ kapalı, yalnızca yapısal okuyucular"), async () => {
      await rec.moveOnto(drop.getByRole("button").first());
      await page.getByTestId("onboarding-input").setInputFiles(`${FIXTURES}/${FILE}`);
      await rec.wait(500);
      const ai = drop.locator('input[type="checkbox"]').first();
      if (await ai.isChecked()) await rec.click(ai, { after: 300 });
      await rec.frame(drop, { dwell: 700 });
    }, { zoom: false });
    await rec.step(tr(ctx, "It is read and classified, and a term is proposed (waiting skipped)", "Okunur, sınıflanır ve bir dönem önerilir (bekleme atlandı)"), async () => {
      await rec.click(page.getByTestId("onboarding-start"));
      await rec.cut(() => page.getByTestId("onboarding-review").waitFor({ timeout: 300_000 }));
      await rec.frame(page.getByTestId("onboarding-progress"), { dwell: 900 });
    }, { clip: "onboarding", zoom: false });
    const review = page.getByTestId("onboarding-review");
    await rec.step(tr(ctx, "Review only what needs a decision", "Yalnızca karar gerekenleri inceleyin"), async () => {
      await review.scrollIntoViewIfNeeded();
      await rec.frame(review, { dwell: 1200 });
      const accept = review.getByRole("button", { name: /Accept all|Tümünü kabul/i }).first();
      if (await accept.isVisible().catch(() => false)) {
        await rec.click(accept);
        await review.getByTestId("blocking-count").filter({ hasText: /^0|: 0| 0 / }).waitFor({ timeout: 20_000 }).catch(() => undefined);
      }
    }, { clip: "onboarding", zoom: false, poster: true });
    await rec.step(tr(ctx, "Commit: the term and its exam requests are created", "Kaydedin: dönem ve sınav talepleri oluşturulur"), async () => {
      const commit = page.getByTestId("onboarding-commit-button");
      await commit.scrollIntoViewIfNeeded();
      await rec.click(commit);
      await rec.cut(() => page.getByTestId("onboarding-result").waitFor({ timeout: 300_000 }));
      await rec.frame(page.getByTestId("onboarding-result"), { dwell: 1600 });
    }, { clip: "onboarding", zoom: false, hold: 900 });
  },
};
