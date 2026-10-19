/**
 * Booking enhancements wave 1 against the REAL backend (no mocks), gated E2E_REAL=1: typed room features
 * (X-08), find a room (X-09), the audit log with undo (X-10), approvals by designated administrators (X-11),
 * the in-app bell, and a crawler over every sidebar and ⌘K link for an administrator and a teacher (no 404,
 * no page that answers 403).
 *
 * Backend: smartsched/deploy/pod-ci/gates/e2e-backend-entry.sh (real Bahar 2026 workbooks, seeded admin,
 * booking clock pinned to Monday 16 Feb 2026 08:00). Everything this spec changes is its own: new users, a
 * new room in the A-block room group (so the approval rule touches nothing else) and a feature with a unique
 * name; afterAll removes the rule, the designation, the feature and the room.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:8760 NEXT_PUBLIC_API_URL=http://127.0.0.1:8760 PW_PORT=3760 \
 *     npx playwright test e2e/wave1.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, TERM_CODE, fillDate, login } from "./helpers";
import { pinLanguage } from "./language";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const TAG = `W${STAMP.slice(-6).toUpperCase()}`;
const ADMIN = { username: `w1.yonetici.${STAMP}`, email: `w1.yonetici.${STAMP}@uni.edu.tr`, password: "Yonetici-2026!" };
const APPROVER = { username: `w1.onayci.${STAMP}`, email: `w1.onayci.${STAMP}@uni.edu.tr`, first: "Ayşe", last: "Yılmaz", password: "Onayci-2026!" };
const TEACHER = { username: `w1.hoca.${STAMP}`, email: `w1.hoca.${STAMP}@uni.edu.tr`, first: "Deniz", last: "Kaya", password: "Ogretmen-2026!" };
const TEACHER2 = { username: `w1.hoca2.${STAMP}`, email: `w1.hoca2.${STAMP}@uni.edu.tr`, first: "Mert", last: "Demir", password: "Ogretmen-2026!" };
const WEDNESDAY = "2026-02-18";
const THURSDAY = "2026-02-19";
const FRIDAY = "2026-02-20";

test.describe.configure({ mode: "serial" });
test.skip(!REAL, SKIP_REASON);
// the assertions read Turkish (the product default): pin it, whatever the previous spec left behind
pinLanguage("tr");

interface GridSlot {
  date: string;
  period_id: number;
  room_id: number;
  status: string;
  allow_single?: boolean;
  booking?: { id: number; status: string };
}
interface Grid {
  periods: { id: number; name: string; start_period: number; end_period: number }[];
  rooms: { id: number; code: string; name: string }[];
  slots: GridSlot[];
}
interface Ctx {
  api: APIRequestContext;
  token: string;
  approverToken: string;
  teacherToken: string;
  teacher2Token: string;
  termId: number;
  groupA: number;
  room: { id: number; code: string; name: string };
  approverId: number;
  ruleId: number | null;
  featureIds: number[];
}
const ctx = { ruleId: null, featureIds: [] } as unknown as Ctx;

async function call<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token = ctx.token): Promise<{ status: number; body: T }> {
  const res = await ctx.api.fetch(`${API}${path}`, { method, data: body, headers: { Authorization: `Bearer ${token}` } });
  const text = await res.text();
  return { status: res.status(), body: (text ? JSON.parse(text) : undefined) as T };
}
async function api<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token = ctx.token): Promise<T> {
  const r = await call<T>(method, path, body, token);
  if (r.status >= 400) throw new Error(`${method} ${path} → ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}
async function loginToken(identifier: string, password: string): Promise<string> {
  const body = identifier.includes("@") ? { email: identifier, password } : { username: identifier, password };
  const res = await ctx.api.post(`${API}/auth/login`, { data: body });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { access_token: string }).access_token;
}
const dayGrid = (date: string, token = ctx.teacherToken) => api<Grid>("GET", `/bookings/grid?display=day&date=${date}&room_group_id=${ctx.groupA}`, undefined, token);
/** the first periods of our own room that are reservable on the date */
async function ownFree(date: string, n = 1, token = ctx.teacherToken): Promise<GridSlot[]> {
  const g = await dayGrid(date, token);
  const order = new Map(g.periods.map((p, i) => [p.id, i]));
  const day = g.slots.filter((s) => s.room_id === ctx.room.id && s.date === date).sort((a, b) => (order.get(a.period_id) ?? 0) - (order.get(b.period_id) ?? 0));
  for (let i = 0; i + n <= day.length; i++) {
    const part = day.slice(i, i + n);
    if (part.every((s) => s.status === "available" && s.allow_single)) return part;
  }
  throw new Error(`no ${n} free periods in ${ctx.room.code} on ${date}`);
}
const cell = (page: Page, s: { date: string; period_id: number; room_id: number }) => page.locator(`button[data-slot-key="${s.date}|${s.period_id}|${s.room_id}"]`);

