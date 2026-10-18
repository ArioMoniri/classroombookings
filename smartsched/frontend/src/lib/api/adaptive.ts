"use client";
/**
 * AS-16 / AS-17 adaptive analytics (backend app/api/v1/analytics.py; services peaks.py, forecast.py, exam_load.py).
 * Any signed-in viewer reads; the what-if needs PLANNER+.
 *
 * - `GET /analytics/peaks`: weekday x period x group busy share with 80 % ranges and `peak` marks (`format=csv`).
 * - `GET /analytics/forecast/demand`: room demand per group (`requests` computed counts, `seasonal_naive` from a
 *   published term of the same season, or `none` + `needs`).
 * - `GET /analytics/forecast/shortfall`: demand vs suitable supply per (weekday, period, group).
 * - `POST /analytics/forecast/what-if`: today vs the scenario; `solve: true` queues a draft run ("Senaryo: …").
 * - `GET /analytics/forecast/exams`: exam seats per day / slot, invigilators, holds.
 *
 * Every answer has `confidence: high | medium | low | none` and a `needs {tr, en}` sentence when it is thin. A range is
 * calibrated (AS-21) and shown with "düşük güven" beside it while confidence is `low`; `requests` counts get no range.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { buildUrl, HttpError, request } from "./client";

const s = { silent: true } as const;

const Pair = z.object({ tr: z.string().default(""), en: z.string().default("") });
export type Pair = z.infer<typeof Pair>;
const num = z.number().nullable().catch(null);

export const Confidence = z.enum(["high", "medium", "low", "none"]).catch("none");
export type Confidence = z.infer<typeof Confidence>;

/* ------------------------------------------------------------------ peaks */

export const PeakCell = z.object({
  day: z.number(),
  period: z.number(),
  group: z.string().default("*"),
  value: z.number(),
  lo80: z.number().nullable().catch(null),
  hi80: z.number().nullable().catch(null),
  mean: num.optional(),
  n_weeks: z.number().default(0),
  rooms: z.number().default(0),
  seat_fill: num.optional(),
  peak: z.boolean().default(false),
  label: Pair.optional(),
});
export type PeakCell = z.infer<typeof PeakCell>;

export const PEAK_GROUPS = ["building", "campus", "room_type", "capacity_band"] as const;
export type PeakGroup = (typeof PEAK_GROUPS)[number];
export const PEAK_KINDS = ["LECTURE", "EXAM", "MIDTERM", "ADD_DROP", "MAKEUP", "SUMMER"] as const;
export type PeakKind = (typeof PEAK_KINDS)[number];

export const Peaks = z.object({
  term_id: z.number().nullable().catch(null),
  term_code: z.string().nullable().catch(null),
  period_kind: z.string().default("LECTURE"),
  group_by: z.string().default("building"),
  threshold_pct: z.number().default(85),
  weeks: z.array(z.number()).catch([]).default([]),
  rooms: z.number().catch(0).default(0),
  cells: z.array(PeakCell).default([]),
  peaks: z.array(PeakCell).default([]),
  period_profile: z.array(z.object({ period: z.number(), value: z.number() })).catch([]).default([]),
  method: z.string().default("none"),
  basis: Pair.nullable().catch(null).optional(),
  confidence: Confidence,
  confidence_label: Pair.nullable().catch(null).optional(),
  needs: Pair.nullable().catch(null).optional(),
});
export type Peaks = z.infer<typeof Peaks>;

export interface PeaksQuery {
  term_id?: number | null;
  group_by?: PeakGroup;
  period_kind?: PeakKind;
  threshold?: number;
}

/* ------------------------------------------------------------------ forecast */

export const ForecastCell = z.object({
  key: z.string(),
  label: z.union([Pair, z.string()]).optional(),
  value: z.number(),
  lo80: z.number().nullable().catch(null),
  hi80: z.number().nullable().catch(null),
  method: z.string().default("none"),
  basis: Pair.nullable().catch(null).optional(),
  confidence: Confidence,
  needs: Pair.nullable().catch(null).optional(),
});
export type ForecastCell = z.infer<typeof ForecastCell>;

export const FORECAST_GROUPS = ["building", "weekday", "period", "tag", "capacity_band"] as const;
export type ForecastGroup = (typeof FORECAST_GROUPS)[number];

export const DemandForecast = z.object({
  term_id: z.number().nullable().catch(null),
  term_code: z.string().nullable().catch(null),
  group_by: z.string().default("building"),
  unit: Pair.nullable().catch(null).optional(),
  method: z.string().default("none"),
  basis: Pair.nullable().catch(null).optional(),
  confidence: Confidence,
  needs: Pair.nullable().catch(null).optional(),
  cells: z.array(ForecastCell).default([]),
  total: z.number().nullable().catch(null).optional(),
});
export type DemandForecast = z.infer<typeof DemandForecast>;

