/**
 * CRBS bookings against the REAL backend (no MSW), gated E2E_REAL=1.
 *
 * Backend: SQLite with the real Bahar 2026 workbooks (room master + weekly grid + planning list), with the
 * booking clock inside the term (Monday 16 Feb 2026, 08:00): the fixtures are Bahar 2026 and staff cannot
 * book the past. docs/testing/2026-10-08-real-backend-e2e.md describes the stack; the clock wrapper is the
 * same two-line patch tests/crbs_env.py uses (`app.services.bookings.today/now_local`).
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:8400 PW_PORT=3800 npx playwright test e2e/bookings.spec.ts
 *   (the frontend runs in real mode against the same backend)
 *
 * Users are created through the real API on every run (an e2e administrator and, through the UI, a
 * teacher), so the spec can run repeatedly on the same database. Booking setup that CRBS's installer would
 * do (published timetable, 18-period schedule, bookable session, room groups, the 23 Nisan holiday) is made
 * idempotently through the API first.
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import fs from "node:fs";

const REAL = process.env.E2E_REAL === "1";
const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const SEED_ADMIN = { email: process.env.E2E_ADMIN_EMAIL ?? "admin@smartsched.local", password: process.env.E2E_ADMIN_PASSWORD ?? "Admin-2026!" };
const TERM_CODE = process.env.E2E_TERM_CODE ?? "2026-BAHAR";
const STAMP = Date.now().toString(36);
const ADMIN = { username: `e2e.yonetici.${STAMP}`, email: `e2e.yonetici.${STAMP}@uni.edu.tr`, password: "Yonetici-2026!" };
const TEACHER = { username: `e2e.hoca.${STAMP}`, email: `e2e.hoca.${STAMP}@uni.edu.tr`, first: "Elif", last: "Şahin", password: "Ogretmen-2026!" };
const MONDAY = "2026-02-16";
const THURSDAY = "2026-02-19";
const HOLIDAY = "2026-04-23";

test.describe.configure({ mode: "serial" });
test.skip(!REAL, "real-backend booking flow: set E2E_REAL=1 (see the header)");

interface Ctx {
  api: APIRequestContext;
  token: string;
  termId: number;
  groupA: number;
  rooms: Record<string, number>;
  periods: Record<string, number>;
  teacherId?: number;
  singleId?: number;
  seriesBookingId?: number;
}
const ctx = {} as Ctx;

async function api<T = unknown>(method: "GET" | "POST" | "PUT", path: string, body?: unknown, token = ctx.token): Promise<T> {
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

async function uiLogin(page: Page, identifier: string, password: string) {
  await page.goto("/login");
  await page.fill("#identifier", identifier);
  await page.fill("#password", password);
  await page.click('[data-testid="login-submit"]');
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  const seed = await loginToken(SEED_ADMIN.email, SEED_ADMIN.password);
  ctx.token = seed;
  // an e2e administrator, created through the real API
  await api("POST", "/users", { username: ADMIN.username, email: ADMIN.email, displayname: "E2E Yönetici", role: "ADMIN", password: ADMIN.password });
  ctx.token = await loginToken(ADMIN.username, ADMIN.password);

  const dates = await api<{ today: string }>("GET", "/bookings/dates");
  test.skip(dates.today < "2026-02-02" || dates.today > "2026-06-28", `the backend's booking clock (${dates.today}) must be inside Bahar 2026; see the header`);

  // published timetable = the imported weekly grid (CRBS has no timetable; SmartSched blocks it)
  const terms = await api<{ id: number; code: string }[]>("GET", "/terms");
  ctx.termId = terms.find((x) => x.code === TERM_CODE)!.id;
  const runs = await api<{ id: number; kind: string; term_id: number; label: string; is_active: boolean }[]>("GET", "/runs");
  const board = runs.find((r) => r.term_id === ctx.termId && r.kind === "COURSE" && r.label.startsWith("Grid import"));
  if (board && !board.is_active) await api("POST", `/runs/${board.id}/activate`);
  // the university's 18 periods, a bookable session, room groups, the 23 Nisan holiday
  let schedules = await api<{ id: number; name: string; periods: { id: number; name: string }[] }[]>("GET", "/booking-admin/schedules");
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
  let groups = await api<{ id: number; name: string; room_ids: number[] }[]>("GET", "/room-admin/groups");
  if (!groups.length) groups = await api("POST", "/room-admin/groups/from-buildings");
  const rooms = await api<{ id: number; code: string; room_group_id: number | null }[]>("GET", "/room-admin/rooms");
  ctx.rooms = Object.fromEntries(rooms.map((r) => [r.code, r.id]));
  ctx.groupA = rooms.find((r) => r.code === "A101")!.room_group_id!;
  expect(rooms.find((r) => r.code === "A102")!.room_group_id).toBe(ctx.groupA);
  const holidays = await api<{ date_start: string }[]>("GET", `/holidays?term_id=${ctx.termId}`);
  if (!holidays.some((h) => h.date_start === HOLIDAY)) await api("POST", "/holidays", { term_id: ctx.termId, name: "Ulusal Egemenlik ve Çocuk Bayramı", date_start: HOLIDAY, date_end: HOLIDAY });
});

test.afterAll(async () => {
  await ctx.api?.dispose();
});

test("1. the administrator creates a teacher in Setup → Users", async ({ page }) => {
  await uiLogin(page, ADMIN.username, ADMIN.password);
  await page.goto("/admin/users");
  await page.getByTestId("users-new").click();
  const dialog = page.getByTestId("user-dialog");
  await dialog.locator("#u-username").fill(TEACHER.username);
  await dialog.locator("#u-email").fill(TEACHER.email);
  await dialog.locator("#u-first").fill(TEACHER.first);
  await dialog.locator("#u-last").fill(TEACHER.last);
  await dialog.locator("#u-role").selectOption({ label: "Teacher" });
  await dialog.locator("#u-password").fill(TEACHER.password);
  // the admin screens added a password confirmation (CRBS gap audit #22)
  if (await dialog.locator("#u-password2").count()) await dialog.locator("#u-password2").fill(TEACHER.password);
  await dialog.getByTestId("user-save").click();
  await expect(dialog).toBeHidden();
  await page.getByTestId("users-search").fill(TEACHER.username);
  await expect(page.locator(`[data-username="${TEACHER.username}"]`)).toContainText("Teacher");
  const found = await api<{ items: { id: number; username: string; role: string; permissions?: string[] }[] }>("GET", `/users/search?q=${TEACHER.username}`);
  ctx.teacherId = found.items[0]!.id;
  expect(found.items[0]).toMatchObject({ username: TEACHER.username, role: "TEACHER" });
});

test("2. the teacher signs in and sees bookings but no setup or planning screens", async ({ page }) => {
  await uiLogin(page, TEACHER.username, TEACHER.password);
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: /erişiminiz yok|do not have access/i })).toBeVisible();
  await page.goto(`/bookings?date=${MONDAY}&group=${ctx.groupA}`);
  await expect(page.getByTestId("booking-grid")).toBeVisible();
  const me = await api<{ permissions: string[] }>("GET", "/auth/me", undefined, await loginToken(TEACHER.username, TEACHER.password));
  expect(me.permissions).toContain("book_single.create");
  expect(me.permissions.some((p) => p.startsWith("setup.") || p.startsWith("planning."))).toBe(false);
});

test("3. the teacher books A 101 on a free slot", async ({ page }) => {
  await uiLogin(page, TEACHER.username, TEACHER.password);
  await page.goto(`/bookings?date=${MONDAY}&group=${ctx.groupA}`);
  const free = page.locator(`button[data-slot-key^="${MONDAY}|"][data-slot-key$="|${ctx.rooms.A101}"][data-tone="available"]`).first();
  const key = await free.getAttribute("data-slot-key");
  await free.click();
  const sheet = page.getByTestId("book-sheet");
  await expect(sheet).toContainText("A 101");
  await sheet.locator("#book-notes").fill("E2E tez savunması");
  await sheet.getByTestId("book-submit").click();
  await expect(sheet).toBeHidden();
  await expect(page.locator(`button[data-slot-key="${key}"]`)).toHaveAttribute("data-tone", "booked-mine");
  const mine = await api<{ id: number; room_name: string; notes: string }[]>("GET", "/bookings/mine", undefined, await loginToken(TEACHER.username, TEACHER.password));
  const b = mine.find((x) => x.room_name === "A 101" && x.notes === "E2E tez savunması");
  expect(b).toBeTruthy();
  ctx.singleId = b!.id;
});

test("4. a slot held by the timetable (FZT 132, Monday P4) is refused with a clear Turkish message", async ({ page }) => {
  await uiLogin(page, TEACHER.username, TEACHER.password);
  await page.goto(`/bookings?date=${MONDAY}&group=${ctx.groupA}`);
  // the grid shows it as timetable; activating it explains why it cannot be booked
  const held = page.locator(`button[data-slot-key="${MONDAY}|${ctx.periods.P4}|${ctx.rooms.A101}"]`);
  await expect(held).toHaveAttribute("data-tone", "timetable");
  await expect(held).toContainText("FZT 132");
  await held.click();
  await expect(page.getByTestId("slot-info-message")).toContainText("yayımlanmış ders programında FZT 132 dersine ayrılmış");
  await page.keyboard.press("Escape");
  // and the backend refuses a move into it: edit the booking from step 3 to P4
  await page.goto(`/my-bookings`);
  await page.locator(`[data-booking-id="${ctx.singleId}"] button`).last().click();
  await page.getByTestId("booking-edit").click();
  await page.locator("#edit-period").selectOption({ value: String(ctx.periods.P4) });
  await page.getByTestId("edit-save").click();
  await expect(page.getByTestId("edit-error")).toHaveText("A 101, 16.02.2026 P4–P5: yayımlanmış ders programında FZT 132 dersi var; bu saat rezerve edilemez.");
});

test("5. a recurring booking skips the 23 Nisan holiday", async ({ page }) => {
  // CRBS teachers cannot make recurring bookings; the administrator grants it on A 102 through the room ACL
  await api("POST", "/room-admin/acl", { entity_type: "room", entity_id: ctx.rooms.A102, context_type: "user", context_id: ctx.teacherId, permissions: ["room.view", "book_single.create", "book_recur.create"] });
  await uiLogin(page, TEACHER.username, TEACHER.password);
  await page.goto(`/bookings?date=${THURSDAY}&group=${ctx.groupA}`);
  const free = page.locator(`button[data-slot-key^="${THURSDAY}|"][data-slot-key$="|${ctx.rooms.A102}"][data-tone="available"]`).first();
  await free.click();
  const sheet = page.getByTestId("book-sheet");
  await sheet.getByRole("tab", { name: "Her hafta" }).click();
  await sheet.getByTestId("recur-preview-btn").click();
  const preview = sheet.getByTestId("recur-preview");
  const holidayRow = preview.locator(`li[data-date="${HOLIDAY}"]`);
  await expect(holidayRow).toHaveAttribute("data-kind", "holiday");
  await expect(holidayRow).toContainText("Ulusal Egemenlik ve Çocuk Bayramı");
  await expect(holidayRow).toContainText("Atlanır");
  await expect(sheet.getByTestId("recur-summary")).toContainText("1 tatil");
  await sheet.getByTestId("book-submit").click();
  await expect(sheet).toBeHidden();
  const mine = await api<{ id: number; date: string; series_id: number | null; room_name: string }[]>("GET", `/bookings/mine?from=${THURSDAY}`, undefined, await loginToken(TEACHER.username, TEACHER.password));
  const series = mine.filter((b) => b.series_id && b.room_name === "A 102");
  expect(series.length).toBeGreaterThan(5);
  expect(series.some((b) => b.date === HOLIDAY)).toBe(false);
  expect(series.some((b) => b.date === "2026-04-16") || series.some((b) => b.date === "2026-04-30")).toBe(true);
  ctx.seriesBookingId = series[0]!.id;
});

test("6. the teacher cancels with a reason (one booking, then the whole series)", async ({ page }) => {
  await uiLogin(page, TEACHER.username, TEACHER.password);
  await page.goto("/my-bookings");
  await page.locator(`[data-booking-id="${ctx.singleId}"] button`).last().click();
  await page.getByTestId("booking-cancel").click();
  await page.locator("#cancel-reason").fill("Toplantı ertelendi");
  await page.getByRole("button", { name: "İptal et", exact: true }).click();
  await expect(page.getByTestId("booking-sheet")).toBeHidden();
  const token = await loginToken(TEACHER.username, TEACHER.password);
  const one = await api<{ status: string; cancel_reason: string | null }>("GET", `/bookings/${ctx.singleId}`, undefined, token);
  expect(one).toMatchObject({ status: "CANCELLED", cancel_reason: "Toplantı ertelendi" });
  // the series: scope "Tüm seri"
  await page.goto("/my-bookings");
  await page.locator(`[data-booking-id="${ctx.seriesBookingId}"] button`).last().click();
  await page.getByTestId("booking-cancel").click();
  await page.getByRole("tab", { name: "Tüm seri" }).click();
  await page.locator("#cancel-reason").fill("Dönem planı değişti");
  await page.getByRole("button", { name: "İptal et", exact: true }).click();
  await expect(page.getByTestId("booking-sheet")).toBeHidden();
  const left = await api<{ series_id: number | null; room_name: string }[]>("GET", "/bookings/mine", undefined, token);
  expect(left.filter((b) => b.series_id && b.room_name === "A 102")).toHaveLength(0);
});

test("7. the administrator sees it in the CSV export", async ({ page }) => {
  await uiLogin(page, ADMIN.username, ADMIN.password);
  await page.goto("/my-bookings");
  await page.getByText("İptal edilenleri de ekle").click();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("export-csv").click()]);
  const csv = fs.readFileSync((await download.path())!, "utf-8");
  expect(csv.charCodeAt(0)).toBe(0xfeff); // UTF-8 BOM for Excel
  const rows = csv.split(/\r?\n/).filter((l) => l.includes(TEACHER.username));
  expect(rows.length).toBeGreaterThan(5);
  expect(rows.some((l) => l.includes("A 101") && l.includes(",Cancelled,") && l.includes("E2E tez savunması"))).toBe(true);
  expect(rows.some((l) => l.includes("A 102"))).toBe(true);
  expect(csv).toContain("Elif Şahin");
});

/* ---------------------------------------------------------------- CRBS screen behaviours (parity audit) */

