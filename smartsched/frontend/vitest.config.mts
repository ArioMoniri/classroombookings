import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

// CI (pod CI on a 2 vCPU / 8 GB arm64 pod that also runs the app, and GitHub Actions): at most 2 forks, each
// with its own capped V8 heap (execArgv overrides the gate's NODE_OPTIONS heap for the workers), and a 30 s
// per-test budget so a loaded host does not time out a correct test. Locally: vitest defaults.
const CI = !!process.env.CI;

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
    ...(CI
      ? {
          pool: "forks" as const,
          maxWorkers: 2,
          execArgv: ["--max-old-space-size=1536"],
          testTimeout: 30_000,
          hookTimeout: 30_000,
        }
      : {}),
  },
});