async function openPalette(page: Page) {
  await page.getByTestId("helper-trigger").click() // HX: the palette trigger is the helper's "Ara veya sor";
  await expect(page.getByRole("dialog")).toBeVisible();
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.token = await loginToken(ADMIN_EMAIL, ADMIN_PASSWORD);
  await api("POST", "/users", { username: ADMIN.username, email: ADMIN.email, displayname: "Wave1 Yönetici", role: "ADMIN", password: ADMIN.password });
  ctx.token = await loginToken(ADMIN.username, ADMIN.password);
  const dates = await api<{ today: string }>("GET", "/bookings/dates");
  test.skip(dates.today < "2026-02-02" || dates.today > "2026-06-28", `the backend's booking clock (${dates.today}) must be inside Bahar 2026`);

  // the booking setup CRBS's installer would make (same as e2e/bookings.spec.ts, idempotent)
  const terms = await api<{ id: number; code: string }[]>("GET", "/terms");
  ctx.termId = terms.find((x) => x.code === TERM_CODE)!.id;
  const runs = await api<{ id: number; kind: string; term_id: number; label: string; is_active: boolean }[]>("GET", "/runs");
  const board = runs.find((r) => r.term_id === ctx.termId && r.kind === "COURSE" && (r.label ?? "").startsWith("Grid import"));
  if (board && !board.is_active) await api("POST", `/runs/${board.id}/activate`);
  let schedules = await api<{ id: number; periods: { id: number; name: string }[] }[]>("GET", "/booking-admin/schedules");
  let schedule = schedules.find((s) => s.periods.length >= 18);
  if (!schedule) {
    const s = await api<{ id: number }>("POST", "/booking-admin/schedules", { name: `Ders saatleri ${STAMP}` });
    await api("POST", `/booking-admin/schedules/${s.id}/periods/from-grid?days=1,2,3,4,5`);
    schedules = await api("GET", "/booking-admin/schedules");
    schedule = schedules.find((x) => x.id === s.id)!;
  }
  const sessions = await api<{ term_id: number; default_schedule_id: number | null; is_selectable: boolean }[]>("GET", "/booking-admin/sessions");
  const sess = sessions.find((s) => s.term_id === ctx.termId)!;
  if (!sess.is_selectable || sess.default_schedule_id !== schedule.id) await api("PUT", `/booking-admin/sessions/${ctx.termId}`, { is_selectable: true, default_schedule_id: schedule.id });
  let groups = await api<{ id: number }[]>("GET", "/room-admin/groups");
  if (!groups.length) groups = await api("POST", "/room-admin/groups/from-buildings");
  const rooms = await api<{ id: number; code: string; room_group_id: number | null }[]>("GET", "/room-admin/rooms");
  ctx.groupA = rooms.find((r) => r.code === "A101")!.room_group_id!;

  // our own room in the A group: no timetable, so it is free all week, and the approval rule touches nothing else
  const no = 100 + (Date.now() % 900);
  const made = await api<{ id: number; code: string; display_name: string }>("POST", "/rooms", { code: `W ${no}`, display_name: `E2E Onay Salonu ${STAMP}`, capacity: 120 });
  await api("PUT", `/room-admin/rooms/${made.id}`, { room_group_id: ctx.groupA, is_bookable: true });
  ctx.room = { id: made.id, code: made.code, name: made.display_name };

  const deps = await api<{ id: number; name: string }[]>("GET", "/departments");
  const dept = deps[0]?.id ?? null;
  const appr = await api<{ id: number }>("POST", "/users", { username: APPROVER.username, email: APPROVER.email, firstname: APPROVER.first, lastname: APPROVER.last, displayname: `${APPROVER.first} ${APPROVER.last}`, role: "ADMIN", password: APPROVER.password });
  ctx.approverId = appr.id;
  await api("POST", "/users", { username: TEACHER.username, email: TEACHER.email, firstname: TEACHER.first, lastname: TEACHER.last, role: "TEACHER", password: TEACHER.password, department_id: dept });
  await api("POST", "/users", { username: TEACHER2.username, email: TEACHER2.email, firstname: TEACHER2.first, lastname: TEACHER2.last, role: "TEACHER", password: TEACHER2.password, department_id: dept });
  ctx.approverToken = await loginToken(APPROVER.username, APPROVER.password);
  ctx.teacherToken = await loginToken(TEACHER.username, TEACHER.password);
  ctx.teacher2Token = await loginToken(TEACHER2.username, TEACHER2.password);
});

