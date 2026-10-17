// @vitest-environment node
/**
 * U-01 (persona test 2026-10-15) for the shell, bookings, approvals, admin, find-room, notifications, audit,
 * import, auth and settings sources and the primitives the sweep touched: no `outline-none` token, and every
 * hidden-outline class string with a focus-visible width also sets `focus-visible:outline-solid` (Tailwind 4:
 * `outline-hidden` keeps `--tw-outline-style: none`, so the width alone draws no ring). The Tailwind semantics
 * are proven with the real compiler in components/timetable/focus-ring.test.ts.
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const root = path.resolve(__dirname, "../..");
const SCOPE = [
  "components/shell", "components/bookings", "components/approvals", "components/admin", "components/findroom", "components/notifications",
  "components/audit", "components/import", "components/auth", "components/settings", "app/(app)/bookings", "app/(app)/my-bookings",
  "app/(app)/find-room", "app/(app)/approvals", "app/(app)/admin", "app/(app)/profile", "app/(app)/settings", "app/(app)/import", "app/login",
  "app/setup", "app/reset-password",
];
const FILES = ["components/ui/button.tsx", "components/ui/tabs.tsx", "components/ui/segmented-glass.tsx", "components/ui/sheet.tsx"];

function sources(dir: string): string[] {
  const abs = path.join(root, dir);
  return readdirSync(abs).flatMap((f) => {
    const p = path.join(abs, f);
    if (statSync(p).isDirectory()) return sources(path.join(dir, f));
    return /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f) ? [p] : [];
  });
}

describe("focus ring (U-01), shell and admin sweep", () => {
  it("no `outline-none`, and hidden outlines restore a solid focus-visible ring", () => {
    const offenders: string[] = [];
    for (const file of [...SCOPE.flatMap(sources), ...FILES.map((f) => path.join(root, f)).filter((f) => existsSync(f))]) {
      const src = readFileSync(file, "utf8");
      const rel = path.relative(root, file);
      if (/(?<![\w-])outline-none(?![\w-])/.test(src)) offenders.push(`${rel}: outline-none`);
      for (const m of src.matchAll(/"[^"\n]*"|'[^'\n]*'|`[^`]*`/g)) {
        const s = m[0];
        if (!s.includes("outline-hidden")) continue;
        if (/(?<![\w:-])focus-visible:outline(?:-\d+)?(?![\w(\[-])/.test(s) && !s.includes("focus-visible:outline-solid")) offenders.push(`${rel}: ${s.slice(0, 80)}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
