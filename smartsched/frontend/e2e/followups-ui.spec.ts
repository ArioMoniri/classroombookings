/**
 * Follow-ups UI against the REAL backend (no mocks), gated E2E_REAL=1. Owner requirement: academicians add their
 * own requests and preferences, admins moderate each class, person and request from the admin panel; wishes are
 * never applied by themselves; phones at 390 px; TR (default) + EN. The runnable form of F-05 S03 part 2 (P19-T2
 * "Tercih ekle", docs/testing/flows/F-05-taleplerim-and-moderation.md):
 *
 * 1. An academician linked to the instructor of R601 PTL 102 §1 (`PUT /auth/sso/admin/users/{id}/instructor`)
 *    opens Taleplerim, taps the class row: the sheet preselects it. A time window is refused with the
 *    "bölüm formu sabitliyor" explanation (fixed_by_department), already in the server's preview (`?dry_run=1`)
 *    before sending. The room picker (`GET /moderation/me/rooms`) lists the bookable rooms by building with their
 *    capacity; "c301" typed + Enter picks the listed C 301; the summary is the server's preview text and
 *    `effective` (nothing stored by a preview), then the sent wish. A building wish equal to the department's own
 *    block is refused in the preview and on sending (already_requested); block A is sent. Tercihlerim lists both
 *    as Bekliyor.
 * 2. A pending wish (sent through the API) is withdrawn from Tercihlerim after a confirmation.
 * 3. The coordinator sees "N tercih bekliyor" on the person (Kişiler), the header link opens Tercihler ›
 *    Akademisyen tercihleri, accepts the room wish (soft rule "bölüm odasından sonra", also in the rules table)
 *    and rejects the building wish only with a written reason (an empty one is refused) and a code.
 * 4. The academician reads Kabul edildi / Kabul edilmedi with "Gerekçe: Oda uygun değil: …"; the in-app notices
 *    preference.accepted / .rejected arrived; Profil › Bildirimler lists both events (read from the API).
 * 5. Phone 390 × 844: the sheet is a bottom sheet with 44 px targets and 16 px inputs, nothing scrolls sideways;
 *    the coordinator's reject dialog is a bottom sheet.
 * 6. Yönetim › Kullanıcılar: the identity chips and the method select ask the server (`identity=`,
 *    `self_signup_days=7`) and the count is the server's total.
 * 7. Program wizard (F-07): a programme created and undone archives its new person; a second programme naming
 *    that person gets `instructor_archived_namesake` (the pre-check answers 422 with the issue), "Bu kişiyi
 *    kullan" sets the slot to the record (`instructor_restored` info), and the commit reports the reopened person.
 *
 * Everything this spec creates is its own (two users, their wishes); afterAll unlinks the instructor and deletes
 * the users. The wishes stay as decided rows of the term (audited), like any coordinator decision.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19002 NEXT_PUBLIC_API_URL=http://127.0.0.1:19002 PW_PORT=19003 \
 *     npx playwright test e2e/followups-ui.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, TERM_CODE, login, pinTermCode } from "./helpers";
import { pinLanguage } from "./language";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const TEACHER = { username: `fu.hoca.${STAMP}`, email: `fu.hoca.${STAMP}@uni.edu.tr`, password: "Ogretmen-2026!" };
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };

test.describe.configure({ mode: "serial", timeout: 240_000 });
test.skip(!REAL, SKIP_REASON);
// the assertions read Turkish (the product default): pin it, whatever the previous spec left behind
pinLanguage("tr");

interface Row {
  request_id: number;
  label: string;
  instructors: { id: number; name: string; role: string | null }[];
  requested: { start_period: number | null; rooms: string[] };
}
const ctx = {} as { api: APIRequestContext; token: string; teacherToken: string; termId: number; activeBefore: { id: number; code: string; is_active: boolean }[] | null; userId: number; instructorId: number; instructorName: string; rows: Row[]; ptl102: Row };

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
async function loginToken(email: string, password: string): Promise<string> {
  const res = await ctx.api.post(`${API}/auth/login`, { data: { email, password } });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { access_token: string }).access_token;
}
const noSidewaysScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
async function phone(browser: Browser, email: string, password: string): Promise<Page> {
  const c = await browser.newContext(PHONE);
  const p = await c.newPage();
  await login(p, email, password);
  return p;
}
/** the visible interactive elements of `scope` under 44 × 44 px (MOBILE.md M-02, label hit areas count) */
async function smallTargets(page: Page, testId: string): Promise<{ el: string; w: number; h: number }[]> {
  return page.evaluate((id) => {
    const root = document.querySelector(`[data-testid="${id}"]`);
    if (!root) return [{ el: `missing ${id}`, w: 0, h: 0 }];
    const out: { el: string; w: number; h: number }[] = [];
    for (const el of root.querySelectorAll<HTMLElement>("button, input:not([type=hidden]), select, textarea, [role=checkbox], [role=radio]")) {
      const r = el.getBoundingClientRect();
      // the Sheet primitive's own close button (components/ui/sheet.tsx, icon-sm = 36 px on touch) is the ui owner's
      if (!r.width || !r.height || el.closest("[aria-hidden=true]") || el.closest("[data-slot=sheet-close]")) continue;
      let w = r.width;
      let h = r.height;
      const label = el.closest("label") ?? (el.id ? document.querySelector(`label[for="${el.id}"]`) : null);
      if (label) {
        const l = label.getBoundingClientRect();
        w = Math.max(w, l.width);
        h = Math.max(h, l.height);
      }
      // 0.5 px of sub-pixel layout slack (device scale 2); anything really under 44 still fails
      if (w < 43.5 || h < 43.5) out.push({ el: (el.dataset.testid || el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40), w: Math.round(w), h: Math.round(h) });
    }
    return out;
  }, testId);
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.token = await loginToken(ADMIN_EMAIL, ADMIN_PASSWORD);
  const terms = await api<{ id: number; code: string; is_active: boolean }[]>("GET", "/terms");
  ctx.termId = terms.find((t) => t.code === TERM_CODE)!.id;
  // Taleplerim reads the server's current term (no switcher for academicians): on a stack that also holds a newer
  // term (the Final next to Bahar) make TERM_CODE the active one for this spec; afterAll puts the flags back
  const current = await call<{ id: number }>("GET", "/terms/current");
  ctx.activeBefore = null;
  if (current.status !== 200 || current.body.id !== ctx.termId) {
    ctx.activeBefore = terms.map((t) => ({ id: t.id, code: t.code, is_active: t.is_active }));
    await api("PUT", `/terms/${ctx.termId}`, { is_active: true });
  }
  // the real row the backend test uses: R601 PTL 102 §1 (asked C 601, Tuesday P4 fixed by the department form)
  const found = await api<{ items: Row[] }>("GET", `/terms/${ctx.termId}/moderation/matchings?q=${encodeURIComponent("PTL 102")}&limit=50`);
  const ptl = found.items.find((m) => m.label === "PTL 102 §1")!;
  const primary = ptl.instructors.find((i) => i.role === "PRIMARY") ?? ptl.instructors[0]!;
  ctx.instructorId = primary.id;
  ctx.instructorName = primary.name;
  // a re-run on the same backend: wishes an earlier run left pending for this person are decided first, so the
  // counts and texts below are this run's own
  const left = await api<{ items: { id: number; status: string; instructor: { id: number | null } | null }[] }>("GET", `/terms/${ctx.termId}/moderation/teacher-preferences?status=pending`);
  for (const w of left.items.filter((i) => i.instructor?.id === ctx.instructorId)) {
    await call("POST", `/moderation/preferences/${w.id}/decide`, { decision: "reject", reason: "e2e: an earlier run left it pending", with_submission: true });
  }
  const user = await api<{ id: number }>("POST", "/users", { email: TEACHER.email, username: TEACHER.username, full_name: "Fu Hoca", role: "TEACHER", password: TEACHER.password });
  ctx.userId = user.id;
  await api("PUT", `/auth/sso/admin/users/${ctx.userId}/instructor`, { instructor_id: ctx.instructorId });
  ctx.teacherToken = await loginToken(TEACHER.email, TEACHER.password);
  const mine = await api<{ items: Row[] }>("GET", `/terms/${ctx.termId}/moderation/matchings?limit=500`, undefined, ctx.teacherToken);
  ctx.rows = mine.items;
  ctx.ptl102 = mine.items.find((m) => m.label === "PTL 102 §1")!;
  expect(ctx.ptl102, "the academician sees PTL 102 §1").toBeTruthy();
});

