// Bookings (the classroombookings side): pick a free period in a room on the day grid, add a note, book
// it, and find it in My bookings. Booked as the seeded administrator on the next teaching day of the
// current term (Güz 2026-27). Same selectors as smartsched/frontend/e2e/bookings.spec.ts.
import { api, tr } from "./_shared.mjs";

const ROOM = process.env.REC_BOOK_ROOM ?? "A203";
const NOTES = "ING 301 make-up lecture";

/** next Monday-Friday after today (Europe/Istanbul), as YYYY-MM-DD */
function nextTeachingDay() {
  const d = new Date(new Date().toLocaleString("en-US", { timeZone: "Europe/Istanbul" }));
  do d.setDate(d.getDate() + 1);
  while (d.getDay() === 0 || d.getDay() === 6);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default {
  id: "room-booking",
  title: "Book a room",
  db: "seeded",
  role: "admin",
  verified: "2026-10-08 against the Liquid Glass v2 UI and the real backend",
  async setup({ page }) {
    const rooms = (await api(page, "/room-admin/rooms")).data ?? [];
    const room = rooms.find((r) => r.code === ROOM);
    if (!room?.room_group_id) throw new Error(`room ${ROOM} has no group: scripts/record/stack.sh up runs the booking setup`);
    // idempotent: cancel this journey's booking from an earlier take
    const mine = (await api(page, "/bookings/mine")).data ?? [];
    for (const b of mine) if (b.notes === NOTES) await api(page, `/bookings/${b.id}/cancel`, { method: "POST", body: { scope: "one", reason: "recording retake" } });
    const date = nextTeachingDay();
    await page.goto(`/bookings?date=${date}&group=${room.room_group_id}`);
    await page.getByTestId("booking-grid").waitFor({ timeout: 30_000 });
    const free = page.locator(`button[data-slot-key^="${date}|"][data-slot-key$="|${room.id}"][data-tone="available"]`);
    await free.first().waitFor({ timeout: 30_000 });
    // a mid-morning period if one is free (reads naturally), else the first free one
    const keys = await free.evaluateAll((els) => els.map((e) => e.getAttribute("data-slot-key")));
    this.key = keys[Math.min(2, keys.length - 1)];
    this.room = room;
  },
  async run(rec, ctx) {
    const { page } = rec;
    const slot = page.locator(`button[data-slot-key="${this.key}"]`).first();
    const sheet = page.getByTestId("book-sheet");
    await rec.step(tr(ctx, "Rooms by period for one day; classes from the timetable are already there", "Bir günün derslikleri ve saatleri; ders programındaki dersler zaten yerinde"), async () => {
      await rec.frame(page.getByTestId("booking-grid"), { dwell: 1500 });
    }, { zoom: false, hold: 300 });
    await rec.step(tr(ctx, "Pick a free period in a room that fits", "Sığan bir derslikte boş bir saat seçin"), async () => {
      await rec.click(slot);
      await sheet.waitFor();
      await rec.frame(sheet, { dwell: 900 });
    });
    await rec.step(tr(ctx, "Add a note and book it", "Bir not ekleyip rezerve edin"), async () => {
      await rec.type(sheet.locator("#book-notes"), NOTES, { delay: 55 });
      await rec.click(sheet.getByTestId("book-submit"));
      await sheet.waitFor({ state: "hidden", timeout: 20_000 });
      await page.locator(`button[data-slot-key="${this.key}"][data-tone="booked-mine"]`).waitFor({ timeout: 20_000 });
      await rec.frame(page.locator(`button[data-slot-key="${this.key}"]`), { dwell: 1300 });
    });
    await rec.step(tr(ctx, "It is listed under My bookings, with a calendar feed and CSV export", "Rezervasyonlarım altında listelenir; takvim aboneliği ve CSV dışa aktarma ile"), async () => {
      await rec.click(page.getByTestId("nav-my-bookings"));
      await page.getByTestId("booking-list").waitFor({ timeout: 20_000 });
      await rec.frame(page.getByTestId("booking-list"), { dwell: 1600 });
    }, { hold: 1200, poster: true });
  },
};