export const ShortfallCell = z.object({
  day: z.number(),
  period: z.number(),
  group: z.string().default("*"),
  demand: z.number().default(0),
  supply: z.number().default(0),
  load_pct: num.optional(),
  shortfall: z.number().default(0),
  p_shortfall: num.optional(),
  competing: z.array(z.string()).catch([]).default([]),
});
export type ShortfallCell = z.infer<typeof ShortfallCell>;

export const Shortfall = z.object({
  method: z.string().default("none"),
  confidence: Confidence,
  basis: Pair.nullable().catch(null).optional(),
  needs: Pair.nullable().catch(null).optional(),
  no_fit: z.number().catch(0).default(0),
  cells: z.array(ShortfallCell).default([]),
});
export type Shortfall = z.infer<typeof Shortfall>;

export const FitReport = z.object({
  classes: z.number().catch(0).default(0),
  no_fit: z.number().catch(0).default(0),
  shortfall_cells: z.number().catch(0).default(0),
  shortfall_total: z.number().catch(0).default(0),
});
export type FitReport = z.infer<typeof FitReport>;

export const WhatIfOut = z.object({
  scenario: z.object({ label: Pair.optional() }).passthrough().optional(),
  method: z.string().default("none"),
  confidence: Confidence,
  needs: Pair.nullable().catch(null).optional(),
  today: FitReport,
  what_if: FitReport,
  delta: z.object({ no_fit: z.number().catch(0).default(0), shortfall_total: z.number().catch(0).default(0) }).catch({ no_fit: 0, shortfall_total: 0 }),
  run_id: z.number().nullable().catch(null).optional(),
});
export type WhatIfOut = z.infer<typeof WhatIfOut>;

export type WhatIfScope = "all" | "faculty" | "program";
export interface WhatIfIn {
  term_id: number;
  enrolment_pct: number;
  scope: WhatIfScope;
  scope_value?: string;
  rooms_closed?: number[];
  extra_sections?: number;
  solve: boolean;
}

/* ------------------------------------------------------------------ exams */

export const ExamDay = z.object({ date: z.string(), label: Pair.optional(), exams: z.number().default(0), seats: z.number().default(0) });
export type ExamDay = z.infer<typeof ExamDay>;
export const ExamSlot = z.object({
  date: z.string(),
  period: z.number(),
  exams: z.number().default(0),
  seats: z.number().default(0),
  exam_capacity: num.optional(),
  seat_pct: num.optional(),
  invigilators: num.optional(),
  pool: num.optional(),
  invigilators_short: num.optional(),
});
export type ExamSlot = z.infer<typeof ExamSlot>;

export const ExamForecast = z.object({
  method: z.string().default("none"),
  confidence: Confidence,
  needs: Pair.nullable().catch(null).optional(),
  basis: Pair.nullable().catch(null).optional(),
  days: z.array(ExamDay).catch([]).default([]),
  peak_day: z.string().nullable().catch(null).optional(),
  peak_label: Pair.nullable().catch(null).optional(),
  peak_exams: num.optional(),
  weekday_mean: num.optional(),
  peak_to_mean: num.optional(),
  slots: z.array(ExamSlot).catch([]).default([]),
  peak_slot: ExamSlot.nullable().catch(null).optional(),
  holds: z
    .object({
      exam_run_id: num.optional(),
      buffer_periods: num.optional(),
      rooms: num.optional(),
      days: num.optional(),
      held_room_periods: num.optional(),
      closed_room_periods: num.optional(),
      freed_room_periods: num.optional(),
    })
    .nullable()
    .catch(null)
    .optional(),
});
export type ExamForecast = z.infer<typeof ExamForecast>;

/* ------------------------------------------------------------------ api + hooks */

export const adaptiveApi = {
  peaks: (q: PeaksQuery) => request("/analytics/peaks", { query: { ...q }, schema: Peaks, ...s }),
  peaksCsvUrl: (q: PeaksQuery) => buildUrl("/analytics/peaks", { ...q, format: "csv" }),
  demand: (termId: number | null, groupBy: ForecastGroup) => request("/analytics/forecast/demand", { query: { term_id: termId, group_by: groupBy }, schema: DemandForecast, ...s }),
  shortfall: (termId: number) => request("/analytics/forecast/shortfall", { query: { term_id: termId, peaks_only: true }, schema: Shortfall, ...s }),
  whatIf: (body: WhatIfIn) => request("/analytics/forecast/what-if", { method: "POST", body, schema: WhatIfOut, ...s }),
  exams: (termId: number) => request("/analytics/forecast/exams", { query: { term_id: termId }, schema: ExamForecast, ...s }),
};

