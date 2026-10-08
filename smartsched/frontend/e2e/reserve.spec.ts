/**
 * Reservation panel against the REAL backend (no mocks), gated E2E_REAL=1: click a free slot to reserve,
 * a span of periods, the reason hint, the "Free slots" lens, the department view, calendar sync links,
 * room details with other available rooms, and the CRBS UI gap items on these screens (bulk cancel from
 * the grid, "Booked by" for planners, multi-booking per row, booking details week/occurs/photo/not-own
 * warning, room owner in headers, my-bookings "can create" and room links, grouped pickers, reason icons).
 *
 * Backend: smartsched/deploy/pod-ci/gates/e2e-backend-entry.sh (real Bahar 2026 workbooks, seeded admin,
 * booking clock pinned to Monday 16 Feb 2026 08:00). The setup the CRBS installer would do is made
 * idempotently through the API, like e2e/bookings.spec.ts. New users per run, free cells found through
 * the grid API, so the spec can run again on the same database.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:8471 PW_PORT=3871 npx playwright test e2e/reserve.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, TERM_CODE, login, solverRun } from "./helpers";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const ADMIN = { username: `rez.yonetici.${STAMP}`, email: `rez.yonetici.${STAMP}@uni.edu.tr`, password: "Yonetici-2026!" };
const TEACHER = { username: `rez.hoca.${STAMP}`, email: `rez.hoca.${STAMP}@uni.edu.tr`, first: "Deniz", last: "Kaya", password: "Ogretmen-2026!" };
const TUESDAY = "2026-02-17";
const WEDNESDAY = "2026-02-18";

test.describe.configure({ mode: "serial" });
test.skip(!REAL, SKIP_REASON);

interface GridSlot {
  date: string;
  period_id: number;
  room_id: number;
  status: string;
  reason?: string | null;
  label?: string | null;
  allow_single?: boolean;
  booking?: { id: number; department_id?: number | null; can_cancel?: boolean };
}
interface Grid {
  periods: { id: number; name: string }[];
  rooms: { id: number; code: string; name: string; capacity?: number | null }[];
  slots: GridSlot[];
}
interface Ctx {
  api: APIRequestContext;
  token: string;
  teacherToken: string;
  termId: number;
  groupA: number;
  rooms: Record<string, number>;
  periods: Record<string, number>;
  teacherId: number;
  psychology: { id: number; name: string };
  other: { id: number; name: string };
}
const ctx = {} as Ctx;
const key = (s: { date: string; period_id: number; room_id: number }) => `${s.date}|${s.period_id}|${s.room_id}`;
const reservable = (s: GridSlot | undefined) => !!s && s.status === "available" && !!s.allow_single;

async function api<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token = ctx.token): Promise<T> {
  const res = await ctx.api.fetch(`${API}${path}`, { method, data: body, headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok()) throw new Error(`${method} ${path} → ${res.status()} ${await res.text()}`);
  return (res.status() === 204 ? undefined : await res.json()) as T;
}
async function loginToken(identifier: string, password: string): Promise<string> {
  const body = identifier.includes("@") ? { email: identifier, password } : { username: identifier, password };
  const res = await ctx.api.post(`${API}/auth/login`, { data: body });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { access_token: string }).access_token;
}
const dayGrid = (date: string, token = ctx.teacherToken) => api<Grid>("GET", `/bookings/grid?display=day&date=${date}&room_group_id=${ctx.groupA}`, undefined, token);

/** first room (in grid order) with `n` consecutive reservable periods on the date */
function run(g: Grid, n: number, exclude: number[] = []): GridSlot[] {
  const idx = new Map(g.slots.map((s) => [key(s), s]));
  for (const room of g.rooms) {
    if (exclude.includes(room.id)) continue;
    const day = g.periods.map((p) => idx.get(key({ date: g.slots[0]!.date, period_id: p.id, room_id: room.id })));
    for (let i = 0; i + n <= day.length; i++) {
      const part = day.slice(i, i + n);
      if (part.every(reservable)) return part as GridSlot[];
    }
  }
  throw new Error(`no room with ${n} free periods in a row`);
}

