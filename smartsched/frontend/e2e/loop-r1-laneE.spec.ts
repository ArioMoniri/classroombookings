/**
 * Flow loop round 1, lane E (Turkish/English consistency and admin screens; docs/ROADMAP.md "Flow loop tickets —
 * round 1") against the REAL backend (no mocked API), gated E2E_REAL=1:
 *
 * 1. T-R1-31 (R1-M-17): the webhook URL guard, the Entra tenant "common", a text file named .png as a room photo and
 *    a CSV row whose e-mail exists each read as a Turkish sentence next to the field, never "Value error" or an
 *    English sentence.
 * 2. T-R1-32 (R1-M-18): /admin/audit summaries hold no raw key; the actor filter lists nobody twice.
 * 3. T-R1-33 (R1-M-19/21/38): a CSV with the header "email,full_name,role,password" is read by its names (3 result
 *    rows, a summary line); the limited user-admin sees a reason under every permission they cannot grant; the
 *    filters survive a reload in the address.
 * 4. T-R1-34 (R1-M-20): "T 101" created in A Blok is listed as "T 101 · Test dersliği", its capacity is editable in the
 *    sheet, and the backend puts it in building A.
 * 5. Phone 390 × 844 (touch): /admin/users starts its first user row above 300 px, /admin/audit its first event above
 *    200 px, both without sideways scroll (MOBILE.md M-01); the weekday toggles of /admin/schedules are 44 px apart.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:19230 NEXT_PUBLIC_API_URL=http://127.0.0.1:19230 PW_PORT=19231 \
 *     npx playwright test e2e/loop-r1-laneE.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const STAMP = Date.now().toString(36);
const PASSWORD = "Flow-2026!pw";
const LIMITED = { email: `limited.${STAMP}@smartsched.local` };
const EXISTING = { email: `var.${STAMP}@smartsched.local` };
const ROOM_CODE = `T ${(Date.now() % 900) + 100}`;
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "tr-TR", timezoneId: "Europe/Istanbul" };
const ENGLISH = /Value error|must |not allowed|blocked address|belongs to|webhook URL|the file is/;
const RAW_KEY = /\b[a-z]+[._][a-z_.]+\b/;

test.describe.configure({ mode: "serial", timeout: 180_000 });
test.skip(!REAL, SKIP_REASON);

const ctx = {} as { api: APIRequestContext; token: string; teacherRoleId: number; roomId: number };

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
async function api<T = unknown>(method: "GET" | "POST" | "PUT" | "DELETE", p: string, body?: unknown): Promise<T> {
  const r = await call<T>(method, p, body);
  if (r.status >= 400) throw new Error(`${method} ${p} → ${r.status} ${JSON.stringify(r.body)}`);
  return r.body;
}
async function noSideScroll(page: Page): Promise<void> {
  const m = await page.evaluate(() => ({ sw: document.scrollingElement!.scrollWidth, vw: document.documentElement.clientWidth }));
  expect(m.sw, `scrollWidth ${m.sw} > ${m.vw}`).toBeLessThanOrEqual(m.vw + 1);
}
const roomsTab = (page: Page) => page.goto("/admin/rooms?tab=rooms");

test.beforeAll(async () => {
  ctx.api = await pwRequest.newContext();
  const res = await ctx.api.post(`${API}/auth/login`, { data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD } });
  expect(res.ok(), await res.text()).toBeTruthy();
  ctx.token = ((await res.json()) as { access_token: string }).access_token;
  await api("PUT", "/auth/profile", { language: "tr" });
  const roles = await api<{ id: number; code: string | null; name: string }[]>("GET", "/roles");
  ctx.teacherRoleId = roles.find((r) => r.code === "TEACHER")!.id;
  await api("POST", "/users", { email: EXISTING.email, firstname: "V.", lastname: "A.", role: "TEACHER", password: PASSWORD });
  // F-11 S03: a user-admin role that may read roles but holds no planning or approval permission
  const role = await api<{ id: number }>("POST", "/roles", { name: `Kullanıcı yöneticisi ${STAMP}`, permissions: ["setup.users", "setup.roles", "room.view"] });
  await api("POST", "/users", { email: LIMITED.email, firstname: "L.", lastname: "A.", role_id: role.id, password: PASSWORD });
  // the webhook master switch and a well-formed (fake) Entra configuration, so both forms are on the screen
  await call("PUT", "/calendar/admin/settings", { webhooks_enabled: true });
});

test.afterAll(async () => {
  if (ctx.roomId) await call("DELETE", `/rooms/${ctx.roomId}`);
  await ctx.api.dispose();
});

test("T-R1-31: refusals read in Turkish next to the field, without pydantic's prefix", async ({ page }) => {
  await login(page);
  await page.goto("/settings?tab=integrations");
  await page.getByTestId("webhook-new").click();
  await page.getByTestId("webhook-url").fill("http://127.0.0.1:19102/hook");
  await page.getByTestId("webhook-save").click();
  const we = (await page.getByTestId("webhook-error").textContent())!.trim();
  expect(we).toMatch(/^Bu adres /);
  expect(we).not.toMatch(ENGLISH);
  // the English detail is there for support, folded away
  await expect(page.getByTestId("webhook-error-detail")).toContainText("blocked address");
  await page.keyboard.press("Escape");

  await page.goto("/settings?tab=sso");
  await page.getByTestId("sso-tenant").fill("common");
  await page.getByTestId("sso-save").click();
  const se = (await page.getByTestId("sso-error").textContent())!.trim();
  expect(se).toBe("“common” kullanılamaz: üniversitenin kendi dizin (tenant) kimliğini girin.");

  // the CSV row whose e-mail exists (status word + reason in Turkish)
  await page.goto("/admin/users");
  await page.getByTestId("users-import").click();
  await page.locator("#imp-file").setInputFiles({ name: "users.csv", mimeType: "text/csv", buffer: Buffer.from(`email,full_name,role,password\n${EXISTING.email},V. A.,TEACHER,${PASSWORD}\n`) });
  await page.getByTestId("import-run").click();
  const results = page.getByTestId("import-results");
  await expect(results).toContainText("E-posta var");
  await expect(results).toContainText("Bu e-posta başka bir kullanıcıya ait.");
  expect(await results.innerText()).not.toMatch(ENGLISH);
});

test("T-R1-34 + T-R1-31: a new room keeps its code, its capacity is editable, a wrong photo type is refused in Turkish", async ({ page }) => {
  await login(page);
  await roomsTab(page);
  await page.getByTestId("room-new").click();
  await page.getByTestId("room-new-code").fill(ROOM_CODE);
  await page.getByTestId("room-new-name").fill("Test dersliği");
  await page.getByTestId("room-new-capacity").fill("40");
  await page.getByTestId("room-new-group").selectOption({ label: "A Blok" });
  await page.getByTestId("room-create").click();
  const stored = ROOM_CODE.replace(" ", "");
  const title = page.getByTestId(`room-title-${stored}`);
  await expect(title).toContainText(`${ROOM_CODE} · Test dersliği`);
  const room = (await api<{ id: number; code: string; capacity: number; room_group: string | null; building_code: string | null; code_label: string }[]>("GET", "/room-admin/rooms")).find((r) => r.code === stored)!;
  ctx.roomId = room.id;
  expect(room.room_group).toBe("A Blok");
  expect(room.building_code).toBe("A");
  expect(room.code_label).toBe(ROOM_CODE);

  await page.getByTestId(`room-edit-${stored}`).click();
  await page.getByTestId("room-capacity").fill("42");
  await page.locator('[role="dialog"] input[type="file"]').last().setInputFiles({ name: "foto.png", mimeType: "image/png", buffer: Buffer.from("this is a text file, not a png\n") });
  const pe = (await page.getByTestId("room-photo-error").textContent())!.trim();
  expect(pe).toBe("Dosya bir jpg, png, gif ya da webp görseli değil.");
  await page.getByTestId("room-save").click();
  await expect.poll(async () => (await api<{ capacity: number }>("GET", `/rooms/${room.id}`)).capacity).toBe(42);
  // focus goes back to the row's edit button once the sheet has closed (README §4.7), never to <body>
  await expect.poll(() => page.evaluate(() => document.activeElement?.tagName)).not.toBe("BODY");
});

test("T-R1-33: a CSV header names the columns, the filters live in the address, the limited admin reads why a box is off", async ({ page, browser }) => {
  await login(page);
  await page.goto("/admin/users");
  await page.getByTestId("users-import").click();
  const csv = `email,full_name,role,password\nds.${STAMP}@smartsched.local,D. S.,TEACHER,${PASSWORD}\nnopass.${STAMP}@smartsched.local,N. P.,TEACHER,\n${EXISTING.email},P. T.,TEACHER,${PASSWORD}\n`;
  await page.locator("#imp-file").setInputFiles({ name: "users.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByTestId("import-run").click();
  const results = page.getByTestId("import-results");
  await expect(results.locator("tbody tr")).toHaveCount(3);
  expect(await results.innerText()).not.toContain("full_name");
  await expect(page.getByTestId("import-summary-line")).toHaveText("3 satır: 1 oluşturuldu, 1 parola yok, 1 e-posta var");
  await page.keyboard.press("Escape");

  await page.goto(`/admin/users?role=${ctx.teacherRoleId}&q=ds`);
  await page.reload();
  await expect(page).toHaveURL(new RegExp(`role=${ctx.teacherRoleId}`));
  await expect(page.getByTestId("users-search")).toHaveValue("ds");
  await expect(page.getByTestId("users-role-filter")).toHaveValue(String(ctx.teacherRoleId));

  // the limited user-admin: every permission they lack is a disabled box with a visible reason (F-11 S04)
  const other = await browser.newContext();
  const p2 = await other.newPage();
  await login(p2, LIMITED.email, PASSWORD);
  await expect(p2).toHaveURL(/\/admin\/users/);
  await p2.goto("/admin/roles");
  await p2.getByRole("button", { name: new RegExp(`Kullanıcı yöneticisi ${STAMP}`) }).first().click();
  const editor = p2.getByTestId("role-editor");
  await expect(editor).toBeVisible();
  const n = await editor.evaluate((ed) => ({
    disabled: ed.querySelectorAll('[role="checkbox"][aria-disabled="true"]').length,
    hints: [...ed.querySelectorAll('[data-testid="role-disabled-hint"]')].filter((h) => h.getBoundingClientRect().width > 0).length,
  }));
  expect(n.disabled).toBeGreaterThan(0);
  expect(n.hints).toBeGreaterThanOrEqual(n.disabled);
  await expect(editor.getByTestId("role-disabled-hint").first()).toHaveText("Bu yetki sizde yok");
  await other.close();
});

test("T-R1-32: audit rows are domain sentences and the actor filter lists nobody twice", async ({ page }) => {
  await login(page);
  await page.goto("/admin/audit");
  await expect(page.getByTestId("audit-list")).toBeVisible();
  const summaries = await page.locator('[data-testid^="audit-summary-"]').allTextContents();
  expect(summaries.length).toBeGreaterThan(0);
  expect(summaries.filter((s) => RAW_KEY.test(s))).toEqual([]);
  expect(summaries).toContain("Kullanıcı eklendi");
  const actors = await page.getByTestId("audit-actor").locator("option").allTextContents();
  expect(actors.filter((l, i) => actors.indexOf(l) !== i)).toEqual([]);
  const types = await page.getByTestId("audit-entity").locator("option").allTextContents();
  expect(types.filter((x) => RAW_KEY.test(x))).toEqual([]);
});

test("phone: users and audit start their lists high, no sideways scroll; weekday toggles do not overlap", async ({ browser }) => {
  const context = await browser.newContext(PHONE);
  const page = await context.newPage();
  await login(page);
  await page.goto("/admin/users");
  await expect(page.locator('[data-testid="users-table"] tbody tr').first()).toBeVisible();
  const rowTop = await page.evaluate(() => document.querySelector('[data-testid="users-table"] tbody tr')!.getBoundingClientRect().top);
  expect(rowTop).toBeLessThan(300);
  await noSideScroll(page);
  await page.getByTestId("users-filters-open").tap();
  await expect(page.getByTestId("users-filters-sheet")).toBeVisible();
  await page.keyboard.press("Escape");

  await page.goto("/admin/audit");
  await expect(page.locator('[data-testid^="audit-event-"]').first()).toBeVisible();
  const eventTop = await page.evaluate(() => document.querySelector('[data-testid^="audit-event-"]')!.getBoundingClientRect().top);
  expect(eventTop).toBeLessThan(200);
  await noSideScroll(page);

  await page.goto("/admin/schedules");
  await expect(page.locator('[role="group"] button[aria-pressed]').first()).toBeVisible();
  const boxes = await page.evaluate(() => {
    const g = [...document.querySelectorAll('[role="group"]')].find((x) => x.querySelectorAll("button[aria-pressed]").length >= 7);
    return g ? [...g.querySelectorAll("button[aria-pressed]")].map((b) => { const r = b.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }) : [];
  });
  expect(boxes.length).toBe(7);
  for (const b of boxes) expect(Math.min(b.w, b.h)).toBeGreaterThanOrEqual(44);
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i]!, b = boxes[j]!;
    expect(a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h, `toggles ${i} and ${j} overlap`).toBe(false);
  }
  await context.close();
});
