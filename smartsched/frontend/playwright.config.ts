import { defineConfig, devices } from "@playwright/test";

process.env.PLAYWRIGHT_BROWSERS_PATH ??= "/opt/pw-browsers";
const PORT = Number(process.env.PW_PORT ?? 3100);
/**
 * Every browser spec runs against the REAL FastAPI backend (there is no mock API). Start the e2e backend
 * first: FastAPI on SQLite with the real Bahar 2026 workbooks, the seeded admin and a full-term run,
 * booking clock inside the term (smartsched/deploy/pod-ci/gates/e2e-backend-entry.sh; pod CI gate
 * e2e-real.sh does the same in Docker). Then:
 *
 *   E2E_REAL=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx playwright test
 *
 * E2E_REAL=1 states that the backend is up; without it every spec skips with a pointer to this comment.
 * e2e/global-setup.ts checks the backend and resolves the run ids the specs need.
 */
const REAL = process.env.E2E_REAL === "1";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /(real-backend|bookings|calendar|languages|motion-audit|smoke|admin-gaps)\.spec\.ts/,
  globalSetup: REAL ? "./e2e/global-setup.ts" : undefined,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["github"]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `npx next build && npx next start -p ${PORT}`,
    url: `http://127.0.0.1:${PORT}/login`,
    reuseExistingServer: !process.env.CI,
    timeout: 300_000,
    env: {
      NEXT_PUBLIC_API_URL: API_URL,
    },
  },
});
