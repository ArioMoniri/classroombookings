// Journey 4: drag a class to another slot in the calendar (dnd-kit in components/timetable). The
// redesign may replace the grid; the fallback is the event sheet → move dialog flow.
import { findRun, termId, tr } from "./_shared.mjs";

export default {
  id: "calendar-drag",
  title: "Drag a class in the calendar",
  db: "seeded",
  role: "admin",
  verified: false,
  async setup({ page, termCode }) {
    const tid = await termId(page, termCode);
    const run = await findRun(page, tid);
    if (!run) throw new Error("no feasible COURSE run (the grid import creates one)");
    await page.goto(`/runs/${run.id}?tab=grid`);
    await page.locator("[data-assignment-id]").first().waitFor({ timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    const event = page.locator("[data-assignment-id][data-status='ok']").first();
    await rec.step(tr(ctx, "Every class of the week, room by room", "Haftanın tüm dersleri, derslik derslik"), async () => {
      await rec.frame(page.locator("[data-testid='day-grid'], [data-testid='week-grid'], [data-testid='timetable']").first(), { dwell: 1400 });
    }, { zoom: false });
    await rec.step(tr(ctx, "Drag a class to a free slot", "Bir dersi boş bir saate sürükleyin"), async () => {
      const b = await event.boundingBox();
      // two rows down = two periods later in the day grid; the backend re-checks the move
      await rec.drag(event, { x: b.x + b.width / 2, y: b.y + b.height / 2 + b.height * 2.2 });
    });
    await rec.step(tr(ctx, "SmartSched checks clashes and locks the new slot", "SmartSched çakışmaları kontrol eder ve yeni saati kilitler"), async () => {
      await page.locator("[data-sonner-toast], [data-testid='move-dialog']").first().waitFor({ timeout: 20_000 }).catch(() => undefined);
      const confirm = page.getByTestId("move-confirm");
      if (await confirm.isVisible().catch(() => false) && (await confirm.isEnabled())) await rec.click(confirm);
      await rec.wait(1200);
    }, { hold: 1500, poster: true });
  },
};
