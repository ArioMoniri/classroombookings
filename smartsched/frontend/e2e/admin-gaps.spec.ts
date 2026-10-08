/**
 * Admin and shell rows of the CRBS UI gap audit (docs/review/2026-10-08-crbs-ui-gap-audit.md) against the REAL
 * backend (no mock API), gated E2E_REAL=1. Each step names the audit item it proves; the parity inventory
 * (smartsched/backend/tests/parity/inventory.py) maps the titles to the S-xx screen rows.
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx playwright test e2e/admin-gaps.spec.ts
 *
 * Everything the steps create carries a per-run stamp and is deleted again (sessions, holiday, room,
 * department, week, translation override); settings the steps change (maintenance mode, LDAP port) are put
 * back in `finally`, so the spec can run repeatedly next to bookings.spec.ts on the same database.
 */
import { expect, test, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";

const STAMP = Date.now().toString(36);
/** this spec's own administrator (English profile language), created through the real API by the seeded admin */
const ME = { username: `e2e.admingaps.${STAMP}`, email: `e2e.admingaps.${STAMP}@uni.edu.tr`, password: "Yonetici-2026!" };
/** the sorting fixtures: a = disabled, no department; b = enabled, with a department */
const SA = `e2e.a.srt${STAMP}`;
const SB = `e2e.b.srt${STAMP}`;
const SESSION = { name: `E2E Yaz ${STAMP}`, code: `E2E-YAZ-${STAMP}`.toUpperCase().slice(0, 32), start: "2026-07-06", end: "2026-08-28" };
const ROOM_NO = 100 + (Date.now() % 900);
const ROOM = { code: `Z ${ROOM_NO}`, canonical: `Z${ROOM_NO}`, name: `E2E Seminer ${STAMP}` };
// 1×1 transparent PNG: a real image the backend's check_image accepts
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");

test.describe.configure({ mode: "serial" });
test.skip(!REAL, SKIP_REASON);

/** Same-origin call through the Next proxy (the httpOnly cookie carries the JWT). */
async function call<T = unknown>(page: Page, method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
  const res = await page.evaluate(
    async ({ url, method, body }) => {
      const r = await fetch(url, { method, headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) }, body: body === undefined ? undefined : JSON.stringify(body) });
      return { status: r.status, body: r.status === 204 ? null : ((await r.json().catch(() => null)) as unknown) };
    },
    { url: `/api/v1${path}`, method, body },
  );
  expect(res.status, `${method} ${path} → ${res.status} ${JSON.stringify(res.body)}`).toBeLessThan(300);
  return res.body as T;
}

let ready = false;
async function signIn(page: Page) {
  const ctx = page.context();
  const english = () => ctx.addCookies([{ name: "NEXT_LOCALE", value: "en", url: test.info().project.use.baseURL ?? "http://127.0.0.1:3100" }]);
  if (!ready) {
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await call(page, "POST", "/users", { username: ME.username, email: ME.email, displayname: "E2E Kurulum Yöneticisi", role: "ADMIN", password: ME.password });
    await ctx.clearCookies();
    await login(page, ME.username, ME.password);
    await call(page, "PUT", "/auth/profile", { language: "en" });
    await ctx.clearCookies();
    ready = true;
  }
  await english();
  await login(page, ME.username, ME.password);
}

async function openPalette(page: Page) {
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByRole("dialog").getByRole("combobox")).toBeVisible();
}

async function openUserMenu(page: Page) {
  await page.getByTestId("user-menu").filter({ visible: true }).first().click();
}

