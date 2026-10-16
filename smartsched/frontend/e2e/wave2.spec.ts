/**
 * Bookings wave 2 + KVKK UI against the REAL backend (no mocks), gated E2E_REAL=1, on the real Bahar 2026 data:
 *
 * 1. P2 resolver: the spec books slots of the imported board that the full-term solver run holds, then publishes the
 *    solver run, so the conflicts are real. /bookings shows the banner; the resolver lists the groups. A manual
 *    decision whose target room is taken meanwhile (booked through the API between the dry run and the apply) comes
 *    back as 409 `invalid_items` and is shown inside its row; nothing changed. "Önerilenleri uygula" fills the
 *    suggestions, the review shows the dry-run counts, applying shows the result (moved / notified).
 * 2. P8 policies: Ayarlar › Rezervasyon kuralları creates a refusing rule for teachers in the form; a second rule
 *    (request) comes from the API. A teacher's grid marks refused cells, the slot sheet's "Neden?" lists the rule;
 *    request-only cells carry the marker and the book sheet says the booking goes to the approvers.
 * 3. V2 public view: switching it on needs the KVKK acknowledgement and records the sign-off; signed out, /public,
 *    a building and a room open with large type and a date switcher; switched off, the same URL is the plain 404 page.
 * 4. A4 KVKK: Admin › KVKK publishes a notice (the gate never covers /admin/kvkk); a teacher must read it ("Okudum")
 *    before using the app; Profil › Gizlilik shows the SMS withdrawal consequence, prepares and downloads the export;
 *    an erasure request is completed from the queue with the counts and the "partial" explanation; retention refuses
 *    a period under the legal floor; the inventory downloads as CSV.
 * 5. Phone 390 × 844 (touch): the resolver, Admin › KVKK, Profil › Gizlilik and the public room page have no sideways
 *    scroll; the main actions are ≥ 44 px.
 *
 * Everything the spec changes is its own (users, bookings, policies, the public switch is restored to off).
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19030 NEXT_PUBLIC_API_URL=http://127.0.0.1:19030 PW_PORT=19031 \
 *     npx playwright test e2e/wave2.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const TEACHER = { username: `w2.hoca.${STAMP}`, email: `w2.hoca.${STAMP}@uni.edu.tr`, password: "Ogretmen-2026!" };
const LEAVER = { username: `w2.ayrilan.${STAMP}`, email: `w2.ayrilan.${STAMP}@uni.edu.tr`, password: "Ogretmen-2026!" };
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
/** a Thursday of week 5: the seeded resolver bookings of other runs never use it */
const CLASH_DAY = "2026-03-05";
const REFUSED_DAY = "2026-03-27";
const REQUEST_DAY = "2026-02-26";

test.describe.configure({ mode: "serial", timeout: 300_000 });
test.skip(!REAL, SKIP_REASON);

interface Slot {
  date: string;
  period_id: number;
  room_id: number;
  status: string;
  reason?: string | null;
  request_only?: boolean;
}
interface Grid {
  periods: { id: number; start_period: number }[];
  slots: Slot[];
}
const ctx = { policies: [] as number[], bookings: [] as number[] } as {
  api: APIRequestContext;
  token: string;
  teacherToken: string;
  termId: number;
  groupA: number;
  solverRun: number;
  boardRun: number;
  policies: number[];
  bookings: number[];
  rooms: Record<string, number>;
};

