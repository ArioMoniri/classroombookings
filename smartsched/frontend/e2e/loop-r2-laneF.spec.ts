/**
 * Flow loop round 2, lane F (docs/ROADMAP.md "Flow loop tickets — round 2", lane F): admin screens, the audit
 * undo and the server strings that reached the Turkish admin UI. Runs on the recording stack (stack.sh up, the
 * real workbooks, admin language tr):
 *
 *  1. T-R2-31 (F-02 S10, R2-S-09 / R2-M-11): "Geri al" on a booking's audit row keeps the focus on that row
 *     (motion T4); the undone row and the cancelled booking carry a coded reason rendered "Geri alma: #<id>",
 *     never "undo of #<id>". On a phone "Geri al" is a 44 px button inside the card.
 *  2. T-R2-33 (R2-M-18): a duplicate feature name is a Turkish 409 (API and the dialog); a room photo that is no
 *     image is refused in Turkish with no English tail (API and the sheet); /admin/settings in Turkish shows no
 *     English sentence: the English CHANGELOG sits in a closed <details lang="en">.
 *  3. T-R2-32 (F-11 S04 / S01 / S05, F-05 S00, M-02 / M-07): the limited admin's role editor has a reason under
 *     every disabled box; the user form says a missing role next to the field; a room created as "T 1xx" is
 *     listed as "T 1xx"; re-picking the same instructor writes no audit row; at 390 touch /admin/roles,
 *     /admin/settings, /admin/rooms (rooms + features) and /admin/departments have no control under 44 px from
 *     this lane's components and the departments table is a card list.
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:<api> PW_PORT=<web> npx playwright test loop-r2-laneF
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const PASSWORD = "Flow-2026!pw";
const LIMITED = { email: `limited.f.${STAMP}@smartsched.local` };
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
/** English UI words that must not be on a Turkish admin screen (U-09, M-36); data such as the seeded "Administrator" role name is not a UI word */
const EN_WORDS = /\b(the|and|with|for|not|are|this|that|your|from|users?|roles?|bookings?|permissions?|exists|file|image|saved|error|invalid|please|undo)\b/i;

test.describe.configure({ mode: "serial", timeout: 180_000 });
test.skip(!REAL, SKIP_REASON);

type AuditRow = { id: number; action: string; reason: string | null; undo_of: number | null; entity_id: string | null };
const ctx = {} as { api: APIRequestContext; token: string; limitedRoleId: number; roomId: number; day: string; groupId: number; periodId: number };

