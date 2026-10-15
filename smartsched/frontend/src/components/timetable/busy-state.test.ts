// @vitest-environment node
/**
 * Motion audit 2026-10-15 T1 for the calendar, studio, classes, runs and chat views: a busy control is never
 * spinner-only. Spinners come from `@/components/ui/busy-label` (`BusyButton` / `BusyLabel` / `BusyGlyph`),
 * which add aria-busy and a gerund label and show a static glyph under reduced motion (OS or in-app switch).
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const root = path.resolve(__dirname, "../..");
const SCOPE = ["components/studio", "components/timetable", "components/classes", "components/runs", "components/chat", "app/(app)/timetable", "app/(app)/classes", "app/(app)/generate", "app/(app)/runs"];
function sources(dir: string): string[] {
  const abs = path.join(root, dir);
  return readdirSync(abs).flatMap((f) => {
    const p = path.join(abs, f);
    if (statSync(p).isDirectory()) return sources(path.join(dir, f));
    return /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f) ? [p] : [];
  });
}

describe("busy state (T1)", () => {
  it("no hand-rolled spinner (animate-spin) in these views", () => {
    const hits = SCOPE.flatMap(sources).flatMap((f) =>
      readFileSync(f, "utf8")
        .split("\n")
        .map((l, i) => [l, i] as const)
        .filter(([l]) => /\banimate-spin\b/.test(l))
        .map(([, i]) => `${path.relative(root, f)}:${i + 1}`),
    );
    expect(hits).toEqual([]);
  });
});
