/**
 * Shared helpers for the real-backend browser specs (smoke, real-backend). One robust login: the inputs
 * are targeted by test id (the password field's label also prefixes the show/hide toggle's accessible
 * name "Show password", so label regexes match two elements).
 */
import path from "node:path";
import { expect, request as pwRequest, test, type Locator, type Page } from "@playwright/test";
import { resolveFixturesDir } from "../src/test/fixtures-dir";

export const REAL = process.env.E2E_REAL === "1";
export const SKIP_REASON = "runs against the real backend: start it and set E2E_REAL=1 (see playwright.config.ts)";
export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@smartsched.local";
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "Admin-2026!";
export const TERM_CODE = process.env.E2E_TERM_CODE ?? "2026-BAHAR";
/** set by e2e/global-setup.ts from the backend's runs (imported board, full-term solver run) */
export const boardRun = () => Number(process.env.E2E_BOARD_RUN ?? 1);
export const solverRun = () => Number(process.env.E2E_SOLVER_RUN ?? process.env.E2E_BOARD_RUN ?? 1);
/** the Bahar 2026 workbooks the e2e backend imported: the raw smartsched/backend/tests/fixtures on pod CI and a plain
 * local backend; on a recording stack the masked copies (E2E_FIXTURES_DIR / $REC_WORKDIR/fixtures), else a clear
 * KVKK error (src/test/fixtures-dir.ts) */
export const FIXTURES = resolveFixturesDir(process.env, path.resolve(process.cwd(), "../backend/tests/fixtures"));
export const PLANNING_LIST = path.join(FIXTURES, "bahar_derslik_planlama_listesi_v5.xlsx");

/**
 * A published privacy notice (A4 KVKK, wave2.spec.ts 4) can never be retired, and until a user reads it a blocking
 * sheet covers the app on their first page. Specs that are not about the notice acknowledge it for their test users
 * through the API (`POST /me/privacy/ack`), the same request the sheet's "Okudum" sends, and reload so the shell
 * reads the acknowledgement. Returns whether there was one to acknowledge.
 */
