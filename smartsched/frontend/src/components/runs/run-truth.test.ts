import { describe, expect, it } from "vitest";
import { placedOf, runIssueCounts, verdictExceptions, waiverOf } from "./run-truth";

describe("one source of truth for run counts (admin persona M-06/M-07/M-08 and the Studio '716 yerleşti')", () => {
  it("placed is stats.placed; stats.events is the requested total", () => {
    expect(placedOf({ events: 716, placed: 687, events_total: 716 })).toEqual({ placed: 687, total: 716 });
    expect(placedOf({ events: 120 })).toEqual({ placed: 120, total: 120 });
    expect(placedOf({})).toEqual({ placed: null, total: null });
  });

  it("waivers come from stats.waived_rules / waived_violations and the waived_rules diagnosis", () => {
    const w = waiverOf({ waived_rules: ["capacity"], waived_violations: { capacity: 123 } }, [{ code: "waived_rules", params: { events: 123 } }]);
    expect(w).toEqual({ rules: ["capacity"], events: 123, byKind: { capacity: 123 } });
    expect(waiverOf({}, [])).toEqual({ rules: [], events: 0, byKind: {} });
  });

  it("grid issue counts use the grid's own definitions, over the whole run", () => {
    const c = runIssueCounts([
      { id: 1, reasons: ["room overlap with MAT 112"] },
      { id: 2, reasons: ["capacity 140 > 120"] },
      { id: 3, reasons: ["seats short", "capacity 90 > 80"] },
      { id: 3, reasons: ["seats short"] },
      { id: 4, reasons: [] },
    ]);
    expect(c).toEqual({ conflicts: 2, overCapacity: 1 });
  });

  it("a run with no exception has none; otherwise every exception is listed with its count", () => {
    expect(verdictExceptions({ waiver: { rules: [], events: 0, byKind: {} }, counts: { conflicts: 0, overCapacity: 0 }, lockedTooSmall: 0 })).toEqual([]);
    expect(verdictExceptions({ waiver: { rules: ["capacity"], events: 123, byKind: { capacity: 123 } }, counts: { conflicts: 308, overCapacity: 5 }, lockedTooSmall: 7 }).map((e) => [e.key, e.n])).toEqual([
      ["waived", 123],
      ["conflicts", 308],
      ["overCapacity", 5],
      ["lockedTooSmall", 7],
    ]);
  });
});

describe("run parsing keeps structured stats (missing_only_week, waived_rules) and is_active", () => {
  it("stats_detail has the objects the flat stats drop", async () => {
    const { ScheduleRun } = await import("@/lib/api/schemas");
    const adapt = await import("@/lib/api/adapters");
    const r = ScheduleRun.parse(adapt.run({ id: 3, term_id: 1, term_code: "B", kind: "COURSE", horizon: "TERM", horizon_params: {}, status: "FEASIBLE", params: {}, objective_value: null, soft_score: 80, hard_score: 100, stats: { placed: 687, events: 716, missing_only_week: { "1": 2 }, waived_rules: ["capacity"] }, diagnosis: [], parent_run_id: null, prompt_text: null, is_active: true, created_at: "2026-10-15T10:00:00Z", finished_at: null }));
    expect(r.stats.placed).toBe(687);
    expect(r.stats.missing_only_week).toBeUndefined();
    expect(r.stats_detail?.missing_only_week).toEqual({ "1": 2 });
    expect(r.stats_detail?.waived_rules).toEqual(["capacity"]);
    expect(r.is_active).toBe(true);
  });
});