const noRetry = (n: number, e: unknown) => !(e instanceof HttpError && [401, 403, 404, 422].includes(e.status)) && n < 2;

export const adaptiveKeys = {
  peaks: (q: PeaksQuery) => ["adaptive", "peaks", q.term_id ?? null, q.group_by ?? "building", q.period_kind ?? "LECTURE", q.threshold ?? null] as const,
  demand: (termId: number | null, g: string) => ["adaptive", "demand", termId, g] as const,
  shortfall: (termId: number | null) => ["adaptive", "shortfall", termId] as const,
  exams: (termId: number | null) => ["adaptive", "exams", termId] as const,
};

export function usePeaks(q: PeaksQuery, enabled = true) {
  return useQuery({ queryKey: adaptiveKeys.peaks(q), queryFn: () => adaptiveApi.peaks(q), enabled, retry: noRetry, staleTime: 5 * 60_000 });
}
export function useDemandForecast(termId: number | null, groupBy: ForecastGroup, enabled = true) {
  return useQuery({ queryKey: adaptiveKeys.demand(termId, groupBy), queryFn: () => adaptiveApi.demand(termId, groupBy), enabled, retry: noRetry, staleTime: 5 * 60_000 });
}
export function useShortfall(termId: number | null) {
  return useQuery({ queryKey: adaptiveKeys.shortfall(termId), queryFn: () => adaptiveApi.shortfall(termId ?? 0), enabled: termId !== null, retry: noRetry, staleTime: 5 * 60_000 });
}
export function useExamForecast(termId: number | null) {
  return useQuery({ queryKey: adaptiveKeys.exams(termId), queryFn: () => adaptiveApi.exams(termId ?? 0), enabled: termId !== null, retry: noRetry, staleTime: 5 * 60_000 });
}
export function useWhatIf() {
  return useMutation({ mutationFn: (body: WhatIfIn) => adaptiveApi.whatIf(body) });
}

/* ------------------------------------------------------------------ pure helpers (tested) */

/**
 * AS-21 (API.md): `lo80` / `hi80` are calibrated (split conformal), so a range is shown whenever it is a range; it is
 * never shown for `requests` cells (computed counts, lo == hi) or an empty answer (`none`).
 */
export function showRange(c: { lo80: number | null; hi80: number | null; confidence: Confidence; method?: string }): boolean {
  if (c.lo80 === null || c.hi80 === null || c.lo80 === c.hi80) return false;
  if (c.method === "requests" || c.confidence === "none") return false;
  return true;
}

/** "düşük güven" goes beside the range whenever the backend says `low` (one published term of the season); never on
 *  computed `requests` counts. `medium` appears only once two published terms of a season exist. */
export function lowConfidence(c: { confidence: Confidence; method?: string }): boolean {
  return c.confidence === "low" && c.method !== "requests";
}

/** ISO weekday 1..7 of an ISO date (no time zone shift: the date is a calendar day) */
export function isoWeekday(date: string): number {
  const [y, m, d] = date.split("-").map(Number);
  const wd = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1)).getUTCDay();
  return wd === 0 ? 7 : wd;
}

export interface PeakHit {
  /** the peak cells the asked span touches */
  hits: PeakCell[];
  /** the nearest off-peak start period of the same day for the same length, or null */
  alternative: { start: number; end: number } | null;
}

/**
 * The find-room "Yoğun saat" chip: does the asked (weekday, periods) touch a peak cell (any group)? Then the nearest
 * span of the same length on the same day with no peak cell, scanning outwards from the asked start.
 */
export function peakHit(cells: readonly PeakCell[], day: number, start: number, end: number, maxPeriod = 18): PeakHit {
  const peakAt = new Set(cells.filter((c) => c.day === day && c.peak).map((c) => c.period));
  const known = new Set(cells.filter((c) => c.day === day).map((c) => c.period));
  const hits = cells.filter((c) => c.day === day && c.peak && c.period >= start && c.period <= end);
  if (!hits.length) return { hits: [], alternative: null };
  const len = end - start;
  const free = (a: number) => {
    for (let p = a; p <= a + len; p++) if (peakAt.has(p) || !known.has(p)) return false;
    return true;
  };
  for (let step = 1; step < maxPeriod; step++) {
    for (const a of [start - step, start + step]) {
      if (a >= 1 && a + len <= maxPeriod && free(a)) return { hits, alternative: { start: a, end: a + len } };
    }
  }
  return { hits, alternative: null };
}