test.afterAll(async () => {
  if (!ctx.api) return;
  if (ctx.ruleId) await call("DELETE", `/approval-rules/${ctx.ruleId}`);
  for (const r of (await call<{ id: number; room_id: number }[]>("GET", "/approval-rules")).body ?? []) if (r.room_id === ctx.room?.id) await call("DELETE", `/approval-rules/${r.id}`);
  if (ctx.approverId) await call("PUT", `/approvals/approvers/${ctx.approverId}`, { scopes: [] });
  for (const id of ctx.featureIds) await call("DELETE", `/room-admin/features/${id}?confirm=true`);
  // a room with bookings cannot be deleted (409 room_has_bookings): take it out of booking instead
  if (ctx.room && (await call("DELETE", `/rooms/${ctx.room.id}`)).status === 409) await call("PUT", `/room-admin/rooms/${ctx.room.id}`, { is_bookable: false });
  await ctx.api.dispose();
});

test("wave1 1. room features: a typed feature, a value in the grid, the bulk CSV check and the solver-tag impact confirm (X-08)", async ({ page }) => {
  test.setTimeout(150_000);
  const name = `E2E Projeksiyon ${STAMP}`;
  await login(page, ADMIN.username, ADMIN.password);
  await page.goto("/admin/rooms?tab=features");
  const tab = page.getByTestId("features-tab");
  await expect(tab).toBeVisible();
  await expect(tab.getByTestId("features-adopt")).toBeVisible();

  // a yes/no feature that feeds the solver tag
  await tab.getByTestId("feature-new").click();
  const dialog = page.getByRole("dialog");
  await dialog.getByTestId("feature-name").fill(name);
  await dialog.getByTestId("feature-type").selectOption("BOOLEAN");
  await dialog.getByTestId("feature-solver-tag").fill(TAG.toLowerCase());
  await expect(dialog).toContainText(/yerleştirme kurallarını etkiler|affects timetable placement/);
  await dialog.getByTestId("feature-save").click();
  await expect(dialog).toBeHidden();
  const features = await api<{ id: number; name: string; solver_tag: string | null }[]>("GET", "/room-admin/features");
  const feature = features.find((f) => f.name === name)!;
  ctx.featureIds.push(feature.id);
  expect(feature.solver_tag).toBe(TAG);
  await expect(tab.getByTestId(`feature-${feature.id}`)).toBeVisible();

  // the values grid: tick it for our room and save the changed row
  const row = tab.getByTestId(`values-row-${ctx.room.code}`);
  await row.scrollIntoViewIfNeeded();
  await row.getByRole("checkbox", { name: new RegExp(name) }).click();
  await expect(row).toHaveAttribute("data-dirty", "true");
  await tab.getByTestId("feature-values-save").click();
  await expect.poll(async () => (await api<{ values: Record<string, unknown>; tags: string[] }>("GET", `/room-admin/rooms/${ctx.room.id}/features`)).tags).toContain(TAG);

  // removing the solver tag that a room carries: 409 → the impact is shown → confirm
  await tab.getByTestId(`feature-${feature.id}`).getByRole("button", { name: new RegExp(`düzenle|Edit`) }).click();
  await dialog.getByTestId("feature-solver-tag").fill("");
  await dialog.getByTestId("feature-save").click();
  await expect(dialog.getByTestId("feature-impact")).toBeVisible();
  await expect(dialog.getByTestId("feature-impact")).toContainText(TAG);
  await dialog.getByTestId("feature-save").click();
  await expect(dialog).toBeHidden();
  await expect.poll(async () => (await api<{ tags: string[] }>("GET", `/room-admin/rooms/${ctx.room.id}/features`)).tags).not.toContain(TAG);

  // bulk CSV: a bad cell is reported per cell (dry run), a good file applies
  await tab.getByTestId("features-bulk").click();
  const bulk = page.getByTestId("features-bulk-dialog");
  await expect(bulk.getByTestId("features-template")).toBeVisible();
  await bulk.getByTestId("features-file").setInputFiles({ name: "kotu.csv", mimeType: "text/csv", buffer: Buffer.from(`kod;${name}\n${ctx.room.code};belki\n`, "utf-8") });
  await bulk.getByTestId("features-check").click();
  await expect(bulk.getByTestId("features-report")).toContainText(/1 (hata|errors)/);
  await expect(bulk.getByTestId("features-apply")).toBeDisabled();
  await bulk.getByTestId("features-file").setInputFiles({ name: "iyi.csv", mimeType: "text/csv", buffer: Buffer.from(`kod;${name}\n${ctx.room.code};hayır\n`, "utf-8") });
  await bulk.getByTestId("features-check").click();
  await expect(bulk.getByTestId("features-report")).toContainText(/0 (hata|errors)/);
  await bulk.getByTestId("features-apply").click();
  await expect(bulk).toBeHidden();
  await expect.poll(async () => (await api<{ values: Record<string, unknown> }>("GET", `/room-admin/rooms/${ctx.room.id}/features`)).values[String(feature.id)]).toBe(false);
});