async function call<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown, token = ctx.token): Promise<{ status: number; body: T }> {
  const res = await ctx.api.fetch(`${API}${path}`, { method, data: body, headers: { Authorization: `Bearer ${token}` } });
  const text = await res.text();
  let parsed: unknown = undefined;
  try {
    parsed = text ? JSON.parse(text) : undefined;
  } catch {
    parsed = text;
  }
  return { status: res.status(), body: parsed as T };
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
/** M-01: no sideways scroll on the layout viewport */
async function noSideScroll(page: Page): Promise<void> {
  const m = await page.evaluate(() => ({ sw: document.scrollingElement!.scrollWidth, vw: document.documentElement.clientWidth }));
  expect(m.sw, `scrollWidth ${m.sw} > ${m.vw}`).toBeLessThanOrEqual(m.vw + 1);
}
/** sign in as someone else in the same page (a signed-in visit to /login bounces to the dashboard) */
async function signInAs(page: Page, id: string = ADMIN_EMAIL, password: string = ADMIN_PASSWORD): Promise<void> {
  await page.goto("about:blank");
  await page.context().clearCookies();
  await login(page, id, password);
}
async function phone(browser: Browser, as?: { id: string; password: string }): Promise<Page> {
  const c = await browser.newContext(PHONE);
  const p = await c.newPage();
  if (as) await login(p, as.id, as.password);
  return p;
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.token = await loginToken(ADMIN_EMAIL, ADMIN_PASSWORD);
  const terms = await api<{ id: number; code: string }[]>("GET", "/terms");
  ctx.termId = terms.find((x) => x.code === "2026-BAHAR")!.id;
  const runs = await api<{ id: number; kind: string; term_id: number; label: string; is_active: boolean; horizon?: string; status: string }[]>("GET", "/runs");
  const board = runs.find((r) => r.term_id === ctx.termId && r.kind === "COURSE" && r.label.startsWith("Grid import"))!;
  const solver = [...runs].reverse().find((r) => r.term_id === ctx.termId && r.kind === "COURSE" && !r.label.startsWith("Grid import") && ["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL"].includes(r.status))!;
  ctx.boardRun = board.id;
  ctx.solverRun = solver.id;
  // the bookable session, 18 periods and room groups (as bookings.spec.ts)
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
  ctx.rooms = Object.fromEntries(rooms.map((r) => [r.code, r.id]));
  ctx.groupA = rooms.find((r) => r.code === "A101")!.room_group_id!;
  await api("PUT", "/public-schedule/admin/settings", { enabled: false });
  // the teacher who books under the policies and reads the notice
  await api("POST", "/users", { username: TEACHER.username, email: TEACHER.email, firstname: "Derya", lastname: "Kaya", role: "TEACHER", password: TEACHER.password });
  ctx.teacherToken = await loginToken(TEACHER.username, TEACHER.password);
  // a notice published by an earlier run of this spec: acknowledged up front, so tests 1–3 see the app
  for (const token of [ctx.token, ctx.teacherToken]) {
    const me = await api<{ notice: { id: number } | null; needs_ack: boolean }>("GET", "/me/privacy", undefined, token);
    if (me.needs_ack && me.notice) await api("POST", "/me/privacy/ack", { notice_id: me.notice.id }, token);
  }
});

test.afterAll(async () => {
  for (const id of ctx.policies) await call("DELETE", `/booking-policies/${id}`);
  await call("PUT", "/public-schedule/admin/settings", { enabled: false });
  await ctx.api?.dispose();
});

