// Sample journey (used to test the pipeline): sign in → dashboard.
import { tr } from "./_shared.mjs";

export default {
  id: "login-dashboard",
  title: "Sign in and read the dashboard",
  db: "seeded",
  role: "admin",
  verified: "2026-10-08 against the pre-redesign UI",
  async setup({ page }) {
    await page.goto("/login");
    await page.getByTestId("login-submit").waitFor();
  },
  async run(rec, ctx) {
    const { page } = rec;
    await rec.step(tr(ctx, "Sign in with your planner account", "Planlamacı hesabınızla giriş yapın"), async () => {
      await rec.type(page.getByLabel(/E-posta|E-mail/i).first(), ctx.creds.email);
      await rec.type(page.getByLabel(/Şifre|Password/i).first(), ctx.creds.password, { delay: 35 });
      await rec.click(page.getByTestId("login-submit"), { after: 200 });
      await page.getByTestId("dashboard").waitFor({ timeout: 30_000 });
    });
    await rec.step(tr(ctx, "The dashboard shows this term at a glance", "Pano, dönemin özetini gösterir"), async () => {
      // wait for the real numbers (tiles count up, the heatmap loads after the tiles)
      await page.getByText(/^(Mon|Pzt)$/).first().waitFor({ timeout: 30_000 }).catch(() => undefined);
      await rec.wait(900);
    }, { zoom: false, hold: 1000 });
    await rec.step(tr(ctx, "Requests that need review are one click away", "İncelenecek talepler bir tık uzakta"), async () => {
      const tile = page.getByTestId("dashboard").getByText(/needs review|incelenecek|inceleme/i).first()
        .locator("xpath=ancestor::*[contains(@class,'rounded')][1]");
      await rec.moveOnto(tile);
      await rec.frame(tile, { dwell: 1800 });
    }, { hold: 600, poster: true });
    await rec.step(tr(ctx, "Room use by building and day, from the published board", "Bina ve güne göre derslik kullanımı, yayımlanan programdan"), async () => {
      const card = page.getByText(/utilisation by building|binalara göre|bina bazında/i).first()
        .locator("xpath=ancestor::*[contains(@class,'rounded')][1]");
      await rec.moveOnto(card, { at: [0.3, 0.45] });
      await rec.frame(card, { dwell: 1800 });
    }, { hold: 1200 });
  },
};