test.afterAll(async () => {
  if (!ctx.api) return;
  if (ctx.activeBefore) {
    await call("PUT", `/terms/${ctx.termId}`, { is_active: false });
    for (const t of ctx.activeBefore.filter((x) => x.is_active)) await call("PUT", `/terms/${t.id}`, { is_active: true });
  }
  if (ctx.userId) {
    await call("PUT", `/auth/sso/admin/users/${ctx.userId}/instructor`, { instructor_id: null });
    await call("DELETE", `/users/${ctx.userId}`);
  }
  await ctx.api.dispose();
});

test("1 · academician: Tercih ekle from the class row, time refused as fixed by the department, room and building sent", async ({ page }) => {
  await login(page, TEACHER.email, TEACHER.password);
  await page.goto("/moderation/me");
  await expect(page.getByTestId("my-requests")).toBeVisible();
  await expect(page.getByTestId("wish-open")).toHaveText(/Tercih ekle/);
  await expect(page.getByTestId("my-wishes-empty")).toBeVisible();

  // the class row opens the sheet with that class preselected
  await page.locator(`[data-testid="mine-table"] [data-row-id="${ctx.ptl102.request_id}"]`).click();
  const sheet = page.getByTestId("wish-sheet");
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole("checkbox", { name: /PTL 102 §1/ })).toBeChecked();

  // a time window on a class whose time the department fixed: warned, and the send is disabled with the reason
  // (T-R1-16: no server call and no submit for a time wish on department-fixed classes)
  await sheet.getByTestId("wish-kind-day_window").click();
  await expect(sheet.getByTestId("wish-fixed")).toContainText("bölüm formu sabitliyor");
  await sheet.getByTestId("wish-latest").selectOption("6");
  await expect(sheet.getByTestId("wish-submit")).toBeDisabled();
  await expect(sheet.getByTestId("wish-blocked")).toContainText("bölüm formu sabitliyor");
  await expect(sheet.getByTestId("wish-error")).toHaveCount(0);

  // a room wish from the picker: the bookable rooms by building, with the capacity
  await sheet.getByTestId("wish-kind-room_preference").click();
  const list = sheet.getByTestId("wish-room-list");
  const rooms = await call<{ items: { id: number; code: string; building: string; capacity: number }[]; count: number }>("GET", "/moderation/me/rooms", undefined, ctx.teacherToken);
  expect(rooms.status).toBe(200);
  const buildings = [...new Set(rooms.body.items.map((r) => r.building))].sort((a, b) => a.localeCompare(b, "tr"));
  await expect(list.getByTestId("wish-room-group")).toHaveCount(buildings.length);
  expect(await list.getByTestId("wish-room-group").evaluateAll((els) => els.map((e) => e.getAttribute("data-building")))).toEqual(buildings);
  await expect(list.getByTestId("wish-room")).toHaveCount(Math.min(80, rooms.body.count));
  const c301 = rooms.body.items.find((r) => r.code.replace(/\s+/g, "") === "C301")!;
  await expect(list.locator('[data-testid="wish-room"][data-code="C301"]')).toContainText(`${c301.capacity} kişilik`);
  // a code typed as people write it picks the listed room
  await sheet.getByTestId("wish-room-search").fill("c301");
  await expect(list.getByTestId("wish-room")).toHaveCount(1);
  await sheet.getByTestId("wish-room-search").press("Enter");
  await expect(sheet.getByTestId("wish-rooms-picked")).toContainText("C 301");
  await expect(sheet.getByRole("checkbox", { name: /C 301/ })).toBeChecked();
  // the summary is the server's own preview (`?dry_run=1`), which stores nothing
  const summary = sheet.getByTestId("wish-summary");
  await expect(summary).toHaveAttribute("data-source", "server");
  await expect(summary.getByTestId("wish-summary-item")).toHaveText("PTL 102 §1: oda tercihi C 301");
  await expect(summary.getByTestId("wish-effective")).toContainText("Koordinatör onaylarsa");
  const stored = await api<{ counts: { pending: number } }>("GET", `/moderation/me/preferences?term_id=${ctx.termId}`, undefined, ctx.teacherToken);
  expect(stored.counts.pending, "a preview stores nothing").toBe(0);
  await sheet.getByTestId("wish-note").fill("Deney düzeneği C blokta");
  await sheet.getByTestId("wish-submit").click();
  await expect(sheet.getByTestId("wish-sent")).toContainText("PTL 102 §1: oda tercihi C 301");
  await expect(sheet).toContainText("Koordinatör onaylarsa bir sonraki çözümde bölüm talebinden sonra gelen bir tercih olarak uygulanır");

  // another one from the same sheet: block C is what the department asked (C 601) → already_requested; A is sent
  await sheet.getByTestId("wish-another").click();
  await sheet.getByTestId("wish-kind-building_preference").click();
  await sheet.getByTestId("wish-building-C").click();
  await expect(sheet.getByTestId("wish-preview-error")).toContainText("Bölüm formu bu dersler için bunu zaten istiyor");
  // T-R1-16: while the preview refuses, the send is disabled with the reason instead of a second refusal
  await expect(sheet.getByTestId("wish-submit")).toBeDisabled();
  await expect(sheet.getByTestId("wish-blocked")).toBeVisible();
  await sheet.getByTestId("wish-building-C").click();
  await sheet.getByTestId("wish-building-input").fill("a");
  await sheet.getByTestId("wish-building-add").click();
  await expect(sheet.getByTestId("wish-summary-item")).toHaveText("PTL 102 §1: A blok tercihi");
  await sheet.getByTestId("wish-submit").click();
  await expect(sheet.getByTestId("wish-sent")).toContainText("A blok tercihi");
  await sheet.getByTestId("wish-done").click();
  await expect(sheet).toBeHidden();

  const cards = page.getByTestId("my-wish");
  await expect(cards).toHaveCount(2);
  await expect(page.getByTestId("my-wishes-counts")).toHaveText("2 bekliyor · 0 kabul · 0 ret");
  await expect(cards.first().getByTestId("wish-status")).toHaveText("Bekliyor");
  await expect(page.locator(`[data-testid="mine-table"] [data-row-id="${ctx.ptl102.request_id}"]`).getByTestId("wish-status")).toHaveText("Bekliyor");
  // the server agrees: two pending, switched off, soft, weight 1, ranked below the department
  const mine = await api<{ counts: Record<string, number>; items: { enabled: boolean; hardness: string; weight: number; rank: string }[] }>("GET", `/moderation/me/preferences?term_id=${ctx.termId}`, undefined, ctx.teacherToken);
  expect(mine.counts.pending).toBe(2);
  expect(mine.items.every((i) => !i.enabled && i.hardness === "soft" && i.weight === 1 && i.rank === "below_department")).toBe(true);
});

