/**
 * Approval-first bookings against the REAL backend (no mocks), gated E2E_REAL=1 (owner requirement 2026-10-15:
 * "a request for an empty slot shows first to the admin, who approves or not and puts reasons why they didn't,
 * and these get notified to users"). The runnable form of docs/testing/flows F-01 S01, S07–S10 and F-11 S07, S09:
 *
 * 1. Yönetim › Ayarlar: the approval mode "Her talep önce onaya" is saved (GET /org/settings → all); the roles
 *    screen labels bookings.skip_approval in Turkish.
 * 2. A teacher's two-period submission; the approver opens it from the bell's link (`?request=&group=`), the
 *    reject dialog refuses an empty reason, then rejects both periods with a code and a text; the teacher reads
 *    "Reddedildi" and "Gerekçe: Oda uygun değil: …" in Taleplerim.
 * 3. Withdraw with a confirmation; the approver finds it under "Karara bağlanan" as "Geri çekildi" (M-34).
 * 4. Settings › Entegrasyonlar: calendar sync needs the KVKK acknowledgement and shows the sign-off, its legal
 *    basis in Turkish (M-40).
 * 5. Phone 390 × 844 (touch): the reject dialog is a full-width bottom sheet, reason rows ≥ 44 px, no sideways
 *    scroll; Taleplerim's withdraw button ≥ 44 px.
 * 6. A two-period submission approved at once ("2 saatin hepsini onayla"); the teacher reads "Onaylandı" (F-01 S07).
 * 7. Profile › Bildirimler: switching off e-mail for "Talebim onaylandı" is saved (F-01 S11); on a phone the events
 *    are grouped (only Onaylar open), rows ≥ 44 px, the panel stays short and nothing scrolls sideways.
 * 8. Settings › Entegrasyonlar › Giden webhook'lar: the delivery switch heads the card; a loopback URL is refused
 *    next to the field (M-41); a new webhook shows its secret once, then is deleted after a confirmation.
 *
 * Everything this spec changes is its own (users, a room in the A group, a webhook); afterAll restores the approval
 * mode, calendar sync and webhook delivery, removes the approver designation and deletes the webhooks it made.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:18994 NEXT_PUBLIC_API_URL=http://127.0.0.1:18994 PW_PORT=18995 \
 *     npx playwright test e2e/approval-first.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, TERM_CODE, pickSegment } from "./helpers";
import { pinLanguage } from "./language";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const ADMIN = { username: `af.yonetici.${STAMP}`, email: `af.yonetici.${STAMP}@uni.edu.tr`, password: "Yonetici-2026!" };
const TEACHER = { username: `af.hoca.${STAMP}`, email: `af.hoca.${STAMP}@uni.edu.tr`, first: "Pınar", last: "Tekin", password: "Ogretmen-2026!" };
const THURSDAY = "2026-02-19";
const FRIDAY = "2026-02-20";
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };

test.describe.configure({ mode: "serial", timeout: 300_000 });
test.skip(!REAL, SKIP_REASON);
// the assertions read Turkish (the product default): pin it, whatever the previous spec left behind
pinLanguage("tr");

interface GridSlot {
  date: string;
  period_id: number;
  room_id: number;
  status: string;
  allow_single?: boolean;
}
interface Grid {
  periods: { id: number; name: string }[];
  slots: GridSlot[];
}
interface Req {
  id: number;
  status: string;
  group_id: number | null;
  booking_id: number | null;
  reason_code: string | null;
  note: string | null;
  bookings: { id: number; date: string; period_id: number }[];
}
const ctx = { webhooks: [] as number[] } as { api: APIRequestContext; token: string; teacherToken: string; termId: number; groupA: number; room: { id: number; name: string }; adminId: number; mode: string; calendar: boolean; sending: boolean; webhooks: number[] };

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
/** free periods of our own room on a date, in period order */
async function free(date: string, n: number, skip = 0): Promise<GridSlot[]> {
  const g = await api<Grid>("GET", `/bookings/grid?display=day&date=${date}&room_group_id=${ctx.groupA}`, undefined, ctx.teacherToken);
  const order = new Map(g.periods.map((p, i) => [p.id, i]));
  const day = g.slots.filter((s) => s.room_id === ctx.room.id && s.date === date && s.status === "available" && s.allow_single).sort((a, b) => (order.get(a.period_id) ?? 0) - (order.get(b.period_id) ?? 0));
  for (let i = skip; i + n <= day.length; i++) {
    const part = day.slice(i, i + n);
    if (part.every((s, k) => k === 0 || (order.get(s.period_id) ?? 0) === (order.get(part[k - 1]!.period_id) ?? 0) + 1)) return part;
  }
  throw new Error(`no ${n} adjacent free periods in our room on ${date}`);
}
/** one request by the teacher (POST /bookings → 202) */
async function requestOne(date: string, skip = 0): Promise<Req> {
  const [slot] = await free(date, 1, skip);
  const r = await call<{ id: number; status: string }>("POST", "/bookings", { room_id: ctx.room.id, date, period_id: slot!.period_id, term_id: ctx.termId, notes: "Telafi dersi" }, ctx.teacherToken);
  expect(r.status, JSON.stringify(r.body)).toBe(202);
  return (await api<Req[]>("GET", "/approvals/mine", undefined, ctx.teacherToken)).find((x) => x.booking_id === r.body.id)!;
}
/** helpers.login with a longer wait: a `next dev` server compiles the landing page on first use */
async function login(page: Page, identifier: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.getByTestId("login-identifier").fill(identifier);
  await page.getByTestId("login-password").fill(password);
  await page.getByTestId("login-submit").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 120_000 });
}
const noSidewaysScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
async function phonePage(browser: Browser, who: { id: string; password: string }): Promise<Page> {
  const c = await browser.newContext(PHONE);
  const p = await c.newPage();
  await login(p, who.id, who.password);
  return p;
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.token = await loginToken(ADMIN_EMAIL, ADMIN_PASSWORD);
  const made = await api<{ id: number }>("POST", "/users", { username: ADMIN.username, email: ADMIN.email, displayname: "Onay Yöneticisi", role: "ADMIN", password: ADMIN.password });
  ctx.adminId = made.id;
  ctx.token = await loginToken(ADMIN.username, ADMIN.password);
  const dates = await api<{ today: string }>("GET", "/bookings/dates");
  test.skip(dates.today < "2026-02-02" || dates.today > "2026-06-28", `the backend's booking clock (${dates.today}) must be inside Bahar 2026`);
  ctx.mode = (await api<{ approval_mode?: string }>("GET", "/org/settings")).approval_mode ?? "rules";
  const integrations = await api<{ calendar_sync_enabled: boolean; webhooks_enabled: boolean }>("GET", "/calendar/admin/settings");
  ctx.calendar = integrations.calendar_sync_enabled;
  ctx.sending = integrations.webhooks_enabled;

  // the booking setup CRBS's installer would make (same as e2e/wave1.spec.ts, idempotent)
  const terms = await api<{ id: number; code: string }[]>("GET", "/terms");
  ctx.termId = terms.find((x) => x.code === TERM_CODE)!.id;
  const runs = await api<{ id: number; kind: string; term_id: number; label: string; is_active: boolean }[]>("GET", "/runs");
  const board = runs.find((r) => r.term_id === ctx.termId && r.kind === "COURSE" && r.label.startsWith("Grid import"));
  if (board && !board.is_active) await api("POST", `/runs/${board.id}/activate`);
  let schedules = await api<{ id: number; periods: { id: number }[] }[]>("GET", "/booking-admin/schedules");
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
  const no = 100 + (Date.now() % 900);
  const room = await api<{ id: number; display_name: string }>("POST", "/rooms", { code: `AF ${no}`, display_name: `E2E Onay Dersliği ${STAMP}`, capacity: 60 });
  await api("PUT", `/room-admin/rooms/${room.id}`, { room_group_id: ctx.groupA, is_bookable: true });
  ctx.room = { id: room.id, name: room.display_name };

  // our administrator approves for every room; a teacher requests
  await api("PUT", `/approvals/approvers/${ctx.adminId}`, { scopes: [{ type: "all" }] });
  await api("POST", "/users", { username: TEACHER.username, email: TEACHER.email, firstname: TEACHER.first, lastname: TEACHER.last, role: "TEACHER", password: TEACHER.password });
  ctx.teacherToken = await loginToken(TEACHER.username, TEACHER.password);
});

