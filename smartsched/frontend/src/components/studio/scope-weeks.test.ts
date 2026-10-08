import { describe, expect, it } from "vitest";
import { nextWeeks } from "./scope-step";

describe("week chips", () => {
  it("replace the selection on a plain click", () => {
    expect(nextWeeks([1], 3, false)).toEqual([3]);
    expect(nextWeeks([1, 2, 5], 3, false)).toEqual([3]);
  });
  it("add or remove one week with ⌘ / Ctrl / ⇧", () => {
    expect(nextWeeks([1], 3, true)).toEqual([1, 3]);
    expect(nextWeeks([1, 3], 1, true)).toEqual([3]);
  });
});
