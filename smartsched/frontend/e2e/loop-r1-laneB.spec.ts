/**
 * Flow loop round 1, lane B (docs/ROADMAP.md "Flow loop tickets — round 1", rounds/round-1-tickets.json) against the
 * REAL backend, gated E2E_REAL=1. The ticket checks a builder can run in a browser:
 *
 * - T-R1-10 approval-first: grid cells, phone slots, find-room results / alternatives and the "Kurallar" popover say
 *   "Talep et · Onay gerekir" / "Onaylayıcılara gider", never "Rezerve et"; /booking-policies/effective → request.
 * - T-R1-12 focus: after a grid request, a find-room search and a decision focus is never on <body>; "Talep et"
 *   carries aria-busy while it sends.
 * - T-R1-13 a two-period request is one row in Taleplerim; the approvals drawer names the span with one "Kapat".
 * - T-R1-14 the own open request reads "Talebiniz bekliyor" in find-room, no server timing in the header.
 * - T-R1-18 "d" on a focused approvals row opens the reject dialog.
 * - T-R1-11 Taleplerim at 1440: the asked → assigned pair is never cut, no term-wide 5000-row fetch, every row a Tab
 *   stop. T-R1-19: /bookings on a phone logs no page error. Phone 390 × 844: no sideways scroll on the screens touched.
 *
 * Everything it makes is its own (a teacher, an academician linked to an unlinked instructor, a room); afterAll puts
 * the approval mode back, unlinks the instructor and withdraws what is still open.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19112 NEXT_PUBLIC_API_URL=http://127.0.0.1:19112 PW_PORT=19113 \
 *     npx playwright test e2e/loop-r1-laneB.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";
import { pinLanguage } from "./language";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const TEACHER = { username: `lb.hoca.${STAMP}`, email: `lb.hoca.${STAMP}@uni.edu.tr`, first: "Lale", last: "Bora", password: "Ogretmen-2026!" };
const ACAD = { username: `lb.akad.${STAMP}`, email: `lb.akad.${STAMP}@uni.edu.tr`, first: "Ali", last: "Tan", password: "Akademisyen-2026!" };
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };

test.describe.configure({ mode: "serial", timeout: 300_000 });
test.skip(!REAL, SKIP_REASON);
pinLanguage("tr");

interface Slot {
  date: string;
  period_id: number;
  room_id: number;
  status: string;
  allow_single?: boolean;
}
interface Grid {
  term: { id: number };
  periods: { id: number; name: string; start_period: number }[];
  slots: Slot[];
}
const ctx = {} as { api: APIRequestContext; admin: string; teacher: string; mode: string; groupId: number; room: { id: number; name: string }; day: string; termId: number; instructorId: number | null; acadId: number };

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
/** `n` consecutive free periods of our room on `day` (the grid's order) */
async function freeRun(n: number, day = ctx.day): Promise<Slot[]> {
  const g = await api<Grid>("GET", `/bookings/grid?display=day&date=${day}&room_group_id=${ctx.groupId}`, undefined, ctx.teacher);
  const order = new Map(g.periods.map((p) => [p.id, p.start_period]));
  const mine = g.slots.filter((s) => s.room_id === ctx.room.id).sort((a, b) => (order.get(a.period_id) ?? 0) - (order.get(b.period_id) ?? 0));
  for (let i = 0; i + n <= mine.length; i++) {
    const run = mine.slice(i, i + n);
    if (run.every((s) => s.status === "available" && s.allow_single) && run.every((s, k) => k === 0 || (order.get(s.period_id) ?? 0) === (order.get(run[k - 1]!.period_id) ?? 0) + 1)) return run;
  }
  throw new Error(`no ${n} free periods in ${ctx.room.name} on ${day}`);
}
const noSidewaysScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
const activeIsBody = (page: Page) => page.evaluate(() => !document.activeElement || document.activeElement === document.body);
async function phonePage(browser: Browser, id: string, password: string): Promise<Page> {
  const p = await (await browser.newContext(PHONE)).newPage();
  await login(p, id, password);
  return p;
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.admin = await token(ADMIN_EMAIL, ADMIN_PASSWORD);
  ctx.mode = (await api<{ approval_mode?: string }>("GET", "/org/settings")).approval_mode ?? "rules";
  await api("PUT", "/org/settings", { approval_mode: "all" });
  // our own room in a room group, so a free slot exists whatever the timetable holds
  let groups = await api<{ id: number }[]>("GET", "/room-admin/groups");
  if (!groups.length) groups = await api("POST", "/room-admin/groups/from-buildings");
  ctx.groupId = groups[0]!.id;
  const no = 100 + (Date.now() % 900);
  const room = await api<{ id: number; display_name: string }>("POST", "/rooms", { code: `LB ${no}`, display_name: `LB ${no}`, capacity: 60 });
  await api("PUT", `/room-admin/rooms/${room.id}`, { room_group_id: ctx.groupId, is_bookable: true });
  ctx.room = { id: room.id, name: room.display_name };
  await api("POST", "/users", { username: TEACHER.username, email: TEACHER.email, firstname: TEACHER.first, lastname: TEACHER.last, role: "TEACHER", password: TEACHER.password });
  ctx.teacher = await token(TEACHER.username, TEACHER.password);
  await api("PUT", "/auth/profile", { language: "tr" }, ctx.teacher);
  // a weekday at least two days ahead, open for bookings
  const dates = await api<{ today: string; dates: { date: string; weekday: number; open: boolean }[] }>("GET", "/bookings/dates", undefined, ctx.teacher);
  const ahead = dates.dates.filter((d) => d.open && d.weekday <= 5 && d.date > dates.today);
  ctx.day = (ahead[2] ?? ahead[0])!.date;
  // the academician: a new login linked to an instructor of the current term nobody is linked to yet
  const me = await api<{ current_term: { id: number } | null }>("GET", "/moderation/me");
  ctx.termId = me.current_term!.id;
  const people = await api<{ items: { id: number; requests: number; linked_user: boolean }[] }>("GET", `/terms/${ctx.termId}/moderation/people`);
  const free = people.items.filter((p) => !p.linked_user && p.requests >= 3).sort((a, b) => a.requests - b.requests);
  const made = await api<{ id: number }>("POST", "/users", { username: ACAD.username, email: ACAD.email, firstname: ACAD.first, lastname: ACAD.last, role: "TEACHER", password: ACAD.password });
  ctx.acadId = made.id;
  ctx.instructorId = free[0]?.id ?? null;
  if (ctx.instructorId) await api("PUT", `/auth/sso/admin/users/${made.id}/instructor`, { instructor_id: ctx.instructorId });
  await api("PUT", "/auth/profile", { language: "tr" }, await token(ACAD.username, ACAD.password));
});