test("8. names and notes follow permissions and the show-names setting", async ({ page }) => {
  // the administrator books A 101 Monday P2 with a note
  const admin = await api<{ id: number }>("POST", "/bookings", { room_id: ctx.rooms.A101, date: MONDAY, period_id: ctx.periods.P2, notes: "Bölüm kurulu" });
  try {
    await api("PUT", "/org/settings", { bookings_show_name: false });
    await uiLogin(page, TEACHER.username, TEACHER.password);
    await page.goto(`/bookings?date=${MONDAY}&group=${ctx.groupA}`);
    const cell = page.locator(`button[data-slot-key="${MONDAY}|${ctx.periods.P2}|${ctx.rooms.A101}"]`);
    await expect(cell).toHaveAttribute("data-tone", "booked-single");
    await expect(cell).toContainText("Rezerve"); // Teacher: no view_other_users → no name
    await expect(cell).toContainText("Bölüm kurulu"); // but view_other_notes (data.sql)
    await expect(cell).not.toContainText("E2E Yönetici");
    await api("PUT", "/org/settings", { bookings_show_name: true });
    await page.reload();
    await expect(cell).toContainText("E2E Yönetici");
  } finally {
    await api("PUT", "/org/settings", { bookings_show_name: false });
    await api("POST", `/bookings/${admin.id}/cancel`, { scope: "one", reason: "e2e cleanup" });
  }
});

