/**
 * Shared helpers for the real-backend browser specs (smoke, real-backend). One robust login: the inputs
 * are targeted by test id (the password field's label also prefixes the show/hide toggle's accessible
 * name "Show password", so label regexes match two elements).
 */
import path from "node:path";
import { expect, type Page } from "@playwright/test";

export const REAL = process.env.E2E_REAL === "1";
export const SKIP_REASON = "runs against the real backend: start it and set E2E_REAL=1 (see playwright.config.ts)";
export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@smartsched.local";
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "Admin-2026!";
export const TERM_CODE = process.env.E2E_TERM_CODE ?? "2026-BAHAR";
/** set by e2e/global-setup.ts from the backend's runs (imported board, full-term solver run) */
export const boardRun = () => Number(process.env.E2E_BOARD_RUN ?? 1);
export const solverRun = () => Number(process.env.E2E_SOLVER_RUN ?? process.env.E2E_BOARD_RUN ?? 1);
/** the real Bahar 2026 workbooks the e2e backend imported (smartsched/backend/tests/fixtures) */
export const FIXTURES = process.env.E2E_FIXTURES_DIR ?? path.resolve(process.cwd(), "../backend/tests/fixtures");
export const PLANNING_LIST = path.join(FIXTURES, "bahar_derslik_planlama_listesi_v5.xlsx");

/** Sign in through the form; resolves once the app left /login. */
export async function login(page: Page, identifier = ADMIN_EMAIL, password = ADMIN_PASSWORD): Promise<void> {
  await page.goto("/login");
  await page.getByTestId("login-identifier").fill(identifier);
  await page.getByTestId("login-password").fill(password);
  await page.getByTestId("login-submit").click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 30_000 });
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
