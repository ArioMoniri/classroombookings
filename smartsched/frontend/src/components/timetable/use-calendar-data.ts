"use client";
/**
 * Term → run → index for the calendar (planner usability M1: open the selected term's latest usable run of
 * the right kind, and a week that run covers).
 */
import { useMemo } from "react";
import { useCalendarIndex } from "@/lib/api/calendar";
import { useRuns, useTerms } from "@/lib/api/hooks";
import type { ScheduleRun, Term } from "@/lib/api/schemas";
import { useUiStore } from "@/stores/ui";
import { buildModel, type CalendarModel } from "./model/index-model";

const USABLE = new Set<ScheduleRun["status"]>(["FEASIBLE", "OPTIMAL", "FEASIBLE_PARTIAL", "TIMEOUT"]);

export function usableRuns(runs: readonly ScheduleRun[] | undefined, termId: number | null): ScheduleRun[] {
  return (runs ?? []).filter((r) => USABLE.has(r.status) && (termId === null || r.term_id === termId)).sort((a, b) => b.id - a.id);
}

/** Latest usable run of the term, of the kind its term implies (exam terms → EXAM runs). */
export function defaultRun(runs: readonly ScheduleRun[], term: Term | undefined): ScheduleRun | undefined {
  const wantExam = term ? term.kind !== "REGULAR" && term.kind !== "SUMMER" : false;
  return runs.find((r) => (r.kind === "EXAM") === wantExam) ?? runs[0];
}

export function useTermContext(): { term: Term | undefined; termId: number | null; terms: Term[] } {
  const terms = useTerms();
  const storeTerm = useUiStore((s) => s.termId);
  const list = useMemo(() => terms.data ?? [], [terms.data]);
  const term = list.find((t) => t.id === storeTerm) ?? list.find((t) => t.is_active) ?? list[0];
  return { term, termId: term?.id ?? null, terms: list };
}

export interface CalendarData {
  term: Term | undefined;
  runs: ScheduleRun[];
  runId: number | null;
  run: ScheduleRun | undefined;
  model: CalendarModel | null;
  loading: boolean;
  error: boolean;
  refetch: () => void;
  noRun: boolean;
}

export function useCalendarData(requestedRun: number | null): CalendarData {
  const { term, termId } = useTermContext();
  const runsQ = useRuns(termId !== null ? { term_id: termId } : undefined);
  const runs = useMemo(() => usableRuns(runsQ.data, termId), [runsQ.data, termId]);
  const run = (requestedRun !== null ? (runsQ.data ?? []).find((r) => r.id === requestedRun) : undefined) ?? defaultRun(runs, term);
  const runId = requestedRun ?? run?.id ?? null;
  const index = useCalendarIndex(runId);
  const model = useMemo(() => (index.data ? buildModel(index.data) : null), [index.data]);
  return {
    term,
    runs,
    runId,
    run,
    model,
    loading: runsQ.isLoading || (runId !== null && index.isLoading),
    error: index.isError,
    refetch: () => void index.refetch(),
    noRun: !runsQ.isLoading && runId === null,
  };
}