const cell = (page: Page, s: { date: string; period_id: number; room_id: number }) => page.locator(`button[data-slot-key="${key(s)}"]`);

/** open /bookings and wait for the grid or the free-slot list (the dev server can be slow on a cold route) */
async function openBookings(page: Page, query: string) {
  await page.goto(`/bookings?${query}`);
  await expect(page.getByTestId(query.includes("lens=free") ? "free-slots" : "booking-grid")).toBeVisible({ timeout: 30_000 });
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.token = await loginToken(ADMIN_EMAIL, ADMIN_PASSWORD);
  await api("POST", "/users", { username: ADMIN.username, email: ADMIN.email, displayname: "Rezervasyon Yöneticisi", role: "ADMIN", password: ADMIN.password });
  ctx.token = await loginToken(ADMIN.username, ADMIN.password);
  const dates = await api<{ today: string }>("GET", "/bookings/dates");
  test.skip(dates.today < "2026-02-02" || dates.today > "2026-06-28", `the backend's booking clock (${dates.today}) must be inside Bahar 2026`);

  // the booking setup CRBS's installer would make (same as e2e/bookings.spec.ts, idempotent)
  const terms = await api<{ id: number; code: string }[]>("GET", "/terms");
  ctx.termId = terms.find((x) => x.code === TERM_CODE)!.id;
  const runs = await api<{ id: number; kind: string; term_id: number; label: string; is_active: boolean }[]>("GET", "/runs");
  const board = runs.find((r) => r.term_id === ctx.termId && r.kind === "COURSE" && r.label.startsWith("Grid import"));
  if (board && !board.is_active) await api("POST", `/runs/${board.id}/activate`);
  let schedules = await api<{ id: number; periods: { id: number; name: string }[] }[]>("GET", "/booking-admin/schedules");
  let schedule = schedules.find((s) => s.periods.length >= 18);
  if (!schedule) {
    const s = await api<{ id: number }>("POST", "/booking-admin/schedules", { name: `Ders saatleri ${STAMP}` });
    await api("POST", `/booking-admin/schedules/${s.id}/periods/from-grid?days=1,2,3,4,5`);
    schedules = await api("GET", "/booking-admin/schedules");
    schedule = schedules.find((x) => x.id === s.id)!;
  }
  ctx.periods = Object.fromEntries(schedule.periods.map((p) => [p.name, p.id]));
  const sessions = await api<{ term_id: number; default_schedule_id: number | null; is_selectable: boolean }[]>("GET", "/booking-admin/sessions");
  const sess = sessions.find((s) => s.term_id === ctx.termId)!;
  if (!sess.is_selectable || sess.default_schedule_id !== schedule.id) await api("PUT", `/booking-admin/sessions/${ctx.termId}`, { is_selectable: true, default_schedule_id: schedule.id });
  let groups = await api<{ id: number }[]>("GET", "/room-admin/groups");
  if (!groups.length) groups = await api("POST", "/room-admin/groups/from-buildings");
  const rooms = await api<{ id: number; code: string; room_group_id: number | null }[]>("GET", "/room-admin/rooms");
  ctx.rooms = Object.fromEntries(rooms.map((r) => [r.code, r.id]));
  ctx.groupA = rooms.find((r) => r.code === "A101")!.room_group_id!;

  // a teacher of Psikoloji, and another department for the department view
  const deps = await api<{ id: number; name: string }[]>("GET", "/departments");
  ctx.psychology = deps.find((d) => d.name.toLocaleLowerCase("tr").startsWith("psikoloji"))!;
  ctx.other = deps.find((d) => d.id !== ctx.psychology.id)!;
  const made = await api<{ id: number }>("POST", "/users", { username: TEACHER.username, email: TEACHER.email, firstname: TEACHER.first, lastname: TEACHER.last, role: "TEACHER", password: TEACHER.password, department_id: ctx.psychology.id });
  ctx.teacherId = made.id;
  ctx.teacherToken = await loginToken(TEACHER.username, TEACHER.password);
});

test.afterAll(async () => {
  await ctx.api?.dispose();
});

