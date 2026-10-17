/**
 * Gözetmen ataması helpers on a real under-staffed plan: the 2026 Final exam run with `instructor_pool=none` and one
 * staff member (193 no_candidates + 607 slot_shortage errors, 1 teaching_unchecked warning; trimmed to 3 per code).
 */
import { describe, expect, it } from "vitest";
import type { Diagnosis, PlanBrief, PlanDetail } from "@/lib/api/invigilation";
import fixture from "./__fixtures__/plan-final-pool-none.json";
import addFx from "./__fixtures__/add-duty-final.json";
import { allInstructorsParams, bySession, diagCounts, filterPosts, fromRows, groupDiagnoses, isBoardRun, knownPhase, newRow, parsePostKey, planTone, poolEmptyDiag, postDates, progressView, rowProblem, suggestionSummary, toRows } from "./invigilation-model";

const plan = fixture as unknown as PlanDetail;

describe("invigilation model", () => {
  it("groups diagnoses by code, errors first, keeping every item", () => {
    const g = groupDiagnoses(plan.diagnosis);
    expect(g.map((x) => x.severity)).toEqual(["error", "error", "warning"]);
    expect(g.at(-1)!.code).toBe("teaching_unchecked");
    expect(g.reduce((s, x) => s + x.items.length, 0)).toBe(plan.diagnosis.length);
    expect(g[0]!.posts).toBeGreaterThan(0);
  });

  it("sums the backend's suggestions per code", () => {
    const nc = groupDiagnoses(plan.diagnosis).find((x) => x.code === "no_candidates")!;
    const tips = suggestionSummary(nc.items, "tr");
    expect(tips[0]!.count).toBe(nc.items.length);
    expect(tips[0]!.text).toMatch(/havuza ekleyin/);
  });

  it("tones an INFEASIBLE plan red and a fully staffed one green", () => {
    expect(planTone(plan)).toBe("infeasible");
    expect(planTone({ status: "FEASIBLE", counts: { ...plan.counts, missing: 0 } })).toBe("feasible");
    expect(planTone({ status: "RUNNING", counts: plan.counts })).toBe("tint");
  });

  it("filters posts by date, text and under-staffing, in time then room order", () => {
    const dates = postDates(plan.posts);
    expect(dates[0]).toBe("2026-05-13");
    const day = filterPosts(plan.posts, { date: "2026-06-01", query: "", onlyMissing: false });
    expect(day.every((p) => p.date === "2026-06-01")).toBe(true);
    expect(filterPosts(plan.posts, { date: "all", query: "bme419", onlyMissing: false })[0]!.room).toBe("C 201");
    expect(filterPosts(plan.posts, { date: "all", query: "", onlyMissing: true }).every((p) => p.missing > 0)).toBe(true);
    const sessions = bySession(day);
    expect(sessions.every((s) => s.posts.every((p) => `${p.date}|${p.start_period}-${p.end_period}` === s.key))).toBe(true);
  });

  it("round-trips the unavailability editor rows to the API body", () => {
    const rows = toRows([{ date: "2026-06-01", start_period: 1, end_period: 4, note: "rapor" }, { day: 5 }]);
    expect(rows[0]).toMatchObject({ mode: "date", whole: false, start: 1, end: 4, note: "rapor" });
    expect(rows[1]).toMatchObject({ mode: "day", day: 5, whole: true });
    expect(fromRows(rows)).toEqual([{ date: "2026-06-01", start_period: 1, end_period: 4, note: "rapor" }, { day: 5 }]);
    expect(rowProblem(newRow())).toBe("date");
    expect(rowProblem({ ...newRow(), mode: "day", whole: false, start: 5, end: 3 })).toBe("range");
    expect(rowProblem({ ...newRow(), date: "2026-06-02" })).toBeNull();
  });

  it("reads a post key", () => {
    expect(parsePostKey("2026-05-13|30|6-8")).toEqual({ date: "2026-05-13", roomId: 30, start: 6, end: 8 });
    expect(parsePostKey("x")).toBeNull();
  });

  it("groups a shortage staffed by hand afterwards (resolved) on its own, after the open ones", () => {
    const resolved = { ...(addFx.diagnosis_resolved as unknown as Diagnosis) };
    const list = [resolved, ...plan.diagnosis];
    const g = groupDiagnoses(list);
    expect(g.at(-1)).toMatchObject({ code: "no_candidates", resolved: true, posts: 1 });
    expect(g.filter((x) => !x.resolved).map((x) => x.code)).toEqual(groupDiagnoses(plan.diagnosis).map((x) => x.code));
    expect(g.reduce((s, x) => s + x.items.length, 0)).toBe(list.length);
    const errors = plan.diagnosis.filter((d) => d.severity === "error").length;
    expect(diagCounts(list)).toEqual({ errors, others: plan.diagnosis.length - errors, resolved: 1 });
  });

  it("shows the backend's own progress: phases and percentages as reported, the time meter only while solving", () => {
    const seen = addFx.progress_seen.map((x) => progressView({ status: x.status as PlanBrief["status"], progress: x.progress, params: { time_limit_s: 3 } }, 5));
    expect(seen.map((v) => [v.phase, v.pct, v.solving])).toEqual([["queued", 0, false], ["loading", 10, false], ["solving", 30, true], ["persisting", 90, false], ["done", 100, false]]);
    // elapsed beyond the limit fills the meter, never past it
    expect(seen[2]).toMatchObject({ limit: 3, elapsed: 5, meter: 3 });
    expect(seen[1]!.meter).toBeNull();
    // a backend without progress (or a job that has not reported yet): no number made up
    expect(progressView({ status: "RUNNING", progress: undefined, params: {} }, 4)).toMatchObject({ phase: "running", pct: null, limit: 20 });
    expect(knownPhase("persisting")).toBe(true);
    expect(knownPhase("warming_up")).toBe(false);
  });
});

