/**
 * The 13 classroombookings languages plus Turkish (ROADMAP P18-LANG) against the REAL backend, gated E2E_REAL=1.
 *
 * The administrator enables German and French (CRBS setup/Language), switches the interface language in the
 * picker and the bookings grid header shows the CRBS day and month names (`calendar_lang.php`, imported by
 * smartsched/backend/tools/crbs_lang_import.py); strings CRBS does not translate stay English. The org settings
 * the spec changes (languages, weekday pattern) are restored afterwards.
 *
 * The grid needs the booking setup bookings.spec.ts makes idempotently (bookable Bahar 2026 term, schedule,
 * room groups) and the booking clock inside the term; Playwright runs the specs in file order with one worker,
 * so bookings.spec.ts has run first.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:8400 PW_PORT=3800 npx playwright test e2e/languages.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";
const MONDAY = "2026-02-16";

test.describe.configure({ mode: "serial" });
test.skip(!REAL, SKIP_REASON);

type OrgSettings = { languages: string[]; default_language: string; pattern_weekday: string | null };
let api: APIRequestContext;
let token = "";
let saved: OrgSettings | null = null;

async function call<T>(method: "GET" | "PUT", path: string, body?: unknown): Promise<T> {
  const res = await api.fetch(`${API}${path}`, { method, data: body, headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok()) throw new Error(`${method} ${path} → ${res.status()} ${await res.text()}`);
  return (await res.json()) as T;
}

test.beforeAll(async () => {
  api = await pwRequest.newContext();
  const res = await api.post(`${API}/auth/login`, { data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD } });
  expect(res.ok(), await res.text()).toBeTruthy();
  token = ((await res.json()) as { access_token: string }).access_token;
  const dates = await call<{ today: string }>("GET", "/bookings/dates");
  test.skip(dates.today < "2026-02-02" || dates.today > "2026-06-28", `the backend's booking clock (${dates.today}) must be inside Bahar 2026`);
  const org = await call<OrgSettings>("GET", "/org/settings");
  saved = { languages: org.languages, default_language: org.default_language, pattern_weekday: org.pattern_weekday ?? "" };
  // CRBS setup/Language: enable German and French next to the current ones; a weekday pattern with names so
  // the grid header shows CRBS's day and month names whatever the organisation chose before
  await call("PUT", "/org/settings", { languages: [...new Set([...org.languages, "de", "fr"])], pattern_weekday: "EEEE d MMMM" });
});

test.afterAll(async () => {
  if (saved) await call("PUT", "/org/settings", saved).catch(() => undefined);
  await api?.dispose();
});

/** Settings → General → language picker → the language; the shell keeps it (cookie) on the next pages. */
async function pickLanguage(page: Page, code: "de" | "fr", name: string) {
  await page.goto("/settings?tab=general");
  const picker = page.getByTestId("locale-picker");
  await expect(picker).toBeVisible();
  await picker.click();
  const option = page.getByTestId(`locale-option-${code}`);
  await expect(option).toContainText(name);
  // CRBS translates only part of SmartSched: the picker says so, with the share
  await expect(page.getByTestId(`locale-partial-${code}`)).toHaveText(/\d+\s?%/);
  await option.click();
  await expect(page.locator("html")).toHaveAttribute("lang", code);
}

test("the administrator switches to German and French; the bookings grid header uses CRBS's day and month names", async ({ page }) => {
  await login(page);
  // the first bookings page of a session applies the profile / organisation language (CRBS); switch after it
  await page.goto(`/bookings?date=${MONDAY}`);
  await expect(page.getByTestId("booking-grid")).toBeVisible({ timeout: 30_000 });

  for (const [code, name, header, untranslated] of [
    ["de", "Deutsch", "Montag 16 Februar", "Bookings"],
    ["fr", "Français", "Lundi 16 Février", "Bookings"],
  ] as const) {
    await pickLanguage(page, code, name);
    await page.goto(`/bookings?date=${MONDAY}&display=room`);
    const grid = page.getByTestId("booking-grid");
    await expect(grid).toBeVisible({ timeout: 30_000 });
    // CRBS-shared: cal_monday / cal_february of crbs-core/application/language/{german,french}/calendar_lang.php
    await expect(grid.locator("th").filter({ hasText: header }).first()).toBeVisible();
    await expect(page.getByTestId("date-picker-trigger")).toContainText(header.split(" ")[0]!);
    // CRBS has no German/French text for the page title: English, per key
    await expect(page.getByRole("heading", { level: 1, name: untranslated })).toBeVisible();
  }
});