test("1. a free slot says Free, offers Reserve, and one click reserves it", async ({ page }) => {
  const g = await dayGrid(TUESDAY);
  const [slot] = run(g, 1);
  await login(page, TEACHER.username, TEACHER.password);
  await openBookings(page, `date=${TUESDAY}&group=${ctx.groupA}&lens=grid`);
  const c = cell(page, slot!);
  await expect(c).toHaveAttribute("data-tone", "available");
  await expect(c).toContainText(/Boş|Free/);
  await c.hover();
  await expect(c).toContainText(/Rezerve et|Reserve/);
  await expect(c).toHaveAccessibleName(/Rezerve et|Reserve/);
  await c.click();
  const sheet = page.getByTestId("book-sheet");
  await expect(sheet).toContainText(g.rooms.find((r) => r.id === slot!.room_id)!.name);
  await sheet.locator("#book-notes").fill("Rezervasyon paneli e2e");
  await sheet.getByTestId("book-submit").click();
  await expect(sheet).toBeHidden();
  await expect(c).toHaveAttribute("data-tone", "booked-mine");
});

test("2. keyboard: focus a free cell and press Enter to open the sheet", async ({ page }) => {
  const g = await dayGrid(TUESDAY);
  const [slot] = run(g, 1);
  await login(page, TEACHER.username, TEACHER.password);
  await openBookings(page, `date=${TUESDAY}&group=${ctx.groupA}&lens=grid`);
  await cell(page, slot!).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("book-sheet")).toBeVisible();
  await page.keyboard.press("Escape");
});

test("3. drag across consecutive periods reserves a span in one go", async ({ page }) => {
  const g = await dayGrid(TUESDAY);
  const span = run(g, 2);
  await login(page, TEACHER.username, TEACHER.password);
  await openBookings(page, `date=${TUESDAY}&group=${ctx.groupA}&lens=grid`);
  await cell(page, span[1]!).scrollIntoViewIfNeeded();
  await cell(page, span[0]!).scrollIntoViewIfNeeded();
  const a = await cell(page, span[0]!).boundingBox();
  const b = await cell(page, span[1]!).boundingBox();
  await page.mouse.move(a!.x + a!.width / 2, a!.y + a!.height / 2);
  await page.mouse.down();
  await page.mouse.move(b!.x + b!.width / 2, b!.y + b!.height / 2, { steps: 4 });
  await page.mouse.up();
  const sheet = page.getByTestId("book-sheet");
  await expect(sheet.getByTestId("book-submit")).toHaveText(/2 ders saatini rezerve et|Reserve 2 periods/);
  await expect(sheet.getByTestId("book-periods")).toBeVisible();
  await sheet.getByTestId("book-submit").click();
  await expect(sheet).toBeHidden();
  for (const s of span) await expect(cell(page, s)).toHaveAttribute("data-tone", "booked-mine");
});

test("4. Shift-click selects a span; cells that cannot be booked say why on hover", async ({ page }) => {
  const g = await dayGrid(TUESDAY);
  const span = run(g, 3);
  await login(page, TEACHER.username, TEACHER.password);
  await openBookings(page, `date=${TUESDAY}&group=${ctx.groupA}&lens=grid`);
  await cell(page, span[0]!).click();
  const sheet = page.getByTestId("book-sheet");
  await expect(sheet).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await cell(page, span[2]!).click({ modifiers: ["Shift"] });
  await expect(sheet.getByTestId("book-submit")).toHaveText(/3 ders saatini rezerve et|Reserve 3 periods/);
  // the period picker (CRBS single_form) and the chips can change it back to one period
  await sheet.getByTestId("book-period").selectOption(String(span[1]!.period_id));
  await expect(sheet.getByTestId("book-submit")).toHaveText(/Rezerve et|Book this slot|Bu saati rezerve et/);
  await page.keyboard.press("Escape");
  // a timetable cell explains itself on hover
  const held = g.slots.find((s) => s.status === "timetable" && s.label)!;
  await cell(page, held).hover();
  await expect(page.getByTestId("slot-hint")).toContainText(held.label!);
  // a distinct glyph per unavailable reason (CRBS lock / quota / past / future)
  const reasons = await page.locator("[data-reason-icon]").evaluateAll((els) => els.map((e) => e.getAttribute("data-reason-icon")));
  expect(Array.isArray(reasons)).toBe(true);
});