test("wave1 2. find a room: ⌘K, Wednesday 10:10–12:30 for 90 ranked like the API with its reasons, Reserve through the booking sheet, recent searches (X-09)", async ({ page }) => {
  test.setTimeout(150_000);
  await login(page, TEACHER.username, TEACHER.password);
  await page.goto("/bookings");
  await openPalette(page);
  await page.getByRole("dialog").getByRole("combobox").fill("boş derslik");
  await page.locator('[cmdk-item][data-value="action-find-room"]').click();
  await page.waitForURL(/\/find-room/);

  const view = page.getByTestId("find-room");
  await fillDate(view.getByTestId("fr-date"), WEDNESDAY);
  await view.getByTestId("fr-start").fill("10.10");
  await view.getByTestId("fr-end").fill("12:30");
  await view.getByTestId("fr-headcount").fill("90");
  await view.getByTestId("fr-search").click();
  await expect(view.getByTestId("fr-summary")).toBeVisible();

  // the same ranking as the backend's own answer, with its Turkish reasons
  const out = await api<{ results: { code: string; status: string; action: string; reason: { tr: string } | null }[] }>(
    "POST",
    "/rooms/find",
    { term_id: ctx.termId, date: WEDNESDAY, start: "10:10", end: "12:30", headcount: 90, include_busy: false, flex: { periods: 2, other_days: false }, limit: 60 },
    ctx.teacherToken,
  );
  const free = out.results.filter((r) => ["free", "requestable", "partial"].includes(r.status));
  expect(free.length).toBeGreaterThan(0);
  const rows = view.getByTestId("fr-results").locator("li");
  await expect(rows).toHaveCount(free.length);
  const shown = await rows.evaluateAll((els) => els.map((e) => (e.getAttribute("data-testid") ?? "").replace("fr-room-", "")));
  expect(shown).toEqual(free.map((r) => r.code));
  if (free[0]!.reason) await expect(rows.first()).toContainText(free[0]!.reason.tr);

  // one click: the booking sheet with the room and the periods, then the room is no longer free
  const pick = free.find((r) => r.status === "free" && r.action === "book")!;
  await view.getByTestId(`fr-reserve-${pick.code}`).click();
  const sheet = page.getByTestId("book-sheet");
  await expect(sheet).toBeVisible();
  await sheet.getByTestId("book-submit").click();
  await expect(sheet).toBeHidden();
  await expect(view.getByTestId(`fr-room-${pick.code}`)).toHaveCount(0);
  const mine = await api<{ room_name: string; date: string }[]>("GET", `/bookings/mine?from=${WEDNESDAY}&to=${WEDNESDAY}`, undefined, ctx.teacherToken);
  expect(mine.some((b) => b.date === WEDNESDAY)).toBe(true);

  // the search is remembered and re-runs in one click
  await page.reload();
  await expect(view.getByTestId("fr-recent")).toBeVisible();
  await view.getByTestId("fr-recent").getByRole("button").first().click();
  await expect(view.getByTestId("fr-summary")).toBeVisible();
});

