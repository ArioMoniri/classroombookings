import { describe, expect, it } from "vitest";
import { placedOf, runIssueCounts, runOutcome, verdictExceptions, waiverOf } from "./run-truth";

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

describe("how a run ended (round-1 R1-M-15: a cancelled run must not read like a clean result)", () => {
  it("a cancelled run names who stopped it and when; a generic cancel has no name", () => {
    expect(runOutcome({ status: "CANCELLED", error: "cancelled by admin@smartsched.local", finished_at: "2026-10-16T10:00:00" })).toEqual({ kind: "cancelled", by: "admin@smartsched.local", at: "2026-10-16T10:00:00" });
    expect(runOutcome({ status: "CANCELLED", error: "cancelled by a planner", finished_at: null })).toEqual({ kind: "cancelled", by: null, at: null });
    expect(runOutcome({ status: "CANCELLED", error: null })).toEqual({ kind: "cancelled", by: null, at: null });
  });
  it("running, failed and finished runs", () => {
    expect(runOutcome({ status: "RUNNING" })).toEqual({ kind: "active" });
    expect(runOutcome({ status: "ERROR", error: "boom" })).toEqual({ kind: "failed" });
    expect(runOutcome({ status: "INFEASIBLE" })).toEqual({ kind: "failed" });
    expect(runOutcome({ status: "FEASIBLE_PARTIAL" })).toEqual({ kind: "finished" });
    expect(runOutcome({ status: "TIMEOUT" })).toEqual({ kind: "finished" });
  });
});

describe("ScheduleRun.error (round-1 sweeper 2: the shared schema carries the cancel / failure text)", () => {
  it("parses with, without and with a null error; the report reads it before any extra request", async () => {
    const { ScheduleRun } = await import("@/lib/api/schemas");
    const base = { id: 9, term_id: 1, term_code: "2026-BAHAR", kind: "COURSE", horizon: "WEEK", horizon_params: { weeks: [3] }, status: "CANCELLED", params: {}, objective_value: null, soft_score: null, hard_score: null, parent_run_id: null, prompt_text: null, created_at: "2026-10-08T08:00:00Z", finished_at: "2026-10-08T08:01:00Z" };
    const cancelled = ScheduleRun.parse({ ...base, error: "cancelled by admin@smartsched.local" });
    expect(cancelled.error).toBe("cancelled by admin@smartsched.local");
    expect(runOutcome(cancelled)).toEqual({ kind: "cancelled", by: "admin@smartsched.local", at: "2026-10-08T08:01:00Z" });
    expect(ScheduleRun.parse({ ...base, error: null }).error).toBeNull();
    expect(ScheduleRun.parse(base).error).toBeUndefined(); // an older server: run-view falls back to the light re-read
  });
});
