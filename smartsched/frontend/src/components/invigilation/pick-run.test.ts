/** The default exam run of Gözetmen ataması (real e2e ids: Bahar grid exam board #2, Final solver run #7). */
import { describe, expect, it } from "vitest";
import type { ScheduleRun } from "@/lib/api/schemas";
import { pickExamRun } from "./invigilation-view";

const run = (id: number, term_id: number, kind: "COURSE" | "EXAM", status = "FEASIBLE", is_active = false) => ({ id, term_id, kind, status, is_active }) as ScheduleRun;
const runs = [run(7, 2, "EXAM", "FEASIBLE_PARTIAL"), run(5, 1, "COURSE"), run(4, 2, "EXAM"), run(2, 1, "EXAM")];

describe("pickExamRun", () => {
  it("opens the exam run of the newest plan", () => {
    expect(pickExamRun(runs, 1, 7)?.id).toBe(7);
  });
  it("else the active term's published exam run, else its newest", () => {
    expect(pickExamRun([...runs.slice(0, 3), run(2, 1, "EXAM", "FEASIBLE", true)], 2, null)?.id).toBe(7);
    expect(pickExamRun(runs, 1, null)?.id).toBe(2);
    expect(pickExamRun([run(9, 1, "EXAM", "INFEASIBLE")], 1, null)).toBeUndefined();
  });
});

describe("pickExamRun with imported boards (T-R1-42)", () => {
  // a grid import board (params.source GRID_IMPORT) carries no exam link: never the default while a solved run exists
  const board = (id: number, term_id: number) => ({ id, term_id, kind: "EXAM", status: "FEASIBLE", is_active: false, params: { source: "GRID_IMPORT" }, label: "Grid import: final.xlsx" }) as unknown as ScheduleRun;
  it("prefers the term's solved exam run over its newer imported board", () => {
    expect(pickExamRun([board(9, 3), run(7, 3, "EXAM", "FEASIBLE_PARTIAL")], 3, null)?.id).toBe(7);
    expect(pickExamRun([board(9, 3)], 3, null)?.id).toBe(9);
    expect(pickExamRun([board(9, 3), run(7, 1, "EXAM")], 2, null)?.id).toBe(7);
  });
});
