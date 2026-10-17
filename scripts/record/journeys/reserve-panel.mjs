// The reservation panel on the booking grid: a free period offers Reserve on hover; one click opens the
// sheet; a drag across periods reserves a span; the room details sheet shows the room, its day and the other
// rooms free at that time. Booked as the seeded administrator on the next teaching day of Güz 2026-27, in the
// A building group. Same selectors as smartsched/frontend/e2e/reserve.spec.ts.
import { api, cancelMine, dayGrid, freeRun, nextTeachingDay, slotKey, tr } from "./_shared.mjs";


export default {
  id: "reserve-panel",
  title: "Reserve from the grid: one click, a drag, room details",
  db: "seeded",
  role: "admin",
  verified: "2026-10-15 on the real backend (snapshot 6c4b790)",
  async setup({ page }) {
    const rooms = (await api(page, "/room-admin/rooms")).data ?? [];
    const group = rooms.find((r) => r.code === "A101")?.room_group_id;
    const date = await nextTeachingDay(page, 1);
    // this journey's own bookings from an earlier take: the administrator's bookings without a note on that day
    await cancelMine(page, [], { unnoted: date });
    const grid = await dayGrid(page, date, group);
    const [one] = freeRun(grid, 1, { maxPeriod: 5 });
    const span = freeRun(grid, 3, { exclude: [one.room_id], maxPeriod: 6 });
    // room details: the room of the single reservation (its day then shows the booking just made)
    this.room = grid.rooms.find((r) => r.id === one.room_id);
    Object.assign(this, { one, span, date, group });
    await page.goto(`/bookings?date=${date}&group=${group}&lens=grid`);
    await page.getByTestId("booking-grid").waitFor({ timeout: 30_000 });
    await page.locator(`button[data-slot-key="${slotKey(one)}"]`).waitFor({ timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    const cell = (s) => page.locator(`button[data-slot-key="${slotKey(s)}"]`).first();
    const sheet = page.getByTestId("book-sheet");
    await rec.step(tr(ctx, "Point at a free period: it offers Reserve", "Boş bir saatin üzerine gelin: Rezerve et sunar"), async () => {
      await rec.moveOnto(cell(this.one));
      await rec.wait(900); // the hover shows Reserve
      await rec.click(cell(this.one));
      await sheet.waitFor();
    }, { clip: "reserve-slot" });
    await rec.step(tr(ctx, "One more click reserves it", "Bir tık daha ve rezerve edildi"), async () => {
      await rec.wait(300);
      await rec.click(sheet.getByTestId("book-submit"));
      await sheet.waitFor({ state: "hidden", timeout: 20_000 });
      await page.locator(`button[data-slot-key="${slotKey(this.one)}"][data-tone="booked-mine"]`).waitFor({ timeout: 20_000 });
      await rec.wait(900);
    }, { clip: "reserve-slot", poster: true });
    await rec.step(tr(ctx, "Drag across periods to reserve a span", "Bir aralık için saatlerin üzerinden sürükleyin"), async () => {
      await rec.drag(cell(this.span[0]), cell(this.span[2]), { after: 400 });
      await sheet.getByTestId("book-periods").waitFor({ timeout: 20_000 });
      await rec.wait(900);
    }, { clip: "reserve-drag" });
    await rec.step(tr(ctx, "Three periods, one booking", "Üç ders saati, tek rezervasyon"), async () => {
      await rec.click(sheet.getByTestId("book-submit"));
      await sheet.waitFor({ state: "hidden", timeout: 20_000 });
      await page.locator(`button[data-slot-key="${slotKey(this.span[2])}"][data-tone="booked-mine"]`).waitFor({ timeout: 20_000 });
      await rec.wait(900);
    });
    const info = page.getByTestId("room-info");
    await rec.step(tr(ctx, "Room details: seats, features and the room's day", "Derslik ayrıntıları: kapasite, özellikler ve günü"), async () => {
      await rec.click(page.getByTestId(`room-info-${this.room.code}`));
      await info.waitFor();
      await rec.frame(info.getByTestId("room-facts"), { dwell: 1200 });
    }, { clip: "room-details" });
    await rec.step(tr(ctx, "Other rooms free at the same time, ranked by fit", "Aynı saatte boş diğer derslikler, uygunluğa göre"), async () => {
      const alts = info.getByTestId("room-alternatives");
      await alts.scrollIntoViewIfNeeded();
      await alts.locator('[data-testid^="alt-reserve-"]').first().waitFor({ timeout: 20_000 }).catch(() => undefined);
      await rec.moveOnto(alts.locator('[data-testid^="alt-reserve-"]').first());
      await rec.frame(alts, { dwell: 1500 });
    }, { clip: "room-details", hold: 1200 });
  },
};
