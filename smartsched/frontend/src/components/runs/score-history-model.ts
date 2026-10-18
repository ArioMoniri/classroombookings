// CH-08 (docs/design/v3/charts.md §4 row 12): the soft score across this term's finished course runs, for the
// line on /runs. Only runs with a usable timetable and a score count (OPTIMAL, FEASIBLE, FEASIBLE_PARTIAL); cancelled,
// failed, running and queued runs, exam runs (another scale) and imported boards (no solver score) are left out.
// Ordered by `finished_at`. Pure. Original work.
import type { ChartFormat } from "@/components/charts/chart-format";
import type { Translate } from "@/components/charts/chart-summary";
import type { ScheduleRun } from "@/lib/api/schemas";
import { isImportBoard } from "./run-kinds";

/** fewer finished runs than this → no chart at all (the ticket: "else nothing") */
export const MIN_RUNS = 3;
const USABLE = new Set(["OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL"]);

export interface ScorePoint {
  /** "#12": the bucket */
  label: string;
  id: number;
  soft: number;
  finished: string;
  active: boolean;
  [key: string]: unknown;
}

export function scoreHistory(runs: readonly ScheduleRun[] | undefined): ScorePoint[] {
  return (runs ?? [])
    .filter((r) => r.kind === "COURSE" && USABLE.has(r.status) && r.soft_score !== null && r.finished_at !== null && !isImportBoard(r))
    .sort((a, b) => a.finished_at!.localeCompare(b.finished_at!) || a.id - b.id)
    .map((r) => ({ label: `#${r.id}`, id: r.id, soft: r.soft_score!, finished: r.finished_at!, active: r.is_active === true }));
}

export function scoreSummary(points: readonly ScorePoint[], t: Translate, f: ChartFormat): string {
  const last = points.at(-1);
  if (!last) return "";
  const best = points.reduce((b, p) => (p.soft > b.soft ? p : b), points[0]!);
  const active = points.find((p) => p.active);
  return [
    active ? t("charts.runs.active", { run: active.label, score: f.num(active.soft) }) : "",
    t("charts.runs.summary", { last: last.label, score: f.num(last.soft), best: best.label, bestScore: f.num(best.soft) }),
  ]
    .filter(Boolean)
    .join(" ");
}
