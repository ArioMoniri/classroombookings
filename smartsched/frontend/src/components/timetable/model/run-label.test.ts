import { describe, expect, it } from "vitest";
import { runOptionLabel, weekRanges } from "./run-label";

const t = (k: string, v?: Record<string, string | number>) => (k === "calendar.nav.weekShort" ? `W${v?.n}` : k === "classes.kind.exams" ? "Exams" : k === "classes.kind.meetings" ? "Classes" : k.replace("runs.status.", ""));

describe("run picker label (UI polish: the /timetable run selector truncated '…Feasible · 1(')", () => {
  it("compresses week lists into ranges", () => {
    expect(weekRanges([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14])).toBe("1–14");
    expect(weekRanges([7, 3, 4, 5])).toBe("3–5, 7");
    expect(weekRanges([3])).toBe("3");
  });
  it("short label: kind only when runs of both kinds are listed, weeks as ranges; the full label for the tooltip", () => {
    const run = { id: 12, kind: "COURSE", status: "FEASIBLE", horizon: "WEEK", horizon_params: { weeks: [1, 2, 3, 4, 5, 6, 7] } } as const;
    expect(runOptionLabel(run, t, false)).toEqual({ short: "#12 · FEASIBLE · W1–7", full: "#12 · Classes · FEASIBLE · W1–7" });
    expect(runOptionLabel(run, t, true).short).toBe("#12 · Classes · FEASIBLE · W1–7");
    expect(runOptionLabel({ ...run, horizon: "TERM", horizon_params: { weeks: [] } }, t, false).short).toBe("#12 · FEASIBLE");
  });
});