async function call<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", p: string, body?: unknown, token = ctx.token): Promise<{ status: number; body: T }> {
  const res = await ctx.api.fetch(`${API}${p}`, { method, data: body, headers: { Authorization: `Bearer ${token}` } });
  const text = await res.text();
  let parsed: unknown;
  try {
    parsed = text ? JSON.parse(text) : undefined;
  } catch {
    parsed = text;
  }
  return { status: res.status(), body: parsed as T };
}
async function api<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", p: string, body?: unknown, token = ctx.token): Promise<T> {
  const r = await call<T>(method, p, body, token);
  if (r.status >= 400) throw new Error(`${method} ${p} → ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}
async function tokenOf(email: string, password: string): Promise<string> {
  const res = await ctx.api.post(`${API}/auth/login`, { data: { email, password } });
  expect(res.ok(), await res.text()).toBeTruthy();
  return ((await res.json()) as { access_token: string }).access_token;
}
async function lastAudit(params: string): Promise<AuditRow | undefined> {
  return (await api<{ items: AuditRow[] }>("GET", `/audit?limit=1&${params}`)).items[0];
}
async function auditCount(action: string): Promise<number> {
  return (await api<{ items: AuditRow[] }>("GET", `/audit?limit=200&action=${action}`)).items.filter((e) => e.action === action).length;
}

/** MOBILE.md M-02 over the whole page (scrolled in 0.8 × viewport steps): visible controls under 44 × 44 without a hit area */
async function m02(page: Page): Promise<{ el: string; w: number; h: number }[]> {
  const out = new Map<string, { el: string; w: number; h: number }>();
  const h = await page.evaluate(() => document.documentElement.clientHeight);
  const total = await page.evaluate(() => document.scrollingElement!.scrollHeight);
  for (let y = 0; y < total + h; y += Math.floor(h * 0.8)) {
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await page.waitForTimeout(150);
    const bad = await page.evaluate(() => {
      const SEL = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=checkbox],[role=radio],[role=switch],[role=menuitem],[role=option],[role=slider],[tabindex]:not([tabindex="-1"])';
      const hits = (el: Element, x: number, y: number) => {
        const t = document.elementFromPoint(x, y);
        return !!t && (t === el || el.contains(t));
      };
      const bad: { el: string; w: number; h: number }[] = [];
      for (const el of document.querySelectorAll<HTMLElement>(SEL)) {
        const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
        if (!r.width || !r.height || cs.visibility === "hidden" || el.closest('[aria-hidden="true"],[inert]')) continue;
        if (el.checkVisibility && !el.checkVisibility()) continue;
        if (r.width <= 1 && r.height <= 1 && el !== document.activeElement) continue;
        if (el.tagName === "A" && cs.display === "inline" && /^(P|LI|TD|SPAN|DD)$/.test(el.parentElement?.tagName ?? "")) continue;
        let w = r.width, h = r.height;
        const lab = (el as HTMLInputElement).labels?.[0];
        if (lab) { const l = lab.getBoundingClientRect(); w = Math.max(w, l.width); h = Math.max(h, l.height); }
        if (w >= 44 && h >= 44) continue;
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
        const VW = document.documentElement.clientWidth, VH = document.documentElement.clientHeight;
        const inView = cy > 22 && cy < VH - 22 && cx > 22 && cx < VW - 22;
        if (!inView) continue; // probed on another scroll step
        if ([[cx - 22, cy], [cx + 21, cy], [cx, cy - 22], [cx, cy + 21]].every(([x, y]) => hits(el, x!, y!))) continue;
        bad.push({ el: (el.dataset.testid || el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40), w: Math.round(w), h: Math.round(h) });
      }
      return bad;
    });
    for (const b of bad) out.set(`${b.el}|${b.w}|${b.h}`, b);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  return [...out.values()];
}
/** the offenders that belong to the shared primitives of lane A's T-R2-05 (Switch 38 wide, tabs 38 tall, toast close): reported in the console, not this lane's */
const PRIMITIVE = /^(.*\|38\|(22|44)|Bildirimi kapat\|.*|.*\|\d+\|38)$/;
const ownOffenders = (list: { el: string; w: number; h: number }[]) => list.filter((b) => !PRIMITIVE.test(`${b.el}|${b.w}|${b.h}`));

async function englishWords(page: Page): Promise<string[]> {
  return page.evaluate((re) => {
    const main = document.querySelector("main") ?? document.body;
    const clone = main.cloneNode(true) as HTMLElement;
    clone.querySelectorAll('[lang="en"], script, style').forEach((n) => n.remove());
    document.body.appendChild(clone);
    const text = clone.innerText;
    clone.remove();
    const rx = new RegExp(re, "gi");
    return [...new Set((text.match(rx) ?? []).map((w) => w.toLowerCase()))];
  }, EN_WORDS.source);
}

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  ctx.token = await tokenOf(ADMIN_EMAIL, ADMIN_PASSWORD);
  await api("PUT", "/auth/profile", { language: "tr" });
  // F-11 S03: a user-admin role that may read roles but holds no planning or approval permission
  const role = await api<{ id: number }>("POST", "/roles", { name: `Kullanıcı yöneticisi F ${STAMP}`, permissions: ["setup.users", "setup.roles", "room.view"] });
  ctx.limitedRoleId = role.id;
  await api("POST", "/users", { email: LIMITED.email, firstname: "L.", lastname: "F.", role_id: role.id, password: PASSWORD });
  // a bookable room of our own in the first group and an open weekday ahead (like loop-r1-laneB)
  let groups = await api<{ id: number }[]>("GET", "/room-admin/groups");
  if (!groups.length) groups = await api("POST", "/room-admin/groups/from-buildings");
  ctx.groupId = groups[0]!.id;
  const no = 100 + (Date.now() % 900);
  const room = await api<{ id: number }>("POST", "/rooms", { code: `LF ${no}`, display_name: `LF ${no}`, capacity: 40 });
  await api("PUT", `/room-admin/rooms/${room.id}`, { room_group_id: ctx.groupId, is_bookable: true });
  ctx.roomId = room.id;
  const dates = await api<{ today: string; dates: { date: string; weekday: number; open: boolean }[] }>("GET", "/bookings/dates");
  const ahead = dates.dates.filter((d) => d.open && d.weekday <= 5 && d.date > dates.today);
  ctx.day = (ahead[2] ?? ahead[0])!.date;
  const grid = await api<{ periods: { id: number; start_period: number }[] }>("GET", `/bookings/grid?display=day&date=${ctx.day}&room_group_id=${ctx.groupId}`);
  ctx.periodId = [...grid.periods].sort((a, b) => a.start_period - b.start_period)[0]!.id;
});

test.afterAll(async () => {
  await call("DELETE", `/rooms/${ctx.roomId}`);
  await ctx.api.dispose();
});

/** books our room on ctx.day at the first free period from `from` on; returns the booking id and its create event */
async function bookAndEvent(): Promise<{ bookingId: number; created: AuditRow }> {
  const grid = await api<{ periods: { id: number; start_period: number }[]; slots: { room_id: number; period_id: number; status: string }[] }>("GET", `/bookings/grid?display=day&date=${ctx.day}&room_group_id=${ctx.groupId}`);
  const free = grid.slots.filter((s) => s.room_id === ctx.roomId && s.status === "available").map((s) => s.period_id);
  expect(free.length, "a free period of our room").toBeGreaterThan(0);
  const b = await api<{ id: number }>("POST", "/bookings", { room_id: ctx.roomId, date: ctx.day, period_id: free[0], notes: `lane F ${STAMP}` });
  const created = await lastAudit(`entity_type=booking&entity_id=${b.id}`);
  expect(created?.action).toBe("booking.create");
  return { bookingId: b.id, created: created! };
}

async function undoFromAudit(page: Page, created: AuditRow, bookingId: number): Promise<void> {
  await page.goto("/admin/audit");
  const row = page.getByTestId(`audit-event-${created.id}`);
  await expect(row).toBeVisible();
  const undo = row.getByTestId(`audit-undo-${created.id}`);
  await undo.click();
  const dialog = page.locator('[role="alertdialog"], [role="dialog"]').last(); // kit's ConfirmDialog is an alertdialog
  await expect(dialog).toContainText("geri alınsın mı?");
  await dialog.getByRole("button", { name: "Geri al" }).click();
  await expect(page.getByText(/1 rezervasyon geri getirildi/)).toBeVisible();
  // motion T4 / U-07: the focus is on the undone row, not <body>
  await expect.poll(() => page.evaluate(() => document.activeElement?.getAttribute("data-audit-id") ?? document.activeElement?.tagName), { timeout: 5_000 }).toBe(String(created.id));
  await expect(row).toContainText("geri alındı");
  await expect(row).not.toContainText(/undo of/i);
  // the undo row (newest booking.cancel) reads "Geri alma: #<id>" and "#<id> geri alındı"
  const undone = await lastAudit(`action=booking.cancel`);
  expect(undone?.undo_of).toBe(created.id);
  expect(undone?.reason).toBe(`undo_of:${created.id}`);
  const undoneRow = page.getByTestId(`audit-event-${undone!.id}`);
  await expect(undoneRow).toContainText(`Geri alma: #${created.id}`);
  await expect(undoneRow).toContainText(`#${created.id} geri alındı`);
  await expect(undoneRow).not.toContainText(/undo of/i);
  const booking = await api<{ status: string; cancel_reason: string | null }>("GET", `/bookings/${bookingId}`);
  expect(booking.status).toBe("CANCELLED");
  expect(booking.cancel_reason).toBe(`undo_of:${created.id}`);
}