test("wave1 3. audit log: filter a booking, the before/after diff, Undo, a refused undo with its reason, CSV export (X-10)", async ({ page }) => {
  test.setTimeout(150_000);
  const [a, b] = await ownFree(THURSDAY, 2, ctx.token);
  const first = await api<{ id: number }>("POST", "/bookings", { room_id: ctx.room.id, date: THURSDAY, period_id: a!.period_id, term_id: ctx.termId, notes: "Denetim e2e" });
  const second = await api<{ id: number }>("POST", "/bookings", { room_id: ctx.room.id, date: THURSDAY, period_id: b!.period_id, term_id: ctx.termId, notes: "Denetim e2e 2" });
  // a later change to the second booking: its create can no longer be undone
  await api("PUT", `/bookings/${second.id}?scope=one`, { notes: "değişti" });

  await login(page, ADMIN.username, ADMIN.password);
  await page.goto("/admin/audit");
  const view = page.getByTestId("audit");
  await view.getByTestId("audit-entity").selectOption("booking");
  await view.getByTestId("audit-entity-id").fill(String(first.id));
  await view.getByTestId("audit-apply").click();
  const event = view.locator('[data-action="booking.create"]').first();
  await expect(event).toBeVisible();
  // the row reads as a domain sentence (UI/UX review §3); the raw action key moved into the opened details
  await event.locator("button[aria-expanded]").first().click();
  await expect(event.locator('[data-testid^="audit-action-"]')).toHaveText("booking.create");
  await expect(event.getByTestId("audit-diff")).toContainText("Denetim e2e");
  await event.getByRole("button", { name: /Geri al|Undo/ }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: /Geri al|Undo/ }).click();
  await expect(page.getByRole("alertdialog")).toBeHidden();
  await expect.poll(async () => (await api<{ status: string }>("GET", `/bookings/${first.id}`)).status).toBe("CANCELLED");

  // refused: a later event touched the booking (409 changed_since, the backend's Turkish sentence)
  await view.getByTestId("audit-entity-id").fill(String(second.id));
  await view.getByTestId("audit-apply").click();
  const created = view.locator('[data-action="booking.create"]').first();
  await created.getByRole("button", { name: /Geri al|Undo/ }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: /Geri al|Undo/ }).click();
  await expect(page.getByTestId("audit-undo-error")).toContainText(/değişiklik yapıldı|change/);
  await page.keyboard.press("Escape");

  // the CSV export of the filtered range
  const href = await view.getByTestId("audit-export").getAttribute("href");
  expect(href).toContain("/api/v1/audit/export.csv");
  // what the download link fetches, with the browser's session cookie
  const csv = await page.evaluate(async (url) => {
    const r = await fetch(url, { credentials: "same-origin" });
    return { status: r.status, type: r.headers.get("content-type") ?? "", text: await r.text() };
  }, href!);
  expect(csv.status).toBe(200);
  expect(csv.type).toContain("text/csv");
  expect(csv.text).toContain("booking.create");
});