test("9. grid orientation (display type × columns), room card and print view", async ({ page }) => {
  await uiLogin(page, ADMIN.username, ADMIN.password);
  try {
    await api("PUT", "/org/settings", { displaytype: "day", d_columns: "rooms" });
    await page.goto(`/bookings?date=${MONDAY}&group=${ctx.groupA}`);
    const grid = page.getByTestId("booking-grid");
    await expect(grid.locator("thead th").first()).toHaveText("Ders saati"); // periods down, rooms across
    await expect(grid.locator("thead")).toContainText("A 101");
    await expect(grid.locator("tbody th").first()).toContainText("P1");
  } finally {
    await api("PUT", "/org/settings", { displaytype: "day", d_columns: "periods" });
  }
  await page.goto(`/bookings?date=${MONDAY}&group=${ctx.groupA}`);
  await expect(page.getByTestId("booking-grid").locator("thead th").first()).toHaveText("Salon");
  // room card from the grid header
  await page.getByTestId("room-info-A101").click();
  await expect(page.getByTestId("room-info")).toContainText("A 101");
  await expect(page.getByTestId("room-info")).toContainText("A Blok");
  await page.keyboard.press("Escape");
  // week view by room: Saturday and Sunday have no periods, so they are not listed
  await page.goto(`/bookings?display=room&date=${MONDAY}&room=${ctx.rooms.A101}`);
  await expect(page.getByTestId("booking-grid").locator("tbody th")).toHaveCount(5);
  // print: only the grid and its title remain
  await page.emulateMedia({ media: "print" });
  await expect(page.locator('[data-print-hide]').first()).toBeHidden();
  await expect(page.getByTestId("booking-grid")).toBeVisible();
  await page.emulateMedia({ media: "screen" });
  await expect(page.getByTestId("print")).toBeVisible();
});

