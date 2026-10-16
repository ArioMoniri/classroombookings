/** The heat grid: one tab stop, arrow keys, Enter drills down, numbers in the cells and the readout, hatched blocks. */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HeatGrid } from "./heat-grid";

const cells: Record<string, { occupied: number; blocked: number; capacity: number; pct: number }> = {
  "0-0": { occupied: 4, blocked: 0, capacity: 31, pct: 12.9 },
  "0-1": { occupied: 25, blocked: 2, capacity: 31, pct: 86.2 },
  "1-0": { occupied: 0, blocked: 31, capacity: 31, pct: 0 },
  "1-1": { occupied: 0, blocked: 0, capacity: 31, pct: 0 },
};

function setup(onActivate = vi.fn()) {
  render(
    <HeatGrid
      label="A blok"
      locale="tr"
      rows={[{ key: "p1", label: "08:30", text: "08:30–09:10" }, { key: "p2", label: "09:20", text: "09:20–10:00" }]}
      cols={[{ key: "d1", label: "Pzt", text: "Pazartesi" }, { key: "d2", label: "Sal", text: "Salı" }]}
      cell={(r, c) => cells[`${r}-${c}`]}
      describe={(r, c) => `cell ${r}-${c}: ${cells[`${r}-${c}`]!.occupied} dolu`}
      onActivate={onActivate}
      hint="hint"
      data-testid="g"
    />,
  );
  return onActivate;
}

describe("HeatGrid", () => {
  it("prints the number in every cell and hatches a fully pre-occupied one", () => {
    setup();
    const grid = screen.getByRole("grid", { name: "A blok" });
    const gridcells = grid.querySelectorAll("[role=gridcell]");
    expect([...gridcells].map((c) => c.textContent)).toEqual(["13", "86", "—", "0"]);
    expect(gridcells[2]!.getAttribute("data-state")).toBe("blocked");
    expect(gridcells[1]!.getAttribute("data-partly")).toBe("true");
    expect(gridcells[1]!.getAttribute("data-step")).toBe("4");
  });

  it("has one tab stop and moves with the arrow keys, showing the counts in the readout", () => {
    setup();
    const all = screen.getAllByRole("gridcell");
    expect(all.filter((c) => c.tabIndex === 0)).toHaveLength(1);
    all[0]!.focus();
    fireEvent.keyDown(all[0]!, { key: "ArrowRight" });
    expect(document.activeElement).toBe(all[1]);
    fireEvent.keyDown(all[1]!, { key: "ArrowDown" });
    expect(document.activeElement).toBe(all[3]);
    expect(screen.getByTestId("g-readout").textContent).toBe("cell 1-1: 0 dolu");
    fireEvent.keyDown(all[3]!, { key: "Home" });
    expect(document.activeElement).toBe(all[2]);
  });

  it("activates the focused cell with Enter and on click", () => {
    const on = setup();
    const all = screen.getAllByRole("gridcell");
    all[0]!.focus();
    fireEvent.keyDown(all[0]!, { key: "Enter" });
    expect(on).toHaveBeenLastCalledWith(0, 0);
    fireEvent.click(all[3]!);
    expect(on).toHaveBeenLastCalledWith(1, 1);
  });
});