const shots = process.env.E2E_SHOTS_DIR;
async function shot(page: Page, name: string) {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png`, fullPage: false });
}

type Role = { id: number; code: string | null; name: string };
type UserPage = { total: number; items: { id: number; username: string | null }[] };
type SessionRow = { term_id: number; name: string };

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test("admin gaps 1. the user menu and ⌘K open the profile; the menu names the backend version (#1, #24)", async ({ page }) => {
  const health = await call<{ version: string }>(page, "GET", "/health");
  await page.goto("/admin");
  await openUserMenu(page);
  await expect(page.getByTestId("app-version")).toHaveText(`Version ${health.version}`);
  await shot(page, "01-user-menu-profile-version");
  await page.getByTestId("user-menu-profile").click();
  await page.waitForURL("**/profile");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByTestId("admin-version")).toHaveCount(0);

  await page.goto("/admin");
  await expect(page.getByTestId("admin-version")).toHaveText(`Version ${health.version}`);
  await openPalette(page);
  await page.keyboard.type("Profile");
  await page.getByRole("option", { name: /^Profile/ }).click();
  await page.waitForURL("**/profile");
});

test("admin gaps 2. the sidebar Users entry and the old settings tab open /admin/users; sort by enabled and department; the password is asked twice (#8, #22)", async ({ page }) => {
  const roles = await call<Role[]>(page, "GET", "/roles");
  const teacher = roles.find((r) => r.code === "TEACHER") ?? roles[0]!;
  const deps = await call<{ id: number; name: string }[]>(page, "GET", "/departments");
  // a: disabled, no department; b: enabled, with a department
  await call(page, "POST", "/users", { username: SA, email: `${SA}@uni.edu.tr`, displayname: "E2E A", role_id: teacher.id, is_active: false, password: "Parola-2026!" });
  await call(page, "POST", "/users", { username: SB, email: `${SB}@uni.edu.tr`, displayname: "E2E B", role_id: teacher.id, department_id: deps[0]?.id ?? null, password: "Parola-2026!" });

  await page.goto("/bookings");
  await page.getByTestId("nav-admin-users").filter({ visible: true }).first().click();
  await page.waitForURL("**/admin/users");
  await page.goto("/settings?tab=users");
  await page.waitForURL("**/admin/users");

  await page.getByTestId("users-search").fill(`srt${STAMP}`);
  const order = () => page.locator("[data-testid=users-table] tbody tr[data-username]").evaluateAll((rows) => rows.map((r) => r.getAttribute("data-username")));
  await expect.poll(order).toEqual([SA, SB]);
  await page.getByTestId("users-sort").selectOption("-enabled,username");
  await expect.poll(order).toEqual([SB, SA]);
  if (deps[0]) {
    await page.getByTestId("users-sort").selectOption("department,username");
    await expect.poll(order).toEqual([SA, SB]);
  }

  await page.getByTestId("users-new").click();
  const dialog = page.getByTestId("user-dialog");
  await dialog.locator("#u-username").fill(`e2e.c.${STAMP}`);
  await dialog.locator("#u-role").selectOption(`id:${teacher.id}`);
  await dialog.locator("#u-password").fill("Parola-2026!");
  await dialog.getByTestId("user-password-confirm").fill("Parola-2027!");
  await expect(dialog.getByText("The two passwords do not match.").first()).toBeVisible();
  await shot(page, "02-user-password-confirm");
  await dialog.getByTestId("user-save").click();
  await expect(dialog).toBeVisible();
  await dialog.getByTestId("user-password-confirm").fill("Parola-2026!");
  await dialog.getByTestId("user-save").click();
  await expect(dialog).toBeHidden();
  const found = await call<UserPage>(page, "GET", `/users/search?q=e2e.c.${STAMP}`);
  expect(found.items.map((u) => u.username)).toContain(`e2e.c.${STAMP}`);
});

test("admin gaps 3. a session is created and edited in Admin → Sessions (#3)", async ({ page }) => {
  await page.goto("/admin/sessions");
  await page.getByTestId("session-new").click();
  const dialog = page.getByTestId("session-dialog");
  await dialog.getByTestId("session-name").fill(SESSION.name);
  await dialog.getByTestId("session-code").fill(SESSION.code);
  await dialog.getByTestId("session-start").fill(SESSION.start);
  await dialog.getByTestId("session-end").fill(SESSION.end);
  await shot(page, "03-session-create");
  await dialog.getByTestId("session-save").click();
  await expect(dialog).toBeHidden();
  await expect(page.locator("#sess-settings")).toHaveText(SESSION.name);

  await page.getByTestId("session-edit").click();
  await dialog.getByTestId("session-name").fill(`${SESSION.name} (düzenlendi)`);
  await dialog.getByTestId("session-end").fill("2026-08-21");
  await dialog.getByTestId("session-save").click();
  await expect(dialog).toBeHidden();
  await expect(page.locator("#sess-settings")).toHaveText(`${SESSION.name} (düzenlendi)`);
  const terms = await call<{ code: string; name: string; end_date: string }[]>(page, "GET", "/terms");
  const mine = terms.find((x) => x.code === SESSION.code);
  expect(mine?.end_date).toBe("2026-08-21");
  expect(mine?.name).toBe(`${SESSION.name} (düzenlendi)`);
});

test("admin gaps 4. a holiday is edited and shows its duration (#6, #23)", async ({ page }) => {
  await page.goto("/admin/holidays");
  await page.locator("#hol-term").selectOption({ label: `${SESSION.name} (düzenlendi)` });
  await page.locator("#hol-name").fill(`E2E Tatil ${STAMP}`);
  await page.locator("#hol-start").fill("2026-07-15");
  await page.locator("#hol-end").fill("2026-07-15");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const row = page.getByTestId("holiday-list").locator("li", { hasText: `E2E Tatil ${STAMP}` });
  await expect(row.getByTestId("holiday-duration")).toHaveText("1 day");
  await row.getByTestId("holiday-edit").click();
  const dialog = page.getByTestId("holiday-dialog");
  await dialog.getByTestId("holiday-edit-end").fill("2026-07-17");
  await expect(dialog.getByText("3 days")).toBeVisible();
  await dialog.getByTestId("holiday-save").click();
  await expect(dialog).toBeHidden();
  await expect(row.getByTestId("holiday-duration")).toHaveText("3 days");
  await shot(page, "04-holiday-duration");
});

test("admin gaps 5. deleting a session names what goes with it, then deletes it (#3)", async ({ page }) => {
  const sessions = await call<SessionRow[]>(page, "GET", "/booking-admin/sessions");
  const bahar = sessions.find((s) => s.term_id !== undefined && s.name !== `${SESSION.name} (düzenlendi)`)!;
  const usage = await call<{ bookings: number; active_bookings: number; sections: number; runs: number }>(page, "GET", `/terms/${bahar.term_id}/usage`);
  await page.goto("/admin/sessions");
  // a session with timetable data: the counts first, and the confirm stays off until acknowledged (then cancel)
  await page.getByRole("button", { name: new RegExp(`^${bahar.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`) }).first().click();
  await page.getByTestId("session-delete").click();
  const dialog = page.getByTestId("session-delete-dialog");
  await expect(dialog.getByTestId("session-usage-bookings")).toContainText(`${usage.bookings} (${usage.active_bookings} active)`);
  if (usage.bookings + usage.sections + usage.runs > 0) {
    await expect(dialog.getByTestId("session-delete-confirm")).toBeDisabled();
    await expect(dialog.getByTestId("session-delete-ack")).toBeVisible();
  }
  await shot(page, "05-session-delete-counts");
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();

  // the e2e session: one holiday, no bookings
  await page.getByRole("button", { name: new RegExp(`^${SESSION.name}`) }).click();
  await page.getByTestId("session-delete").click();
  await expect(dialog.getByTestId("session-usage-bookings")).toContainText("0 (0 active)");
  await expect(dialog.getByTestId("session-usage")).toContainText("Holidays1");
  await dialog.getByTestId("session-delete-confirm").click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: new RegExp(`^${SESSION.name}`) })).toHaveCount(0);
  const terms = await call<{ code: string }[]>(page, "GET", "/terms");
  expect(terms.some((x) => x.code === SESSION.code)).toBe(false);
});

test("admin gaps 6. ⌘K New room creates a room in Admin → Rooms; photo lightbox, access checker link, delete (#4, #15, #25)", async ({ page }) => {
  await page.goto("/admin");
  await openPalette(page);
  await page.keyboard.type("New room");
  await page.getByRole("option", { name: /New room/ }).click();
  await page.waitForURL(/\/admin\/rooms\?tab=rooms&new=1/);
  const create = page.getByTestId("room-create-dialog");
  await expect(create).toBeVisible();
  await create.getByTestId("room-new-code").fill(ROOM.code);
  await create.getByTestId("room-new-name").fill(ROOM.name);
  await create.getByTestId("room-new-capacity").fill("24");
  const groups = await create.getByTestId("room-new-group").locator("option").count();
  if (groups > 1) await create.getByTestId("room-new-group").selectOption({ index: 1 });
  await shot(page, "06-room-create");
  await create.getByTestId("room-create").click();
  await expect(create).toBeHidden();
  await page.getByRole("searchbox", { name: "Search rooms" }).fill(STAMP);
  await expect(page.getByTestId(`room-edit-${ROOM.canonical}`)).toBeVisible();

  const rooms = await call<{ id: number; code: string }[]>(page, "GET", "/room-admin/rooms");
  const room = rooms.find((r) => r.code === ROOM.canonical)!;
  expect(room).toBeTruthy();

  // photo: upload in the edit sheet, then enlarge it
  await page.getByTestId(`room-edit-${ROOM.canonical}`).click();
  await page.locator('input[type=file][accept^="image/"]').setInputFiles({ name: "seminer.png", mimeType: "image/png", buffer: PNG });
  await page.getByTestId("room-photo-enlarge").click();
  await expect(page.getByTestId("room-photo-lightbox").locator("img")).toBeVisible();
  await shot(page, "06-room-photo-lightbox");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("room-photo-lightbox")).toBeHidden();
  await page.keyboard.press("Escape");

  // access checker for this room
  await page.getByTestId(`room-check-access-${ROOM.canonical}`).click();
  await page.waitForURL(`**/admin/access?room=${room.id}`);
  await expect(page.getByTestId("access-room")).toHaveValue(String(room.id));

  // delete
  await page.goto("/admin/rooms?tab=rooms");
  await page.getByRole("searchbox", { name: "Search rooms" }).fill(STAMP);
  await page.getByTestId(`room-delete-${ROOM.canonical}`).click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.getByTestId(`room-edit-${ROOM.canonical}`)).toHaveCount(0);
  const after = await call<{ code: string }[]>(page, "GET", "/room-admin/rooms");
  expect(after.some((r) => r.code === ROOM.canonical)).toBe(false);
});

test("admin gaps 7. the access checker opens from a user row with ?user= (#15)", async ({ page }) => {
  const found = await call<UserPage>(page, "GET", `/users/search?q=${SB}`);
  const id = found.items[0]!.id;
  await page.goto("/admin/users");
  await page.getByTestId("users-search").fill(SB);
  await page.getByRole("button", { name: `Actions for ${SB}` }).click();
  await page.getByTestId(`user-check-access-${id}`).click();
  await page.waitForURL(`**/admin/access?user=${id}`);
  await expect(page.getByTestId("access-user")).toHaveValue(String(id));
  await page.getByTestId("access-room").selectOption({ index: 1 });
  await expect(page.getByTestId("access-result")).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/admin/access\\?user=${id}&room=\\d+`));
  await shot(page, "07-access-from-user");
});