test("1. resolver: real clashes after publishing; a taken target comes back inside its row; the suggestions apply", async ({ page }) => {
  // the board is the published timetable while we book; then the solver run is published over it
  const active = (await api<{ id: number; is_active: boolean }[]>("GET", "/runs")).find((r) => r.is_active && (r.id === ctx.boardRun || r.id === ctx.solverRun));
  if (active?.id !== ctx.boardRun) await api("POST", `/runs/${ctx.boardRun}/activate`);
  const assignments = await api<{ day: number; weeks: number[] | null; start_period: number; end_period: number; room_ids: number[] }[]>("GET", `/runs/${ctx.solverRun}/assignments`);
  const roomGroup = new Map<number, number | null>((await api<{ id: number; room_group_id: number | null }[]>("GET", "/room-admin/rooms")).map((r) => [r.id, r.room_group_id]));
  const grids = new Map<number, Grid>();
  const made: { kind: "series" | "single"; room: number; period: number }[] = [];
  for (const a of assignments) {
    if (made.length >= 3) break;
    if (a.day !== 4 || !a.room_ids.length || !(a.weeks ?? []).includes(5)) continue;
    const room = a.room_ids[0]!;
    if (made.some((m) => m.room === room)) continue;
    const gid = roomGroup.get(room);
    if (!gid) continue;
    if (!grids.has(gid)) grids.set(gid, await api<Grid>("GET", `/bookings/grid?display=day&date=${CLASH_DAY}&room_group_id=${gid}`));
    const g = grids.get(gid)!;
    const period = g.periods.find((p) => p.start_period === a.start_period);
    const slot = period && g.slots.find((s) => s.room_id === room && s.period_id === period.id && s.status === "available");
    if (!slot || !period) continue;
    if (made.length === 0) {
      const out = await api<{ created: { id: number }[] }>("POST", "/bookings/recurring", { room_id: room, period_id: period.id, date: CLASH_DAY, start: CLASH_DAY, end: "2026-03-19", notes: `W2 seminer ${STAMP}` });
      ctx.bookings.push(...out.created.map((b) => b.id));
      made.push({ kind: "series", room, period: period.id });
    } else {
      const out = await api<{ id: number }>("POST", "/bookings", { room_id: room, date: CLASH_DAY, period_id: period.id, notes: `W2 toplantı ${STAMP}` });
      ctx.bookings.push(out.id);
      made.push({ kind: "single", room, period: period.id });
    }
  }
  expect(made.length, "three slots of the board that the solver run holds").toBe(3);
  await api("POST", `/runs/${ctx.solverRun}/activate`);
  const summary = await api<{ runs: { run_id: number; open: number }[] }>("GET", "/bookings/conflicts/summary");
  const open = summary.runs.find((r) => r.run_id === ctx.solverRun)?.open ?? 0;
  expect(open).toBeGreaterThanOrEqual(3);

  await signInAs(page);
  await page.goto(`/bookings?date=${CLASH_DAY}&group=${ctx.groupA}`);
  const banner = page.getByTestId("conflict-banner");
  await expect(banner).toContainText(/Yayınlanan programla çakışan \d+ rezervasyon/);
  await banner.getByTestId(`conflict-banner-open-${ctx.solverRun}`).click();
  await expect(page).toHaveURL(new RegExp(`/bookings/conflicts/${ctx.solverRun}$`));
  await expect(page.getByTestId("resolver")).toBeVisible();

  // a single booking of ours: decide by hand, then someone takes the target room between the dry run and the apply
  const plan = await api<{ groups: { key: string; kind: string; conflicts: { booking_id: number; date: string; start_period: number }[]; options: { id: string; kind: string; room_id?: number }[] }[] }>("GET", `/bookings/conflicts/${ctx.solverRun}/plan`);
  const single = plan.groups.find((g) => g.kind === "booking" && g.conflicts.some((c) => ctx.bookings.includes(c.booking_id)) && g.options.some((o) => o.kind === "move_room"))!;
  expect(single, "one of our single bookings has a room option").toBeTruthy();
  const target = single.options.find((o) => o.kind === "move_room")!;
  const card = page.getByTestId(`resolver-group-${single.key}`);
  await card.getByTestId(`resolver-option-${single.key}-${target.id}`).click();
  await page.getByTestId("resolver-apply").click();
  const review = page.getByTestId("resolver-review");
  await expect(review.getByTestId("resolver-dry")).toContainText(/1 rezervasyon taşınacak/);
  // someone else books the target room at that time (the period id comes from the target group's grid)
  const clash = single.conflicts[0]!;
  const tg = await api<Grid>("GET", `/bookings/grid?display=day&date=${clash.date}&room_group_id=${roomGroup.get(target.room_id!)}`);
  const tp = tg.periods.find((x) => x.start_period === clash.start_period)!;
  const racer = await api<{ id: number }>("POST", "/bookings", { room_id: target.room_id, date: clash.date, period_id: tp.id, notes: `W2 yarış ${STAMP}` });
  await review.getByTestId("resolver-confirm").click();
  await expect(page.getByTestId("resolver-failure")).toContainText("Hiçbir değişiklik yapılmadı");
  await expect(card.getByTestId("resolver-problems")).toContainText(/dolu/);
  await api("POST", `/bookings/${racer.id}/cancel`, { reason: "e2e" }).catch(() => undefined);

  // the suggestions: auto → review with the dry-run counts → apply → result
  await page.reload();
  await page.getByTestId("resolver-auto").click();
  await expect(review.getByTestId("resolver-dry")).toContainText(/rezervasyon taşınacak/);
  await review.getByTestId("resolver-confirm").click();
  const result = page.getByTestId("resolver-result");
  await expect(result).toBeVisible();
  expect(Number((await result.getByTestId("resolver-result-moved").innerText()).match(/\d+/)![0])).toBeGreaterThan(0);
  const after = await api<{ runs: { run_id: number; open: number }[] }>("GET", "/bookings/conflicts/summary");
  expect(after.runs.find((r) => r.run_id === ctx.solverRun)?.open ?? 0).toBeLessThan(open);

});