test.afterAll(async () => {
  if (!ctx.api) return;
  await call("PUT", "/org/settings", { approval_mode: ctx.mode });
  if (ctx.calendar !== undefined) await call("PUT", "/calendar/admin/settings", { calendar_sync_enabled: ctx.calendar, webhooks_enabled: ctx.sending });
  if (ctx.adminId) await call("PUT", `/approvals/approvers/${ctx.adminId}`, { scopes: [] });
  for (const id of ctx.webhooks) await call("DELETE", `/webhooks/${id}`);
  await ctx.api.dispose();
});

test("approval-first 1. the approval mode is set in Yönetim › Ayarlar; bookings.skip_approval is labelled", async ({ page }) => {
  await call("PUT", "/org/settings", { approval_mode: "rules" });
  await login(page, ADMIN.username, ADMIN.password);
  await page.goto("/admin/settings");
  const block = page.getByTestId("approval-mode");
  await expect(block).toContainText("Rezervasyon onayı");
  await expect(block).toContainText("Her talep önce onaya:");
  await expect(page.getByTestId("approval-mode-direct")).toContainText("Onaysız doğrudan rezervasyon");
  await pickSegment(page, "Her talep önce onaya", block);
  await page.getByTestId("org-save").click();
  await expect(page.getByText("Kaydedildi").first()).toBeVisible();
  await expect.poll(async () => (await api<{ approval_mode: string }>("GET", "/org/settings")).approval_mode).toBe("all");
  // the teacher's free slot now needs approval
  expect((await api<{ action: string }>("GET", `/approvals/rooms/${ctx.room.id}/check`, undefined, ctx.teacherToken)).action).toBe("request");
  await page.goto("/admin/roles");
  await expect(page.getByText("Onaysız doğrudan rezervasyon").first()).toBeVisible();
});

