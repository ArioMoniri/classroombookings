"use client";
/**
 * RF-16: the university's period grid (`GET /period-grid`, edited on /admin/schedules, RF-09) is read once in the
 * app shell before the first screen that shows times, and replaces the built-in `@/lib/time` grid at runtime.
 *
 * - The page waits (the same skeleton as HydrationGate) until the grid answered, with a 1.5 s ceiling; on an error
 *   or a timeout the built-in times stay (the fallback).
 * - The last grid this device saw is kept in localStorage and applied at once on the next visit, so a returning
 *   person does not wait; the request still refreshes it.
 * - An edit on /admin/schedules writes the same query (`periodGridKey`), so the next screen opened shows it.
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { request } from "@/lib/api/client";
import { PeriodGrid, periodGridKey } from "@/lib/api/rf-admin";
import { applyPeriodGrid, periodGridVersion, subscribePeriodGrid } from "@/lib/time";
import { useHydrated } from "@/lib/use-hydrated";

export const PERIOD_GRID_CACHE_KEY = "smartsched.periodGrid";
const WAIT_MS = 1500;

function readCache(): boolean {
  try {
    const raw = window.localStorage.getItem(PERIOD_GRID_CACHE_KEY);
    return raw ? applyPeriodGrid(JSON.parse(raw) as { start: string; end: string }[]) : false;
  } catch {
    return false;
  }
}

function writeCache(rows: readonly { start: string; end: string }[]): void {
  try {
    window.localStorage.setItem(PERIOD_GRID_CACHE_KEY, JSON.stringify(rows.map((r) => ({ start: r.start, end: r.end }))));
  } catch {
    /* private mode / full storage: the next visit waits for the request again */
  }
}

/** The grid version: components that keep derived values can subscribe to it. */
export function usePeriodGridVersion(): number {
  return useSyncExternalStore(subscribePeriodGrid, periodGridVersion, () => 0);
}

export function PeriodGridGate({ children }: { children: ReactNode }) {
  const hydrated = useHydrated();
  // the cached grid is applied in the first client effect pass (never during SSR or the hydration render)
  const [cached, setCached] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const q = useQuery({
    queryKey: periodGridKey,
    queryFn: () => request("/period-grid", { schema: PeriodGrid, silent: true }),
    enabled: hydrated,
    retry: false,
    staleTime: 5 * 60_000,
  });
  useEffect(() => {
    if (!hydrated) return;
    if (readCache()) setCached(true);
    const id = window.setTimeout(() => setTimedOut(true), WAIT_MS);
    return () => window.clearTimeout(id);
  }, [hydrated]);
  const rows = q.data?.periods;
  // the server's grid is applied in an effect (module state, never during render), then the page renders with it
  const [appliedFor, setAppliedFor] = useState<unknown>(null);
  useEffect(() => {
    if (!rows) return;
    if (applyPeriodGrid(rows)) writeCache(rows);
    setAppliedFor(rows);
  }, [rows]);
  const ready = hydrated && (cached || timedOut || q.isError || (!!rows && appliedFor === rows));
  if (!ready)
    return (
      <div aria-hidden className="space-y-4" data-testid="period-grid-wait">
        <Skeleton className="h-10 w-64 rounded-xl" />
        <Skeleton className="h-48 rounded-2xl" />
      </div>
    );
  return <>{children}</>;
}

