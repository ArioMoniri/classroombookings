// Admin: create an account in Setup → Users and pick its role. The role picker offers only roles whose
// permissions the signed-in administrator holds (no privilege escalation).
// The account is a functional one (the planning office), not an invented person.
import { api, tr } from "./_shared.mjs";

const ACCOUNT = { username: "planlama", email: "planlama@smartsched.local", first: "Planlama", last: "Ofisi", password: "Planlama-2026!" };

export default {
  id: "admin-user",
  title: "Create a user and pick a role",
  db: "seeded",
  role: "admin",
  verified: "2026-10-08 against the Liquid Glass v2 UI and the real backend",
  async setup({ page }) {
    // idempotent: remove the account from an earlier take
    const found = await api(page, `/users/search?q=${ACCOUNT.username}`);
    for (const u of found.data?.items ?? []) if (u.username === ACCOUNT.username) await api(page, `/users/${u.id}`, { method: "DELETE" });
    await page.goto("/admin/users");
    await page.getByTestId("users-table").waitFor({ timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    const dialog = page.getByTestId("user-dialog");
    await rec.step(tr(ctx, "Setup → Users lists every account with its role", "Kurulum → Kullanıcılar tüm hesapları rolleriyle listeler"), async () => {
      await rec.frame(page.getByTestId("users-table"), { dwell: 1200 });
    }, { zoom: false, hold: 400 });
    await rec.step(tr(ctx, "Add an account for the planning office", "Planlama ofisi için bir hesap ekleyin"), async () => {
      await rec.click(page.getByTestId("users-new"));
      await dialog.waitFor();
      await rec.type(dialog.locator("#u-username"), ACCOUNT.username, { delay: 60 });
      await rec.type(dialog.locator("#u-email"), ACCOUNT.email, { delay: 30 });
      await rec.type(dialog.locator("#u-first"), ACCOUNT.first, { delay: 50 });
      await rec.type(dialog.locator("#u-last"), ACCOUNT.last, { delay: 50 });
    });
    await rec.step(tr(ctx, "Pick the role; roles with rights you lack are greyed out", "Rolü seçin; sizde olmayan yetkileri içeren roller pasiftir"), async () => {
      const role = dialog.locator("#u-role");
      await rec.moveOnto(role);
      await rec.frame(role, { dwell: 500 });
      const value = await role.evaluate((el) => [...el.options].find((o) => /planner|planlamac/i.test(o.textContent ?? ""))?.value ?? "");
      await role.selectOption(value || { index: 2 });
      await rec.wait(900);
      await rec.type(dialog.locator("#u-password"), ACCOUNT.password, { delay: 35 });
    });
    await rec.step(tr(ctx, "Save: the account can sign in straight away", "Kaydedin: hesap hemen giriş yapabilir"), async () => {
      await rec.click(dialog.getByTestId("user-save"));
      await dialog.waitFor({ state: "hidden", timeout: 20_000 });
      await rec.type(page.getByTestId("users-search"), ACCOUNT.username, { delay: 70 });
      await page.locator(`[data-username="${ACCOUNT.username}"]`).first().waitFor({ timeout: 20_000 });
      await rec.frame(page.locator(`[data-username="${ACCOUNT.username}"]`).first(), { dwell: 1400 });
    }, { hold: 1400, poster: true });
  },
};