test("admin gaps 8. the role editor lists the role's users and links to them (#16)", async ({ page }) => {
  const roles = await call<Role[]>(page, "GET", "/roles");
  const teacher = roles.find((r) => r.code === "TEACHER") ?? roles[0]!;
  await page.goto("/admin/roles");
  await page.getByRole("button", { name: new RegExp(`^${teacher.name}`) }).click();
  const box = page.getByTestId("role-users");
  await expect(box).toBeVisible();
  await expect(box.getByRole("heading")).toHaveText(/^Users \(\d+\)$/);
  await shot(page, "08-role-users");
  await box.getByTestId("role-users-all").click();
  await page.waitForURL(`**/admin/users?role=${teacher.id}`);
  await expect(page.getByTestId("users-role-filter")).toHaveValue(String(teacher.id));
  await page.getByTestId("users-search").fill(SB);
  await expect(page.locator(`[data-username="${SB}"]`)).toBeVisible();
});

test("admin gaps 9. a schedule description is saved (#19)", async ({ page }) => {
  await page.goto("/admin/schedules");
  const desc = page.getByTestId("schedule-description");
  if (!(await desc.isVisible().catch(() => false))) {
    await page.getByPlaceholder("New schedule name").fill(`E2E ${STAMP}`.slice(0, 32));
    await page.getByRole("button", { name: "Create schedule" }).click();
  }
  await desc.fill(`E2E açıklama ${STAMP}`);
  await page.getByTestId("schedule-save").click();
  await page.reload();
  await expect(page.getByTestId("schedule-description")).toHaveValue(`E2E açıklama ${STAMP}`);
});

