import { defineConfig, devices } from "@playwright/test";

process.env.PLAYWRIGHT_BROWSERS_PATH ??= "/opt/pw-browsers";
const PORT = Number(process.env.PW_PORT ?? 3100);
/**
 * E2E_REAL=1 runs e2e/real-backend.spec.ts against a running FastAPI backend (NEXT_PUBLIC_API_URL,
 * default http://127.0.0.1:8000) with the mock switched off; otherwise only the mock smoke specs run.
 * See docs/testing/2026-10-08-real-backend-e2e.md for the backend setup.
 */
const REAL = process.env.E2E_REAL === "1";

export default defineConfig({
  testDir: "./e2e",
  ...(REAL ? { testMatch: /real-backend\.spec\.ts/ } : { testIgnore: /real-backend\.spec\.ts/ }),
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
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
      NEXT_PUBLIC_API_MOCK: REAL ? "0" : "1",
      NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000",
      AUTH_SECRET: "e2e-secret",
    },
  },
});