test.afterAll(async () => {
  if (!ctx.api) return;
  for (const r of (await call<{ id: number; status: string }[]>("GET", "/approvals/mine", undefined, ctx.teacher)).body ?? []) if (r.status === "PENDING") await call("POST", `/approvals/${r.id}/withdraw`, undefined, ctx.teacher);
  if (ctx.acadId) await call("PUT", `/auth/sso/admin/users/${ctx.acadId}/instructor`, { instructor_id: null });
  await call("PUT", "/org/settings", { approval_mode: ctx.mode });
  await ctx.api.dispose();
});

test("T-R1-10 approval-first: the verdict, grid cells, phone slots and find-room say Talep et, never Rezerve et", async ({ page, browser }) => {
  const [slot] = await freeRun(1);
  const eff = await api<{ verdict: string; approval: { first: boolean; source: string }; violations: { message_tr: string }[] }>("GET", `/booking-policies/effective?room_id=${ctx.room.id}&date=${ctx.day}&period_id=${slot!.period_id}`, undefined, ctx.teacher);
  expect(eff.verdict).toBe("request");
  expect(eff.approval).toMatchObject({ first: true, source: "approval_mode" });
  expect(eff.violations.at(-1)!.message_tr).toContain("Her talep önce onaya");

  await login(page, TEACHER.username, TEACHER.password);
  await page.goto(`/bookings?date=${ctx.day}&group=${ctx.groupId}`);
  const cell = page.locator(`button[data-slot-key="${slot!.date}|${slot!.period_id}|${slot!.room_id}"]`);
  await expect(cell).toHaveAttribute("aria-label", /Talep et · Onay gerekir/);
  const labels = await page.locator('[data-testid="booking-grid-wrap"] button[data-tone="available"]').evaluateAll((els) => els.map((e) => e.getAttribute("aria-label") ?? ""));
  expect(labels.length).toBeGreaterThan(0);
  expect(labels.filter((l) => /rezerve et/i.test(l))).toEqual([]);

  // find-room: results and the "Kurallar" popover
  await page.goto(`/find-room?date=${ctx.day}&text=${encodeURIComponent(ctx.room.name)}`);
  await page.getByTestId("fr-search").click();
  const row = page.getByTestId(`fr-room-${ctx.room.name.replace(" ", "")}`).or(page.locator(`[data-testid^="fr-room-"]`).first());
  await expect(row.first()).toBeVisible();
  const buttons = await page.locator('[data-testid="fr-results"] button, [data-testid="fr-alternatives"] button').allInnerTexts();
  expect(buttons.filter((b) => /rezerve et/i.test(b))).toEqual([]);
  await expect(page.locator('[data-testid="fr-summary"]').locator("xpath=..")).not.toContainText(" ms");
  const why = page.getByTestId("policy-why").first();
  if (await why.isVisible()) {
    await why.click();
    const panel = page.getByTestId("policy-why-panel");
    await expect(panel).toContainText("Onaylayıcılara gider");
    await expect(panel).toContainText("Her talep önce onaya");
    await expect(panel).not.toContainText("Rezerve edebilirsiniz");
    await page.keyboard.press("Escape");
  }

  // the phone slot list names the request too
  const p = await phonePage(browser, TEACHER.username, TEACHER.password);
  await p.goto(`/bookings?date=${ctx.day}&group=${ctx.groupId}`);
  const freeSlots = p.getByTestId("free-slot");
  await expect(freeSlots.first()).toBeVisible();
  const names = await freeSlots.evaluateAll((els) => els.map((e) => e.getAttribute("aria-label") ?? ""));
  expect(names.filter((n) => /rezerve et/i.test(n))).toEqual([]);
  expect(names.some((n) => /talep et \(onay gerekir\)/.test(n))).toBe(true);
  expect(await noSidewaysScroll(p)).toBe(true);
  await p.context().close();
});

