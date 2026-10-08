// Calendar: open a class in the inspector, move it to a free room with the free-room finder (the server
// dry-runs the move first), then undo. Same flow as the e2e test "inspector, explain, move with the
// free-room finder, undo restores the backend" (smartsched/frontend/e2e/calendar.spec.ts), on the published
// full-term solver run of the current term.
import { api, termId, tr } from "./_shared.mjs";

const WEEK = 3;

export default {
  id: "calendar-move",
  title: "Move a class in the calendar, then undo",
  db: "seeded",
  role: "admin",
  verified: "2026-10-08 against the Liquid Glass v2 UI and the real backend",
  async setup({ page }) {
    const tid = await termId(page, process.env.REC_CAL_TERM ?? "2026-GUZ");
    const runs = (await api(page, `/runs?term_id=${tid}`)).data ?? [];
    const run = runs.find((r) => r.is_active && r.kind === "COURSE") ?? runs.find((r) => r.kind === "COURSE" && r.horizon === "TERM");
    if (!run) throw new Error("no published COURSE run: scripts/record/stack.sh runs");
    const idx = (await api(page, `/runs/${run.id}/calendar-index`)).data;
    // the busiest room of the run
    const count = new Map();
    for (const a of idx.assignments) for (const r of a.rooms ?? []) count.set(r, (count.get(r) ?? 0) + 1);
    const ranked = [...count.entries()].sort((a, b) => b[1] - a[1]).map(([r]) => r);
    const dialog = page.getByTestId("move-dialog");
    const insp = page.getByTestId("class-inspector");
    // find a class whose move to a free room the server accepts (some keep real clashes and need "force")
    for (const rid of ranked.slice(0, 4)) {
      await page.goto(`/timetable?run=${run.id}&week=${WEEK}&lens=week&subject=room:${rid}`);
      const chips = page.locator(`[data-testid=calendar-event][data-room-id="${rid}"]`);
      await chips.first().waitFor({ timeout: 30_000 });
      const n = Math.min(8, await chips.count());
      for (let i = 0; i < n; i++) {
        const chip = chips.nth(i);
        const aid = Number(await chip.getAttribute("data-assignment-id"));
        await chip.click();
        await insp.waitFor();
        await insp.getByTestId("inspector-move").click();
        await dialog.waitFor();
        const free = dialog.locator(`[data-testid=free-room][data-status=free]:not([data-room-id="${rid}"])`).first();
        if (!(await free.waitFor({ timeout: 15_000 }).then(() => true, () => false))) {
          await page.keyboard.press("Escape");
          continue;
        }
        const target = Number(await free.getAttribute("data-room-id"));
        const res = await api(page, `/runs/${run.id}/assignments/${aid}/move-preview`, { method: "POST", body: { room_ids: [target], week: WEEK } });
        await page.keyboard.press("Escape");
        if (res.data?.items?.[0]?.ok) {
          Object.assign(this, { runId: run.id, rid, aid, target });
          await page.goto(`/timetable?run=${run.id}&week=${WEEK}&lens=week&subject=room:${rid}`);
          await chips.first().waitFor({ timeout: 30_000 });
          return;
        }
      }
    }
    throw new Error("no class that can move to a free room");
  },
  async run(rec, ctx) {
    const { page } = rec;
    const { rid, aid, target } = this;
    const chip = page.locator(`[data-testid=calendar-event][data-assignment-id="${aid}"]`).first();
    const insp = page.getByTestId("class-inspector");
    const dialog = page.getByTestId("move-dialog");
    await rec.step(tr(ctx, "One room's week, from the published timetable", "Bir dersliğin haftası, yayımlanan programdan"), async () => {
      await rec.frame(page.getByTestId("time-grid"), { dwell: 1300 });
    }, { zoom: false, hold: 300 });
    await rec.step(tr(ctx, "Click a class: the inspector shows when, where and why", "Bir derse tıklayın: denetçi ne zaman, nerede ve neden olduğunu gösterir"), async () => {
      await rec.click(chip);
      await insp.waitFor();
      await rec.frame(insp, { dwell: 1600 });
    });
    await rec.step(tr(ctx, "Move it: only rooms that are free and fit are offered", "Taşıyın: yalnızca boş ve sığan derslikler önerilir"), async () => {
      await rec.click(insp.getByTestId("inspector-move"));
      await dialog.waitFor();
      const free = dialog.locator(`[data-testid=free-room][data-room-id="${target}"]`).first();
      await rec.click(free);
      await dialog.getByTestId("move-server-ok").waitFor({ timeout: 20_000 });
      await rec.frame(dialog.getByTestId("move-server-ok"), { dwell: 1100 });
    });
    await rec.step(tr(ctx, "The server re-checks every rule before it saves", "Sunucu kaydetmeden önce tüm kuralları yeniden kontrol eder"), async () => {
      await rec.click(dialog.getByTestId("move-confirm"));
      await dialog.waitFor({ state: "hidden", timeout: 20_000 });
      await page.locator(`[data-testid=calendar-event][data-assignment-id="${aid}"][data-room-id="${rid}"]`).waitFor({ state: "detached", timeout: 20_000 }).catch(() => undefined);
      await rec.wait(900);
    }, { zoom: false });
    await rec.step(tr(ctx, "Changed your mind? Undo puts it back", "Vazgeçtiniz mi? Geri al eski yerine koyar"), async () => {
      const undo = page.locator("[data-sonner-toast]").getByRole("button", { name: /undo|geri al/i }).first();
      if (await undo.isVisible().catch(() => false)) await rec.click(undo);
      else {
        await page.getByTestId("calendar-title").click();
        await rec.press("ControlOrMeta+z");
      }
      // the live region is visually hidden: wait for it in the DOM, not on screen
      await page.getByTestId("calendar-live").filter({ hasText: /Undone|Geri alındı/i }).waitFor({ state: "attached", timeout: 8_000 }).catch(() => undefined);
      await chip.waitFor({ timeout: 20_000 });
      await rec.frame(chip, { dwell: 1200 });
    }, { hold: 1300, poster: true });
  },
};
