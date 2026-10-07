import { defineConfig, devices } from "@playwright/test";

process.env.PLAYWRIGHT_BROWSERS_PATH ??= "/opt/pw-browsers";
const PORT = Number(process.env.PW_PORT ?? 3100);

export default defineConfig({
  testDir: "./e2e",
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
      NEXT_PUBLIC_API_MOCK: "1",
      NEXT_PUBLIC_API_URL: "http://127.0.0.1:8000",
      AUTH_SECRET: "e2e-secret",
    },
  },
});