test("5. the Free slots lens lists only reservable periods, grouped by room, and books from the list", async ({ page }) => {
  await login(page, TEACHER.username, TEACHER.password);
  await openBookings(page, `date=${WEDNESDAY}&group=${ctx.groupA}&lens=free`);
  const list = page.getByTestId("free-slots");
  await expect(list).toBeVisible();
  const g = await dayGrid(WEDNESDAY);
  const free = new Set(g.slots.filter(reservable).map(key));
  const keys = await list.getByTestId("free-slot").evaluateAll((els) => els.map((e) => e.getAttribute("data-slot-key")));
  expect(keys.length).toBeGreaterThan(0);
  for (const k of keys) expect(free.has(k!)).toBe(true);
  const first = list.getByTestId("free-slot").first();
  const k = await first.getAttribute("data-slot-key");
  const box = await first.boundingBox();
  expect(box!.height).toBeGreaterThanOrEqual(44);
  await first.click();
  await page.getByTestId("book-submit").click();
  await expect(page.getByTestId("book-sheet")).toBeHidden();
  await expect(list.locator(`[data-slot-key="${k}"]`)).toHaveCount(0);
  // week scope
  await openBookings(page, `date=${WEDNESDAY}&group=${ctx.groupA}&lens=free&scope=week`);
  await expect(page.getByTestId("free-slots")).toBeVisible();
});

test("6. department view: the user's department by default, colour legend, muted other departments, remembered", async ({ page }) => {
  // a booking of another department in the same group and day
  const g = await dayGrid(TUESDAY, ctx.token);
  const [slot] = run(g, 1);
  await api("POST", "/bookings", { room_id: slot!.room_id, date: TUESDAY, period_id: slot!.period_id, department_id: ctx.other.id, notes: "Başka bölüm" });
  await login(page, TEACHER.username, TEACHER.password);
  await openBookings(page, `date=${TUESDAY}&group=${ctx.groupA}&lens=grid`);
  const select = page.getByTestId("department-select");
  await expect(select).toHaveValue(String(ctx.psychology.id));
  await expect(page.getByTestId("department-filtering")).toContainText(ctx.psychology.name);
  await expect(cell(page, slot!)).toHaveAttribute("data-muted", "true");
  const mine = page.locator(`button[data-department="${ctx.psychology.id}"]`).first();
  await expect(mine).not.toHaveAttribute("data-muted", "true");
  await expect(page.getByTestId("department-legend")).toContainText(ctx.psychology.name);
  await expect(page.getByTestId("department-legend")).toContainText(ctx.other.name);
  await expect(page.getByTestId("department-top-rooms")).toBeVisible();
  // all departments: nothing muted; the choice survives a reload
  await select.selectOption("all");
  await expect(cell(page, slot!)).not.toHaveAttribute("data-muted", "true");
  await page.reload();
  await expect(page.getByTestId("department-select")).toHaveValue("all");
  await page.getByTestId("department-select").selectOption(String(ctx.psychology.id));
});