test("wave1 4. approvals: approves-for in the user form, a rule, the request (202) from the booking sheet, the inbox badge, approve; reject with a suggestion; part of a series; a 409 re-check; the requester's timeline and bell (X-11)", async ({ page, browser }) => {
  test.setTimeout(240_000);
  // the administrator designates the approver (user form "Approves for") and adds a rule on our room with a hold
  await login(page, ADMIN.username, ADMIN.password);
  await page.goto("/admin/users");
  await page.getByTestId("users-search").fill(APPROVER.username);
  await page.getByRole("button", { name: new RegExp(APPROVER.username) }).click();
  await page.getByRole("menuitem", { name: /Düzenle|Edit/ }).click();
  const user = page.getByTestId("user-dialog");
  await user.getByTestId("user-approves-for").locator("summary").click();
  await user.getByTestId("user-scope-all").click();
  await user.getByTestId("user-save").click();
  await expect(user).toBeHidden();
  await expect.poll(async () => (await api<{ user_id: number; scopes: { type: string }[] }[]>("GET", "/approvals/approvers")).find((x) => x.user_id === ctx.approverId)?.scopes.map((x) => x.type)).toEqual(["all"]);

  await page.goto("/admin/approval-rules");
  await page.getByTestId("rule-new").click();
  const form = page.getByRole("dialog");
  await form.getByTestId("rule-type").selectOption("room");
  await form.getByTestId("rule-entity").selectOption(String(ctx.room.id));
  await form.getByTestId("rule-hold").fill("120");
  await form.getByTestId("rule-save").click();
  await expect(form).toBeHidden();
  const rules = await api<{ id: number; entity_id: number | null }[]>("GET", "/approval-rules");
  ctx.ruleId = rules.find((r) => r.entity_id === ctx.room.id)!.id;
  await expect(page.getByTestId(`rule-${ctx.ruleId}`)).toBeVisible();

  // the teacher books our room: the sheet says it needs approval, the answer is 202 PENDING and the slot is held
  const teacher = await browser.newPage();
  await login(teacher, TEACHER.username, TEACHER.password);
  const [slot] = await ownFree(FRIDAY);
  await teacher.goto(`/bookings?date=${FRIDAY}&group=${ctx.groupA}&lens=grid`);
  await expect(teacher.getByTestId("booking-grid")).toBeVisible({ timeout: 30_000 });
  await cell(teacher, slot!).click();
  const sheet = teacher.getByTestId("book-sheet");
  await expect(sheet.getByTestId("book-approval")).toBeVisible();
  await expect(sheet.getByTestId("book-submit")).toHaveText(/Talep et|Send request/);
  const answer = teacher.waitForResponse((r) => r.url().endsWith("/api/v1/bookings") && r.request().method() === "POST");
  await sheet.getByTestId("book-submit").click();
  expect((await answer).status()).toBe(202);
  await expect(sheet).toBeHidden();
  await expect(cell(teacher, slot!)).toHaveAttribute("data-tone", "booked-pending");

  // the approver: a count on the sidebar entry, the inbox, approve
  const approver = await browser.newPage();
  await login(approver, APPROVER.username, APPROVER.password);
  await approver.goto("/approvals");
  await expect(approver.getByTestId("nav-approvals")).toHaveAccessibleName(/açık talep|open request/);
  const mine = await api<{ id: number; status: string; booking_id: number }[]>("GET", "/approvals/mine", undefined, ctx.teacherToken);
  const req1 = mine.find((r) => r.status === "PENDING")!;
  await approver.getByTestId(`approval-${req1.id}`).click();
  const drawer = approver.getByTestId("approval-drawer");
  await expect(drawer.getByTestId("request-timeline")).toBeVisible();
  await expect(drawer.getByTestId("approval-room-day")).toBeVisible();
  await drawer.getByTestId("approval-approve").click();
  await expect.poll(async () => (await api<{ status: string }>("GET", `/approvals/${req1.id}`, undefined, ctx.approverToken)).status).toBe("APPROVED");

  // a second request is rejected with a suggested room ("Another room" → Reject, suggest)
  const [slot2] = await ownFree(FRIDAY);
  const r2 = await call<{ id: number; status: string }>("POST", "/bookings", { room_id: ctx.room.id, date: FRIDAY, period_id: slot2!.period_id, term_id: ctx.termId }, ctx.teacherToken);
  expect(r2.status).toBe(202);
  const req2 = (await api<{ id: number; booking_id: number }[]>("GET", "/approvals/mine", undefined, ctx.teacherToken)).find((r) => r.booking_id === r2.body.id)!;
  await approver.goto(`/approvals?request=${req2.id}`);
  await drawer.getByTestId("approval-note").fill("Bu saatte bakım var");
  await drawer.getByTestId("approval-other-room").click();
  const others = drawer.getByTestId("approval-other-rooms");
  await expect(others.locator("li").first()).toBeVisible({ timeout: 20_000 });
  await others.locator("li").first().getByRole("button", { name: /Reddet, öner|Reject, suggest/ }).click();
  // approval-first: a rejection needs a reason code and a written reason (the drawer's note is carried over)
  const reject = approver.getByTestId("reject-dialog");
  await expect(reject.getByTestId("reject-text")).toHaveValue("Bu saatte bakım var");
  await reject.getByTestId("reject-code-room_unavailable").click();
  await reject.getByTestId("reject-confirm").click();
  await expect.poll(async () => (await api<{ status: string }>("GET", `/approvals/${req2.id}`, undefined, ctx.approverToken)).status).toBe("REJECTED");

  // part of a series: a weekly request (the administrator: teachers have no recurring right in CRBS) for four Fridays, approve three
  const [slot3] = await ownFree(FRIDAY);
  const series = await call<{ series_id: number; status: string; created: { date: string }[] }>(
    "POST",
    "/bookings/recurring",
    { room_id: ctx.room.id, period_id: slot3!.period_id, date: FRIDAY, term_id: ctx.termId, start: FRIDAY, end: "2026-03-13" },
  );
  expect(series.status).toBe(202);
  expect(series.body.status).toBe("PENDING");
  const req3 = (await api<{ id: number; series_id: number | null }[]>("GET", "/approvals/mine")).find((r) => r.series_id === series.body.series_id)!;
  await approver.goto(`/approvals?request=${req3.id}`);
  const instances = drawer.getByTestId("approval-instances");
  await expect(instances.getByRole("checkbox")).toHaveCount(series.body.created.length);
  await instances.getByRole("checkbox").last().click();
  await expect(drawer.getByTestId("approval-approve")).toHaveText(new RegExp(String(series.body.created.length - 1)));
  await drawer.getByTestId("approval-approve").click();
  await expect.poll(async () => (await api<{ status: string }>("GET", `/approvals/${req3.id}`, undefined, ctx.approverToken)).status).toBe("APPROVED");
  const after = await api<{ bookings: { status: string }[] }>("GET", `/approvals/${req3.id}`, undefined, ctx.approverToken);
  expect(after.bookings.filter((x) => x.status === "BOOKED")).toHaveLength(series.body.created.length - 1);

  // a 409 re-check: two teachers ask for the same slot; one is approved behind the drawer's back
  // the hold blocks the slot for others: drop the hold first so a second teacher can ask for the same slot
  await api("PUT", `/approval-rules/${ctx.ruleId}`, { entity_type: "room", entity_id: ctx.room.id, steps: [{ approvers: { type: "designated" }, min_approvals: 1 }], hold_minutes: 0, lead_time_workdays: 0, expires_before_start_minutes: 0, allow_self_approve: false, active: true, name: null, tag: null, term_id: null });
  const [slot4] = await ownFree(THURSDAY);
  const a = await call<{ id: number }>("POST", "/bookings", { room_id: ctx.room.id, date: THURSDAY, period_id: slot4!.period_id, term_id: ctx.termId }, ctx.teacherToken);
  expect(a.status).toBe(202);
  const reqA = (await api<{ id: number; booking_id: number }[]>("GET", "/approvals/mine", undefined, ctx.teacherToken)).find((r) => r.booking_id === a.body.id)!;
  const b = await call<{ id: number }>("POST", "/bookings", { room_id: ctx.room.id, date: THURSDAY, period_id: slot4!.period_id, term_id: ctx.termId }, ctx.teacher2Token);
  expect(b.status).toBe(202);
  const reqB = (await api<{ id: number; booking_id: number }[]>("GET", "/approvals/mine", undefined, ctx.teacher2Token)).find((r) => r.booking_id === b.body.id)!;
  await approver.goto(`/approvals?request=${reqB.id}`);
  await expect(drawer.getByTestId(`competing-${reqA.id}`)).toBeVisible();
  await api("POST", `/approvals/${reqA.id}/decide`, { decision: "approve" }, ctx.approverToken);
  await drawer.getByTestId("approval-approve").click();
  await expect(drawer.getByTestId("approval-error")).toBeVisible();

  // the requester: timeline with the decisions and the suggestion, the bell links to the request
  await teacher.goto(`/my-bookings?request=${req2.id}`);
  const list = teacher.getByTestId("my-requests");
  await expect(list.locator(`[data-request-id="${req1.id}"]`)).toHaveAttribute("data-status", "APPROVED");
  const rejected = list.locator(`[data-request-id="${req2.id}"]`);
  await expect(rejected).toHaveAttribute("data-status", "REJECTED");
  await expect(rejected.getByTestId("request-timeline")).toContainText("Bu saatte bakım var");
  await expect(rejected.getByTestId("request-suggestions")).toBeVisible();
  // the desktop top bar's bell (the phone top bar has its own, hidden here)
  await expect(teacher.locator('[data-testid="notification-count"]:visible')).toBeVisible();
  await teacher.locator('[data-testid="notification-bell"]:visible').click();
  const panel = teacher.getByTestId("notification-panel");
  await expect(panel.locator('[data-unread="true"]').first()).toBeVisible();
  await panel.locator('[data-unread="true"]').first().click();
  await teacher.waitForURL(/\/my-bookings\?request=\d+/);
  await teacher.close();
  await approver.close();
});