test("admin gaps 10. maintenance mode shows a banner on every page; Admin links the CSV export (#13, #14)", async ({ page }) => {
  try {
    await page.goto("/admin/settings");
    const toggle = page.getByTestId("org-maintenance");
    if ((await toggle.getAttribute("aria-checked")) !== "true") await toggle.click();
    await page.getByRole("textbox", { name: "Maintenance message" }).fill(`E2E bakım ${STAMP}`);
    await page.getByTestId("org-save").click();
    await expect.poll(async () => (await call<{ maintenance_mode: boolean }>(page, "GET", "/org/public")).maintenance_mode).toBe(true);
    for (const path of ["/admin", "/my-bookings", "/profile"]) {
      await page.goto(path);
      await expect(page.getByTestId("shell-maintenance")).toContainText(`E2E bakım ${STAMP}`);
    }
    await shot(page, "10-maintenance-banner");
    await page.goto("/bookings");
    await expect(page.getByTestId("shell-maintenance")).toHaveCount(0);
  } finally {
    await call(page, "PUT", "/org/settings", { maintenance_mode: false });
  }
  await page.goto("/admin");
  await expect(page.getByTestId("shell-maintenance")).toHaveCount(0);
  await page.getByTestId("admin-export").click();
  await page.waitForURL("**/my-bookings#export-title");
  await expect(page.locator("#export-title")).toBeVisible();
});

