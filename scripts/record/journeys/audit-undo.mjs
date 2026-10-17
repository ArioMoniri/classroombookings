// Audit log with undo: an administrator's change to a booking is in Setup → Audit log, with the before/after
// values; Undo puts it back after a confirm. The setup makes the change through the API, as e2e/wave1.spec.ts
// ("audit log") does: a booking (the journey's own note) moved to another free room at the same period, which
// the log records as booking.move (create, series create, move and cancel can be undone).
import { api, cancelMine, dayGrid, freeRun, nextTeachingDay, termId, tr } from "./_shared.mjs";

const NOTE = "Tutorial";

export default {
  id: "audit-undo",
  title: "Audit log: see a change before and after, then undo it",
  db: "seeded",
  role: "admin",
  verified: "2026-10-15 on the real backend (snapshot 6c4b790)",
  async setup({ page }) {
    await cancelMine(page, [NOTE, "Tutorial, both groups"]);
    const rooms = (await api(page, "/room-admin/rooms")).data ?? [];
    const group = rooms.find((r) => r.code.startsWith("C"))?.room_group_id;
    const date = await nextTeachingDay(page);
    const grid = await dayGrid(page, date, group);
    const [slot] = freeRun(grid, 1, { maxPeriod: 4 });
    // another room free at the same period
    const other = grid.slots.find((x) => x.period_id === slot.period_id && x.room_id !== slot.room_id && x.status === "available" && x.allow_single);
    if (!other) throw new Error("no second free room at that period");
    const tid = await termId(page, "2026-GUZ");
    const made = await api(page, "/bookings", { method: "POST", body: { room_id: slot.room_id, date, period_id: slot.period_id, term_id: tid, notes: NOTE } });
    if (made.status >= 400) throw new Error(`booking: ${made.status} ${JSON.stringify(made.data)}`);
    const upd = await api(page, `/bookings/${made.data.id}?scope=one`, { method: "PUT", body: { room_id: other.room_id } });
    if (upd.status >= 400) throw new Error(`booking update: ${upd.status} ${JSON.stringify(upd.data)}`);
    this.bookingId = made.data.id;
    this.roomBefore = slot.room_id;
    await page.goto("/admin/audit");
    await page.getByTestId("audit").waitFor({ timeout: 30_000 });
    await page.getByTestId("audit-list").waitFor({ timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    const view = page.getByTestId("audit");
    await rec.step(tr(ctx, "Every change is logged: show the bookings", "Her değişiklik kayıtlıdır: rezervasyonları gösterin"), async () => {
      const sel = view.getByTestId("audit-entity");
      await rec.moveOnto(sel);
      await sel.selectOption("booking");
      await rec.wait(400);
      await rec.click(view.getByTestId("audit-apply"));
      await view.locator('[data-action="booking.move"]').first().waitFor({ timeout: 20_000 });
    }, { hold: 500 });
    const event = view.locator('[data-action="booking.move"]').first();
    await rec.step(tr(ctx, "Open a change: the value before and after", "Bir değişikliği açın: önceki ve sonraki değer"), async () => {
      await rec.click(event.locator("button[aria-expanded]").first());
      await event.getByTestId("audit-diff").waitFor({ timeout: 20_000 }).catch(() => undefined);
      await rec.frame(event, { dwell: 1300 });
    }, { clip: "audit-undo", poster: true });
    await rec.step(tr(ctx, "Undo moves it back", "Geri al eski yerine taşır"), async () => {
      await rec.click(event.locator('[data-testid^="audit-undo-"]').first());
      const dialog = page.getByRole("dialog");
      await dialog.waitFor();
      await rec.click(dialog.getByRole("button", { name: /Undo|Geri al/ }).last());
      await dialog.waitFor({ state: "hidden", timeout: 20_000 });
      for (let i = 0; i < 40; i++) {
        if ((await api(page, `/bookings/${this.bookingId}`)).data?.room_id === this.roomBefore) break;
        await page.waitForTimeout(250);
      }
      await rec.wait(400);
    }, { clip: "audit-undo", hold: 900 });
  },
};