test("10. maintenance mode stops bookings for staff, administrators bypass it", async ({ browser }) => {
  await api("PUT", "/org/settings", { maintenance_mode: true, maintenance_mode_message: "Sistem bakımda, 14:00'te açılır." });
  try {
    const teacher = await browser.newPage();
    await uiLogin(teacher, TEACHER.username, TEACHER.password);
    await teacher.goto("/bookings");
    await expect(teacher.getByTestId("maintenance-message")).toHaveText("Sistem bakımda, 14:00'te açılır.");
    const admin = await browser.newPage();
    await uiLogin(admin, ADMIN.username, ADMIN.password);
    await admin.goto(`/bookings?date=${MONDAY}&group=${ctx.groupA}`);
    await expect(admin.getByText("Bakım modu açık")).toBeVisible();
    await expect(admin.getByTestId("booking-grid")).toBeVisible();
  } finally {
    await api("PUT", "/org/settings", { maintenance_mode: false });
  }
});

test("11. profile language (per user, like CRBS)", async ({ page }) => {
  await uiLogin(page, TEACHER.username, TEACHER.password);
  await page.goto("/profile");
  await page.getByTestId("profile-language").selectOption("en");
  await page.getByTestId("profile-save").click();
  await expect(page.getByRole("heading", { level: 1, name: "Profile" })).toBeVisible();
  const prof = await api<{ language: string }>("GET", "/auth/profile", undefined, await loginToken(TEACHER.username, TEACHER.password));
  expect(prof.language).toBe("en");
  await page.getByTestId("profile-language").selectOption("tr");
  await page.getByTestId("profile-save").click();
  await expect(page.getByRole("heading", { level: 1, name: "Profil" })).toBeVisible();
});