test("admin gaps 11. departments: create, edit and delete (S-16)", async ({ page }) => {
  const name = `E2E Bölüm ${STAMP}`;
  await page.goto("/admin/departments");
  await page.getByRole("button", { name: "New department" }).click();
  await page.locator("#dep-name").fill(name);
  await page.getByRole("button", { name: "Save" }).click();
  const row = page.getByRole("row", { name: new RegExp(name) });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: `Edit ${name}` }).click();
  await page.locator("#dep-desc").fill("Uçtan uca test");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(row).toContainText("Uçtan uca test");
  await row.getByRole("button", { name: `Delete ${name}` }).click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(row).toHaveCount(0);
});

test("admin gaps 12. timetable weeks: add one with a colour and delete it (S-20)", async ({ page }) => {
  const name = `E2E ${STAMP}`.slice(0, 20);
  await page.goto("/admin/weeks");
  await page.getByPlaceholder("e.g. A Haftası").last().fill(name);
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText(name, { exact: true })).toBeVisible();
  const weeks = await call<{ id: number; name: string; bgcol: string }[]>(page, "GET", "/booking-admin/weeks");
  expect(weeks.find((w) => w.name === name)?.bgcol).toMatch(/^#?[0-9a-fA-F]{6}$/);
  await page.getByRole("button", { name: `Delete ${name}` }).click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.getByText(name, { exact: true })).toHaveCount(0);
});

test("admin gaps 13. organisation settings: a translation override reaches the shell, then is removed (S-21, S-24)", async ({ page }) => {
  const text = `Hesabım ${STAMP}`;
  await page.goto("/admin/settings");
  await expect(page.getByTestId("org-name")).toBeVisible();
  const section = page.locator("section[aria-labelledby=org-tr]");
  await section.getByRole("combobox", { name: "Language" }).selectOption("en");
  await section.getByRole("textbox", { name: "Set" }).fill("crbs");
  await section.getByRole("textbox", { name: "Key" }).fill("nav.profile");
  await section.getByRole("textbox", { name: "Text" }).fill(text);
  await section.getByRole("button", { name: "Add" }).click();
  await expect(section.getByRole("textbox", { name: "crbs.nav.profile" })).toHaveValue(text);
  try {
    await page.reload();
    await openUserMenu(page);
    await expect(page.getByTestId("user-menu-profile")).toHaveText(text);
    await page.keyboard.press("Escape");
  } finally {
    await page.goto("/admin/settings");
    const s2 = page.locator("section[aria-labelledby=org-tr]");
    await s2.getByRole("combobox", { name: "Language" }).selectOption("en");
    await s2.locator("li", { hasText: "crbs.nav.profile" }).getByRole("button", { name: "Delete" }).click();
    await expect(s2.getByRole("textbox", { name: "crbs.nav.profile" })).toHaveCount(0);
  }
});

test("admin gaps 14. LDAP settings save and read back; e-mail settings show the outbox (S-22, S-23)", async ({ page }) => {
  const before = await call<{ port: number | null }>(page, "GET", "/org/auth/ldap");
  try {
    await page.goto("/admin/authentication");
    await page.locator("#ldap-port").fill("3389");
    await page.getByRole("button", { name: "Save" }).first().click();
    await expect.poll(async () => (await call<{ port: number | null }>(page, "GET", "/org/auth/ldap")).port).toBe(3389);
  } finally {
    await call(page, "PUT", "/org/auth/ldap", { port: before.port ?? 389 });
  }
  await page.goto("/admin/email");
  await expect(page.locator("#outbox")).toBeVisible();
  await expect(page.locator("#smtp-host")).toBeVisible();
});
