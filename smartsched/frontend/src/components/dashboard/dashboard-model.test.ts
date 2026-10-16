import { describe, expect, it } from "vitest";
import type { ScheduleRun } from "@/lib/api/schemas";
import { latestPlan, shownWeek } from "./dashboard-model";

const run = (over: Partial<ScheduleRun>): ScheduleRun => ({
  id: 1,
  term_id: 2,
  term_code: "2026-GUZ",
  kind: "COURSE",
  horizon: "WEEK",
  horizon_params: { weeks: [], dates: [] },
  status: "FEASIBLE",
  label: null,
  progress: 100,
  params: {} as ScheduleRun["params"],
  objective_value: null,
  soft_score: null,
  hard_score: null,
  stats: { solver: "cpsat", events: 10 },
  is_active: false,
  objective_breakdown: {},
  diagnosis: [],
  parent_run_id: null,
  prompt_text: "",
  created_at: "2026-10-16T08:00:00Z",
  finished_at: "2026-10-16T08:01:00Z",
  ...over,
});
// a weekly-grid import: no solver stats, no prompt, no diagnosis
const board = (over: Partial<ScheduleRun>) => run({ stats: {}, prompt_text: null, ...over });

describe("dashboard plan (T-R1-39)", () => {
  it("talks about the published imported board, not 'no timetable yet'", () => {
    expect(latestPlan([board({ id: 4, kind: "EXAM" }), board({ id: 3, is_active: true })])?.id).toBe(3);
  });

  it("prefers the published run over a newer unpublished solver run, course first", () => {
    const runs = [run({ id: 10 }), board({ id: 4, kind: "EXAM", is_active: true }), board({ id: 3, is_active: true })];
    expect(latestPlan(runs)?.id).toBe(3);
    expect(latestPlan([run({ id: 10 }), board({ id: 4, kind: "EXAM", is_active: true })])?.id).toBe(4);
  });

  it("without a published run: the newest finished solver run, never an unpublished board", () => {
    expect(latestPlan([board({ id: 3 }), run({ id: 9, status: "RUNNING" }), run({ id: 8, kind: "EXAM" }), run({ id: 7 })])?.id).toBe(7);
    expect(latestPlan([board({ id: 3 })])).toBeUndefined();
    expect(latestPlan(undefined)).toBeUndefined();
  });

  it("shows the picked week, else the measured one, clamped to the term", () => {
    expect(shownWeek(undefined, 2, 4, 14)).toBe(2);
    expect(shownWeek(5, 2, 4, 14)).toBe(5);
    expect(shownWeek(undefined, undefined, 4, 14)).toBe(4);
    expect(shownWeek(20, undefined, 4, 14)).toBe(14);
  });
});
