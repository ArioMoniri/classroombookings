/** The utilisation scale (tokens.md §2.5): five steps, hatched pre-occupied cells, numbers never read as 0. */
import { describe, expect, it } from "vitest";
import { cellState, heatStep, pctText, signed } from "./heat-scale";

describe("heat scale", () => {
  it("maps percentages onto the five documented steps", () => {
    expect([0, 0.4, 1, 25, 25.1, 50, 51, 75, 76, 100].map(heatStep)).toEqual([0, 1, 1, 1, 2, 2, 3, 3, 4, 4]);
  });
  it("hatches a cell whose rooms are all pre-occupied and leaves it out of the scale", () => {
    expect(cellState({ occupied: 0, blocked: 31, capacity: 31, pct: 0 })).toEqual({ kind: "blocked" });
    expect(cellState({ occupied: 0, blocked: 0, capacity: 0, pct: 0 })).toEqual({ kind: "empty" });
    expect(cellState(undefined)).toEqual({ kind: "empty" });
  });
  it("keeps the colour of a partly blocked cell and flags it (real Bahar wk 3, building A, Wednesday)", () => {
    expect(cellState({ occupied: 206, blocked: 3, capacity: 558, pct: 37.1 })).toEqual({ kind: "value", pct: 37.1, step: 2, partlyBlocked: true });
  });
  it("prints a nearly empty cell with a decimal so it never reads as 0", () => {
    expect(pctText(0.4, "tr")).toBe("0,4");
    expect(pctText(12.9, "tr")).toBe("13");
    expect(pctText(0, "en")).toBe("0");
  });
  it("signs deltas with a real minus", () => {
    expect(signed(-9.9, "tr")).toBe("−9,9");
    expect(signed(3, "en")).toBe("+3");
    expect(signed(0, "en")).toBe("0");
  });
});
