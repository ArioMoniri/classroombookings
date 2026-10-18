import { describe, expect, it } from "vitest";
import { makeChartFormat } from "@/components/charts/chart-format";
import { translate, type MessageKey, type Vars } from "@/lib/i18n";
import { ScheduleRun } from "@/lib/api/schemas";
import { MIN_RUNS, scoreHistory, scoreSummary } from "./score-history-model";

const t = (k: MessageKey, v?: Vars) => translate("tr", k, v);
const f = makeChartFormat("tr");
let n = 0;
const run = (over: Record<string, unknown> = {}) =>
  ScheduleRun.parse({
    id: ++n,
    term_id: 1,
    term_code: "2026-BAHAR",
    kind: "COURSE",
    horizon: "TERM",
    horizon_params: { weeks: [] },
    status: "FEASIBLE",
    params: {},
    objective_value: null,
    soft_score: 80,
    hard_score: 100,
    stats: { solver: "cp-sat", events: 600 },
    diagnosis: [],
    parent_run_id: null,
    prompt_text: null,
    created_at: "2026-10-15T10:00:00Z",
    finished_at: "2026-10-15T10:01:00Z",
    ...over,
  });

describe("CH-08 soft score history model", () => {
  it("orders by finished_at, not by id", () => {
    const pts = scoreHistory([
      run({ id: 30, soft_score: 70, finished_at: "2026-10-16T09:00:00Z" }),
      run({ id: 10, soft_score: 60, finished_at: "2026-10-14T09:00:00Z" }),
      run({ id: 20, soft_score: 90, finished_at: "2026-10-15T09:00:00Z" }),
    ]);
    expect(pts.map((p) => p.id)).toEqual([10, 20, 30]);
    expect(pts.map((p) => p.soft)).toEqual([60, 90, 70]);
  });

  it("excludes cancelled, failed, running and queued runs, runs without a score, exam runs and imported boards", () => {
    const pts = scoreHistory([
      run({ id: 1 }),
      run({ id: 2, status: "CANCELLED" }),
      run({ id: 3, status: "FAILED", soft_score: null }),
      run({ id: 4, status: "RUNNING", finished_at: null }),
      run({ id: 5, status: "QUEUED", finished_at: null, soft_score: null }),
      run({ id: 6, soft_score: null }),
      run({ id: 7, kind: "EXAM" }),
      run({ id: 8, stats: {} }),
      run({ id: 9, status: "FEASIBLE_PARTIAL", stats: { solver: "cp-sat", placed: 500, events_total: 530 } }),
      run({ id: 11, status: "OPTIMAL" }),
    ]);
    expect(pts.map((p) => p.id)).toEqual([1, 9, 11]);
  });

  it("labels the active run and keeps its index", () => {
    const pts = scoreHistory([run({ id: 1 }), run({ id: 2, is_active: true }), run({ id: 3 })]);
    expect(pts.map((p) => p.label)).toEqual(["#1", "#2", "#3"]);
    expect(pts.find((p) => p.active)?.id).toBe(2);
  });

  it(`needs at least ${MIN_RUNS} finished runs`, () => {
    expect(MIN_RUNS).toBe(3);
  });

  it("summary names the active run and the best run", () => {
    const pts = scoreHistory([run({ id: 1, soft_score: 70 }), run({ id: 2, soft_score: 92, is_active: true }), run({ id: 3, soft_score: 85 })]);
    expect(scoreSummary(pts, t, f)).toBe("Etkin çalıştırma #2: 92. Son çalıştırma #3: 85; en yüksek #2 (92).");
    const none = scoreHistory([run({ id: 4, soft_score: 70 }), run({ id: 5, soft_score: 75 }), run({ id: 6, soft_score: 72 })]);
    expect(scoreSummary(none, t, f)).toBe("Son çalıştırma #6: 72; en yüksek #5 (75).");
  });
});