test("2 · academician: withdraw a pending wish after a confirmation", async ({ page }) => {
  const other = ctx.rows.find((r) => r.label !== "PTL 102 §1") ?? ctx.ptl102;
  await api("POST", "/moderation/me/preferences", { kind: "room_preference", request_ids: [other.request_id], rooms: ["C 302"] }, ctx.teacherToken);
  await login(page, TEACHER.email, TEACHER.password);
  await page.goto("/moderation/me");
  const card = page.getByTestId("my-wish").filter({ hasText: "C 302" });
  await expect(card).toHaveCount(1);
  await card.getByTestId("wish-withdraw").click();
  const dialog = page.getByTestId("wish-withdraw-dialog");
  await expect(dialog).toContainText("Tercih geri çekilsin mi?");
  await dialog.getByTestId("wish-withdraw-confirm").click();
  await expect(page.getByTestId("my-wish").filter({ hasText: "C 302" })).toHaveCount(0);
  await expect(page.getByTestId("my-wish")).toHaveCount(2);
});

test("3 · coordinator: person badge, accept the room wish (soft rule after the department's room), reject the building wish with a reason", async ({ page }) => {
  await login(page);
  await pinTermCode(page, TERM_CODE); // the spec works on TERM_CODE; the shell would open the current term by date
  await page.goto("/moderation?tab=people");
  // Kişiler searches names (a course code finds nobody there: F-05 S06)
  await page.getByTestId("moderation-search").fill(ctx.instructorName);
  const person = page.getByTestId("people-table").getByTestId("mod-row").filter({ has: page.getByTestId("wish-pending-badge") });
  await expect(person.first().getByTestId("wish-pending-badge")).toHaveText("2 tercih bekliyor");

  // the header link opens Tercihler › Akademisyen tercihleri, pending first
  await page.getByTestId("wishes-pending-link").click();
  await expect(page).toHaveURL(/tab=preferences/);
  const review = page.getByTestId("teacher-wishes");
  await expect(review).toBeVisible();
  await expect(review.getByTestId("wish-filter-pending")).toContainText("2");
  const room = review.getByTestId("wish-card").filter({ hasText: "oda tercihi C 301" });
  await expect(room).toContainText("Bölümün istediği önce: C 601");
  await expect(room).toContainText("Akademisyenin notu: “Deney düzeneği C blokta”");
  await room.getByTestId("wish-accept").click();
  await expect(review.getByTestId("wish-card").filter({ hasText: "oda tercihi C 301" })).toHaveCount(0);

  const building = review.getByTestId("wish-card").filter({ hasText: "A blok tercihi" });
  await building.getByTestId("wish-reject").click();
  const dialog = page.getByTestId("wish-reject-dialog");
  await dialog.getByTestId("wish-reject-confirm").click();
  await expect(dialog).toContainText("Gerekçe en az 3 karakter olmalı.");
  await dialog.getByTestId("wish-reject-code").selectOption("room_unavailable");
  await dialog.getByTestId("wish-reject-reason").fill("A blokta bu saatte uygun laboratuvar yok");
  await dialog.getByTestId("wish-reject-confirm").click();
  await expect(dialog).toBeHidden();
  await expect(review.getByTestId("wish-review-empty")).toContainText("İnceleme bekleyen tercih yok.");

  // decided cards are newest first; an earlier run on the same backend may have left older ones
  await review.getByTestId("wish-filter-accepted").click();
  await expect(review.getByTestId("wish-card").filter({ hasText: "oda tercihi C 301" }).first().getByTestId("wish-soft-rule")).toHaveText("Yumuşak kural · bölüm odasından sonra");
  await review.getByTestId("wish-filter-rejected").click();
  await expect(review.getByTestId("wish-card").filter({ hasText: "A blok tercihi" }).first()).toContainText("Gerekçe: Oda uygun değil: A blokta bu saatte uygun laboratuvar yok");

  // the accepted wish is an enabled TEACHER soft rule of the term (the Tercihler rules list reads /constraints)
  const rules = await api<{ source: string; enabled: boolean; hardness: string; params: { room_ids?: number[] } }[]>("GET", `/constraints?term_id=${ctx.termId}`);
  const teacherRules = rules.filter((r) => r.source === "TEACHER");
  expect(teacherRules.filter((r) => r.enabled).length).toBeGreaterThanOrEqual(1);
  expect(teacherRules.every((r) => r.hardness === "soft")).toBe(true);
});

