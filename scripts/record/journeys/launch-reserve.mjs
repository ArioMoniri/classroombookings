// Launch video, chapter 5: a member of staff books a room on a phone with /reserve (quick reserve, W3-SLOT):
// a day, a period, how many people, a room that is free, one tap to book, the receipt. Recorded as the academic
// staff role (REC_TEACHER=1 account "Akademik Personel", a role, not a person) with REC_DEVICE=phone (taps).
// The journey cancels its own earlier booking first, so every take starts from the same free room.
import { api, tr } from "./_shared.mjs";

export default {
  id: "launch-reserve",
  title: "Quick reserve on a phone: day, period, people, room, book",
  db: "seeded",
  role: "teacher",
  verified: false,
  async setup({ page }) {
    const mine = (await api(page, "/bookings/mine")).data ?? [];
    for (const b of mine) if (b.notes == null && b.status !== "CANCELLED") await api(page, `/bookings/${b.id}/cancel`, { method: "POST", body: { scope: "one", reason: "recording retake" } });
    await page.goto("/reserve");
    await page.getByTestId("qr-days").waitFor({ timeout: 30_000 });
    await page.waitForLoadState("networkidle").catch(() => undefined);
  },
  async run(rec, ctx) {
    const { page } = rec;
    const days = page.locator('[data-testid^="qr-day-"]:not([disabled]):not([aria-disabled="true"])');
    await rec.step(tr(ctx, "When: tomorrow, a free period", "Ne zaman: yarın, boş bir ders saati"), async () => {
      await rec.click(days.nth(1), { after: 700 });
      const slot = page.locator('[data-testid^="qr-slot-"]:not([disabled]):not([aria-disabled="true"])').nth(1);
      await rec.click(slot, { after: 700 });
    }, { hold: 400 });
    await rec.step(tr(ctx, "Where: how many people; only rooms that are free and fit are listed", "Nerede: kaç kişi; yalnız boş ve sığan derslikler listelenir"), async () => {
      const people = page.locator('[data-testid^="qr-people-"]').nth(2);
      if (await people.isVisible().catch(() => false)) await rec.click(people, { after: 900 });
      await page.getByTestId("qr-rooms").waitFor({ timeout: 30_000 });
      await rec.frame(page.getByTestId("qr-count"), { dwell: 500 });
      const room = page.locator('[data-testid^="qr-room-"][data-action="book"]').first();
      // on a phone the confirm sheet is fixed over the lower part of the screen: bring the room into the free part
      await room.evaluate((el) => el.scrollIntoView({ block: "center", behavior: "smooth" }));
      await rec.wait(700);
      await rec.click(room, { after: 800 });
      await page.locator('[data-testid^="qr-room-"][aria-checked="true"]').first().waitFor({ timeout: 10_000 }).catch(() => undefined);
    }, { hold: 300 });
    await rec.step(tr(ctx, "One tap books it; the server checks the slot first", "Tek dokunuş ayırır; sunucu önce saati kontrol eder"), async () => {
      await rec.click(page.getByTestId("qr-submit"), { after: 300 });
      await page.getByTestId("qr-receipt").waitFor({ timeout: 30_000 });
      await rec.frame(page.getByTestId("qr-receipt"), { dwell: 2000 });
    }, { hold: 700, poster: true });
  },
};
