// Round-1 sweeper 2 (lane H ask, MOBILE.md M-02/M-03): /settings?tab=solver on a phone had 14 px fields, 16 × 16
// slider thumbs and a 36 px save button. jsdom has no layout or media queries, so this asserts the class contract:
// the number fields are the md field (44 px / 16 px on coarse pointers), the save button steps to 44 px, and the
// slider thumb grows a 44 × 44 ::after on touch.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { fieldSize } from "@/components/ui/field-styles";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";

const src = readFileSync(join(process.cwd(), "src/components/settings/settings-view.tsx"), "utf8");
const solverForm = src.slice(src.indexOf("function SolverForm("), src.indexOf("/** Review D16"));

describe("solver settings on touch", () => {
  it("the save button is 44 px on coarse pointers (size sm alone is 36)", () => {
    const save = solverForm.split("\n").find((l) => l.includes('data-testid="save-solver"'));
    expect(save).toContain("pointer-coarse:h-11");
  });

  it("the three solver fields are md fields: 44 px tall and 16 px text on touch phones", () => {
    for (const id of ["s-time", "s-workers", "s-seed"]) {
      const line = solverForm.split("\n").find((l) => l.includes(`id="${id}"`));
      expect(line, id).toContain("<Input ");
      expect(line, id).not.toContain('fieldSize="sm"');
    }
    expect(fieldSize.md).toContain("h-(--control-h-md)");
    render(<Input id="s-time" type="number" aria-label="Süre sınırı" />);
    expect(screen.getByRole("spinbutton", { name: "Süre sınırı" })).toHaveClass("h-(--control-h-md)", "max-md:pointer-coarse:text-base");
  });

  it("the weight slider thumb grows a 44 × 44 hit area on coarse pointers", () => {
    render(<Slider min={0} max={10} step={1} defaultValue={[4]} aria-label="Kapasite" />);
    const thumb = document.querySelector('[data-slot="slider-thumb"]');
    expect(thumb).not.toBeNull();
    expect(thumb).toHaveClass("size-4", "after:-inset-2", "pointer-coarse:after:-inset-3.5");
  });

  // round-2 T-R2-29 (R2-M-14): an organisation that saved no weights sees the solver's defaults, not 0, under a
  // Turkish header; the slider rows are 44 px labels with 16 px text on touch (M-02 / M-03)
  it("unsaved weights show the solver defaults with a 'varsayılan' marker under the Ağırlık header", () => {
    expect(solverForm).toContain("SOLVER_DEFAULT_WEIGHTS[k]");
    expect(solverForm).toContain('{locale === "tr" ? "Ağırlık" : "Weight"}');
    expect(solverForm).not.toMatch(/font-medium">w<\/th>/);
    expect(solverForm).toContain('"varsayılan" : "default"');
    expect(src).toContain("room_preference: 10, building_preference: 5, min_capacity_waste: 1, same_room_across_weeks: 8, stability: 1, exam_gap: 10");
    const table = solverForm.split("\n").find((l) => l.includes('data-testid="solver-weights"'));
    expect(table).toContain("pointer-coarse:text-base");
    const row = solverForm.split("\n").find((l) => l.includes("<label") && l.includes("pointer-coarse:min-h-11"));
    expect(row).toBeDefined();
  });

  // round-3 R3-S-06 (MOBILE M-05): on phones the save is a fixed capsule above the tab bar
  it("the solver save is a phone capsule above the tab bar", () => {
    const row = solverForm.split("\n").find((l) => l.includes('data-testid="solver-save-row"'));
    expect(row).toContain("max-sm:fixed");
    expect(row).toContain("max-sm:bottom-[calc(5.25rem+env(safe-area-inset-bottom))]");
    expect(solverForm.indexOf('data-testid="solver-save-row"')).toBeLessThan(solverForm.indexOf('data-testid="save-solver"'));
  });
});