test("4 · academician: Kabul edildi / Kabul edilmedi with the reason; the notices arrived; Profil › Bildirimler lists the events", async ({ page }) => {
  await login(page, TEACHER.email, TEACHER.password);
  await page.goto("/moderation/me");
  await expect(page.getByTestId("my-wishes-counts")).toHaveText("0 bekliyor · 1 kabul · 1 ret");
  const rejected = page.getByTestId("my-wish").filter({ hasText: "A blok tercihi" });
  await expect(rejected.getByTestId("wish-status")).toHaveText("Kabul edilmedi");
  await expect(rejected.getByTestId("my-wish-reason")).toHaveText("Gerekçe: Oda uygun değil: A blokta bu saatte uygun laboratuvar yok");
  const accepted = page.getByTestId("my-wish").filter({ hasText: "oda tercihi C 301" });
  await expect(accepted.getByTestId("wish-status")).toHaveText("Kabul edildi");
  await expect(accepted).toContainText("bölüm talebinden sonra gelen bir tercih");
  await expect(accepted.getByTestId("wish-withdraw")).toHaveCount(0);

  const notices = await api<{ event?: string; kind?: string; title: string }[]>("GET", "/me/notifications", undefined, ctx.teacherToken);
  const titles = notices.map((n) => n.title).join(" | ");
  expect(titles).toContain("tercihiniz kabul edildi");
  expect(titles).toContain("tercihiniz kabul edilmedi");
  // the preferences matrix reads its events from the API, so the two new events appear without a UI change
  const prefs = await api<{ events: { event: string; label_tr: string }[] }>("GET", "/me/notification-preferences", undefined, ctx.teacherToken);
  expect(prefs.events.map((e) => e.event)).toEqual(expect.arrayContaining(["preference.accepted", "preference.rejected"]));
  await page.goto("/profile#notifications");
  await expect(page.getByText("Ders tercihim kabul edildi", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Ders tercihim kabul edilmedi (gerekçesiyle)", { exact: true }).first()).toBeVisible();
});

test("5 · phone 390: the sheet is a bottom sheet with 44 px targets, the reject dialog too, nothing scrolls sideways", async ({ browser }) => {
  const p = await phone(browser, TEACHER.email, TEACHER.password);
  await p.goto("/moderation/me");
  await expect(p.getByTestId("mine-table")).toBeVisible();
  expect(await noSidewaysScroll(p)).toBe(true);
  await p.getByTestId("mine-table").getByTestId("mod-row").first().click();
  const sheet = p.getByTestId("wish-sheet");
  await expect(sheet).toHaveAttribute("data-variant", "sheet");
  // the room picker is part of what is measured (44 px rows, grouped by building)
  await expect(sheet.getByTestId("wish-room-list")).toBeVisible();
  await p.waitForTimeout(400); // the sheet's enter spring (270 ms) settles before measuring
  const box = (await sheet.boundingBox())!;
  expect(box.width).toBeGreaterThanOrEqual(370);
  expect(box.y + box.height).toBeGreaterThan(800); // anchored to the bottom
  expect(await smallTargets(p, "wish-sheet")).toEqual([]);
  const fontSize = await sheet.getByTestId("wish-room-search").evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  expect(fontSize).toBeGreaterThanOrEqual(16);
  expect(await noSidewaysScroll(p)).toBe(true);
  await p.context().close();

  // the coordinator on a phone: a pending wish, the reject dialog is a bottom sheet
  await api("POST", "/moderation/me/preferences", { kind: "room_preference", request_ids: [ctx.ptl102.request_id], rooms: ["C 302"] }, ctx.teacherToken);
  const a = await phone(browser, ADMIN_EMAIL, ADMIN_PASSWORD);
  await a.goto("/moderation?tab=preferences&view=teacher");
  const card = a.getByTestId("wish-card").filter({ hasText: "C 302" });
  await expect(card).toBeVisible();
  expect(await noSidewaysScroll(a)).toBe(true);
  expect(await smallTargets(a, "teacher-wishes")).toEqual([]);
  await card.getByTestId("wish-reject").click();
  const dialog = a.getByTestId("wish-reject-dialog");
  await expect(dialog).toHaveAttribute("data-variant", "sheet");
  await dialog.getByTestId("wish-reject-reason").fill("C 302 bu saatte sınav salonu");
  await dialog.getByTestId("wish-reject-confirm").click();
  await expect(dialog).toBeHidden();
  await a.context().close();
});

test("6 · users admin: identity chips and the method select filter on the server with its total", async ({ page }) => {
  await login(page);
  await pinTermCode(page, TERM_CODE); // the spec works on TERM_CODE; the shell would open the current term by date
  await page.goto("/admin/users");
  await expect(page.getByTestId("identity-filters")).toBeVisible();
  const asked = (pred: (u: URL) => boolean) => page.waitForRequest((r) => r.url().includes("/api/v1/users/search") && pred(new URL(r.url())));

  let req = asked((u) => u.searchParams.get("identity") === "self_signup");
  await page.getByTestId("filter-self").click();
  expect((await req).url()).toContain("self_signup_days=7");

  req = asked((u) => u.searchParams.get("identity") === "invited");
  await page.getByTestId("filter-invited").click();
  await req;

  req = asked((u) => u.searchParams.get("identity") === "local" && u.searchParams.get("offset") === "0");
  await page.getByTestId("filter-method").selectOption("local");
  await req;
  await expect(page.getByTestId("filter-invited")).toHaveAttribute("aria-pressed", "false");
  const total = (await api<{ total: number }>("GET", "/users/search?identity=local&limit=1")).total;
  expect(total).toBeGreaterThan(0);
  await expect(page.getByTestId("users-table").locator("tbody tr")).toHaveCount(Math.min(total, 25));
});

/** a person's name for this run only (letters, so the server reads it as a person) */
const runName = () => `Defne Kaya${[...STAMP].map((c) => String.fromCharCode(97 + (parseInt(c, 36) % 26))).join("")}`;
const draftPayload = (program: string, prefix: string, course: string, person: string) => ({
  program: { faculty_name: "Fen Bilimleri Enstitüsü", name: program, prefix, level: "masterThesis" },
  courses: [
    {
      key: "c1",
      code: `${prefix} 501`,
      name: course,
      t: 3, u: 0, l: 0, credits: 3, ects: 7, year: 1, mode: "F2F",
      sections: [{ key: "s1", label: "1", enrolment: 20, instructors: [{ name: person }] }],
      pattern: { theory_blocks: [3], days: [3], start: "13.30", weeks: "1-14" },
      room: { capacity: null, tags: [], building: "", preferred: "" },
    },
  ],
  cohorts: [],
  rules: {},
});
interface DraftOut { id: number; validation: { issues: { code: string; level: string; vars: Record<string, unknown> }[] } }

test("7 · program wizard: archived namesake → 'Bu kişiyi kullan', 422 pre-check issues, the commit reopens the record", async ({ page }) => {
  const person = runName();
  const first = await api<DraftOut>("POST", "/program-drafts", { term_id: ctx.termId, payload: draftPayload("Biyoteknoloji Tezli Yüksek Lisans", "BTK", "Biyoteknolojide Yöntemler", person) });
  expect(first.validation.issues.map((i) => i.code)).toContain("instructor_new");
  const made = await api<{ created: { people: number[] } }>("POST", `/program-drafts/${first.id}/commit`, { solve: "none" });
  await api("POST", `/program-drafts/${first.id}/undo`);
  const archivedId = made.created.people[0]!;
  const second = await api<DraftOut>("POST", "/program-drafts", { term_id: ctx.termId, payload: draftPayload("Biyoinformatik Tezli Yüksek Lisans", "BIF", "Biyoinformatiğe Giriş", person) });
  const clash = second.validation.issues.find((i) => i.code === "instructor_archived_namesake");
  expect(clash?.vars.id).toBe(archivedId);
  const pre = await call<{ detail: { message_tr: string; issues: { code: string }[] } }>("POST", `/program-drafts/${second.id}/precheck`);
  expect(pre.status).toBe(422);
  expect(pre.body.detail.issues.map((i) => i.code)).toEqual(["instructor_archived_namesake"]);

  try {
    await login(page);
    await pinTermCode(page, TERM_CODE); // the spec works on TERM_CODE; the shell would open the current term by date
    await page.goto(`/programs/new/${second.id}?step=instructors`);
    const slot = page.locator('[data-path="courses.c1.sections.s1.instructors.0"]');
    await expect(slot.getByTestId("field-issues")).toContainText("arşivlenmiş bir öğretim elemanı var (Biyoteknoloji Tezli Yüksek Lisans)");
    await slot.getByTestId("use-archived-person").click();
    await expect(slot.getByTestId("picked-instructor")).toContainText(person);
    await expect(slot.getByTestId("field-issues")).toContainText("yeniden kullanılacak");
    await expect(slot.getByTestId("use-archived-person")).toHaveCount(0);

    await page.goto(`/programs/new/${second.id}?step=generate`);
    await page.getByTestId("generate-mode-only").check();
    await page.getByTestId("generate-open").click();
    await page.getByTestId("generate-go").click();
    await expect(page.getByTestId("wizard-committed")).toBeVisible();
    await expect(page.getByTestId("done-restored")).toContainText("Yeniden açılan arşiv kayıtları:");
    await expect(page.getByTestId("done-restored")).toContainText("1 kişi");
  } finally {
    await call("POST", `/program-drafts/${second.id}/undo`);
    await call("DELETE", `/program-drafts/${second.id}`);
  }
});