test("2. policies: the editor's refusing rule and an API request rule show in a teacher's grid with 'Neden?'", async ({ page }) => {
  await signInAs(page);
  await page.goto("/settings?tab=booking-rules");
  await expect(page.getByTestId("policies-admin")).toBeVisible();
  await page.getByTestId("policy-new").click();
  const form = page.getByTestId("policy-form");
  await form.getByTestId("policy-save").click();
  await expect(form).toContainText("Kurala bir ad verin.");
  await expect(form).toContainText("En az bir sınır");
  await form.getByTestId("policy-name").fill(`E2E ileri tarih ${STAMP}`);
  await form.getByTestId("policy-role-TEACHER").click();
  await form.getByTestId("policy-max_advance_days").fill("30");
  await form.getByTestId("policy-save").click();
  await expect(page.getByTestId("policy-sheet")).toBeHidden();
  const list = await api<{ policies: { id: number; name: string; summary: { tr: string[] } }[] }>("GET", "/booking-policies");
  const mine = list.policies.find((p) => p.name === `E2E ileri tarih ${STAMP}`)!;
  ctx.policies.push(mine.id);
  await expect(page.getByTestId(`policy-summary-${mine.id}`)).toContainText("En fazla 30 gün sonrası için");
  const req = await api<{ id: number }>("POST", "/booking-policies", { name: `E2E talep ${STAMP}`, role_codes: ["TEACHER"], effect: "request", blackouts: [{ from: REQUEST_DAY, label: "Bölüm günü" }] });
  ctx.policies.push(req.id);

  // the teacher: refused cells beyond 30 days, "Neden?" names the rule
  await signInAs(page, TEACHER.username, TEACHER.password);
  await page.goto(`/bookings?date=${REFUSED_DAY}&group=${ctx.groupA}&lens=grid`);
  const refused = page.locator('[data-cell]:has([data-reason-icon="policy"])').first();
  await expect(refused).toBeVisible();
  await refused.click();
  const info = page.getByTestId("slot-info");
  await expect(info.getByTestId("slot-info-message")).toContainText(/30/);
  await info.getByTestId("policy-why").click();
  const why = page.getByTestId("policy-why-panel");
  await expect(why).toContainText("Rezerve edilemez");
  await expect(why).toContainText(`E2E ileri tarih ${STAMP}`);
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");

  // request-only: the marker, and the book sheet says it goes to the approvers
  await page.goto(`/bookings?date=${REQUEST_DAY}&group=${ctx.groupA}&lens=grid`);
  const marked = page.locator('[data-cell][data-tone="available"]:has([data-request-only])').first();
  await expect(marked).toBeVisible();
  await expect(marked).toHaveAttribute("aria-label", /onaylayıcılara talep olarak gider/);
  await marked.click();
  await expect(page.getByTestId("book-policy-request")).toContainText(/rezervasyona kapalı|Bölüm günü/);
});

