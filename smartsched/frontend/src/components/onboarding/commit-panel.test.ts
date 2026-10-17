import { describe, expect, it } from "vitest";
import { matchTerm } from "./commit-panel";

const T = (id: number, code: string, week_count = 14) => ({ id, code, name: code, week_count });

describe("matchTerm (R3-M-04: offer the existing term the files belong to)", () => {
  it("finds the same code, else the one term with the group's season word and year", () => {
    expect(matchTerm([T(1, "2026-BAHAR", 19)], "2026-BAHAR", 2026)?.id).toBe(1);
    expect(matchTerm([T(1, "2026-BAHAR", 19)], "BAHAR", null)?.id).toBe(1);
    expect(matchTerm([T(1, "2026-BAHAR", 19), T(2, "2026-GUZ")], "bahar", 2026)?.id).toBe(1);
    expect(matchTerm([T(1, "2025-BAHAR"), T(2, "2026-BAHAR")], "BAHAR", 2026)?.id).toBe(2);
  });
  it("offers nothing when it is not one clear term", () => {
    expect(matchTerm([T(1, "2025-BAHAR"), T(2, "2026-BAHAR")], "BAHAR", null)).toBeNull();
    expect(matchTerm([T(1, "2026-GUZ")], "BAHAR", 2026)).toBeNull();
    expect(matchTerm([T(1, "2026-BAHAR-CSV")], "", 2026)).toBeNull();
    expect(matchTerm([T(1, "2026-BAHARX")], "BAHAR", 2026)).toBeNull();
  });
});
