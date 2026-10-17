// Flow-loop round 2, lane A (T-R2-07, R2-S-15): with reduced motion (OS or in-app) the Sheet / Dialog popups and
// overlays have no transition and no starting-style offset — nothing moves (motion_designer rule). jsdom has no
// layout; this pins the globals.css contract, e2e/loop-r2-laneA.spec.ts measures translate/opacity two frames after
// the open on a stack.sh build.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");
const block = (start: string) => {
  const i = css.indexOf(start);
  expect(i, start).toBeGreaterThan(-1);
  return css.slice(i, i + 1600);
};

describe("T-R2-07: reduced motion stops the popups", () => {
  for (const ctx of ["@media (prefers-reduced-motion: reduce)", ':root[data-motion="reduced"]']) {
    it(`${ctx}: popups and overlays get transition none, no starting / ending offset`, () => {
      const b = block(`/* T-R2-07 ${ctx}`);
      expect(b).toContain('[data-slot="sheet-content"]');
      expect(b).toContain('[data-slot="dialog-content"]');
      expect(b).toContain('[data-slot="sheet-overlay"]');
      expect(b).toContain('[data-slot="dialog-overlay"]');
      expect(b).toContain("transition: none !important;");
      expect(b).toContain("translate: none !important;");
      expect(b).toContain("transform: none !important;");
      expect(b).toContain("opacity: 1 !important;");
    });
  }
});