test("1a. T-R2-31 desktop: Geri al keeps the focus on the row; no 'undo of' anywhere", async ({ page }) => {
  await login(page);
  const { bookingId, created } = await bookAndEvent();
  await undoFromAudit(page, created, bookingId);
});

test("1b. T-R2-31 phone: a 44 px Geri al inside the card, the focus on the row", async ({ browser }) => {
  const context = await browser.newContext(PHONE);
  const page = await context.newPage();
  await login(page);
  const { bookingId, created } = await bookAndEvent();
  await page.goto("/admin/audit");
  const box = await page.getByTestId(`audit-undo-${created.id}`).boundingBox();
  expect(box, "Geri al visible").not.toBeNull();
  expect(box!.height, `Geri al ${box!.width}×${box!.height}`).toBeGreaterThanOrEqual(44);
  await undoFromAudit(page, created, bookingId);
  await context.close();
});

test("2a. T-R2-33: a duplicate feature name is refused in Turkish (API and dialog)", async ({ page }) => {
  const name = `Projeksiyon ${STAMP}`;
  const f = await api<{ id: number }>("POST", "/room-admin/features", { name, type: "BOOLEAN" });
  const dup = await call<{ detail: { code: string; message: string; message_tr: string } }>("POST", "/room-admin/features", { name: name.toLocaleLowerCase("tr-TR"), type: "BOOLEAN" });
  expect(dup.status).toBe(409);
  expect(dup.body.detail.code).toBe("name_taken");
  expect(dup.body.detail.message_tr).toBe(`Bu adda bir özellik zaten var: ${name.toLocaleLowerCase("tr-TR")}`);
  await login(page);
  await page.goto("/admin/rooms?tab=features");
  await page.getByTestId("feature-new").click();
  await page.getByTestId("feature-name").fill(name);
  await page.getByTestId("feature-save").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Bu adda bir özellik zaten var");
  await expect(dialog).not.toContainText(/exists|a feature named/i);
  await page.keyboard.press("Escape");
  await call("DELETE", `/room-admin/features/${f.id}`);
});

