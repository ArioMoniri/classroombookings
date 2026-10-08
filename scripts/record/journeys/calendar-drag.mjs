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
      // a free slot in the same room column: the first block of empty period cells (as tall as the
      // class) below it; the backend re-checks the move either way
      const target = await event.evaluate((el) => {
        const col = el.closest("[data-room-id]");
        const eb = el.getBoundingClientRect();
        const cells = [...(col?.querySelectorAll("[data-period]") ?? [])].map((c) => c.getBoundingClientRect());
        const rowH = cells[0]?.height || 40;
        const span = Math.max(1, Math.round(eb.height / rowH));
        const busy = [...(col?.querySelectorAll("[data-assignment-id]") ?? [])].map((e) => e.getBoundingClientRect());
        const free = (r) => !busy.some((b) => b.top < r.bottom - 2 && b.bottom > r.top + 2);
        for (let i = 0; i + span <= cells.length; i++) {
          const top = cells[i].top;
          if (top <= eb.bottom || top + span * rowH > window.innerHeight - 20) continue;
          const block = { top, bottom: top + span * rowH };
          if (free(block)) return { x: eb.left + eb.width / 2, y: top + (span * rowH) / 2 };
        }
        return { x: eb.left + eb.width / 2, y: eb.top + eb.height * 2.5 };
      });
      await rec.drag(event, target);
    });
    await rec.step(tr(ctx, "SmartSched checks clashes and locks the new slot", "SmartSched çakışmaları kontrol eder ve yeni saati kilitler"), async () => {
      await page.locator("[data-sonner-toast], [data-testid='move-dialog']").first().waitFor({ timeout: 20_000 }).catch(() => undefined);
      const confirm = page.getByTestId("move-confirm");
      if (await confirm.isVisible().catch(() => false) && (await confirm.isEnabled())) await rec.click(confirm);
      await rec.wait(1200);
    }, { hold: 1500, poster: true });
  },
};