test("12. one-time reset code (shown once) and the reset-password page; setup is closed once done", async ({ page, browser }) => {
  await uiLogin(page, ADMIN.username, ADMIN.password);
  await page.goto("/admin/users");
  await page.getByTestId("users-search").fill(TEACHER.username);
  const row = page.locator(`[data-username="${TEACHER.username}"]`);
  await row.getByRole("button", { name: new RegExp(TEACHER.username) }).click();
  await page.getByRole("menuitem", { name: "Tek kullanımlık sıfırlama kodu" }).click();
  const code = await page.getByTestId("reset-token").inputValue();
  expect(code.length).toBeGreaterThan(8);
  await page.keyboard.press("Escape");
  // the code page (public in CRBS; a signed-out visitor needs the shell's proxy to allow /reset-password)
  const anon = await browser.newPage();
  await anon.goto(`/reset-password?token=${encodeURIComponent(code)}`);
  const target = anon.url().includes("/login") ? page : anon;
  if (target === page) test.info().annotations.push({ type: "shell", description: "proxy.ts redirects signed-out visitors from /reset-password to /login" });
  await target.goto(`/reset-password?token=${encodeURIComponent(code)}`);
  await target.locator("#rs-pw").fill("Yeni-Parola-2026!");
  await target.locator("#rs-pw2").fill("Yeni-Parola-2026!");
  await target.getByRole("button", { name: "Yeni parolayı kaydet" }).click();
  await expect(target.getByTestId("reset-done")).toBeVisible();
  await loginToken(TEACHER.username, "Yeni-Parola-2026!");
  TEACHER.password = "Yeni-Parola-2026!";
  // the first-run wizard only runs while there are no users
  await target.goto("/setup");
  await expect(target.getByText("Bu kurulum zaten tamamlanmış")).toBeVisible();
});