/* ------------------------------------------------------------------------------- crawler */

/** Sidebar links, ⌘K destinations ("Go to" entries and the actions that navigate) and the setup index's links. */
async function destinations(page: Page): Promise<string[]> {
  await page.goto("/bookings");
  await expect(page.getByTestId("booking-grid").or(page.getByTestId("free-slots"))).toBeVisible({ timeout: 30_000 });
  const sidebar = await page.locator('aside a[href^="/"]').evaluateAll((els) => els.map((e) => e.getAttribute("href") ?? ""));
  await openPalette(page);
  const values = await page.locator("[cmdk-item]").evaluateAll((els) => els.map((e) => e.getAttribute("data-value") ?? ""));
  await page.keyboard.press("Escape");
  const gotos = values.filter((v) => v.startsWith("goto-")).map((v) => v.slice(5));
  const actions: string[] = [];
  for (const v of values.filter((x) => x.startsWith("action-"))) {
    await openPalette(page);
    const before = page.url();
    await page.locator(`[cmdk-item][data-value="${v}"]`).click();
    await page.waitForURL((u) => u.href !== before, { timeout: 10_000 }).catch(() => undefined);
    if (page.url() !== before) actions.push(new URL(page.url()).pathname + new URL(page.url()).search);
    await page.goto("/bookings");
  }
  // the setup index (/admin, when the sidebar offers it) links every setup screen the user may open
  const setup: string[] = [];
  if (sidebar.includes("/admin") || gotos.includes("/admin")) {
    await page.goto("/admin");
    await expect(page.locator("main a[href^='/admin/']").first()).toBeVisible({ timeout: 30_000 });
    setup.push(...(await page.locator("main a[href^='/admin/']").evaluateAll((els) => els.map((e) => e.getAttribute("href") ?? ""))));
  }
  return [...new Set([...sidebar, ...gotos, ...actions, ...setup].filter(Boolean))];
}

