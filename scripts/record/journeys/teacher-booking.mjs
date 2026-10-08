// Journey 6: a teacher books a room (CRBS-style bookings, being built now).
// VERIFY LATER: written against the documented endpoints in docs/CRBS_PARITY.md (GET /bookings/context,
// GET /bookings/grid, POST /bookings) before the booking UI existed. The selectors are guesses with
// role/label fallbacks; setup() uses the API to find a free slot so the journey does not depend on
// the grid layout to choose one.
import { api, tr } from "./_shared.mjs";
import { pick } from "../lib/recorder.mjs";

export default {
  id: "teacher-booking",
  title: "Book a room as a teacher",
  db: "seeded",
  role: "teacher",
  verified: false,
  verifyLater: true,
  async setup({ page }) {
    const ctxRes = await api(page, "/bookings/context");
    if (ctxRes.status !== 200) throw new Error(`GET /bookings/context → ${ctxRes.status}: booking API not available yet`);
    const grid = await api(page, "/bookings/grid");
    if (grid.status !== 200) throw new Error(`GET /bookings/grid → ${grid.status}`);
    const free = (grid.data?.slots ?? []).find((s) => s.status === "available");
    if (!free) throw new Error("no available slot in the booking grid");
    this.slot = free;
    await page.goto(`/bookings?date=${free.date}`);
    await pick(page, [page.getByTestId("bookings"), page.getByTestId("booking-grid"), page.getByRole("heading", { name: /rezervasyon|booking/i })], { timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    const s = this.slot;
    await rec.step(tr(ctx, "Teachers see which rooms are free, period by period", "Öğretmenler hangi dersliğin hangi saatte boş olduğunu görür"), async () => {
      await rec.frame(await pick(page, [page.getByTestId("booking-grid"), page.locator("table").first()]), { dwell: 1400 });
    }, { zoom: false });
    await rec.step(tr(ctx, "Pick a free slot", "Boş bir saat seçin"), async () => {
      const slot = await pick(page, [
        page.locator(`[data-room-id='${s.room_id}'][data-period-id='${s.period_id}'][data-date='${s.date}']`),
        page.getByTestId("slot-available"),
        page.getByRole("button", { name: /boş|available|book/i }),
      ]);
      await rec.click(slot);
    });
    await rec.step(tr(ctx, "Add a note and confirm the booking", "Not ekleyip rezervasyonu onaylayın"), async () => {
      const notes = await pick(page, [page.getByTestId("booking-notes"), page.getByLabel(/not|notes/i)]);
      await rec.type(notes, tr(ctx, "Make-up lecture, ACU 132", "Telafi dersi, ACU 132"), { delay: 45 });
      await rec.click(await pick(page, [page.getByTestId("booking-confirm"), page.getByRole("button", { name: /onayla|rezerve|book|confirm/i })]));
      await page.locator("[data-sonner-toast]").first().waitFor({ timeout: 20_000 }).catch(() => undefined);
    }, { hold: 1600, poster: true });
  },
};
