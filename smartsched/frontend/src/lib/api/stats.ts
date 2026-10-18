"use client";
/**
 * Read-only statistics aggregates for the charts lane (CH-07, CH-10, CH-11; docs/design/v3/charts.md §4 rows 5, 6,
 * 15, 19 and §13). On 2026-10-18 none of these three routes exists in the backend yet; the exact specs are the asks
 * in the ch-m-2026-10-18 report and in charts.md "CH-07 … CH-11 notes". Until a route lands, the server answers
 * 404 "Not Found" (FastAPI's unknown-route body) and the caller shows an honest "veri yok" state: never invented
 * numbers. `isMissingRoute` tells that case apart from a real refusal (403, a 404 with a coded detail, 5xx).
 */
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { HttpError, request } from "./client";

const isoDay = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const count = z.number().int().nonnegative();

/** `GET /bookings/stats/weekly?term_id=` (permission `bookings.admin`) */
export const WeeklyBookingStats = z.object({
  term_id: z.number(),
  from: isoDay,
  to: isoDay,
  today: isoDay,
  weeks: z.array(
    z.object({
      /** the term's week number, 1-based */
      week: z.number().int().positive(),
      start: isoDay,
      end: isoDay,
      exam: z.boolean().default(false),
      /** the week contains today and is not over */
      partial: z.boolean().default(false),
      bookings: count,
      requests: z.object({ approved: count, rejected: count, pending: count }).default({ approved: 0, rejected: 0, pending: 0 }),
    }),
  ),
});
export type WeeklyBookingStats = z.infer<typeof WeeklyBookingStats>;

/** `GET /audit/stats/daily?days=30` (permission `audit.view`; days in Europe/Istanbul) */
export const DailyAuditStats = z.object({
  from: isoDay,
  to: isoDay,
  days: z.array(z.object({ day: isoDay, events: count })),
});
export type DailyAuditStats = z.infer<typeof DailyAuditStats>;

/** `GET /me/load?term_id=` (signed in; only the caller's own linked instructor record) */
export const MyLoad = z.object({
  linked: z.boolean(),
  instructor_id: z.number().nullable().default(null),
  term_id: z.number().nullable().default(null),
  /** the published (active) run the load is read from; null = nothing published yet */
  run_id: z.number().nullable().default(null),
  /** ISO weekday 1 = Monday … 7 = Sunday; periods a week on that day */
  days: z.array(z.object({ day: z.number().int().min(1).max(7), periods: count, minutes: count.default(0) })).default([]),
  total_periods: count.default(0),
});
export type MyLoad = z.infer<typeof MyLoad>;

/** The route does not exist on this server (yet): FastAPI's bare 404 "Not Found", 405 or 501. */
export function isMissingRoute(e: unknown): boolean {
  if (!(e instanceof HttpError)) return false;
  if (e.status === 405 || e.status === 501) return true;
  return e.status === 404 && (e.detail === "Not Found" || e.detail === undefined || e.message === "Not Found");
}

const noRetry = (n: number, e: unknown) => !(e instanceof HttpError && e.status >= 400 && e.status < 500) && n < 2;

export const statsApi = {
  bookingsWeekly: (termId: number) => request("/bookings/stats/weekly", { query: { term_id: termId }, schema: WeeklyBookingStats, silent: true }),
  auditDaily: (days = 30) => request("/audit/stats/daily", { query: { days }, schema: DailyAuditStats, silent: true }),
  myLoad: (termId: number | null) => request("/me/load", { query: { term_id: termId ?? undefined }, schema: MyLoad, silent: true }),
};

export const statsKeys = {
  bookingsWeekly: (termId: number | null) => ["stats", "bookings-weekly", termId] as const,
  auditDaily: (days: number) => ["stats", "audit-daily", days] as const,
  myLoad: (termId: number | null) => ["stats", "me-load", termId] as const,
};

export function useWeeklyBookingStats(termId: number | null, enabled = true) {
  return useQuery({ queryKey: statsKeys.bookingsWeekly(termId), queryFn: () => statsApi.bookingsWeekly(termId ?? 0), enabled: enabled && termId !== null, retry: noRetry, staleTime: 60_000 });
}

export function useDailyAuditStats(days = 30, enabled = true) {
  return useQuery({ queryKey: statsKeys.auditDaily(days), queryFn: () => statsApi.auditDaily(days), enabled, retry: noRetry, staleTime: 60_000 });
}

export function useMyLoad(termId: number | null, enabled = true) {
  return useQuery({ queryKey: statsKeys.myLoad(termId), queryFn: () => statsApi.myLoad(termId), enabled, retry: noRetry, staleTime: 60_000 });
}