test("2b. T-R2-33: a non-image room photo is refused in Turkish with no English tail (API and sheet)", async ({ page }) => {
  const res = await ctx.api.post(`${API}/room-admin/rooms/${ctx.roomId}/photo`, {
    headers: { Authorization: `Bearer ${ctx.token}` },
    multipart: { file: { name: "foto.png", mimeType: "image/png", buffer: Buffer.from("\x89PNG\r\n\x1a\n" + "\0".repeat(64), "binary") } },
  });
  expect(res.status()).toBe(400);
  const detail = ((await res.json()) as { detail: { code: string; message_tr: string; message: string } }).detail;
  expect(detail.code).toBe("image_unreadable");
  expect(detail.message_tr).toBe("Dosya okunabilir bir jpg, png ya da gif görseli değil.");
  expect(detail.message_tr).not.toMatch(/the file|readable/i);
  await login(page);
  await page.goto("/admin/rooms?tab=rooms");
  const rooms = await api<{ id: number; code: string }[]>("GET", "/room-admin/rooms");
  const code = rooms.find((r) => r.id === ctx.roomId)!.code;
  await page.getByTestId(`room-edit-${code}`).click();
  const sheet = page.getByRole("dialog");
  await sheet.locator('input[type="file"]').setInputFiles({ name: "foto.png", mimeType: "image/png", buffer: Buffer.from("\x89PNG\r\n\x1a\n" + "\0".repeat(64), "binary") });
  const err = sheet.getByTestId("room-photo-error");
  await expect(err).toBeVisible();
  await expect(err).toHaveText("Dosya okunabilir bir jpg, png ya da gif görseli değil.");
  await page.keyboard.press("Escape");
});

test("2c. T-R2-33: /admin/settings in Turkish shows no English sentence; the changelog is a closed English detail", async ({ page }) => {
  await login(page);
  await page.goto("/admin/settings");
  await expect(page.getByTestId("news-english")).toBeVisible();
  expect(await page.getByTestId("news-english").evaluate((d) => (d as HTMLDetailsElement).open)).toBe(false);
  await expect(page.getByTestId("news-english").locator('[lang="en"]')).toBeHidden(); // the English list is not rendered until asked
  const words = await englishWords(page);
  expect(words, `English UI words on /admin/settings: ${words.join(", ")}`).toEqual([]);
  // opened on request, the English list is marked as English
  await page.getByTestId("news-english").locator("summary").click();
  await expect(page.getByTestId("news-english").locator('[lang="en"]')).toBeVisible();
});

test("3a. T-R2-32 F-11 S04: the limited admin sees a reason under every disabled permission", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, LIMITED.email, PASSWORD);
  await page.goto("/admin/roles");
  await page.getByRole("button", { name: `Kullanıcı yöneticisi F ${STAMP}` }).click();
  const editor = page.getByTestId("role-editor");
  await expect(editor).toBeVisible();
  const counts = await editor.evaluate((ed) => ({
    disabled: [...ed.querySelectorAll('[role="checkbox"]')].filter((c) => c.hasAttribute("disabled") || c.getAttribute("aria-disabled") === "true").length,
    hints: [...ed.querySelectorAll('[data-testid="role-disabled-hint"]')].filter((h) => h.getBoundingClientRect().width > 0).length,
    texts: [...new Set([...ed.querySelectorAll('[data-testid="role-disabled-hint"]')].map((h) => h.textContent?.trim()))],
  }));
  expect(counts.disabled).toBeGreaterThan(0);
  expect(counts.hints, JSON.stringify(counts)).toBeGreaterThanOrEqual(counts.disabled);
  expect(counts.texts).toContain("Bu yetki sizde yok");
  await context.close();
});

