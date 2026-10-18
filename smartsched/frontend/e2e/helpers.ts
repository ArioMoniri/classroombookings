/**
 * Shared helpers for the real-backend browser specs (smoke, real-backend). One robust login: the inputs
 * are targeted by test id (the password field's label also prefixes the show/hide toggle's accessible
 * name "Show password", so label regexes match two elements).
 */
import path from "node:path";
import { expect, type Locator, type Page } from "@playwright/test";
import { resolveFixturesDir } from "./fixtures-dir";

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
 * KVKK error (e2e/fixtures-dir.ts) */
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

/** Sign in through the form; resolves once the app left /login. `?method=local` opens the password door when
 *  Microsoft sign-in is on (sign-in.md §4.2) and is harmless when it is off. A privacy notice an earlier spec
 *  published is acknowledged unless `ackNotice: false` (the notice gate's own test). */
export async function login(page: Page, identifier = ADMIN_EMAIL, password = ADMIN_PASSWORD, { ackNotice = true }: { ackNotice?: boolean } = {}): Promise<void> {
  // A page still showing the app after its cookies were cleared answers its next poll with 401 and redirects
  // itself to /login?expired, which aborts our own navigation (net::ERR_ABORTED). Leave the app first.
  if (page.url() !== "about:blank") await page.goto("about:blank");
  await page.goto("/login?method=local");
  await page.getByTestId("login-identifier").fill(identifier);
  await page.getByTestId("login-password").fill(password);
  await page.getByTestId("login-submit").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30_000 });
  if (ackNotice) await ackPrivacyNotice(page);
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
