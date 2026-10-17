/**
 * Pure choices of the dashboard (unit-tested): which run the hero talks about. The published (is_active) run of
 * the term comes first, whatever its origin: an imported board that is published *is* the term's plan
 * (round-1 T-R1-39; the room heatmap and the room-use number read the same board). Without one, the newest
 * finished solver run (course first); an unpublished import board is a source, not a plan.
 */
import { isImportBoard } from "@/components/runs/runs-list";
import type { ScheduleRun } from "@/lib/api/schemas";

const DONE = new Set<ScheduleRun["status"]>(["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL", "INFEASIBLE", "TIMEOUT"]);

export function latestPlan(runs: readonly ScheduleRun[] | undefined): ScheduleRun | undefined {
  if (!runs) return undefined;
  const live = runs.filter((r) => r.is_active);
  const solved = runs.filter((r) => DONE.has(r.status) && !isImportBoard(r));
  return live.find((r) => r.kind === "COURSE") ?? live[0] ?? solved.find((r) => r.kind === "COURSE") ?? solved[0];
}

/** the week the hero shows: the one the person picked, else the week the server measured (today's week, or the
 *  closest week the published plan covers when today lies outside it), else today's week */
export function shownWeek(remembered: number | undefined, measured: number | undefined, today: number, last: number): number {
  return Math.min(last, Math.max(1, remembered ?? measured ?? today));
}
