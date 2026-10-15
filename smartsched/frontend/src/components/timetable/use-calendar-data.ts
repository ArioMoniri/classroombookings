"use client";
/**
 * Term → run → index for the calendar (planner usability M1: open the selected term's latest usable run of
 * the right kind, and a week that run covers).
 */
import { useMemo } from "react";
import { useCalendarIndex } from "@/lib/api/calendar";
import { HttpError } from "@/lib/api/client";
import { useHydrated } from "@/lib/use-hydrated";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { useRun, useRuns } from "@/lib/api/hooks";
import type { ScheduleRun, Term } from "@/lib/api/schemas";
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

/** The shell's working term (session pick → remembered → current by date), unless a deep-linked run says otherwise. */
export function useTermContext(runTermId?: number | null): { term: Term | undefined; termId: number | null; terms: Term[] } {
  const active = useActiveTerm();
  // the query cache is restored on the client before hydration; render the term only after it (no SSR mismatch)
  const hydrated = useHydrated();
  const found = (runTermId ? active.terms.find((t) => t.id === runTermId) : undefined) ?? active.term;
  const term = hydrated ? found : undefined;
  return { term, termId: term?.id ?? null, terms: hydrated ? active.terms : [] };
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
  /** GET /runs, the deep-linked run or its index answered 403: the role has no planning access (U-02) */
  forbidden: boolean;
}

export const isForbidden = (e: unknown): boolean => e instanceof HttpError && e.status === 403;

/**
 * The page state from the queries. A 403 is "no access", never "no timetable" (a Teacher used to see the
 * planner empty state with Generate / Import); any other /runs failure is an error with retry.
 */
export function calendarFlags(q: { hydrated: boolean; runsPending: boolean; runsError: unknown; requestedError: unknown; indexError: unknown; indexPending: boolean; runId: number | null }): { loading: boolean; error: boolean; noRun: boolean; forbidden: boolean } {
  const forbidden = [q.runsError, q.requestedError, q.indexError].some(isForbidden);
  const runsFailed = Boolean(q.runsError);
  return {
    forbidden,
    loading: !forbidden && (!q.hydrated || q.runsPending || (q.runId !== null && q.indexPending)),
    error: !forbidden && (runsFailed || Boolean(q.indexError)),
    noRun: !forbidden && !runsFailed && q.hydrated && !q.runsPending && q.runId === null,
  };
}

export function useCalendarData(requestedRun: number | null): CalendarData {
  const requested = useRun(requestedRun);
  // server render and the client's first render must agree (the query cache is restored before hydration)
  const hydrated = useHydrated();
  const { term, termId } = useTermContext(requested.data?.term_id ?? null);
  const runsQ = useRuns(termId !== null ? { term_id: termId } : undefined);
  const runs = useMemo(() => usableRuns(runsQ.data, termId), [runsQ.data, termId]);
  // the default run waits for hydration: the restored cache must not pick a run the server could not
  const run = (requestedRun !== null ? (runsQ.data ?? []).find((r) => r.id === requestedRun) : undefined) ?? (hydrated ? defaultRun(runs, term) : undefined);
  const runId = requestedRun ?? run?.id ?? null;
  const index = useCalendarIndex(runId);
  const model = useMemo(() => (index.data ? buildModel(index.data) : null), [index.data]);
  const flags = calendarFlags({ hydrated, runsPending: runsQ.isPending, runsError: runsQ.error, requestedError: requested.error, indexError: index.error, indexPending: index.isPending, runId });
  return {
    term,
    runs,
    runId,
    run,
    model,
    ...flags,
    refetch: () => {
      if (runsQ.isError) void runsQ.refetch();
      void index.refetch();
    },
  };
}
