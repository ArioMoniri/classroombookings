"use client";
/**
 * RF-16 / RF-16b: the university's period grid (`GET /period-grid`, edited on /admin/schedules, RF-09) replaces the
 * built-in `@/lib/time` grid at runtime. Nothing waits for it (orchestrator decision 2026-10-18):
 *
 * - The page renders at once with the grid this device saw last (localStorage, applied in a layout effect right
 *   after hydration, before the first paint) or, on a first visit, the built-in `DEFAULT_PERIODS`.
 * - `GET /period-grid` is read on every load. A different grid is applied in place (`applyPeriodGrid` bumps the
 *   version store in `@/lib/time`), so the views that subscribe (`usePeriodGridVersion`: timetable grid, day
 *   timeline, agenda, classes, find-room) re-render with the new times; nothing remounts, so focus, scroll and
 *   typed text stay. The answer is written to the cache for the next visit.
 * - An error (or an unreadable answer) keeps whatever is showing; the cache is left as it was.
 * - An edit on /admin/schedules writes the same query (`periodGridKey`), so it applies the same way.
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, type ReactNode } from "react";
import { request } from "@/lib/api/client";
import { PeriodGrid, periodGridKey } from "@/lib/api/rf-admin";
import { applyPeriodGrid } from "@/lib/time";
import { useHydrated } from "@/lib/use-hydrated";

export { usePeriodGridVersion } from "@/lib/time";

export const PERIOD_GRID_CACHE_KEY = "smartsched.periodGrid";

type Rows = readonly { start: string; end: string }[];

function readCache(): void {
  try {
    const raw = window.localStorage.getItem(PERIOD_GRID_CACHE_KEY);
    if (raw) applyPeriodGrid(JSON.parse(raw) as Rows);
  } catch {
    /* unreadable cache: the defaults stay */
  }
}

function writeCache(rows: Rows): void {
  try {
    window.localStorage.setItem(PERIOD_GRID_CACHE_KEY, JSON.stringify(rows.map((r) => ({ start: r.start, end: r.end }))));
  } catch {
    /* private mode / full storage: the next visit starts with the defaults */
  }
}

export function PeriodGridGate({ children }: { children: ReactNode }) {
  const hydrated = useHydrated();
  // the device's cached grid, read once on mount (after hydration, before paint: no flash of the defaults for a
  // returning person, and the server-rendered HTML always matches the built-in grid)
  useLayoutEffect(readCache, []);
  const q = useQuery({
    queryKey: periodGridKey,
    queryFn: () => request("/period-grid", { schema: PeriodGrid, silent: true }),
    enabled: hydrated,
    retry: false,
    staleTime: 5 * 60_000,
  });
  const rows = q.data?.periods;
  // module state (an external store) is changed in an effect, never during render; subscribers re-render from it
  useEffect(() => {
    if (rows && applyPeriodGrid(rows)) writeCache(rows);
  }, [rows]);
  return <>{children}</>;
}