test("3. public day view: sign-off to switch on, signed-out pages with a date switcher, the plain 404 when off", async ({ page, browser }) => {
  await signInAs(page);
  await page.goto("/settings?tab=integrations");
  const card = page.getByTestId("public-schedule-admin");
  await expect(card.getByTestId("public-no-signoff").or(card.getByTestId("public-signoff"))).toBeVisible();
  await card.getByTestId("public-schedule-switch").click();
  const notice = page.getByTestId("public-notice");
  await expect(notice.getByTestId("public-notice-text")).toContainText("Asla gösterilmeyenler");
  await expect(notice.getByTestId("public-confirm")).toBeDisabled();
  await notice.getByTestId("public-ack").check();
  await notice.getByTestId("public-confirm").click();
  await expect(card.getByTestId("public-signoff")).toContainText(/açıldı/);

  const anon = await browser.newContext({ locale: "tr-TR", timezoneId: "Europe/Istanbul" });
  const pub = await anon.newPage();
  await pub.goto("/public");
  await expect(pub.getByTestId("public-index")).toBeVisible();
  await pub.getByTestId("public-building-A").click();
  await expect(pub.getByTestId("public-building-rooms")).toBeVisible();
  await pub.goto("/public/rooms/A104");
  await expect(pub.getByTestId("kiosk-title")).toHaveText("A 104");
  const today = await pub.getByTestId("kiosk-long-date").innerText();
  await pub.getByTestId("kiosk-next").click();
  await expect(pub).toHaveURL(/\?date=\d{4}-\d{2}-\d{2}/);
  await expect(pub.getByTestId("kiosk-long-date")).not.toHaveText(today);
  // no personal data: no instructor or booker names, no e-mail address on the page
  const text = await pub.locator("body").innerText();
  expect(text).not.toMatch(/@uni\.edu\.tr|Administrator/);

  // a phone at the door
  const door = await phone(browser);
  await door.goto("/public/rooms/A104");
  await expect(door.getByTestId("kiosk-title")).toBeVisible();
  await noSideScroll(door);
  await door.context().close();

  // a wall screen restarted on a date link keeps its date switcher
  await pub.reload();
  await expect(pub.getByTestId("kiosk-prev")).toBeVisible();
  await anon.close();

  // off: the same URL is the one plain "not found" page (a new screen: the API's 60 s cache does not apply)
  await api("PUT", "/public-schedule/admin/settings", { enabled: false });
  const after = await browser.newContext({ locale: "tr-TR" });
  const gone = await after.newPage();
  await gone.goto("/public/rooms/A104");
  await expect(gone.getByTestId("public-not-found")).toContainText("Bu sayfa kullanılamıyor");
  await after.close();
});

