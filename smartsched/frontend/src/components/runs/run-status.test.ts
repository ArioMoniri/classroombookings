import { describe, expect, it } from "vitest";
import * as adapt from "@/lib/api/adapters";
import { ScheduleRun } from "@/lib/api/schemas";
import { translate } from "@/lib/i18n";
import { partialCounts, runStatusBadge } from "./runs-list";

const base = { id: 9, term_id: 1, term_code: "2026-BAHAR", kind: "COURSE", horizon: "WEEK", horizon_params: { weeks: [3] }, params: {}, objective_value: 120, soft_score: 84, parent_run_id: null, prompt_text: null, label: null, is_active: true, error: null, created_at: "2026-10-08T08:00:00Z", started_at: null, finished_at: "2026-10-08T08:01:00Z", diagnosis: [] };

describe("best-effort (partial) runs", () => {
  it("labels an INFEASIBLE run with stored placements as partial, with counts", () => {
    // backend D3: status stays INFEASIBLE, stats.partial / placed / events_total describe the stored timetable
    const run = ScheduleRun.parse(adapt.run({ ...base, status: "INFEASIBLE", hard_score: 100, stats: { partial: true, placed: 662, unplaced: 21, events_total: 683 } }));
    expect(partialCounts(run)).toEqual({ placed: 662, total: 683 });
    const badge = runStatusBadge(run, (k, v) => translate("en", k, v));
    expect(badge).toEqual({ kind: "warning", label: "Partial · 662/683 placed" });
    expect(runStatusBadge(run, (k, v) => translate("tr", k, v)).label).toBe("Kısmi · 662/683 yerleşti");
  });

  it("labels a FEASIBLE_PARTIAL run as partial, with counts", () => {
    const run = ScheduleRun.parse(adapt.run({ ...base, status: "FEASIBLE_PARTIAL", hard_score: 100, stats: { partial: true, placed: 658, unplaced: 26, events_total: 684 } }));
    expect(partialCounts(run)).toEqual({ placed: 658, total: 684 });
    expect(runStatusBadge(run, (k, v) => translate("en", k, v))).toEqual({ kind: "warning", label: "Partial · 658/684 placed" });
    expect(runStatusBadge(run, (k, v) => translate("tr", k, v)).label).toBe("Kısmi · 658/684 yerleşti");
    // without counts (e.g. a list payload without stats) the plain status label is used
    const bare = ScheduleRun.parse(adapt.run({ ...base, status: "FEASIBLE_PARTIAL", hard_score: 100, stats: {} }));
    expect(runStatusBadge(bare, (k, v) => translate("en", k, v))).toEqual({ kind: "warning", label: "Partial" });
    expect(translate("tr", "runs.status.FEASIBLE_PARTIAL")).toBe("Kısmi");
  });

  it("keeps plain statuses for complete and empty runs", () => {
    const feasible = ScheduleRun.parse(adapt.run({ ...base, status: "FEASIBLE", hard_score: 100, stats: { placed: 683, events_total: 683 } }));
    expect(partialCounts(feasible)).toBeNull();
    expect(runStatusBadge(feasible, (k, v) => translate("en", k, v))).toEqual({ kind: "feasible", label: "Feasible" });
    const empty = ScheduleRun.parse(adapt.run({ ...base, status: "INFEASIBLE", hard_score: 0, stats: {} }));
    expect(runStatusBadge(empty, (k, v) => translate("en", k, v))).toEqual({ kind: "infeasible", label: "Infeasible" });
  });
});