test("13. planners see bookings the published timetable overlaps (conflicts after publishing); teachers cannot", async ({ page }) => {
  // the real list from the API: one UI row per booking, however many timetable slots overlap it
  const pairs = await api<{ booking_id: number }[]>("GET", `/bookings/conflicts?term_id=${ctx.termId}`);
  const bookings = new Set(pairs.map((p) => p.booking_id)).size;
  await uiLogin(page, ADMIN.username, ADMIN.password);
  await page.goto("/admin/conflicts");
  await expect(page.getByRole("heading", { name: "Rezervasyon çakışmaları" })).toBeVisible();
  if (bookings === 0) {
    // SmartSched refuses bookings on timetable slots (test 4), so a clash only appears after a new run is activated
    await expect(page.getByTestId("conflicts-empty")).toHaveText("Yayımlanan ders programıyla çakışan rezervasyon yok.");
  } else {
    await expect(page.getByTestId("conflicts-list").locator("li")).toHaveCount(bookings);
  }
  await page.goto("/admin");
  // listed in the setup tabs and in the overview's calendar group
  await expect(page.getByRole("navigation", { name: "Kurulum" }).getByRole("link", { name: "Rezervasyon çakışmaları", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /^Rezervasyon çakışmaları Yayımlanan/ })).toHaveAttribute("href", "/admin/conflicts");

  const teacher = await page.context().browser()!.newPage();
  await uiLogin(teacher, TEACHER.username, TEACHER.password);
  await teacher.goto("/admin/conflicts");
  await expect(teacher.getByRole("heading", { name: /erişiminiz yok|do not have access/i })).toBeVisible();
  const res = await ctx.api.get(`${API}/bookings/conflicts`, { headers: { Authorization: `Bearer ${await loginToken(TEACHER.username, TEACHER.password)}` } });
  expect(res.status()).toBe(403);
  await teacher.close();
});

