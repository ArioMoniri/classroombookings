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
 * 6. Backend asks batch 3 in the UI: withdrawing the photo and calendar-sync consents asks first and the toast shows
 *    the server's `effects[]` (a real feed link revoked); find-room opened with a GG.AA.YYYY date gives "Neden?" the
 *    full verdict (the result's `period_id`) for a request-only and a refused room; a retention 422 (over 36 500 days)
 *    is shown at its field; the queue's "Tümü" (`status=all`) lists a refused request the default view hides; phone.
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
/** batch 3: a request-only day and a refused day of this spec's own rules (week 4, Wednesday / Tuesday) */
const B3_REQUEST_DAY = "2026-03-04";
const B3_REFUSED_DAY = "2026-03-03";
const B3_USER = { username: `w2.b3.${STAMP}`, email: `w2.b3.${STAMP}@uni.edu.tr`, password: "Ogretmen-2026!" };

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
  // this spec handles its own notice (test 4 is the gate's test): no automatic acknowledgement
  await login(page, id, password, { ackNotice: false });
}
async function phone(browser: Browser, as?: { id: string; password: string }): Promise<Page> {
  const c = await browser.newContext(PHONE);
  const p = await c.newPage();
  if (as) await login(p, as.id, as.password, { ackNotice: false });
  return p;
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.token = await loginToken(ADMIN_EMAIL, ADMIN_PASSWORD);
  const terms = await api<{ id: number; code: string }[]>("GET", "/terms");
  ctx.termId = terms.find((x) => x.code === "2026-BAHAR")!.id;
  const runs = await api<{ id: number; kind: string; term_id: number; label: string; is_active: boolean; horizon?: string; status: string }[]>("GET", "/runs");
  const board = runs.find((r) => r.term_id === ctx.termId && r.kind === "COURSE" && r.label.startsWith("Grid import"))!;
  // the full-term solver run e2e/global-setup.ts resolved (the backend also holds week-3 runs for other specs)
  const solver =
    runs.find((r) => r.id === Number(process.env.E2E_SOLVER_RUN)) ??
    [...runs].reverse().find((r) => r.term_id === ctx.termId && r.kind === "COURSE" && r.horizon === "TERM" && !r.label.startsWith("Grid import") && ["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL"].includes(r.status))!;
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

/** "2026-03-04" → "04.03.2026" (GG.AA.YYYY, how people type dates here) */
const ggaa = (iso: string) => iso.split("-").reverse().join(".");
/** the backend's effect sentence as the toast writes it: Turkish capital first letter, full stop */
const sentence = (m: string) => {
  const s = m.trim().charAt(0).toLocaleUpperCase("tr-TR") + m.trim().slice(1);
  return /[.!?]$/.test(s) ? s : `${s}.`;
};
/** dismiss the notice gate if a notice of an earlier spec is unread */
async function ackNotice(token: string): Promise<void> {
  const me = await api<{ notice: { id: number } | null; needs_ack: boolean }>("GET", "/me/privacy", undefined, token);
  if (me.needs_ack && me.notice) await api("POST", "/me/privacy/ack", { notice_id: me.notice.id }, token);
}

test("6. batch 3: withdrawal effects in the toast; find-room 'Neden?' verdict; a retention 422 at its field; 'Tümü'", async ({ page, browser }) => {
  // --- Gizlilik: the server's effects in the toast (photo: nothing stored; calendar sync: a real feed link revoked)
  await ackNotice(ctx.teacherToken);
  for (const purpose of ["photo", "calendar_sync"]) await api("POST", `/me/consents/${purpose}`, undefined, ctx.teacherToken);
  const feed = await call("POST", "/calendar/feeds/tokens", { label: `e2e ${STAMP}` }, ctx.teacherToken);
  expect(feed.status, JSON.stringify(feed.body)).toBe(201);
  await signInAs(page, TEACHER.username, TEACHER.password);
  await page.goto("/profile#privacy");
  const privacy = page.getByTestId("privacy-section");
  const photo = privacy.getByTestId("consent-photo");
  await expect(photo).toContainText("kayıtlı profil fotoğrafınız hemen silinir");
  await photo.getByTestId("consent-switch-photo").click();
  await expect(page.getByRole("alertdialog").or(page.getByRole("dialog"))).toContainText("Fotoğraf rızası geri alınsın mı?");
  const [photoRes] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/me/consents/photo") && r.request().method() === "DELETE"),
    page.getByRole("button", { name: "Geri al ve fotoğrafı sil" }).click(),
  ]);
  const photoOut = (await photoRes.json()) as { removed_photo: number; effects: { code: string; message_tr: string }[] };
  expect(photoOut.effects.map((e) => e.code)).toEqual([photoOut.removed_photo ? "photo_deleted" : "photo_none"]);
  const toasts = page.locator("[data-sonner-toast]");
  await expect(toasts.filter({ hasText: "Rıza geri alındı" }).first()).toContainText(sentence(photoOut.effects[0]!.message_tr));
  await expect(photo.getByTestId("consent-switch-photo")).not.toBeChecked();

  const cal = privacy.getByTestId("consent-calendar_sync");
  await expect(cal).toContainText("takvim abonelik bağlantılarınız hemen iptal edilir");
  await cal.getByTestId("consent-switch-calendar_sync").click();
  const [calRes] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/me/consents/calendar_sync") && r.request().method() === "DELETE"),
    page.getByRole("button", { name: "Geri al ve bağlantıları kaldır" }).click(),
  ]);
  const calOut = (await calRes.json()) as { revoked_feeds: number; effects: { code: string; count: number | null; message_tr: string }[] };
  expect(calOut.revoked_feeds).toBeGreaterThanOrEqual(1);
  const revoked = calOut.effects.find((e) => e.code === "feeds_revoked")!;
  expect(revoked.count).toBe(calOut.revoked_feeds);
  await expect(toasts.filter({ hasText: revoked.message_tr.slice(2, 40) }).first()).toContainText(sentence(revoked.message_tr));
  // the link is gone at once: a second withdrawal finds nothing to revoke
  const again = await api<{ effects: { code: string }[] }>("DELETE", "/me/consents/calendar_sync", undefined, ctx.teacherToken);
  expect(again.effects.map((e) => e.code)).toEqual(["calendar_none"]);

  // --- find-room: GG.AA.YYYY in the link; "Neden?" asks with the result's period_id → the full verdict
  const reqRule = await api<{ id: number }>("POST", "/booking-policies", { name: `E2E b3 talep ${STAMP}`, role_codes: ["TEACHER"], effect: "request", blackouts: [{ from: B3_REQUEST_DAY, label: "Bölüm toplantısı" }] });
  ctx.policies.push(reqRule.id);
  const refRule = await api<{ id: number }>("POST", "/booking-policies", { name: `E2E b3 kapalı ${STAMP}`, role_codes: ["TEACHER"], blackouts: [{ from: B3_REFUSED_DAY, label: "Kapalı gün" }] });
  ctx.policies.push(refRule.id);
  const verdictCalls: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/booking-policies/effective")) verdictCalls.push(r.url());
  });
  await page.goto(`/find-room?date=${ggaa(B3_REQUEST_DAY)}`);
  const view = page.getByTestId("find-room");
  await view.getByTestId("fr-search").click();
  await expect(view.getByTestId("fr-summary")).toBeVisible();
  const requestable = view.locator('[data-testid^="fr-room-"][data-status="requestable"]').first();
  await expect(requestable).toBeVisible();
  await requestable.getByTestId("policy-why").click();
  const why = page.getByTestId("policy-why-panel");
  await expect(why).toContainText("Onaylayıcılara gider");
  await expect(why.getByTestId("policy-why-violations")).toBeVisible();
  await expect(why).toContainText(`E2E b3 talep ${STAMP}`);
  expect(verdictCalls.some((u) => /[?&]period_id=\d+/.test(u) && u.includes(`date=${B3_REQUEST_DAY}`)), verdictCalls.join("\n")).toBe(true);
  await page.keyboard.press("Escape");

  // a refused day: the refused rooms are among "Uymayan" with the busy ones shown
  await page.goto(`/find-room?date=${ggaa(B3_REFUSED_DAY)}`);
  await view.getByRole("switch", { name: "Dolu derslikleri de göster" }).click();
  await view.getByTestId("fr-search").click();
  await expect(view.getByTestId("fr-summary")).toBeVisible();
  await view.getByText(/Uymayan \d+ derslik/).click();
  const refused = view.locator('[data-testid^="fr-room-"][data-status="policy"]').first();
  await expect(refused).toBeVisible();
  await refused.getByTestId("policy-why").click();
  await expect(why).toContainText("Rezerve edilemez");
  await expect(why.getByTestId("policy-why-violations")).toContainText(/Kapalı gün|kapalı/i);
  await page.keyboard.press("Escape");

  // --- retention: over 36 500 days passes the form, the backend's 422 lands at the days field
  await signInAs(page);
  await page.goto("/admin/kvkk?tab=retention");
  const audit = page.getByTestId("retention-audit");
  const days = audit.getByTestId("retention-days-audit");
  await days.fill("40000");
  const [put] = await Promise.all([page.waitForResponse((r) => r.url().includes("/admin/retention/audit") && r.request().method() === "PUT"), audit.getByTestId("retention-save-audit").click()]);
  expect(put.status()).toBe(422);
  const detail = ((await put.json()) as { detail: { errors: { field: string; floor_days?: number; max_days?: number }[] } }).detail;
  const e = detail.errors.find((x) => x.field === "retain_days")!;
  const fieldErr = audit.getByTestId("retention-field-error-audit-retain_days");
  await expect(fieldErr).toHaveText(`${e.floor_days} ile ${e.max_days} gün arasında.`);
  await expect(days).toHaveAttribute("aria-invalid", "true");
  await expect(audit.getByTestId("retention-error-audit")).toHaveCount(0);
  await days.fill("400");
  await expect(fieldErr).toHaveCount(0);

  // --- the queue: a refused request is hidden by "Açık" and listed by "Tümü"
  await api("POST", "/users", { username: B3_USER.username, email: B3_USER.email, firstname: "Bilgi", lastname: "İsteyen", role: "TEACHER", password: B3_USER.password });
  const b3Token = await loginToken(B3_USER.username, B3_USER.password);
  const info = await api<{ id: number }>("POST", "/me/data-requests", { kind: "info", note: "Hangi verilerim tutuluyor?" }, b3Token);
  await api("POST", `/admin/dsr/${info.id}/refuse`, { reason: "Talep kimlik doğrulaması olmadan yapıldı" });
  await page.goto("/admin/kvkk?tab=requests");
  const queue = page.getByTestId("dsr-queue");
  await expect(queue.getByTestId("dsr-filter-open")).toBeVisible();
  await expect(queue.getByTestId(`dsr-${info.id}`)).toHaveCount(0);
  const [all] = await Promise.all([page.waitForResponse((r) => r.url().includes("/admin/dsr?status=all")), queue.getByTestId("dsr-filter-all").click()]);
  expect(all.status()).toBe(200);
  await expect(queue.getByTestId(`dsr-${info.id}`)).toContainText("Reddedildi");

  // --- phone: the four filters and the field error fit 390 px
  const p = await phone(browser, { id: ADMIN_EMAIL, password: ADMIN_PASSWORD });
  const later = p.getByTestId("notice-gate-later");
  await p.goto("/admin/kvkk?tab=requests");
  if (await later.isVisible().catch(() => false)) await later.click();
  const pq = p.getByTestId("dsr-queue");
  await expect(pq).toBeVisible();
  const allOption = pq.getByTestId("dsr-filter-all");
  if (await allOption.isVisible().catch(() => false)) await allOption.click();
  else await pq.locator("select").first().selectOption("all");
  await expect(pq.getByTestId(`dsr-${info.id}`)).toBeVisible();
  await noSideScroll(p);
  await p.goto("/admin/kvkk?tab=retention");
  const pa = p.getByTestId("retention-audit");
  await pa.getByTestId("retention-days-audit").fill("40000");
  await pa.getByTestId("retention-save-audit").click();
  await expect(pa.getByTestId("retention-field-error-audit-retain_days")).toBeVisible();
  await noSideScroll(p);
  expect((await pa.getByTestId("retention-save-audit").boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await p.context().close();
});
