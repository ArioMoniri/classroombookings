// Find a room: a time, a head count and a room feature (the computer labs, a typed feature adopted from the
// room master's PC tag by setup_api.py bookings), ranked results with their reasons, Reserve from the list.
// Same selectors as smartsched/frontend/e2e/wave1.spec.ts ("find a room"). No camera zoom: the form and the
// ranked list sit side by side, and the whole page tells the story (each pan would cost the GIF ~2.5 MB).
import { api, cancelMine, nextTeachingDay, termId, tr } from "./_shared.mjs";

// the time the persona tests search (wave1.spec.ts): 10:10-12:30
const START = "10:10";
const END = "12:30";

export default {
  id: "find-room",
  title: "Find a room by time, size and feature, then reserve it",
  db: "seeded",
  role: "admin",
  verified: "2026-10-15 on the real backend (snapshot 6c4b790)",
  async setup({ page }) {
    const features = (await api(page, "/room-admin/features")).data ?? [];
    const pc = features.find((f) => f.solver_tag === "PC");
    if (!pc) throw new Error("no PC feature: scripts/record/setup_api.py bookings adopts the room tags");
    const date = await nextTeachingDay(page, 2);
    await cancelMine(page, [], { unnoted: date });
    const tid = await termId(page, "2026-GUZ");
    // the largest head count (in steps of 10) that still leaves a free computer lab, so the list is short
    let headcount = 0;
    for (const h of [60, 50, 40, 30, 20]) {
      const out = (await api(page, "/rooms/find", { method: "POST", body: { term_id: tid, date, start: START, end: END, headcount: h, features: [{ field: pc.id, op: "eq", value: true }], include_busy: false, limit: 60 } })).data;
      if ((out?.results ?? []).some((r) => r.status === "free" && r.action === "book")) {
        headcount = h;
        break;
      }
    }
    if (!headcount) throw new Error("no free computer lab on the next teaching day");
    Object.assign(this, { pc, date, headcount });
    await page.goto("/find-room");
    await page.getByTestId("find-room").waitFor({ timeout: 30_000 });
    // date and time are filled off camera (a native date picker and two times are not worth watching)
    // the date field is a text field that commits on blur (ui/date-field.tsx): fill, then leave it
    await page.getByTestId("fr-date").fill(date);
    await page.getByTestId("fr-date").blur();
    await page.getByTestId("fr-start").fill(START);
    await page.getByTestId("fr-end").fill(END);
  },
  async run(rec, ctx) {
    const { page } = rec;
    const view = page.getByTestId("find-room");
    await rec.step(tr(ctx, "How many people, and what the room needs", "Kaç kişi ve dersliğin neye ihtiyacı olduğu"), async () => {
      await rec.type(view.getByTestId("fr-headcount"), String(this.headcount), { delay: 90, after: 200 });
      await rec.click(view.getByTestId(`fr-feature-${this.pc.id}`), { after: 300 });
    }, { clip: "find-room", zoom: false });
    await rec.step(tr(ctx, "Free rooms that fit, ranked, each with its reason", "Sığan boş derslikler, sıralı ve nedenleriyle"), async () => {
      // the redesigned page searches as you type: the Search button and the summary line are optional
      const search = view.getByTestId("fr-search");
      if (await search.isVisible().catch(() => false)) await rec.click(search);
      const results = view.locator('[data-testid="fr-results"], [data-testid^="fr-reserve-"]').first();
      await results.waitFor({ timeout: 30_000 });
      const list = view.getByTestId("fr-results");
      await rec.frame((await list.isVisible().catch(() => false)) ? list : view.locator('[data-testid^="fr-reserve-"]').first(), { dwell: 1000 });
    }, { clip: "find-room", zoom: false, poster: true });
    await rec.step(tr(ctx, "Reserve straight from the list", "Doğrudan listeden rezerve edin"), async () => {
      const btn = view.locator('[data-testid^="fr-reserve-"]').first();
      const code = (await btn.getAttribute("data-testid")).replace("fr-reserve-", "");
      await rec.click(btn);
      const sheet = page.getByTestId("book-sheet");
      await sheet.waitFor();
      await rec.wait(500);
      await rec.click(sheet.getByTestId("book-submit"));
      await sheet.waitFor({ state: "hidden", timeout: 20_000 });
      await view.getByTestId(`fr-room-${code}`).waitFor({ state: "detached", timeout: 4_000 }).catch(() => undefined);
      await rec.wait(500);
    }, { zoom: false, hold: 700 });
  },
};