test("14. no escalation: a role manager without planning rights cannot grant, edit or import beyond their own permissions", async ({ page }) => {
  // a custom role that manages users and roles but holds no planning permission (made by the administrator)
  const roleName = `E2E Rol yöneticisi ${STAMP}`;
  const own = ["setup.roles", "setup.users", "room.view", "book_single.create"];
  const role = await api<{ id: number }>("POST", "/roles", { name: roleName, permissions: own });
  const mgr = { username: `e2e.rolyon.${STAMP}`, password: "Rolyonetici-2026!" };
  await api("POST", "/users", { username: mgr.username, email: `${mgr.username}@uni.edu.tr`, role_id: role.id, password: mgr.password });
  const roles = await api<{ id: number; code: string | null; name: string; permissions: string[] }[]>("GET", "/roles");
  const planner = roles.find((r) => r.code === "PLANNER")!;
  const plannerMissing = planner.permissions.filter((p) => !own.includes(p)).sort();

  // the backend refuses with the missing permissions in the detail
  const mgrToken = await loginToken(mgr.username, mgr.password);
  const refused = await ctx.api.fetch(`${API}/roles/${planner.id}`, { method: "PUT", data: { description: "x" }, headers: { Authorization: `Bearer ${mgrToken}` } });
  expect(refused.status()).toBe(403);
  expect(await refused.text()).toContain(plannerMissing[0]!);

  await uiLogin(page, mgr.username, mgr.password);
  // role editor: Planner is read-only (names what is missing), cannot be deleted
  await page.goto("/admin/roles");
  await page.getByRole("button", { name: /^Planner/ }).click();
  const editor = page.getByTestId("role-editor");
  await expect(editor.getByTestId("role-readonly")).toContainText(plannerMissing[0]!);
  await expect(editor.getByRole("button", { name: /Rolü sil|Delete role/ })).toHaveCount(0);
  await expect(editor.getByTestId("role-save")).toBeDisabled();
  // a new role cannot get a permission the editor does not hold
  await page.getByTestId("roles-new").click();
  const notHeld = page.getByTestId("role-editor").locator('[data-not-held="true"]');
  await expect(notHeld.first()).toBeVisible();
  await expect(notHeld.first().getByRole("checkbox")).toBeDisabled();
  await expect(page.getByTestId("role-editor").locator('label:not([data-not-held]) [role="checkbox"]').first()).toBeEnabled();

  // users: the administrator's account is beyond this role; the picker disables roles it cannot grant
  await page.goto("/admin/users");
  await page.getByTestId("users-search").fill("admin@smartsched.local");
  await expect(page.locator('[data-username="admin@smartsched.local"]').getByTestId("user-privileged")).toBeVisible();
  await page.getByTestId("users-new").click();
  const dialog = page.getByTestId("user-dialog");
  const plannerOption = dialog.locator("#u-role option", { hasText: /^Planner/ });
  await expect(plannerOption).toBeDisabled();
  await expect(plannerOption).toContainText("eksik:");
  await expect(dialog.locator("#u-role option", { hasText: roleName })).toBeEnabled();
  await expect(dialog.getByTestId("role-disabled-hint")).toBeVisible();
  await page.keyboard.press("Escape");

  // CSV import: a row asking for Planner comes back "forbidden", a row with the manager's own role is created
  await page.getByTestId("users-import").click();
  const imp = page.getByRole("dialog");
  const csv = [
    `e2e.imp1.${STAMP};İlk;Satır;e2e.imp1.${STAMP}@uni.edu.tr;Gecici-2026!;${roleName};`,
    `e2e.imp2.${STAMP};İkinci;Satır;e2e.imp2.${STAMP}@uni.edu.tr;Gecici-2026!;Planner;`,
  ].join("\n");
  await imp.locator("#imp-file").setInputFiles({ name: "kullanicilar.csv", mimeType: "text/csv", buffer: Buffer.from(csv, "utf-8") });
  await imp.locator("#imp-role").selectOption({ label: roleName });
  await imp.getByRole("button", { name: "İçe aktar", exact: true }).click();
  const results = imp.getByTestId("import-results");
  await expect(results).toContainText("Oluşturuldu");
  await expect(results).toContainText("İzin yok");
  await expect(imp.getByTestId("import-forbidden")).toContainText("1 satır");
});