test("3b. T-R2-32 F-11 S01: a missing role is said next to the field, read with it", async ({ page }) => {
  await login(page);
  await page.goto("/admin/users");
  await page.getByTestId("users-new").click();
  const dialog = page.getByTestId("user-dialog");
  await dialog.locator("#u-email").fill(`rolsuz.${STAMP}@smartsched.local`);
  await dialog.getByTestId("user-save").click();
  const err = dialog.getByTestId("role-error");
  await expect(err).toHaveText("Bir rol seçin.");
  await expect(dialog.locator("#u-role")).toHaveAttribute("aria-invalid", "true");
  expect((await dialog.locator("#u-role").getAttribute("aria-describedby")) ?? "").toContain("u-role-error");
  expect(await page.evaluate(() => document.activeElement?.id)).toBe("u-role");
  await dialog.locator("#u-role").selectOption({ index: 1 });
  await expect(err).toBeHidden();
  await page.keyboard.press("Escape");
});

test("3c. T-R2-32 F-11 S05 + F-05 S00: 'T 1xx' is listed as 'T 1xx'; the same instructor again writes no audit row", async ({ page }) => {
  const no = 100 + ((Date.now() + 7) % 900);
  const room = await api<{ id: number; code: string }>("POST", "/rooms", { code: `T ${no}`, display_name: `Test dersliği ${STAMP}`, capacity: 40 });
  await login(page);
  await page.goto("/admin/rooms?tab=rooms");
  const title = page.getByTestId(`room-title-${room.code}`);
  await expect(title).toBeVisible();
  await expect(title).toContainText(`T ${no} · Test dersliği ${STAMP}`);
  await expect(page.locator("main")).not.toContainText(new RegExp(`\\bT${no}\\b`));
  await call("DELETE", `/rooms/${room.id}`);
  // F-05 S00: the seeded teacher is linked to the first instructor; linking again is not a change
  const users = await api<{ id: number; email: string | null }[]>("GET", "/users");
  const teacher = users.find((u) => u.email === "ogretmen@smartsched.local") ?? users.find((u) => u.email !== ADMIN_EMAIL);
  expect(teacher, "a user to link").toBeTruthy();
  const inst = (await api<{ items: { id: number }[] }>("GET", "/instructors?limit=5")).items;
  test.skip(!inst.length, "no instructor rows on this stack");
  const url = `/auth/sso/admin/users/${teacher!.id}/instructor`;
  const before = await auditCount("user.instructor_link");
  const first = await call<{ instructor_id: number }>("PUT", url, { instructor_id: inst[0]!.id });
  test.skip(first.status === 409, "that instructor is linked to another login on this stack");
  expect(first.status).toBe(200);
  const afterFirst = await auditCount("user.instructor_link");
  const again = await call<{ instructor_id: number }>("PUT", url, { instructor_id: inst[0]!.id });
  expect(again.status).toBe(200);
  expect(await auditCount("user.instructor_link")).toBe(afterFirst);
  expect(afterFirst).toBeGreaterThanOrEqual(before);
});

test("3d. T-R2-32 phone: M-02 on the admin routes, M-07 cards on /admin/departments", async ({ browser }) => {
  const context = await browser.newContext(PHONE);
  const page = await context.newPage();
  await login(page);
  const report: Record<string, { el: string; w: number; h: number }[]> = {};
  // roles: the editor of our role open (35 permission boxes)
  await page.goto("/admin/roles");
  await page.getByTestId("roles-picker").selectOption(String(ctx.limitedRoleId)); // phones: the role list is a native select
  await expect(page.getByTestId("role-editor")).toBeVisible();
  report["/admin/roles(editor)"] = await m02(page);
  await page.goto("/admin/settings");
  await expect(page.getByTestId("org-languages")).toBeVisible();
  report["/admin/settings"] = await m02(page);
  await page.goto("/admin/rooms?tab=rooms");
  await expect(page.getByTestId("room-new")).toBeVisible();
  report["/admin/rooms(rooms)"] = await m02(page);
  await page.goto("/admin/rooms?tab=features");
  await expect(page.getByTestId("features-tab")).toBeVisible();
  report["/admin/rooms(features)"] = await m02(page);
  await page.goto("/admin/departments");
  await expect(page.getByTestId("departments-cards")).toBeVisible();
  expect(await page.locator("table").count()).toBe(0);
  report["/admin/departments"] = await m02(page);
  console.log("M-02 phone report:", JSON.stringify(report));
  for (const [route, list] of Object.entries(report)) {
    expect(ownOffenders(list), `${route}: ${JSON.stringify(list)}`).toEqual([]);
  }
  await context.close();
});