test("4. KVKK: publish a notice, the teacher reads it first; Gizlilik; export; erasure from the queue; retention floor; inventory", async ({ page, browser }) => {
  await signInAs(page);
  await page.goto("/admin/kvkk?tab=notice");
  await page.getByTestId("notice-new").click();
  const form = page.getByTestId("notice-form");
  await form.getByTestId("notice-title").fill(`Aydınlatma metni ${STAMP}`);
  await form.getByTestId("notice-body").fill("# Veri sorumlusu\n\nBu metin uçtan uca test için yazıldı.\n\n- Rezervasyon verileri\n- Denetim kaydı");
  await form.getByTestId("notice-preview").click();
  await expect(form.getByRole("heading", { name: "Veri sorumlusu" })).toBeVisible();
  await form.getByTestId("notice-save").click();
  await expect(page.getByTestId("notice-sheet")).toBeHidden();
  const notices = await api<{ id: number; title: string; version: number }[]>("GET", "/admin/privacy-notices");
  const draft = notices.find((n) => n.title === `Aydınlatma metni ${STAMP}`)!;
  await page.getByTestId(`notice-publish-${draft.id}`).click();
  await page.getByRole("button", { name: "Yayımla" }).last().click();
  await expect(page.getByTestId(`notice-v${draft.version}-tr`)).toContainText("yayımlandı");
  // the gate never covers /admin/kvkk; elsewhere an administrator may postpone it
  await expect(page.getByTestId("notice-gate")).toHaveCount(0);
  await page.goto("/bookings");
  await expect(page.getByTestId("notice-gate")).toBeVisible();
  await page.getByTestId("notice-gate-later").click();
  await expect(page.getByTestId("notice-gate")).toHaveCount(0);

  // the teacher must read it before the app
  await signInAs(page, TEACHER.username, TEACHER.password);
  const gate = page.getByTestId("notice-gate");
  await expect(gate).toContainText(`Aydınlatma metni ${STAMP}`);
  await expect(page.getByTestId("notice-gate-later")).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(gate).toBeVisible();
  await gate.getByTestId("notice-gate-ack").click();
  await expect(gate).toHaveCount(0);
  await page.goto("/profile#privacy");
  const privacy = page.getByTestId("privacy-section");
  await expect(privacy.getByTestId("privacy-acked")).toBeVisible();
  await expect(privacy.getByTestId("consent-sms")).toContainText("telefon numaralarınız (SMS ve WhatsApp) hemen silinir");
  await privacy.getByTestId("privacy-request-send").click();
  const download = privacy.locator('[data-testid^="privacy-download-"]').first();
  await expect(download).toBeVisible();
  const [file] = await Promise.all([page.waitForEvent("download"), download.click()]);
  expect(file.suggestedFilename()).toMatch(/^smartsched-verilerim-\d{8}\.zip$/);

  // an erasure request of another person, completed from the queue
  await api("POST", "/users", { username: LEAVER.username, email: LEAVER.email, firstname: "Ayrılan", lastname: "Kişi", role: "TEACHER", password: LEAVER.password });
  const leaverToken = await loginToken(LEAVER.username, LEAVER.password);
  const erase = await api<{ id: number }>("POST", "/me/data-requests", { kind: "erase", note: "Kurumdan ayrıldım" }, leaverToken);
  await signInAs(page);
  await page.goto("/admin/kvkk?tab=requests");
  const row = page.getByTestId(`dsr-${erase.id}`);
  await expect(row.getByTestId(`dsr-days-${erase.id}`)).toContainText(/gün kaldı/);
  await row.getByTestId(`dsr-complete-${erase.id}`).click();
  const dialog = page.getByTestId("dsr-dialog");
  await expect(dialog).toContainText("Geri alınamaz");
  await dialog.getByTestId("dsr-confirm").click();
  const result = page.getByTestId("dsr-result");
  await expect(result).toBeVisible();
  await expect(result.getByTestId("dsr-partial")).toContainText("denetim kayıtları yasal saklama süresince takma adla");

  // retention: under the floor is refused at the field; inventory CSV
  await page.goto("/admin/kvkk?tab=retention");
  const audit = page.getByTestId("retention-audit");
  await audit.getByTestId("retention-days-audit").fill("100");
  await expect(audit).toContainText("En az 365 gün olmalı.");
  await expect(audit.getByTestId("retention-save-audit")).toBeDisabled();
  await page.goto("/admin/kvkk?tab=inventory");
  const [csv] = await Promise.all([page.waitForEvent("download"), page.getByTestId("inventory-csv").click()]);
  expect(csv.suggestedFilename()).toMatch(/^smartsched-kvkk-envanter-.*\.csv$/);

  // phone: Admin › KVKK and Profil › Gizlilik
  const p = await phone(browser, { id: ADMIN_EMAIL, password: ADMIN_PASSWORD });
  await p.goto("/admin/kvkk?tab=requests");
  await expect(p.getByTestId("dsr-queue")).toBeVisible();
  await noSideScroll(p);
  await p.goto("/admin/kvkk?tab=retention");
  await expect(p.getByTestId("retention-editor")).toBeVisible();
  await noSideScroll(p);
  const later = p.getByTestId("notice-gate-later");
  await p.goto("/profile#privacy");
  if (await later.isVisible().catch(() => false)) await later.click();
  await expect(p.getByTestId("privacy-section")).toBeVisible();
  await noSideScroll(p);
  const send = await p.getByTestId("privacy-request-send").boundingBox();
  expect(send!.height).toBeGreaterThanOrEqual(44);
  await p.context().close();
});

test("5. phone: the resolver has no sideways scroll and 44 px options", async ({ browser }) => {
  const p = await phone(browser, { id: ADMIN_EMAIL, password: ADMIN_PASSWORD });
  await p.goto(`/bookings/conflicts/${ctx.solverRun}`);
  const later = p.getByTestId("notice-gate-later");
  if (await later.isVisible().catch(() => false)) await later.click();
  await expect(p.getByTestId("resolver")).toBeVisible();
  await noSideScroll(p);
  const option = p.locator('[data-testid^="resolver-option-"]').first();
  if (await option.count()) expect((await option.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await p.context().close();
});