test("approval-first 2. a two-period submission opens from the approver link and is rejected with a required reason; the requester reads it", async ({ page, browser }) => {
  // the teacher asks for two adjacent periods in one submission (A-12)
  const slots = await free(THURSDAY, 2);
  const sel = await api<{ id: number; slots: { mbs_id: number }[] }>("POST", "/bookings/multi", { slots: slots.map((s) => ({ date: s.date, period_id: s.period_id, room_id: s.room_id })), term_id: ctx.termId }, ctx.teacherToken);
  await api("POST", `/bookings/multi/${sel.id}/create`, { type: "single", slots: sel.slots.map((s) => ({ mbs_id: s.mbs_id, notes: "Telafi dersi" })), dry_run: false }, ctx.teacherToken);
  const mine = (await api<Req[]>("GET", "/approvals/mine", undefined, ctx.teacherToken)).filter((r) => r.status === "PENDING" && r.group_id);
  const group = mine[0]!.group_id!;
  const ids = mine.filter((r) => r.group_id === group).map((r) => r.id);
  expect(ids).toHaveLength(2);
  // one approver notice for the submission, linking the group
  const notes = await api<{ link: string | null; data: { group_id?: number; request_ids?: number[] } | null }[]>("GET", "/me/notifications?limit=50");
  const notice = notes.find((n) => n.data?.group_id === group)!;
  expect(notice.link).toContain(`group=${group}`);
  expect([...(notice.data!.request_ids ?? [])].sort()).toEqual([...ids].sort());

  await login(page, ADMIN.username, ADMIN.password);
  await page.goto(notice.link!);
  const drawer = page.getByTestId("approval-drawer");
  await expect(drawer.getByTestId("approval-group-bar")).toBeVisible({ timeout: 30_000 });
  await drawer.getByTestId("approval-group-reject").click();
  const dialog = page.getByTestId("reject-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("radio")).toHaveCount(4);
  // negative first: nothing chosen, nothing written
  await expect(dialog.getByTestId("reject-confirm")).toHaveAttribute("aria-disabled", "true");
  // aria-disabled: a forced press is refused in the UI, with the message next to each missing field
  await dialog.getByTestId("reject-confirm").click({ force: true });
  await expect(dialog.getByTestId("reject-code-error")).toHaveText("Bir gerekçe türü seçin.");
  await expect(dialog.getByTestId("reject-text-error")).toBeVisible();
  await dialog.getByText("Diğer", { exact: true }).click();
  await dialog.getByTestId("reject-text").fill("   ");
  await expect(dialog.getByTestId("reject-confirm")).toHaveAttribute("aria-disabled", "true");
  await dialog.getByTestId("reject-confirm").click({ force: true });
  await expect(dialog.getByTestId("reject-text-error")).toBeVisible();
  for (const id of ids) expect((await api<Req>("GET", `/approvals/${id}`)).status).toBe("PENDING");
  // the real decision
  await dialog.getByText("Oda uygun değil", { exact: true }).click();
  await dialog.getByTestId("reject-text").fill("Bu saatte bölüm sınavı var.");
  await dialog.getByTestId("reject-confirm").click();
  await expect(page.getByText("2 ders saati reddedildi. Talep edene bildirildi.")).toBeVisible();
  for (const id of ids) {
    await expect.poll(async () => (await api<Req>("GET", `/approvals/${id}`)).status).toBe("REJECTED");
    const r = await api<Req>("GET", `/approvals/${id}`);
    expect([r.reason_code, r.note]).toEqual(["room_unavailable", "Bu saatte bölüm sınavı var."]);
  }

  // the teacher: Taleplerim shows the decision and the reason on the card and in the timeline
  const teacher = await (await browser.newContext({ locale: "tr-TR" })).newPage();
  await login(teacher, TEACHER.username, TEACHER.password);
  await teacher.goto(`/my-bookings?request=${ids[0]}`);
  const row = teacher.locator(`[data-request-id="${ids[0]}"]`);
  await expect(row).toContainText("Reddedildi");
  await expect(row.getByTestId("request-reason")).toContainText("Gerekçe: Oda uygun değil: Bu saatte bölüm sınavı var.");
  await expect(row.getByTestId("request-timeline")).toContainText("Oda uygun değil: Bu saatte bölüm sınavı var.");
  await teacher.context().close();
});

test("approval-first 3. withdraw asks first; the approver sees it under Karara bağlanan (M-34)", async ({ page, browser }) => {
  const req = await requestOne(FRIDAY);
  await login(page, TEACHER.username, TEACHER.password);
  await page.goto("/my-bookings");
  await page.getByTestId(`my-request-${req.id}`).click();
  await page.getByTestId(`withdraw-${req.id}`).click();
  const confirm = page.getByTestId("withdraw-confirm");
  await expect(confirm).toContainText("talebi geri çekilsin mi?");
  await expect(confirm).toContainText("Onaycılara bildirilir ve saat serbest kalır.");
  await confirm.getByTestId("withdraw-confirm-button").click();
  await expect(page.getByText("Talep geri çekildi.")).toBeVisible();
  await expect(page.locator(`[data-request-id="${req.id}"]`)).toContainText("Geri çekildi");
  expect((await call("POST", `/approvals/${req.id}/withdraw`, undefined, ctx.teacherToken)).status).toBe(409);

  const approver = await (await browser.newContext({ locale: "tr-TR" })).newPage();
  await login(approver, ADMIN.username, ADMIN.password);
  await approver.goto("/approvals");
  await expect(approver.getByTestId("approvals-list").or(approver.getByTestId("approvals-empty"))).toBeVisible({ timeout: 120_000 });
  await expect(approver.getByTestId(`approval-${req.id}`)).toHaveCount(0);
  await pickSegment(approver, "Karara bağlanan");
  await expect(approver.getByTestId(`approval-${req.id}`)).toContainText("Geri çekildi");
  await approver.context().close();
});

test("approval-first 4. calendar sync needs the KVKK acknowledgement and shows the sign-off (M-40)", async ({ page }) => {
  await call("PUT", "/calendar/admin/settings", { calendar_sync_enabled: false });
  await login(page, ADMIN.username, ADMIN.password);
  await page.goto("/settings?tab=integrations");
  const card = page.getByTestId("calendar-sync-admin");
  await card.getByTestId("calendar-sync-switch").click();
  const notice = page.getByTestId("calendar-notice");
  await expect(notice.getByTestId("calendar-notice-text")).toContainText("yurt dışına aktarım");
  await expect(notice.getByTestId("calendar-confirm")).toBeDisabled();
  await notice.getByTestId("calendar-ack").check();
  await notice.getByTestId("calendar-confirm").click();
  await expect(card.getByTestId("calendar-signoff")).toContainText("KVKK onayını verdi");
  await expect(card.getByTestId("calendar-signoff")).toContainText("Hukuki dayanak: KVKK md. 9 (7499 sayılı Kanun ile değişik; yurt dışına aktarım)");
  const s = await api<{ calendar_sync_enabled: boolean; calendar_sync_signoff: { by_user_id: number; legal_basis: string } }>("GET", "/calendar/admin/settings");
  expect(s.calendar_sync_enabled).toBe(true);
  expect(s.calendar_sync_signoff.by_user_id).toBe(ctx.adminId);
  await card.getByTestId("calendar-sync-switch").click();
  await expect(card.getByTestId("calendar-signoff")).toContainText("kapattı");
});

test("approval-first 5. phone 390: the reject dialog is a bottom sheet with 44 px rows; Taleplerim has a 44 px withdraw", async ({ browser }) => {
  const req = await requestOne(FRIDAY, 1);
  const p = await phonePage(browser, { id: ADMIN.username, password: ADMIN.password });
  await p.goto(`/approvals?request=${req.id}`);
  const drawer = p.getByTestId("approval-drawer");
  await expect(drawer.getByTestId("approval-reject")).toBeVisible();
  expect(await noSidewaysScroll(p)).toBe(true);
  await drawer.getByTestId("approval-reject").tap();
  const sheet = p.getByTestId("reject-dialog");
  await expect(sheet).toBeVisible();
  await p.waitForTimeout(400);
  const box = (await sheet.boundingBox())!;
  expect(Math.abs(box.y + box.height - 844)).toBeLessThanOrEqual(2);
  expect(box.width).toBeGreaterThanOrEqual(388);
  for (const row of await sheet.getByTestId(/^reject-code-/).all()) expect((await row.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  const confirm = (await sheet.getByTestId("reject-confirm").boundingBox())!;
  expect(confirm.y).toBeGreaterThanOrEqual(844 * 0.6 - 1);
  await sheet.getByTestId("reject-code-capacity").tap();
  await sheet.getByTestId("reject-text").fill("45 kişilik ders, derslik 30 kişilik.");
  await sheet.getByTestId("reject-confirm").tap();
  await expect.poll(async () => (await api<Req>("GET", `/approvals/${req.id}`)).reason_code).toBe("capacity");
  await p.context().close();

  const another = await requestOne(FRIDAY, 1);
  const tp = await phonePage(browser, { id: TEACHER.username, password: TEACHER.password });
  await tp.goto(`/my-bookings?request=${another.id}`);
  const withdraw = tp.getByTestId(`withdraw-${another.id}`);
  await expect(withdraw).toBeVisible();
  expect((await withdraw.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  expect(await noSidewaysScroll(tp)).toBe(true);
  await withdraw.tap();
  const confirmSheet = tp.getByTestId("withdraw-confirm");
  await expect(confirmSheet).toBeVisible();
  await tp.waitForTimeout(400);
  const cb = (await confirmSheet.boundingBox())!;
  expect(Math.abs(cb.y + cb.height - 844)).toBeLessThanOrEqual(2);
  await confirmSheet.getByTestId("withdraw-confirm-button").tap();
  await expect(tp.locator(`[data-request-id="${another.id}"]`)).toContainText("Geri çekildi");
  await tp.context().close();
});

/** the teacher's two-period submission on a date (POST /bookings/multi → create), its request ids */
async function submitTwo(date: string, skip = 0): Promise<{ group: number; ids: number[] }> {
  const slots = await free(date, 2, skip);
  const sel = await api<{ id: number; slots: { mbs_id: number }[] }>("POST", "/bookings/multi", { slots: slots.map((s) => ({ date: s.date, period_id: s.period_id, room_id: s.room_id })), term_id: ctx.termId }, ctx.teacherToken);
  await api("POST", `/bookings/multi/${sel.id}/create`, { type: "single", slots: sel.slots.map((s) => ({ mbs_id: s.mbs_id, notes: "Seminer" })), dry_run: false }, ctx.teacherToken);
  const mine = (await api<Req[]>("GET", "/approvals/mine", undefined, ctx.teacherToken)).filter((r) => r.status === "PENDING" && r.group_id && r.bookings[0]?.date === date);
  const group = Math.max(...mine.map((r) => r.group_id!));
  return { group, ids: mine.filter((r) => r.group_id === group).map((r) => r.id) };
}

test("approval-first 6. a whole submission is approved at once; the teacher reads Onaylandı", async ({ page, browser }) => {
  const { group, ids } = await submitTwo("2026-02-23");
  expect(ids).toHaveLength(2);
  await login(page, ADMIN.username, ADMIN.password);
  await page.goto(`/approvals?request=${ids[1]}&group=${group}`);
  const drawer = page.getByTestId("approval-drawer");
  await expect(drawer.getByTestId("approval-group-bar")).toContainText("Tek talep: 2 ders saati.", { timeout: 30_000 });
  await drawer.getByTestId("approval-note").fill("Onaylandı, iyi dersler.");
  await drawer.getByTestId("approval-group-approve").click();
  await expect(page.getByText(`2 ders saati onaylandı: ${ctx.room.name}.`)).toBeVisible();
  for (const id of ids) await expect.poll(async () => (await api<Req>("GET", `/approvals/${id}`)).status).toBe("APPROVED");

  const teacher = await (await browser.newContext({ locale: "tr-TR" })).newPage();
  await login(teacher, TEACHER.username, TEACHER.password);
  await teacher.goto(`/my-bookings?request=${ids[0]}`);
  await expect(teacher.locator(`[data-request-id="${ids[0]}"]`)).toContainText("Onaylandı");
  await expect(teacher.locator(`[data-request-id="${ids[0]}"]`).getByTestId("request-timeline")).toContainText("Onay Yöneticisi onayladı");
  await teacher.context().close();
});

test("approval-first 7. Profile › Bildirimler saves an event × channel switch; phone 390 shows cards with 44 px rows", async ({ page, browser }) => {
  await api("PUT", "/me/notification-preferences", { events: { "approval.approved": { email: true } } }, ctx.teacherToken);
  await login(page, TEACHER.username, TEACHER.password);
  await page.goto("/profile#notifications");
  const panel = page.getByTestId("notification-prefs");
  await expect(panel.getByTestId("prefs-matrix-approvals")).toBeVisible({ timeout: 30_000 });
  for (const label of ["Onaylar", "Rezervasyonlar", "Onayımı bekleyen yeni oda talepleri", "Talebim onaylandı", "Talebim reddedildi (gerekçesiyle)", "Talebimin süresi doldu", "Uygulama içi", "E-posta"]) await expect(panel).toContainText(label);
  const cell = panel.getByTestId("pref-approval.approved-email");
  await expect(cell).toHaveAttribute("aria-checked", "true");
  await cell.click();
  await expect(page.getByText("Bildirim tercihi kaydedildi.").first()).toBeVisible();
  await expect.poll(async () => {
    const prefs = await api<{ events: { event: string; channels: Record<string, boolean> }[] }>("GET", "/me/notification-preferences", undefined, ctx.teacherToken);
    return prefs.events.find((e) => e.event === "approval.approved")?.channels.email;
  }).toBe(false);

  const p = await phonePage(browser, { id: TEACHER.username, password: TEACHER.password });
  await p.goto("/profile#notifications");
  // in-app + e-mail fit a matrix on a phone: the approvals group is open, the others are collapsed
  const prefs = p.getByTestId("notification-prefs");
  const matrix = prefs.getByTestId("prefs-matrix-approvals");
  await expect(matrix).toBeVisible({ timeout: 30_000 });
  await expect(matrix.getByTestId("pref-approval.approved-email")).toHaveAttribute("aria-checked", "false");
  for (const row of await matrix.locator("tbody tr").all()) expect((await row.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await expect(prefs.getByTestId("prefs-matrix-bookings")).toBeHidden();
  expect((await prefs.boundingBox())!.height).toBeLessThan(1600);
  expect(await noSidewaysScroll(p)).toBe(true);
  // the settings tabs are 44 px on touch
  await p.goto("/settings");
  await expect(p.getByTestId("tab-appearance")).toBeVisible({ timeout: 30_000 });
  expect((await p.getByTestId("tab-appearance").boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await p.context().close();
});

test("approval-first 8. webhooks: a loopback URL is refused next to the field; the secret shows once; delete asks first", async ({ page }) => {
  await login(page, ADMIN.username, ADMIN.password);
  await page.goto("/settings?tab=integrations");
  const card = page.getByTestId("webhooks-admin");
  // the delivery switch heads the card (off by default)
  await call("PUT", "/calendar/admin/settings", { webhooks_enabled: false });
  await page.reload();
  await expect(card.getByTestId("webhooks-switch")).not.toHaveAttribute("data-checked");
  await card.getByTestId("webhooks-switch").click();
  await expect(card.getByTestId("webhooks-switch")).toHaveAttribute("data-checked");
  await expect.poll(async () => (await api<{ webhooks_enabled: boolean }>("GET", "/calendar/admin/settings")).webhooks_enabled).toBe(true);
  await card.getByTestId("webhook-new").click();
  const dialog = page.getByTestId("webhook-dialog");
  await expect(dialog.getByTestId("webhook-save")).toBeDisabled();
  await dialog.getByTestId("webhook-url").fill("https://127.0.0.1/hook");
  await dialog.getByTestId("webhook-save").click();
  await expect(dialog.getByTestId("webhook-error")).toBeVisible();
  const url = `https://hooks-${STAMP}.e2e.invalid/smartsched`;
  await dialog.getByTestId("webhook-url").fill(url);
  await dialog.getByTestId("webhook-save").click();
  const secret = card.getByTestId("webhook-secret");
  await expect(secret).toContainText(url);
  await expect(secret.locator("code")).toHaveText(/^whsec_/);
  const made = (await api<{ id: number; url: string }[]>("GET", "/webhooks")).find((w) => w.url === url)!;
  ctx.webhooks.push(made.id);
  const row = card.getByTestId(`webhook-${made.id}`);
  await expect(row).toContainText("Tüm olaylar");
  await row.getByTestId(`webhook-delete-${made.id}`).click();
  await page.getByTestId("webhook-delete-confirm").getByTestId("webhook-delete-confirm-button").click();
  await expect(row).toHaveCount(0);
  expect((await api<{ id: number }[]>("GET", "/webhooks")).some((w) => w.id === made.id)).toBe(false);
});
