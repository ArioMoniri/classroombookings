/**
 * Languages (ROADMAP P18-LANG, owner decision 2026-10-15: Turkish and English only) against the REAL backend,
 * gated E2E_REAL=1. docs/CRBS_PARITY.md §6.13 lists it as a deliberate difference from CRBS's 13 languages.
 *
 * - the language picker offers two options and switches the interface (html lang, page title);
 * - new writes accept only tr | en: `PUT /auth/profile` and `PUT /org/settings` with "de" answer 422;
 * - a legacy "de" (the language cookie of an older SmartSched session) renders English, page titles included.
 *
 *   E2E_REAL=1 E2E_API_URL=http://127.0.0.1:8400 PW_PORT=3800 npx playwright test e2e/languages.spec.ts
 */
import { expect, request as pwRequest, test, type APIRequestContext } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, REAL, SKIP_REASON, login } from "./helpers";
import { pinLanguage } from "./language";

const API = (process.env.E2E_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "") + "/api/v1";

test.describe.configure({ mode: "serial" });
test.skip(!REAL, SKIP_REASON);
// the assertions read Turkish (the product default): pin it, whatever the previous spec left behind
pinLanguage("tr");

let api: APIRequestContext;
let token = "";

test.beforeAll(async () => {
  api = await pwRequest.newContext();
  const res = await api.post(`${API}/auth/login`, { data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD } });
  expect(res.ok(), await res.text()).toBeTruthy();
  token = ((await res.json()) as { access_token: string }).access_token;
});

test.afterAll(async () => {
  await api?.dispose();
});

test("the language picker offers Turkish and English only and switches the interface", async ({ page }) => {
  await login(page);
  await page.goto("/settings?tab=general");
  const picker = page.getByTestId("locale-toggle").first();
  await expect(picker).toBeVisible();
  await expect(picker.getByRole("button")).toHaveCount(2);
  await expect(picker.getByRole("button")).toHaveText(["tr", "en"]);
  await picker.getByRole("button", { name: "en" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await page.goto("/profile");
  await expect(page).toHaveTitle("Profile · SmartSched");
  await page.goto("/settings?tab=general");
  await page.getByTestId("locale-toggle").first().getByRole("button", { name: "tr" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "tr");
  await page.goto("/profile");
  await expect(page).toHaveTitle("Profil · SmartSched"); // persona U-09: Turkish page titles
});

test("PUT language de is refused (422); tr and en are accepted", async () => {
  const headers = { Authorization: `Bearer ${token}` };
  const de = await api.put(`${API}/auth/profile`, { data: { language: "de" }, headers });
  expect(de.status(), await de.text()).toBe(422);
  const org = await api.put(`${API}/org/settings`, { data: { languages: ["tr", "en", "de"] }, headers });
  expect(org.status(), await org.text()).toBe(422);
  const en = await api.put(`${API}/auth/profile`, { data: { language: "EN" }, headers });
  expect(en.status(), await en.text()).toBe(200);
  expect(((await en.json()) as { language: string }).language).toBe("en");
  const bundle = (await (await api.get(`${API}/org/i18n`, { params: { language: "de" } })).json()) as { language: string; languages: string[] };
  expect(bundle.language).toBe("en"); // an older client asking for German is served English
  expect(bundle.languages.every((l) => l === "tr" || l === "en")).toBe(true);
  // back to the organisation default for the specs that follow
  await api.put(`${API}/auth/profile`, { data: { language: "tr" }, headers });
});

test("a legacy de language cookie renders English", async ({ page, context }) => {
  await login(page);
  const url = new URL(page.url());
  await context.addCookies([{ name: "NEXT_LOCALE", value: "de", domain: url.hostname, path: "/" }]);
  // /settings does not apply the profile language (the bookings pages do, once per sign-in session)
  await page.goto("/settings?tab=general");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page).toHaveTitle("Settings · SmartSched");
  await expect(page.getByTestId("locale-toggle").first().getByRole("button", { name: "en" })).toHaveAttribute("aria-pressed", "true");
  await context.addCookies([{ name: "NEXT_LOCALE", value: "tr", domain: url.hostname, path: "/" }]);
});
