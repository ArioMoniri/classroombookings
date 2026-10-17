/**
 * Flow loop round 2, lane B (docs/ROADMAP.md "Flow loop tickets — round 2", rounds/round-2-tickets.json) against the
 * REAL backend, gated E2E_REAL=1. The ticket checks a builder can run in a browser:
 *
 * - T-R2-09 "Yeniden denetle" keeps the per-date book / skip / replace choices; the POST /bookings/recurring body carries them.
 * - T-R2-12 /approvals: j / k move between rows, Enter opens the drawer with the focus on its title, "a" approves.
 * - T-R2-13 a two-period submission is one row in Yaklaşan ("P1–P2 (08:30–10:00)").
 * - T-R2-14 a stale find-room card (a period taken meanwhile) is refused with the stale toast; no sheet, no booking.
 * - T-R2-16 the cancel toast reads "N rezervasyon iptal edildi · Gerekçe: …" from the My bookings row sheet.
 * - T-R2-17 the multi create answers 202 for a request; a past date is a 409 `past` with message_tr.
 *
 * Everything it makes is its own (a teacher and rooms); afterAll puts the approval mode back.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19320 NEXT_PUBLIC_API_URL=http://127.0.0.1:19320 PW_PORT=19321 \
 *     npx playwright test e2e/loop-r2-laneB.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";
import { pinLanguage } from "./language";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const TEACHER = { username: `lb2.hoca.${STAMP}`, email: `lb2.hoca.${STAMP}@uni.edu.tr`, first: "Leyla", last: "Bal", password: "Ogretmen-2026!" };
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };

test.describe.configure({ mode: "serial", timeout: 300_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

interface Period { id: number; name: string; start_period: number; time_start: string; time_end: string }
interface Grid { term: { id: number }; periods: Period[]; slots: { date: string; period_id: number; room_id: number; status: string; allow_single?: boolean; allow_recur?: boolean }[] }
const ctx = {} as { api: APIRequestContext; admin: string; teacher: string; teacherId: number; mode: string; groupId: number; termId: number; days: string[] };

async function call<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token = ctx.admin): Promise<{ status: number; body: T }> {
  const res = await ctx.api.fetch(`${API}${path}`, { method, data: body, headers: { Authorization: `Bearer ${token}` } });
  const text = await res.text();
  return { status: res.status(), body: (text ? JSON.parse(text) : undefined) as T };
}
async function api<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token = ctx.admin): Promise<T> {
  const r = await call<T>(method, path, body, token);
  if (r.status >= 400) throw new Error(`${method} ${path} → ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}
async function token(identifier: string, password: string): Promise<string> {
  const body = identifier.includes("@") ? { email: identifier, password } : { username: identifier, password };
  const res = await ctx.api.post(`${API}/auth/login`, { data: body });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { access_token: string }).access_token;
}
async function newRoom(tag: string): Promise<{ id: number; name: string }> {
  const no = 100 + ((Date.now() + tag.length * 7) % 900);
  const room = await api<{ id: number; display_name: string }>("POST", "/rooms", { code: `LB2 ${tag}${no}`, display_name: `LB2 ${tag}${no}`, capacity: 60 });
  await api("PUT", `/room-admin/rooms/${room.id}`, { room_group_id: ctx.groupId, is_bookable: true });
  return { id: room.id, name: room.display_name };
}
async function dayGrid(day: string, tok = ctx.teacher): Promise<{ grid: Grid; periods: Period[] }> {
  const grid = await api<Grid>("GET", `/bookings/grid?display=day&date=${day}&room_group_id=${ctx.groupId}`, undefined, tok);
  return { grid, periods: [...grid.periods].sort((a, b) => a.start_period - b.start_period) };
}
const addDays = (iso: string, n: number) => { const d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
async function phonePage(browser: Browser, id: string, password: string): Promise<Page> {
  const p = await (await browser.newContext(PHONE)).newPage();
  await login(p, id, password);
  return p;
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.admin = await token(ADMIN_EMAIL, ADMIN_PASSWORD);
  ctx.mode = (await api<{ approval_mode?: string }>("GET", "/org/settings")).approval_mode ?? "rules";
  let groups = await api<{ id: number }[]>("GET", "/room-admin/groups");
  if (!groups.length) groups = await api("POST", "/room-admin/groups/from-buildings");
  ctx.groupId = groups[0]!.id;
  const made = await api<{ id: number }>("POST", "/users", { username: TEACHER.username, email: TEACHER.email, firstname: TEACHER.first, lastname: TEACHER.last, role: "TEACHER", password: TEACHER.password });
  ctx.teacherId = made.id;
  ctx.teacher = await token(TEACHER.username, TEACHER.password);
  await api("PUT", "/auth/profile", { language: "tr" }, ctx.teacher);
  const dates = await api<{ today: string; dates: { date: string; weekday: number; open: boolean; holiday?: string | null }[] }>("GET", "/bookings/dates", undefined, ctx.teacher);
  const ahead = dates.dates.filter((d) => d.open && d.weekday <= 5 && d.date > dates.today && !d.holiday).map((d) => d.date);
  // weekdays with three more weekly instances open (the recurring preview needs them)
  ctx.days = ahead.filter((d) => [1, 2, 3].every((k) => ahead.includes(addDays(d, 7 * k))));
  expect(ctx.days.length).toBeGreaterThan(6);
});

test.afterAll(async () => {
  if (!ctx.api) return;
  await call("PUT", "/org/settings", { approval_mode: ctx.mode });
  await ctx.api.dispose();
});

test("T-R2-09 Yeniden denetle keeps Atla on D3 and Yerine geç on D4; the series body carries them and the on-behalf booking is replaced", async ({ page }) => {
  const room = await newRoom("R");
  const D1 = ctx.days[0]!, D3 = addDays(D1, 14), D4 = addDays(D1, 21);
  const { grid, periods } = await dayGrid(D1, ctx.admin);
  const slot = grid.slots.filter((s) => s.room_id === room.id && s.status === "available" && s.allow_recur).sort((a, b) => (periods.findIndex((p) => p.id === a.period_id)) - (periods.findIndex((p) => p.id === b.period_id)))[0]!;
  const onBehalf = await api<{ id: number }>("POST", "/bookings", { room_id: room.id, date: D4, period_id: slot.period_id, term_id: grid.term.id, user_id: ctx.teacherId });
  await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto(`/bookings?date=${D1}&group=${ctx.groupId}`);
  await page.locator(`button[data-slot-key="${D1}|${slot.period_id}|${room.id}"]`).click();
  const sheet = page.getByTestId("book-sheet");
  await sheet.getByText("Her hafta", { exact: true }).first().click();
  await sheet.getByTestId("recur-preview-btn").click();
  const list = sheet.getByTestId("recur-preview");
  await expect(list).toBeVisible();
  await list.locator(`li[data-date="${D3}"]`).getByText("Atla", { exact: true }).click();
  await list.locator(`li[data-date="${D4}"]`).getByText("Yerine geç", { exact: true }).click();
  const summary = await sheet.getByTestId("recur-summary").innerText();
  await sheet.getByTestId("recur-preview-btn").click(); // Yeniden denetle
  await expect(sheet.getByTestId("recur-summary")).toHaveText(summary);
  await expect(list.locator(`li[data-date="${D3}"] [aria-checked="true"]`)).toHaveText("Atla");
  await expect(list.locator(`li[data-date="${D4}"] [aria-checked="true"]`)).toHaveText("Yerine geç");
  await expect(list.getByTestId("recur-reset-note")).toHaveCount(0);
  const [req] = await Promise.all([
    page.waitForRequest((r) => r.method() === "POST" && /\/bookings\/recurring$/.test(r.url())),
    sheet.getByTestId("book-submit").click(),
  ]);
  const body = req.postDataJSON() as { instances: { date: string; action: string }[] };
  expect(body.instances.find((i) => i.date === D3)).toEqual({ date: D3, action: "do_not_book" });
  expect(body.instances.find((i) => i.date === D4)).toEqual({ date: D4, action: "replace" });
  await expect(page.locator("[data-sonner-toast]").first()).toContainText(/tarih rezerve edildi/);
  await expect.poll(async () => (await api<{ status: string }>("GET", `/bookings/${onBehalf.id}`)).status).toBe("CANCELLED");
});

test("T-R2-13 + T-R2-17 a two-period submission is one Yaklaşan row; the multi create answers 202 under approval-first; a past date is a coded 409", async ({ page }) => {
  const room = await newRoom("S");
  const D = ctx.days[1]!;
  const { grid, periods } = await dayGrid(D);
  const sel = await api<{ id: number; slots: { mbs_id: number }[] }>("POST", "/bookings/multi", { slots: [0, 1].map((i) => ({ date: D, period_id: periods[i]!.id, room_id: room.id })), term_id: grid.term.id }, ctx.teacher);
  const made = await api<{ created: { id: number }[] }>("POST", `/bookings/multi/${sel.id}/create`, { type: "single", slots: sel.slots.map((s) => ({ mbs_id: s.mbs_id })), dry_run: false }, ctx.teacher);
  const ids = made.created.map((b) => b.id).sort((a, b) => a - b);
  await login(page, TEACHER.username, TEACHER.password);
  await page.goto("/my-bookings");
  const row = page.locator(`[data-booking-ids="${ids.join(",")}"]`);
  await expect(row).toHaveCount(1);
  await expect(row).toHaveAttribute("data-periods", "2");
  await expect(row).toContainText(`${periods[0]!.name}–${periods[1]!.name}`);
  await expect(row).toContainText(`${periods[0]!.time_start.slice(0, 5)}–${periods[1]!.time_end.slice(0, 5)}`);
  const dash = await api<{ totals: { active: number; session: number; all: number } }>("GET", "/bookings/dashboard", undefined, ctx.teacher);
  await expect(page.getByTestId("mine-totals")).toContainText(`${dash.totals.active} etkin · bu dönem ${dash.totals.session} · toplam ${dash.totals.all}`);
  // T-R2-17 (c) + (d)
  await api("PUT", "/org/settings", { approval_mode: "all" });
  const sel2 = await api<{ id: number; slots: { mbs_id: number }[] }>("POST", "/bookings/multi", { slots: [2, 3].map((i) => ({ date: D, period_id: periods[i]!.id, room_id: room.id })), term_id: grid.term.id }, ctx.teacher);
  const r = await call<{ created: { status: string }[] }>("POST", `/bookings/multi/${sel2.id}/create`, { type: "single", slots: sel2.slots.map((s) => ({ mbs_id: s.mbs_id })), dry_run: false }, ctx.teacher);
  expect(r.status).toBe(202);
  expect(r.body.created.every((b) => b.status === "PENDING")).toBe(true);
  await api("PUT", "/org/settings", { approval_mode: ctx.mode });
  const dates = await api<{ today: string }>("GET", "/bookings/dates", undefined, ctx.teacher);
  const past = await call<{ detail: { code: string; message_tr?: string } }>("POST", "/bookings", { room_id: room.id, date: addDays(dates.today, -1), period_id: periods[0]!.id, term_id: grid.term.id }, ctx.teacher);
  expect(past.status).toBe(409);
  expect(past.body.detail.code).toBe("past");
  expect(past.body.detail.message_tr).toMatch(/geçmiş/);
});

test("T-R2-12 /approvals: j/k move between rows, Enter focuses the drawer title, a approves", async ({ page }) => {
  await api("PUT", "/org/settings", { approval_mode: "all" });
  const room = await newRoom("A");
  const D = ctx.days[2]!;
  const { grid, periods } = await dayGrid(D);
  const r1 = await api<{ id: number }>("POST", "/bookings", { room_id: room.id, date: D, period_id: periods[0]!.id, term_id: grid.term.id }, ctx.teacher);
  const r2 = await api<{ id: number }>("POST", "/bookings", { room_id: room.id, date: D, period_id: periods[2]!.id, term_id: grid.term.id }, ctx.teacher);
  const inbox = await api<{ id: number; bookings: { id: number }[] }[]>("GET", "/approvals/inbox?status=open");
  const reqOf = (bid: number) => inbox.find((r) => r.bookings.some((b) => b.id === bid))!.id;
  await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/approvals");
  const first = page.getByTestId(`approval-${reqOf(r1.id)}`);
  await first.focus();
  await page.keyboard.press("j");
  await expect(page.locator("[data-approval-row]:focus")).not.toHaveAttribute("data-testid", `approval-${reqOf(r1.id)}`);
  await page.keyboard.press("k");
  await expect(first).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("approval-drawer").getByTestId("approval-approve")).toBeVisible();
  await expect(page.locator("[data-approval-title]")).toBeFocused();
  await page.keyboard.press("a");
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: /onaylandı/i }).first()).toBeVisible({ timeout: 2_000 });
  await expect.poll(async () => (await api<{ status: string }>("GET", `/bookings/${r1.id}`, undefined, ctx.teacher)).status).toBe("BOOKED");
  await call("POST", `/approvals/${reqOf(r2.id)}/withdraw`, undefined, ctx.teacher);
  await api("PUT", "/org/settings", { approval_mode: ctx.mode });
});

test("T-R2-14 a stale find-room card is refused with the stale toast; T-R2-16 the cancel toast names the count and the reason", async ({ page, browser }) => {
  const room = await newRoom("F");
  const D = ctx.days[3]!;
  const { grid, periods } = await dayGrid(D);
  await login(page, TEACHER.username, TEACHER.password);
  await page.goto(`/find-room?date=${D}`);
  await page.waitForTimeout(1500); // the form re-initialises once the dates query answers
  await page.getByTestId("fr-start").fill(periods[0]!.time_start.slice(0, 5));
  await page.getByTestId("fr-end").fill(periods[1]!.time_end.slice(0, 5));
  await page.getByTestId("fr-search").click();
  await expect(page.getByTestId("fr-summary")).toBeVisible();
  const card = page.locator('[data-testid="fr-results"] li', { hasText: room.name }).locator('[data-testid^="fr-reserve-"]');
  await expect(card).toBeVisible();
  await api("POST", "/bookings", { room_id: room.id, date: D, period_id: periods[0]!.id, term_id: grid.term.id }); // taken meanwhile
  const before = (await api<unknown[]>("GET", "/bookings/mine", undefined, ctx.teacher)).length;
  await card.click();
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: "Bu derslik az önce doldu. Liste yenilendi." })).toBeVisible();
  await expect(page.getByTestId("book-sheet")).toBeHidden();
  expect((await api<unknown[]>("GET", "/bookings/mine", undefined, ctx.teacher)).length).toBe(before);
  await expect(page.locator('[data-testid="fr-results"] li', { hasText: room.name })).toHaveCount(0);
  // T-R2-16: the one-date cancel from the My bookings row sheet
  const b = await api<{ id: number }>("POST", "/bookings", { room_id: room.id, date: D, period_id: periods[3]!.id, term_id: grid.term.id }, ctx.teacher);
  const p = await phonePage(browser, TEACHER.username, TEACHER.password);
  await p.goto("/my-bookings");
  const row = p.locator(`[data-booking-id="${b.id}"]`);
  await row.locator("button").nth(1).click();
  await p.getByRole("dialog").last().getByRole("button", { name: "Rezervasyonu iptal et" }).click();
  await p.locator("#cancel-reason").fill("Oda bakımda");
  await p.getByRole("alertdialog").getByRole("button", { name: "İptal et" }).click();
  await expect(p.locator("[data-sonner-toast]").last()).toHaveText("1 rezervasyon iptal edildi · Gerekçe: Oda bakımda");
  await p.context().close();
});