test("T-R1-12 + T-R1-14: a grid request keeps the focus and shows Gönderiliyor…; find-room focuses the summary and marks the own request", async ({ page }) => {
  const [slot] = await freeRun(1);
  await login(page, TEACHER.username, TEACHER.password);
  await page.goto(`/bookings?date=${ctx.day}&group=${ctx.groupId}`);
  const key = `${slot!.date}|${slot!.period_id}|${slot!.room_id}`;
  await page.locator(`button[data-slot-key="${key}"]`).click();
  const sheet = page.getByTestId("book-sheet");
  const submit = sheet.getByTestId("book-submit");
  await expect(submit).toContainText("Talep et");
  await page.evaluate(() => {
    const w = window as unknown as { __busy: string[] };
    w.__busy = [];
    const el = document.querySelector('[data-testid="book-submit"]')!;
    new MutationObserver(() => w.__busy.push(`${el.getAttribute("aria-busy")}|${el.textContent}`)).observe(el, { attributes: true, childList: true, subtree: true, characterData: true });
  });
  await submit.click();
  await expect(sheet).toBeHidden();
  await expect.poll(() => activeIsBody(page), { timeout: 5_000 }).toBe(false);
  await page.waitForTimeout(1500); // the grid re-renders after the request: focus must survive it
  expect(await activeIsBody(page)).toBe(false);
  const seen = await page.evaluate(() => (window as unknown as { __busy: string[] }).__busy);
  expect(seen.some((s) => s.startsWith("true|"))).toBe(true);

  // find-room: the summary takes the focus; the own request reads "Talebiniz bekliyor"
  await page.goto(`/find-room?date=${ctx.day}&text=${encodeURIComponent(ctx.room.name)}`);
  await page.getByTestId("fr-search").click();
  await expect(page.getByTestId("fr-summary")).toBeFocused();
  // search the requested period itself: the own room is marked, not offered as free
  const mine = page.locator('[data-status="mine_pending"]');
  if (await mine.count()) {
    await expect(mine.first()).toContainText("Talebiniz bekliyor");
    await expect(mine.first().getByRole("link", { name: "Talebi aç" })).toHaveAttribute("href", /\/my-bookings\?request=\d+/);
  }
});