export async function ackPrivacyNotice(page: Page): Promise<boolean> {
  const acked = await page.evaluate(async () => {
    const r = await fetch("/api/v1/me/privacy", { headers: { Accept: "application/json" } });
    if (!r.ok) return false;
    const me = (await r.json()) as { needs_ack?: boolean; notice?: { id: number } | null };
    if (!me.needs_ack || !me.notice) return false;
    const a = await fetch("/api/v1/me/privacy/ack", { method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json" }, body: JSON.stringify({ notice_id: me.notice.id }) });
    return a.ok;
  });
  if (acked) await page.reload();
  return acked;
}

/**
 * Make `termId` the working term of the signed-in user (the current page is reloaded to pick it up).
 * The shell's term is the user's workspace memory (`smartsched.workspace`, keyed by user id; AppShell copies it into
 * `smartsched.ui` once /auth/me answers, and falls back to the current term by date when there is none), so writing
 * `smartsched.ui` alone is overwritten on load. `forget` also drops the user's remembered runs and weeks.
 */
export async function pinTerm(page: Page, termId: number, { forget = false }: { forget?: boolean } = {}): Promise<void> {
  await page.evaluate(
    async ({ id, forget }) => {
      const me = (await (await fetch("/api/v1/auth/me", { headers: { Accept: "application/json" } })).json()) as { id: number };
      const ui = JSON.parse(localStorage.getItem("smartsched.ui") ?? "{}") as { state?: Record<string, unknown> };
      localStorage.setItem("smartsched.ui", JSON.stringify({ ...ui, state: { ...(ui.state ?? {}), termId: id } }));
      const ws = JSON.parse(localStorage.getItem("smartsched.workspace") ?? "{}") as { state?: { users?: Record<string, Record<string, unknown>> }; version?: number };
      const users = { ...(ws.state?.users ?? {}) };
      users[String(me.id)] = { ...(forget ? {} : (users[String(me.id)] ?? {})), termId: id };
      localStorage.setItem("smartsched.workspace", JSON.stringify({ ...ws, state: { ...(ws.state ?? {}), users }, version: ws.version ?? 1 }));
    },
    { id: termId, forget },
  );
  // the running shell keeps its term in memory: load the page again so it reads the pinned one
  await page.reload();
}

/** `pinTerm` by term code (GET /terms through the proxy); returns the term id. */
export async function pinTermCode(page: Page, code: string, opts: { forget?: boolean } = {}): Promise<number> {
  const terms = await api<{ id: number; code: string }[]>(page, "/terms");
  const term = terms.find((t) => t.code === code);
  expect(term, `term ${code} is on this backend`).toBeTruthy();
  await pinTerm(page, term!.id, opts);
  return term!.id;
}

/**
 * A new account meets the first-sign-in welcome sheet (a modal, welcome-guide.md) on its first home or /admin/* page,
 * opened a moment after the page settles, so it races whatever the spec clicks next. Specs that are not about the
 * guide close it for good through the API, the event the sheet's own "never" action sends, and reload so the shell
 * reads that; the welcome-guide specs keep it (`login(..., { welcome: true })`). Returns whether it was due.
 */
export async function dismissWelcomeSheet(page: Page): Promise<boolean> {
  const due = await page.evaluate(async () => {
    const r = await fetch(`/api/v1/welcome?first_route=${encodeURIComponent(location.pathname)}`, { headers: { Accept: "application/json" } });
    if (!r.ok) return false;
    const w = (await r.json()) as { show?: { kind?: string } | null };
    if (w.show?.kind !== "sheet" && w.show?.kind !== "delta") return false;
    const e = await fetch("/api/v1/welcome/events", { method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json" }, body: JSON.stringify({ guide_key: "sheet", event: "dismissed" }) });
    return e.ok;
  });
  if (due) await page.reload();
  return due;
}

/**
 * The client address a sign-in comes from: one per person and test, inside 127.0.0.0/24 (127.0.0.2 to
 * .254; only 127.0.0.1 is a trusted proxy hop). In the e2e stack every browser reaches the backend through the
 * Next.js handler on one host, so a whole school's sign-ins shared 127.0.0.1 and the backend's per-address sign-in
 * throttle (security_http.py: 60 POST /auth/login per address in 300 s) refused the admin on a fast host (pod e2e
 * #141: laneE/laneF, visual-quality, "Çok fazla deneme"). The throttle and its caps stay as shipped; each simulated
 * person gets a machine of their own, as a real one would have. The /24 is the one every e2e request came from
 * before, so the network the backend remembers for devices and audit (hash of the /24, audit.hash_ip) is unchanged:
 * no new-device mails or notifications. Per test, not per file: one address per person and file still put
 * visual-quality's 54 admin sign-ins on one address. The handler forwards `x-forwarded-for` and the backend believes it because
 * the hop is loopback (no nginx in the e2e stack; in production nginx appends the real peer, so a browser cannot
 * choose its address there). The throttle tests (loop-r1-laneA T-R1-09, the backend unit tests) do not use this.
 */
const reporting = new WeakSet<Page>();

export function clientAddressFor(identifier: string): string {
  let where = "";
  try {
    where = test.info().testId; // a test (or a hook of its file) is its own machine
  } catch {
    // outside a test (global setup): the person alone
  }
  let h = 0x811c9dc5;
  for (const ch of `${where}|${identifier.trim().toLowerCase()}`) h = Math.imul(h ^ ch.charCodeAt(0), 0x01000193) >>> 0;
  return `127.0.0.${(h % 253) + 2}`;
}

/** Sign in through the form; resolves once the app left /login. `?method=local` opens the password door when
 *  Microsoft sign-in is on (sign-in.md §4.2) and is harmless when it is off. A privacy notice an earlier spec
 *  published is acknowledged unless `ackNotice: false` (the notice gate's own test); the first-sign-in welcome sheet
 *  is closed for good unless `welcome: true` (the welcome-guide specs). */
export async function login(page: Page, identifier = ADMIN_EMAIL, password = ADMIN_PASSWORD, { ackNotice = true, welcome = false }: { ackNotice?: boolean; welcome?: boolean } = {}): Promise<void> {
  // A page still showing the app after its cookies were cleared answers its next poll with 401 and redirects
  // itself to /login?expired, which aborts our own navigation (net::ERR_ABORTED). Leave the app first.
  if (page.url() !== "about:blank") await page.goto("about:blank");
  await page.context().setExtraHTTPHeaders({ "x-forwarded-for": clientAddressFor(identifier) });
  // an uncaught error in the app is printed with the test's output (the pod keeps only the logs: run #141's Studio
  // scope sentence vanished with no trace of why)
  if (!reporting.has(page)) {
    reporting.add(page);
    page.on("pageerror", (e) => console.log(`[pageerror] ${page.url()} ${e.message}`));
  }
  await page.goto("/login?method=local");
  // the fields are controlled inputs: text typed into the server-rendered form before React hydrated it is dropped
  // on a slow host (the form then answers "identifier required"), so wait until React owns the form
  await page.waitForFunction(() => {
    const el = document.querySelector('[data-testid="login-submit"]');
    return !!el && Object.keys(el).some((k) => k.startsWith("__reactProps$"));
  }, undefined, { timeout: 30_000 });
  const submit = async () => {
    await page.getByTestId("login-identifier").fill(identifier);
    await page.getByTestId("login-password").fill(password);
    await page.getByTestId("login-submit").click();
  };
  await submit();
  // left /login, or the form answered. A "… gerekli" after both fields were filled means the form threw the typed
  // values away (a hydration reset: an app bug, not something to type again); a refusal (wrong password, a 429 lock
  // with its minutes, offline) fails with the form's own sentence instead of a bare timeout
  const away = () => !new URL(page.url()).pathname.startsWith("/login");
  const required = page.locator('[data-testid="login-identifier-required"], [data-testid="login-password-required"]');
  for (const until = Date.now() + 30_000; !away(); ) {
    if (Date.now() > until) throw new Error(`login as ${identifier} did not leave ${new URL(page.url()).pathname} in 30 s`);
    if (await required.count()) throw new Error(`login form dropped typed ${identifier}: hydration reset`);
    if (await page.getByTestId("login-error").count()) {
      await page.waitForTimeout(1_000); // a refusal stays; a late redirect does not
      if (!away() && (await page.getByTestId("login-error").count())) throw new Error(`login as ${identifier} refused: ${(await page.getByTestId("login-error").innerText().catch(() => "")).trim()}`);
    }
    await page.waitForTimeout(100);
  }
  await page.waitForLoadState("domcontentloaded");
  if (ackNotice) await ackPrivacyNotice(page);
  if (!welcome) await dismissWelcomeSheet(page);
}

/** Same-origin GET through the Next proxy (the httpOnly cookie carries the JWT). */
export async function api<T>(page: Page, path: string): Promise<T> {
  const res = await page.evaluate(async (url) => {
    const r = await fetch(url, { headers: { Accept: "application/json" } });
    return { status: r.status, body: (await r.json().catch(() => null)) as unknown };
  }, `/api/v1${path}`);
  expect(res.status, `GET ${path} → ${res.status}`).toBe(200);
  return res.body as T;
}

/** Dashboard tiles animate to the value: plain (1271) or tr-TR grouped (1.271). */
export const numberText = (n: number) => new RegExp(`^(${n}|${new Intl.NumberFormat("tr-TR").format(n).replace(/\./g, "\\.")})$`);

export type Term = { id: number; code: string };
export type Run = { id: number; status: string; kind: string; horizon: string; term_code: string | null };
export const FINISHED = /^(FEASIBLE|OPTIMAL|FEASIBLE_PARTIAL|INFEASIBLE|TIMEOUT|FAILED|ERROR|CANCELLED)$/;

/**
 * Pick a segment of the design system's SegmentedControl: the tab / radio when the track is shown, else the
 * select it collapses into when its container is narrower than its natural width (sheets, phones).
 */
export async function pickSegment(page: Page, name: string, scope: Page | Locator = page): Promise<void> {
  const seg = scope.getByRole("tab", { name, exact: true }).or(scope.getByRole("radio", { name, exact: true })).first();
  if (await seg.isVisible().catch(() => false)) {
    await seg.click();
    return;
  }
  const select = scope.locator("select").filter({ has: page.locator("option", { hasText: name }) }).first();
  await select.selectOption({ label: name });
}

/**
 * The same, by the segment's test id and value: the SegmentedControl keeps its track (with the per-segment test
 * ids) in the DOM when it collapses into a select, so the select is found next to that segment.
 */
export async function pickSegmentById(scope: Page | Locator, testId: string, value: string, timeout = 10_000): Promise<void> {
  const seg = scope.getByTestId(testId);
  const select = scope.locator("[data-slot=segmented-control]").filter({ has: seg }).locator("select");
  await expect(seg.or(select).filter({ visible: true }).first()).toBeVisible({ timeout });
  if (await seg.isVisible()) await seg.click();
  else await select.selectOption(value);
}

/**
 * Type a date into the design system's DateField (a localised text field, 2026-10-16) and leave the field: it
 * commits the typed text on blur or Enter, as a person tabbing on to the next field does. ISO input
 * (YYYY-MM-DD) parses in every locale.
 */
export async function fillDate(field: Locator, iso: string): Promise<void> {
  await field.fill(iso);
  await field.press("Tab");
}

/** The backend's API base for Node-side calls (global-setup.ts uses the same). */
export const API_BASE = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";

/**
 * The booking setup CRBS's installer would make, idempotent (what bookings.spec.ts and reserve.spec.ts build in their
 * beforeAll): TERM_CODE's imported board is the published timetable, a schedule with the university's 18 periods on
 * weekdays is the term's default and the term is bookable, and the rooms have groups (one per building). The e2e gate
 * runs the specs in shards, each on a fresh seed, so a spec that books must not rely on an earlier spec having done
 * this. Returns the term id, the schedule and its periods by name.
 */
export async function ensureBookingSetup(): Promise<{ termId: number; scheduleId: number; periods: Record<string, number> }> {
  const ctx = await pwRequest.newContext();
  try {
    const login = await ctx.post(`${API_BASE}/auth/login`, { data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD }, headers: { "x-forwarded-for": clientAddressFor(`api|${ADMIN_EMAIL}`) } });
    expect(login.ok(), `admin login ${login.status()}`).toBeTruthy();
    const headers = { Authorization: `Bearer ${((await login.json()) as { access_token: string }).access_token}` };
    const call = async <T>(method: "GET" | "POST" | "PUT", p: string, data?: unknown): Promise<T> => {
      const r = await ctx.fetch(`${API_BASE}${p}`, { method, headers, data });
      const text = await r.text();
      expect(r.status(), `${method} ${p} → ${r.status()} ${text.slice(0, 300)}`).toBeLessThan(300);
      return (text ? JSON.parse(text) : null) as T;
    };
    const terms = await call<{ id: number; code: string }[]>("GET", "/terms");
    const termId = terms.find((x) => x.code === TERM_CODE)!.id;
    const runs = await call<{ id: number; kind: string; term_id: number; label: string | null; is_active: boolean }[]>("GET", "/runs");
    const board = runs.find((r) => r.term_id === termId && r.kind === "COURSE" && (r.label ?? "").startsWith("Grid import"));
    if (board && !runs.some((r) => r.term_id === termId && r.kind === "COURSE" && r.is_active)) await call("POST", `/runs/${board.id}/activate`);
    let schedules = await call<{ id: number; periods: { id: number; name: string }[] }[]>("GET", "/booking-admin/schedules");
    let schedule = schedules.find((x) => x.periods.length >= 18);
    if (!schedule) {
      const made = await call<{ id: number }>("POST", "/booking-admin/schedules", { name: `Ders saatleri ${Date.now().toString(36)}`.slice(0, 32) });
      await call("POST", `/booking-admin/schedules/${made.id}/periods/from-grid?days=1,2,3,4,5`);
      schedules = await call("GET", "/booking-admin/schedules");
      schedule = schedules.find((x) => x.id === made.id)!;
    }
    const sessions = await call<{ term_id: number; default_schedule_id: number | null; is_selectable: boolean }[]>("GET", "/booking-admin/sessions");
    const sess = sessions.find((x) => x.term_id === termId);
    expect(sess, `booking session for ${TERM_CODE}`).toBeTruthy();
    // the default schedule is what the grid shows: keep it when it has the 18 periods, else make the full one default
    const current = schedules.find((x) => x.id === sess!.default_schedule_id);
    const used = current && current.periods.length >= 18 ? current : schedule;
    if (!sess!.is_selectable || sess!.default_schedule_id !== used.id) await call("PUT", `/booking-admin/sessions/${termId}`, { is_selectable: true, default_schedule_id: used.id });
    const groups = await call<{ id: number }[]>("GET", "/room-admin/groups");
    if (!groups.length) await call("POST", "/room-admin/groups/from-buildings");
    return { termId, scheduleId: used.id, periods: Object.fromEntries(used.periods.map((x) => [x.name, x.id])) };
  } finally {
    await ctx.dispose();
  }
}
