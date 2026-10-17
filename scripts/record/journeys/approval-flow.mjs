// Approvals: a member of the academic staff asks for a room that needs approval, the period is held as pending,
// the approver opens the request in /approvals and approves it, and the requester sees it confirmed.
// The setup does through the API what an administrator does once (like e2e/wave1.spec.ts): the seeded
// administrator approves for every room, one real room of the B building gets an approval rule, and an
// academic staff account exists. The account is a role, not an invented person ("Akademik Personel").
// Changing user happens off camera (Recorder.cut); the captions say whose screen it is.
import { api, cancelMine, dayGrid, freeRun, nextTeachingDay, slotKey, switchUser, tr } from "./_shared.mjs";

export const STAFF = { username: "akademik.personel", email: "akademik.personel@smartsched.local", firstname: "Akademik", lastname: "Personel", password: "Akademik-2026!" };

export default {
  id: "approval-flow",
  title: "Request a room that needs approval; the approver approves it",
  db: "seeded",
  role: "admin",
  verified: "2026-10-15 on the real backend (snapshot 6c4b790)",
  async setup(ctx) {
    const { page } = ctx;
    this.admin = { ...ctx.creds, lang: ctx.lang };
    const me = (await api(page, "/auth/me")).data;
    await api(page, `/approvals/approvers/${me.id}`, { method: "PUT", body: { scopes: [{ type: "all" }] } });
    const found = (await api(page, `/users/search?q=${STAFF.username}`)).data?.items ?? [];
    let staff = found.find((u) => u.username === STAFF.username);
    if (!staff) {
      const deps = (await api(page, "/departments")).data ?? [];
      const made = await api(page, "/users", { method: "POST", body: { ...STAFF, role: "TEACHER", department_id: deps[0]?.id ?? null } });
      if (made.status >= 400) throw new Error(`staff account: ${made.status} ${JSON.stringify(made.data)}`);
      staff = made.data;
    }
    const rooms = (await api(page, "/room-admin/rooms")).data ?? [];
    const group = rooms.find((r) => r.code.startsWith("B"))?.room_group_id;
    const date = await nextTeachingDay(page);
    const grid = await dayGrid(page, date, group);
    // the rule room: the first B room with a free morning period (stable from take to take)
    const ruled = (await api(page, "/approval-rules")).data ?? [];
    let roomId = ruled.find((r) => r.entity_type === "room")?.entity_id;
    if (!roomId) {
      roomId = freeRun(grid, 1, { maxPeriod: 4 })[0].room_id;
      const rule = await api(page, "/approval-rules", { method: "POST", body: { entity_type: "room", entity_id: roomId, steps: [{ approvers: { type: "designated" }, min_approvals: 1 }], hold_minutes: 0, lead_time_workdays: 0, expires_before_start_minutes: 0, allow_self_approve: false, active: true, name: null, tag: null, term_id: null } });
      if (rule.status >= 400) throw new Error(`approval rule: ${rule.status} ${JSON.stringify(rule.data)}`);
    }
    this.staff = { email: STAFF.email, password: STAFF.password, lang: ctx.lang };
    await switchUser(page, this.staff);
    await cancelMine(page, [], { unnoted: date });
    const fresh = await dayGrid(page, date, group);
    this.slot = freeRun(fresh, 1, { maxPeriod: 4, exclude: fresh.rooms.filter((r) => r.id !== roomId).map((r) => r.id) })[0];
    Object.assign(this, { date, group });
    await page.goto(`/bookings?date=${date}&group=${group}&lens=grid`);
    await page.locator(`button[data-slot-key="${slotKey(this.slot)}"]`).waitFor({ timeout: 30_000 });
  },
  async run(rec, ctx) {
    const { page } = rec;
    const cell = page.locator(`button[data-slot-key="${slotKey(this.slot)}"]`).first();
    const sheet = page.getByTestId("book-sheet");
    await rec.step(tr(ctx, "Academic staff: this room needs approval, and the sheet says so", "Akademik personel: bu derslik onay ister, panel bunu söyler"), async () => {
      await rec.click(cell);
      await sheet.getByTestId("book-approval").waitFor({ timeout: 20_000 });
      await rec.frame(sheet.getByTestId("book-approval"), { dwell: 1300 });
    }, { clip: "approval-request" });
    await rec.step(tr(ctx, "Send the request: the period is held as pending", "Talebi gönderin: saat beklemede olarak tutulur"), async () => {
      await rec.click(sheet.getByTestId("book-submit"));
      await sheet.waitFor({ state: "hidden", timeout: 20_000 });
      await page.locator(`button[data-slot-key="${slotKey(this.slot)}"][data-tone="booked-pending"]`).waitFor({ timeout: 20_000 });
      await rec.frame(cell, { dwell: 1400 });
    }, { clip: "approval-request", poster: true });
    const mine = (await api(page, "/approvals/mine")).data ?? [];
    const req = mine.find((r) => r.status === "PENDING");
    if (!req) throw new Error("no pending request");
    await rec.cut(async () => {
      await switchUser(page, this.admin);
      await page.goto("/approvals");
      await page.getByTestId(`approval-${req.id}`).waitFor({ timeout: 30_000 });
    });
    const drawer = page.getByTestId("approval-drawer");
    await rec.step(tr(ctx, "The approver's inbox: open the request", "Onaylayanın gelen kutusu: talebi açın"), async () => {
      await rec.click(page.getByTestId(`approval-${req.id}`));
      await drawer.getByTestId("approval-room-day").waitFor({ timeout: 20_000 });
      await rec.frame(drawer, { dwell: 1300 });
    }, { clip: "approval-approve" });
    await rec.step(tr(ctx, "Approve: the server re-checks the slot first", "Onaylayın: sunucu önce saati yeniden kontrol eder"), async () => {
      await rec.click(drawer.getByTestId("approval-approve"));
      for (let i = 0; i < 40; i++) {
        if ((await api(page, `/approvals/${req.id}`)).data?.status === "APPROVED") break;
        await page.waitForTimeout(250);
      }
      await rec.wait(700);
    }, { clip: "approval-approve" });
    await rec.cut(async () => {
      await switchUser(page, this.staff);
      await page.goto(`/my-bookings?request=${req.id}`);
      await page.locator(`[data-request-id="${req.id}"][data-status="APPROVED"]`).waitFor({ timeout: 30_000 });
    });
    await rec.step(tr(ctx, "The requester sees it confirmed, with every decision", "Talep eden onaylandığını ve tüm kararları görür"), async () => {
      await rec.frame(page.locator(`[data-request-id="${req.id}"]`), { dwell: 1800 });
    }, { clip: "approval-approve", hold: 1000 });
  },
};
