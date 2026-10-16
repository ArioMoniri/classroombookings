/**
 * Gözetmen ataması helpers on a real under-staffed plan: the 2026 Final exam run with `instructor_pool=none` and one
 * staff member (193 no_candidates + 607 slot_shortage errors, 1 teaching_unchecked warning; trimmed to 3 per code).
 */
import { describe, expect, it } from "vitest";
import type { PlanDetail } from "@/lib/api/invigilation";
import fixture from "./__fixtures__/plan-final-pool-none.json";
import { bySession, filterPosts, fromRows, groupDiagnoses, newRow, parsePostKey, planTone, postDates, rowProblem, suggestionSummary, toRows } from "./invigilation-model";

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
});
