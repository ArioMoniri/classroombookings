import type { ScheduleRun } from "@/lib/api/schemas";

/** An imported published board (grid import) rather than a solver run: it has no solver stats. The run
 * schema drops `params.source`, so this reads the stats the solver always writes (`solver`, `events`). */
export function isImportBoard(r: ScheduleRun): boolean {
  return r.stats.solver === undefined && r.stats.events === undefined && r.prompt_text === null && r.diagnosis.length === 0;
}