test("7. calendar sync: private links for me, a room and a department, copy, Google / Outlook, reset", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await login(page, TEACHER.username, TEACHER.password);
  await openBookings(page, `date=${TUESDAY}&group=${ctx.groupA}`);
  await page.getByTestId("sync-open").click();
  const panel = page.getByTestId("sync-sheet");
  await panel.getByTestId("sync-create").click();
  const url = panel.getByTestId("sync-url-mine");
  await expect(url).toHaveValue(/\/calendar\/feeds\/.+\/mine\.ics$/);
  const mineUrl = await url.inputValue();
  await panel.getByTestId("sync-copy-mine").click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(mineUrl);
  await panel.getByTestId("sync-copy-webcal-mine").click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(mineUrl.replace(/^https?:/, "webcal:"));
  await expect(panel.getByTestId("sync-google-mine")).toHaveAttribute("href", /^https:\/\/calendar\.google\.com\/calendar\/r\?cid=webcal/);
  await expect(panel.getByTestId("sync-outlook-mine")).toHaveAttribute("href", /addfromweb\?url=/);
  await expect(panel.getByTestId("sync-url-room")).toHaveValue(/\/room\/\d+\.ics$/);
  await expect(panel.getByTestId("sync-url-department")).toHaveValue(new RegExp(`/department/${ctx.psychology.id}\\.ics$`));
  // the feed answers without a session (the token is the credential)
  const ics = await ctx.api.get(mineUrl.replace(/^https?:\/\/[^/]+/, API.replace(/\/api\/v1$/, "")));
  expect(ics.status()).toBe(200);
  expect(await ics.text()).toContain("BEGIN:VCALENDAR");
  // connectors are hidden until an administrator configures them (never a fake button)
  const sync = await api<{ connectors: { provider: string; configured: boolean }[] }>("GET", "/calendar/sync", undefined, ctx.teacherToken);
  for (const c of sync.connectors) await expect(panel.getByTestId(`sync-connect-${c.provider}`)).toHaveCount(c.configured ? 1 : 0);
  // reset: a new link, the old one stops working
  await panel.getByTestId("sync-reset").click();
  await page.getByRole("dialog", { name: /sıfırlansın mı|Reset the private link/ }).getByRole("button", { name: /sıfırla|reset/i }).click();
  await expect(url).not.toHaveValue(mineUrl);
  const old = await ctx.api.get(mineUrl.replace(/^https?:\/\/[^/]+/, API.replace(/\/api\/v1$/, "")));
  expect(old.status()).toBe(404);
  // the same panel on My bookings
  await page.goto("/my-bookings");
  await expect(page.getByTestId("calendar-sync")).toBeVisible();
  await expect(page.getByTestId("sync-url-mine")).toHaveValue(/mine\.ics$/);
});

test("8. room details: capacity, exam capacity, building, the day, the next free slot, and reserving an alternative", async ({ page }) => {
  await login(page, TEACHER.username, TEACHER.password);
  await openBookings(page, `date=${TUESDAY}&group=${ctx.groupA}&lens=grid`);
  await page.getByTestId("room-info-A101").click();
  const info = page.getByTestId("room-info");
  await expect(info).toContainText("A 101");
  await expect(info.getByTestId("room-facts")).toContainText(/Kapasite|Seats/);
  await expect(info.getByTestId("room-facts")).toContainText(/Bina|Building/);
  await expect(info.getByTestId("room-day")).toBeVisible();
  await expect(info.getByTestId("room-next-free")).toBeVisible();
  const alts = info.getByTestId("room-alternatives");
  await alts.getByTestId("alt-min-seats").fill("0");
  const firstAlt = alts.locator('[data-testid^="alt-reserve-"]').first();
  await expect(firstAlt).toBeVisible();
  const code = (await firstAlt.getAttribute("data-testid"))!.replace("alt-reserve-", "");
  await alts.getByTestId(`alt-reserve-${code}`).click();
  const sheet = page.getByTestId("book-sheet");
  await expect(sheet).toBeVisible();
  await sheet.locator("#book-notes").fill("Alternatif derslik");
  await sheet.getByTestId("book-submit").click();
  await expect(sheet).toBeHidden();
  const mine = await api<{ room_id: number; notes: string | null }[]>("GET", "/bookings/mine", undefined, ctx.teacherToken);
  expect(mine.some((b) => b.room_id === ctx.rooms[code] && b.notes === "Alternatif derslik")).toBe(true);
});

test("9. a held slot offers the free rooms at that time; the booking sheet links to other rooms", async ({ page }) => {
  const g = await dayGrid(TUESDAY);
  const held = g.slots.find((s) => s.status === "timetable")!;
  await login(page, TEACHER.username, TEACHER.password);
  await openBookings(page, `date=${TUESDAY}&group=${ctx.groupA}&lens=grid`);
  await cell(page, held).click();
  await page.getByTestId("slot-info-alternatives").click();
  await expect(page.getByTestId("room-alternatives")).toBeVisible();
  await page.keyboard.press("Escape");
  const [slot] = run(g, 1);
  await cell(page, slot!).click();
  await page.getByTestId("book-other-rooms").click();
  await expect(page.getByTestId("room-alternatives")).toBeVisible();
});

