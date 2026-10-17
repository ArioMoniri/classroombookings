// Sample journey (used to test the pipeline): sign in → dashboard.
import { tr } from "./_shared.mjs";

export default {
  id: "login-dashboard",
  title: "Sign in and read the dashboard",
  db: "seeded",
  role: "admin",
  verified: "2026-10-15 on the real backend (snapshot 52f96d4)",
  async setup({ page }) {
    await page.goto("/login");
    await page.getByTestId("login-submit").waitFor();
  },
  async run(rec, ctx) {
    const { page } = rec;
    await rec.step(tr(ctx, "Sign in with your planner account", "Planlamacı hesabınızla giriş yapın"), async () => {
      await rec.type(page.getByTestId("login-identifier"), ctx.creds.email);
      await rec.type(page.getByTestId("login-password"), ctx.creds.password, { delay: 35 });
      await rec.click(page.getByTestId("login-submit"), { after: 200 });
      await page.getByTestId("dashboard-hero").waitFor({ timeout: 30_000 });
    }, { clip: "dashboard" });
    await rec.step(tr(ctx, "The dashboard shows this term at a glance", "Pano, dönemin özetini gösterir"), async () => {
      // wait for the real numbers (tiles count up, the heatmap loads after the tiles)
      await page.getByText(/^(Mon|Pzt)$/).first().waitFor({ timeout: 30_000 }).catch(() => undefined);
      await rec.wait(900);
    }, { clip: "dashboard", zoom: false, hold: 1000 });
    await rec.step(tr(ctx, "Room use this week, classes that still need a room, requests waiting for review", "Bu haftanın derslik kullanımı, yer bekleyen dersler, inceleme bekleyen talepler"), async () => {
      const tile = page.getByTestId("dashboard-hero");
      await rec.moveOnto(tile);
      await rec.frame(tile, { dwell: 1800 });
    }, { hold: 600, poster: true });
    await rec.step(tr(ctx, "Room use by building and day, from the published board", "Bina ve güne göre derslik kullanımı, yayımlanan programdan"), async () => {
      const card = page.getByText(/utilisation by building|bina/i).first()
        .locator("xpath=ancestor::*[contains(@class,'rounded')][1]");
      await rec.moveOnto(card, { at: [0.3, 0.45] });
      await rec.frame(card, { dwell: 1800 });
    }, { hold: 1200 });
  },
};
