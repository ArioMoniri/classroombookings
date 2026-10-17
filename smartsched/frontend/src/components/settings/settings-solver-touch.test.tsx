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
});
