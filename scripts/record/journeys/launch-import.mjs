// Launch video, chapter 1: the import page takes the planning office's own workbooks. The take shows the kinds of
// workbook it reads, then a room master upload whose changes are listed before anything is saved (nothing is
// applied: the take never presses Apply, so the stack's data stays as imported).
import { FIXTURES, tr } from "./_shared.mjs";
import { resolve } from "node:path";

export default {
  id: "launch-import",
  title: "Import: the workbook kinds, and a room master checked before it is applied",
  db: "seeded",
  role: "admin",
  verified: false,
  async setup({ page }) {
    await page.goto("/import");
    await page.getByTestId("import-kind-room-master").waitFor({ timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    await rec.step(tr(ctx, "Weekly grids, planning lists, exam lists, the room master: the files the office already keeps", "Haftalık çizelgeler, planlama listeleri, sınav listeleri, derslik ana listesi"), async () => {
      await rec.frame(page.getByTestId("import-kind-planning-list"), { dwell: 700 });
      await rec.moveOnto(page.getByTestId("import-kind-exam-list"));
      await rec.wait(500);
      await rec.moveOnto(page.getByTestId("import-kind-weekly-grid"));
      await rec.wait(500);
    }, { hold: 400 });
    await rec.step(tr(ctx, "Drop the room master: every change is listed before it is saved", "Derslik ana listesini bırakın: her değişiklik kaydetmeden önce listelenir"), async () => {
      await rec.click(page.getByTestId("import-kind-room-master"), { after: 600 });
      const input = page.locator('[data-testid="room-master-import"] input[type="file"]').first();
      await input.waitFor({ state: "attached", timeout: 20_000 });
      await rec.moveOnto(page.getByTestId("import-dropzone"));
      await input.setInputFiles(resolve(FIXTURES, "room_master.csv"));
      await page.getByTestId("room-master-counts").waitFor({ timeout: 30_000 });
      await rec.frame(page.getByTestId("room-master-counts"), { dwell: 1600 });
      const row = page.locator('[data-testid="rm-row-changed"], [data-testid="rm-row-unmatched"]').first();
      if (await row.isVisible().catch(() => false)) await rec.frame(row, { dwell: 1400 });
    }, { hold: 900, poster: true });
  },
};