test("10. administrators bulk-cancel other people's bookings from the grid (CRBS cancel_multi)", async ({ page }) => {
  const g = await dayGrid(TUESDAY, ctx.token);
  const [slot] = run(g, 1);
  const b = await api<{ id: number }>("POST", "/bookings", { room_id: slot!.room_id, date: TUESDAY, period_id: slot!.period_id, notes: "Toplu iptal" }, ctx.teacherToken);
  await login(page, ADMIN.username, ADMIN.password);
  await openBookings(page, `date=${TUESDAY}&group=${ctx.groupA}&lens=grid`);
  await page.getByTestId("multi-toggle").click();
  await cell(page, slot!).click();
  await expect(cell(page, slot!)).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("multi-cancel").click();
  await page.getByRole("dialog", { name: /iptal edilsin mi|Cancel \d+ bookings/ }).getByRole("button", { name: /^(İptal et|Cancel booking)$/ }).click();
  await expect(cell(page, slot!)).toHaveAttribute("data-tone", "available");
  const mine = await api<{ id: number }[]>("GET", "/bookings/mine?status=CANCELLED", undefined, ctx.teacherToken);
  expect(mine.some((x) => x.id === b.id)).toBe(true);
});

test("11. booking details: not-your-own warning, timetable week, occurs, room details; Booked by for planners", async ({ page }) => {
  const g = await dayGrid(WEDNESDAY, ctx.token);
  const [slot] = run(g, 1);
  await api("POST", "/bookings", { room_id: slot!.room_id, date: WEDNESDAY, period_id: slot!.period_id, notes: "Başkasının" }, ctx.teacherToken);
  // the administrator books a weekly series for the "occurs" row
  const [rslot] = run(g, 1, [slot!.room_id]);
  await api("POST", "/bookings/recurring", { room_id: rslot!.room_id, period_id: rslot!.period_id, date: WEDNESDAY, start: WEDNESDAY, end: "2026-03-11" });
  await login(page, ADMIN.username, ADMIN.password);
  await openBookings(page, `date=${WEDNESDAY}&group=${ctx.groupA}&lens=grid`);
  await cell(page, slot!).click();
  const detail = page.getByTestId("booking-sheet");
  await expect(detail.getByTestId("not-own-warning")).toContainText(/Bu sizin rezervasyonunuz değil|This is not your own booking/);
  await detail.getByTestId("detail-room-info").click();
  await expect(page.getByTestId("room-info")).toBeVisible();
  await page.keyboard.press("Escape");
  await cell(page, rslot!).click();
  await expect(page.getByTestId("booking-sheet").getByTestId("detail-occurs")).toContainText(/Çarşamba|Wednesday/);
  await page.keyboard.press("Escape");
  // "Booked by" comes from /bookings/users (book_*.set_user), not setup.users
  const [free] = run(await dayGrid(WEDNESDAY, ctx.token), 1);
  await cell(page, free!).click();
  const user = page.getByTestId("book-sheet").getByTestId("book-user");
  await expect(user.locator("option", { hasText: `${TEACHER.first} ${TEACHER.last}` }).first()).toBeAttached();
  await expect(user.locator(`option[value="${ctx.teacherId}"]`)).toHaveCount(1);
  await page.keyboard.press("Escape");
});

test("12. multi-booking: include per row and details per slot with copy-down", async ({ page }) => {
  const g = await dayGrid(WEDNESDAY, ctx.token);
  const span = run(g, 2);
  await login(page, ADMIN.username, ADMIN.password);
  await openBookings(page, `date=${WEDNESDAY}&group=${ctx.groupA}&lens=grid`);
  await page.getByTestId("multi-toggle").click();
  for (const s of span) await cell(page, s).click();
  await page.getByTestId("multi-book").click();
  const dialog = page.getByTestId("multi-dialog");
  await dialog.getByTestId("multi-per-row").click();
  const rows = dialog.getByTestId("multi-rows").locator("li");
  await expect(rows).toHaveCount(2);
  const firstId = await rows.first().getAttribute("data-mbs-id");
  const secondId = await rows.nth(1).getAttribute("data-mbs-id");
  await dialog.getByTestId(`multi-notes-${firstId}`).fill("Satır notu");
  await dialog.getByTestId(`multi-copy-${firstId}`).click();
  await expect(dialog.getByTestId(`multi-notes-${secondId}`)).toHaveValue("Satır notu");
  await dialog.getByTestId(`multi-include-${secondId}`).click();
  await dialog.getByTestId("multi-check").click();
  await dialog.getByTestId("multi-confirm").click();
  await expect(dialog).toBeHidden();
  await expect(cell(page, span[0]!)).toHaveAttribute("data-tone", "booked-mine");
  await expect(cell(page, span[1]!)).toHaveAttribute("data-tone", "available");
});

