import { describe, expect, it } from "vitest";
import { currentTermByDate, termRange, weekOfTerm } from "./workspace";

const bahar = { id: 1, kind: "REGULAR" as const, start_date: "2026-02-02", end_date: "", week_count: 15 };
const final = { id: 2, kind: "FINAL" as const, start_date: "2026-06-01", end_date: "", week_count: 3 };
const guz = { id: 3, kind: "REGULAR" as const, start_date: "2026-09-28", end_date: "", week_count: 14 };

describe("current term by date", () => {
  it("picks the term that contains today, not the last imported one", () => {
    expect(currentTermByDate([final, bahar], new Date(2026, 2, 10))?.id).toBe(1);
    expect(currentTermByDate([bahar, final], new Date(2026, 5, 9))?.id).toBe(2);
    expect(currentTermByDate([bahar, final, guz], new Date(2026, 9, 8))?.id).toBe(3);
  });

  it("falls back to the latest ended teaching term (an exam period belongs to it)", () => {
    // 8 Oct 2026, only Bahar and its Final imported: Bahar, although Final ended later
    expect(currentTermByDate([final, bahar], new Date(2026, 9, 8))?.id).toBe(1);
  });

  it("prefers a term that starts soon", () => {
    expect(currentTermByDate([bahar, guz], new Date(2026, 8, 1))?.id).toBe(3);
  });

  it("computes ranges and the current week", () => {
    const r = termRange(bahar);
    expect(new Date(r.end).toISOString().slice(0, 10)).toBe("2026-05-17");
    expect(weekOfTerm(bahar, new Date(2026, 1, 18))).toBe(3);
    expect(weekOfTerm(bahar, new Date(2026, 9, 8))).toBe(15);
    expect(weekOfTerm(bahar, new Date(2026, 0, 8))).toBeUndefined();
  });
});