test("T-R1-13 + T-R1-18: a two-period request is one row; the approvals drawer names the span with one Kapat; d opens the reject dialog", async ({ page, browser }) => {
  const run = await freeRun(2);
  const sel = await api<{ id: number; slots: { mbs_id: number }[] }>("POST", "/bookings/multi", { slots: run.map((s) => ({ date: s.date, period_id: s.period_id, room_id: s.room_id })) }, ctx.teacher);
  await api("POST", `/bookings/multi/${sel.id}/create`, { type: "single", slots: sel.slots.map((s) => ({ mbs_id: s.mbs_id })), confirm_unpublished: true }, ctx.teacher);
  const reqs = (await api<{ id: number; group_id: number | null; status: string; bookings: { date: string; period_id: number }[] }[]>("GET", "/approvals/mine", undefined, ctx.teacher)).filter((r) => r.status === "PENDING" && r.bookings.some((b) => b.date === ctx.day && run.some((s) => s.period_id === b.period_id)));
  expect(reqs).toHaveLength(2);
  const gid = reqs[0]!.group_id!;

  const t = await (await browser.newContext({ locale: "tr-TR", timezoneId: "Europe/Istanbul" })).newPage();
  await login(t, TEACHER.username, TEACHER.password);
  await t.goto("/my-bookings");
  const list = t.getByTestId("my-requests");
  await expect(list).toBeVisible();
  await expect(list.locator(`[data-group-id="${gid}"]`)).toHaveCount(1);
  await expect(list.locator(`[data-group-id="${gid}"] [data-testid="group-slot-line"]`)).toContainText(/P\d+–P\d+/);
  await t.context().close();

  await login(page);
  await page.goto(`/approvals?request=${reqs[0]!.id}&group=${gid}`);
  const drawer = page.getByTestId("approval-drawer");
  await expect(drawer.getByTestId("group-slot-line")).toContainText(/P\d+–P\d+ \(\d\d:\d\d–\d\d:\d\d\)/);
  // A / D / R work in the drawer wherever the focus is (its close button included)
  await page.keyboard.press("d");
  await expect(page.getByTestId("reject-dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("reject-dialog")).toBeHidden();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  // and on a focused row of the list
  const rowBtn = page.getByTestId(`approval-${reqs[0]!.id}`);
  await rowBtn.focus();
  await page.keyboard.press("d");
  await expect(page.getByTestId("reject-dialog")).toBeVisible();
  await page.keyboard.press("Escape");
});

test("T-R1-11 Taleplerim at 1440: the pair is never cut, no 5000-row fetch, every row a Tab stop; phone has no sideways scroll", async ({ page, browser }) => {
  test.skip(!ctx.instructorId, "no unlinked instructor with requests in the current term");
  await page.setViewportSize({ width: 1440, height: 900 });
  const asked: string[] = [];
  page.on("request", (r) => asked.push(r.url()));
  await login(page, ACAD.username, ACAD.password);
  await page.goto("/moderation/me");
  const table = page.getByTestId("mine-table");
  await expect(table).toBeVisible({ timeout: 30_000 });
  expect(asked.filter((u) => /moderation\/matchings\?.*limit=5000/.test(u))).toEqual([]);
  expect(asked.some((u) => u.includes("/moderation/me/matchings"))).toBe(true);
  const cut = await table.locator('[data-testid="mine-pair"]').evaluateAll((els) => els.filter((e) => (e.parentElement as HTMLElement).scrollWidth > (e.parentElement as HTMLElement).clientWidth + 1).length);
  expect(cut).toBe(0);
  await expect(page.locator("main")).not.toContainText(/\b20\d\d-(GUZ|BAHAR|YAZ)\b/);
  const rows = table.getByTestId("mod-row");
  const n = await rows.count();
  expect(n).toBeGreaterThan(0);
  for (let i = 0; i < n; i++) await expect(rows.nth(i)).toHaveAttribute("tabindex", "0");

  const p = await phonePage(browser, ACAD.username, ACAD.password);
  await p.goto("/moderation/me");
  await expect(p.getByTestId("my-requests")).toBeVisible({ timeout: 30_000 });
  expect(await noSidewaysScroll(p)).toBe(true);
  await p.context().close();
});

test("T-R1-19 /bookings on a phone logs no page error (twice)", async ({ browser }) => {
  for (let i = 0; i < 2; i++) {
    const p = await (await browser.newContext(PHONE)).newPage();
    const errors: string[] = [];
    p.on("pageerror", (e) => errors.push(e.message));
    await login(p, TEACHER.username, TEACHER.password);
    await p.goto(`/bookings?date=${ctx.day}`);
    await expect(p.getByTestId("booking-grid-wrap")).toBeVisible();
    await p.waitForTimeout(1500);
    expect(errors).toEqual([]);
    expect(await noSidewaysScroll(p)).toBe(true);
    await p.context().close();
  }
});