/** Opens each path: the document is not a 404, no API call answers 403, and the page does not say "no access". */
async function crawl(page: Page, paths: string[]): Promise<string[]> {
  const problems: string[] = [];
  let current = "";
  const denied = (r: import("@playwright/test").Response) => {
    if (r.url().includes("/api/v1/") && r.status() === 403) problems.push(`${current}: ${r.request().method()} ${new URL(r.url()).pathname} → 403`);
  };
  page.on("response", denied);
  for (const p of paths) {
    current = p;
    const res = await page.goto(p);
    if (!res || res.status() === 404) problems.push(`${p}: 404`);
    await page.waitForLoadState("networkidle").catch(() => undefined);
    // Next's default not-found screen (a room may well be called "404", so not the number alone)
    if (await page.getByText(/^This page could not be found\.?$/).count()) problems.push(`${p}: not found page`);
    if (await page.getByText(/Bu sayfaya erişiminiz yok|You do not have access|yetkiniz yok/).count()) problems.push(`${p}: no-access screen`);
  }
  page.off("response", denied);
  return problems;
}

test("wave1 5. every sidebar, ⌘K and setup link opens a page with no 404 and no 403, as administrator and as teacher", async ({ page }) => {
  test.setTimeout(300_000);
  await login(page, ADMIN.username, ADMIN.password);
  // the crawler itself notices a missing page
  expect((await crawl(page, ["/no-such-page-wave1"]))[0]).toContain("404");
  const admin = await destinations(page);
  for (const p of ["/find-room", "/approvals", "/admin/audit", "/admin/approval-rules"]) expect(admin).toContain(p);
  expect(await crawl(page, admin)).toEqual([]);

  await page.context().clearCookies();
  await login(page, TEACHER.username, TEACHER.password);
  const teacher = await destinations(page);
  expect(teacher).toContain("/find-room");
  for (const p of ["/approvals", "/admin/audit", "/admin/approval-rules", "/runs", "/requests"]) expect(teacher).not.toContain(p);
  expect(await crawl(page, teacher)).toEqual([]);
});
