import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";

// CI (pod CI on a 2 vCPU / 8 GB arm64 pod that also runs the app, and GitHub Actions): at most 2 forks, each
// with its own capped V8 heap (execArgv overrides the gate's NODE_OPTIONS heap for the workers), and a 30 s
// per-test budget so a loaded host does not time out a correct test. Locally: vitest defaults.
// The pod still runs gate scripts installed before this config existed (no CI env, a 3 GB container), so the
// capped mode also switches on whenever the cgroup memory limit is small, and drops to one fork under 4 GB.
function cgroupLimitBytes(): number | null {
  for (const file of ["/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"]) {
    try {
      const raw = fs.readFileSync(file, "utf8").trim();
      const n = Number(raw);
      if (raw !== "max" && Number.isFinite(n) && n > 0 && n < 2 ** 52) return n;
    } catch {
      // no cgroup file here (macOS, Windows, no limit)
    }
  }
  return null;
}
const LIMIT = cgroupLimitBytes();
const SMALL = LIMIT !== null && LIMIT < 6 * 1024 ** 3;
const TINY = LIMIT !== null && LIMIT < 4 * 1024 ** 3;
const CI = !!process.env.CI || SMALL;

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
          maxWorkers: TINY ? 1 : 2,
          execArgv: [TINY ? "--max-old-space-size=1280" : "--max-old-space-size=1536"],
          testTimeout: 30_000,
          hookTimeout: 30_000,
        }
      : {}),
  },
});