describe("pool (round-1 T-R1-42)", () => {
  it("finds the empty-pool error and widens the plan's own parameters to every instructor", () => {
    // the fixture's pool has one staff member, so it carries no pool_empty error; the backend's error shape is tested
    expect(poolEmptyDiag(plan.diagnosis)).toBeUndefined();
    const empty: Diagnosis = { code: "pool_empty", severity: "error", text: { tr: "Gözetmen havuzu boş: havuz 'Eğitmen yok' seçili ve havuza kimse eklenmedi", en: "The invigilator pool is empty" }, suggestions: [{ code: "pool_all", text: { tr: "Havuzu 'Tüm eğitmenler' yapıp yeniden çalıştırın (490 eğitmen)", en: "Re-run with the pool set to 'All instructors'" } }] };
    expect(poolEmptyDiag([...plan.diagnosis, empty])).toBe(empty);
    expect(poolEmptyDiag([{ code: "pool_empty", severity: "info", text: { tr: "", en: "" } }])).toBeUndefined();
    expect(poolEmptyDiag(undefined)).toBeUndefined();
    const params = allInstructorsParams({ instructor_pool: "none", max_per_day: 2, time_limit_s: 20 });
    expect(params).toEqual({ instructor_pool: "all", max_per_day: 2 });
    expect(allInstructorsParams(null)).toEqual({ instructor_pool: "all" });
  });

  it("tells an imported board from a solved exam run", () => {
    expect(isBoardRun({ params: { source: "GRID_IMPORT" }, label: "Grid import: final.xlsx" } as never)).toBe(true);
    expect(isBoardRun({ params: { time_limit_s: 30, seed: 0, workers: 2, stability: true, weights: {} }, label: "Final", stats: { placed: 603 }, prompt_text: null, diagnosis: [] } as never)).toBe(false);
    // an older backend without params.source: the board shape (no solver stats, no prompt, grid label)
    expect(isBoardRun({ params: { time_limit_s: 60, seed: 0, workers: 8, stability: true, weights: {} }, label: "Grid import: guz.xlsx", stats: { progress: 100 }, prompt_text: null, diagnosis: [] } as never)).toBe(true);
  });
});