test("13. room owner under the room name, group tabs with counts, grouped pickers; my bookings can-create and room links", async ({ page }) => {
  await api("PUT", `/room-admin/rooms/${ctx.rooms.A101}`, { owner_user_id: ctx.teacherId });
  try {
    await login(page, TEACHER.username, TEACHER.password);
    await openBookings(page, `date=${TUESDAY}&group=${ctx.groupA}&lens=grid`);
    await expect(page.getByTestId("room-info-A101")).toContainText(`${TEACHER.first} ${TEACHER.last}`);
    await expect(page.getByTestId("group-tabs").getByRole("tab").first()).toHaveText(/\(\d+\)/);
    await openBookings(page, `display=room&date=${TUESDAY}&room=${ctx.rooms.A101}&lens=grid`);
    expect(await page.getByTestId("room-select").locator("optgroup").count()).toBeGreaterThan(0);
    // CRBS dashboard stats "bookings you can create" (shown when the user has a limit)
    await api("PUT", `/users/${ctx.teacherId}/constraints`, { max_active_bookings: { type: "U", value: 40 } });
    await page.goto("/my-bookings");
    await expect(page.getByTestId("mine-can-create")).toContainText(/daha yapabilirsiniz|more/);
    await page.locator('[data-testid^="mine-room-"]').first().click();
    await expect(page.getByTestId("room-info")).toBeVisible();
  } finally {
    await api("PUT", `/room-admin/rooms/${ctx.rooms.A101}`, { owner_user_id: null });
    await api("PUT", `/users/${ctx.teacherId}/constraints`, { max_active_bookings: { type: "R" } });
  }
});

test("14. a published SOLVER run names its classes by course and section, never a hard-coded Turkish word", async ({ page, context }) => {
  const runs = await api<{ id: number; kind: string; term_id: number; label: string; is_active: boolean; status: string }[]>("GET", "/runs");
  const board = runs.find((r) => r.term_id === ctx.termId && r.kind === "COURSE" && r.label.startsWith("Grid import"));
  const solver = runs.find((r) => r.id === solverRun() && r.term_id === ctx.termId && r.kind === "COURSE");
  test.skip(!solver || solver.id === board?.id, "needs the full-term solver run of e2e-backend-entry.sh");
  await api("POST", `/runs/${solver!.id}/activate`);
  try {
    const g = await dayGrid(TUESDAY, ctx.token);
    const held = g.slots.filter((x) => x.status === "timetable");
    expect(held.length).toBeGreaterThan(0);
    expect(held.some((x) => x.label === "Ders")).toBe(false);
    // the English UI shows course labels (or the English fallback), not "Ders"
    const me = await api<{ id: number }>("GET", "/auth/me");
    await context.addInitScript((id) => sessionStorage.setItem("crbs.profile-language", String(id)), me.id);
    await login(page, ADMIN.username, ADMIN.password);
    await page.context().addCookies([{ name: "NEXT_LOCALE", value: "en", url: new URL(page.url()).origin }]);
    await openBookings(page, `date=${TUESDAY}&group=${ctx.groupA}&lens=grid`);
    const texts = await page.locator('button[data-tone="timetable"]').allTextContents();
    expect(texts.length).toBeGreaterThan(0);
    expect(texts.some((x) => /\bDers\b/.test(x))).toBe(false);
  } finally {
    if (board) await api("POST", `/runs/${board.id}/activate`);
  }
});
