"use client";
/**
 * Planning analytics (backend app/api/v1/analytics.py; services scenario_compare.py and utilisation.py).
 *
 * - `GET /analytics/compare?a=&b=[&week=]`: two stored runs of one term and kind side by side (nothing re-solved).
 * - `GET /analytics/heatmap/rooms`: room x day x period occupancy of one run or of the live board (published runs +
 *   blocks + bookings), grouped by building / room type / capacity band / room.
 * - `GET /analytics/heatmap/instructors`: instructor load of a course run or the term's published course run.
 *
 * Every endpoint also answers CSV (`format=csv`), served as a download through the same-origin proxy, so the
 * links below are plain anchors. The backend returns `dict[str, Any]` (no OpenAPI schema for these), so the
 * types mirror the service output; nothing here invents data. Errors are `detail: {tr, en}` (404 / 409 / 422).
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { buildUrl, HttpError, request, type Query } from "./client";
import { api } from "./endpoints";
import { qk } from "./hooks";
import type { ScheduleRun } from "./schemas";

export interface Pair {
  tr: string;
  en: string;
}

/* ------------------------------------------------------------------ compare */

export interface RunBrief {
  id: number;
  label: string | null;
  kind: "COURSE" | "EXAM";
  status: string;
  horizon: string;
  horizon_params: { week?: number; weeks?: number[] } & Record<string, unknown>;
  is_active: boolean;
  parent_run_id: number | null;
  created_at: string | null;
  finished_at: string | null;
  hard_score: number | null;
  soft_score: number | null;
}

export interface Metric {
  key: string;
  label: Pair;
  a: number | null;
  b: number | null;
  delta: number | null;
  /** "b": the scenario is better, "a": the baseline is better, "same", or null (neutral metric / no value) */
  better: "a" | "b" | "same" | null;
  /** +1 higher is better, -1 lower is better, 0 neutral */
  direction: -1 | 0 | 1;
  /** false: one run has no data for this metric (a week run against a term run): never better / worse (R1-M-10) */
  comparable?: boolean;
}

export interface Place {
  day: number;
  start_period: number;
  end_period: number;
  time: string;
  when: Pair;
  room_ids: number[];
  rooms: string[];
  weeks: number[];
  locked: boolean;
  origin: string | null;
  dates?: string[];
}

export type ChangeKind = "time" | "room" | "time_room" | "weeks" | "split";

export interface ClassItem {
  request_id: number;
  label: string;
  change?: ChangeKind;
  change_text?: Pair;
  a: Place | null;
  b: Place | null;
  instructor_ids?: number[];
  instructor_text?: string | null;
  enrolment?: number | null;
}

export interface LoadStats {
  periods_per_week: number;
  gaps_per_week: number;
  days_per_week: number;
  max_periods_day: number;
  by_day: Record<string, number>;
}

/** course runs: periods / gaps / days per instructor; exam runs: exams per day per named instructor */
export interface CourseInstructorRow {
  instructor_id: number;
  name: string;
  a: LoadStats;
  b: LoadStats;
  delta: { periods_per_week: number; gaps_per_week: number; days_per_week: number };
}
export interface ExamInstructorRow {
  key: string;
  name: string;
  a: { exams: number; max_per_day: number };
  b: { exams: number; max_per_day: number };
  a_dates: Record<string, number>;
  b_dates: Record<string, number>;
}

export interface Occupancy {
  occupied: number;
  capacity: number;
  blocked: number;
  pct: number;
}

export interface RoomDelta {
  room_id: number;
  code: string;
  building: string | null;
  a: { occupied: number; pct: number };
  b: { occupied: number; pct: number };
  delta: { occupied: number; pct: number };
}

export interface RuleRow {
  rule: string;
  label: Pair;
  a: number;
  b: number;
  delta: number;
  /** null when the runs' scopes differ (round-1 R1-M-10) */
  better: "a" | "b" | "same" | null;
  comparable?: boolean;
}

export interface CompareData {
  term_id: number;
  term_code: string;
  kind: "COURSE" | "EXAM";
  a: RunBrief;
  b: RunBrief;
  headline: Pair;
  metrics: Metric[];
  classes: {
    counts: { unchanged: number; moved: number; only_in_a: number; only_in_b: number; unplaced_in_both: number; by_change: Partial<Record<ChangeKind, number>> };
    moved: ClassItem[];
    only_in_a: ClassItem[];
    only_in_b: ClassItem[];
    truncated: boolean;
  };
  requests_in_scope: number;
  instructors: {
    rows: (CourseInstructorRow | ExamInstructorRow)[];
    a: Record<string, number>;
    b: Record<string, number>;
    changed: number;
  };
  rooms: {
    weeks: number[];
    a: Occupancy;
    b: Occupancy;
    by_building: { building: string; a: Occupancy; b: Occupancy }[];
    changed: RoomDelta[];
  };
  rules: RuleRow[];
  waived_rules: { a: string[]; b: string[] };
  diagnoses: { a: Record<string, number>; b: Record<string, number> };
  definitions: Record<string, Pair>;
}

export type ComparePart = "classes" | "instructors" | "rooms" | "rules" | "metrics";

export function isExamRow(r: CourseInstructorRow | ExamInstructorRow): r is ExamInstructorRow {
  return "key" in r && !("instructor_id" in r);
}

/* ------------------------------------------------------------------ room heatmap */

export interface HeatCount {
  occupied: number;
  held: number;
  blocked: number;
  capacity: number;
  pct: number;
  pct_with_blocks: number;
}
export interface HeatCell extends HeatCount {
  col: string;
  period: number;
}
export interface HeatColumn {
  key: string;
  day: number;
  week?: number;
  weeks?: number[];
  date?: string;
  label: Pair;
}
export interface HeatPeriod {
  period: number;
  start: string;
  end: string;
}
export interface HeatRoomRow {
  room_id: number;
  code: string;
  label: Pair;
  capacity: number;
  exam_capacity?: number | null;
  cells: HeatCell[];
  by_col: (HeatCount & { col: string })[];
  by_period: (HeatCount & { period: number })[];
  total: HeatCount;
}
export interface HeatRow {
  key: string;
  label: Pair;
  rooms: number;
  room_ids: number[];
  cells: HeatCell[];
  by_col: (HeatCount & { col: string })[];
  by_period: (HeatCount & { period: number })[];
  total: HeatCount;
  room_rows?: HeatRoomRow[];
}
export interface RoomHeatmap {
  term_id: number;
  term_code: string;
  source: "run" | "board";
  runs: { run_id: number; kind: string; status: string; label: string | null; is_active: boolean }[];
  kind: "COURSE" | "EXAM" | null;
  group_by: GroupBy;
  axis: "day" | "date";
  scope: "week" | "term";
  weeks: number[];
  periods: HeatPeriod[];
  columns: HeatColumn[];
  rows: HeatRow[];
  overall: { rooms: number; cells: HeatCell[]; by_col: (HeatCount & { col: string })[]; by_period: (HeatCount & { period: number })[]; total: HeatCount };
  counted: { assignments: number; blocks: number; bookings: number };
  notes: (Pair | string)[];
  definitions: Record<string, Pair>;
  empty: boolean;
  empty_text: Pair | null;
}
export type GroupBy = "building" | "room_type" | "capacity_band" | "room";
export const GROUP_BY: readonly GroupBy[] = ["building", "room_type", "capacity_band", "room"];

export interface RoomHeatQuery {
  run_id?: number;
  term_id?: number;
  group_by: GroupBy;
  week?: number;
  scope: "week" | "term";
  axis?: "day" | "date";
  bookings: boolean;
  blocks: boolean;
  rooms: boolean;
}

/* ------------------------------------------------------------------ instructor heatmap */

export interface InstructorRow {
  instructor_id: number;
  name: string;
  title: string | null;
  periods_per_week: number;
  gaps_per_week: number;
  days_per_week: number;
  max_periods_day: number;
  max_gaps_day: number;
  longest_block: number;
  by_day: Record<string, number>;
  cells: { day: number; period: number; weeks: number; share: number }[];
}
export interface InstructorHeatmap {
  term_id: number;
  term_code: string;
  source: "run" | "board";
  run_id: number;
  weeks: number[];
  days: { day: number; label: Pair }[];
  periods: HeatPeriod[];
  matrix: { day: number; period: number; instructors: number; pct: number }[];
  instructors_total: number;
  summary: { periods_per_week_mean: number; periods_per_week_max: number; gaps_per_week_total: number; with_gaps: number };
  rows: InstructorRow[];
  truncated: boolean;
  definitions: Record<string, Pair>;
}
export interface InstructorHeatQuery {
  run_id?: number;
  term_id?: number;
  week?: number;
  scope: "week" | "term";
  q?: string;
  limit?: number;
}

/* ------------------------------------------------------------------ run options */

/** runs with a timetable to analyse (a best-effort partial one and an INFEASIBLE run's placements included) */
export const ANALYSABLE: ReadonlySet<string> = new Set(["OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL", "INFEASIBLE"]);

/**
 * The analysable runs of a term (or of every term), newest first: the shared runs query (`qk.runs` + the zod
 * `ScheduleRun`, label included), so a picker here and the runs list read one cache entry.
 */
export function useRunOptions(termId?: number | null) {
  const q = termId !== null && termId !== undefined ? { term_id: termId } : undefined;
  return useQuery({
    queryKey: qk.runs(q),
    queryFn: () => api.runs.list(q),
    retry: noRetry,
    staleTime: 15_000,
    select: (rows: ScheduleRun[]) => [...rows].filter((r) => ANALYSABLE.has(r.status)).sort((x, y) => y.id - x.id),
  });
}

/* ------------------------------------------------------------------ api */

const toQuery = (o: object): Query => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined)) as Query;

export const analyticsApi = {
  compare: (a: number, b: number, week?: number | null) => request<CompareData>("/analytics/compare", { query: { a, b, week: week ?? undefined }, silent: true }),
  rooms: (q: RoomHeatQuery) => request<RoomHeatmap>("/analytics/heatmap/rooms", { query: toQuery(q), silent: true }),
  instructors: (q: InstructorHeatQuery) => request<InstructorHeatmap>("/analytics/heatmap/instructors", { query: toQuery(q), silent: true }),
};

/** same-origin CSV download links (the proxy attaches the session and forwards Content-Disposition) */
export const csvHref = {
  compare: (a: number, b: number, part: ComparePart, week?: number | null) => buildUrl("/analytics/compare", { a, b, week: week ?? undefined, format: "csv", part }),
  rooms: (q: RoomHeatQuery) => buildUrl("/analytics/heatmap/rooms", { ...toQuery(q), format: "csv" }),
  instructors: (q: InstructorHeatQuery) => buildUrl("/analytics/heatmap/instructors", { ...toQuery(q), format: "csv" }),
};

export const ak = {
  compare: (a: number, b: number, week: number | null) => ["analytics", "compare", a, b, week] as const,
  rooms: (q: RoomHeatQuery) => ["analytics", "heat-rooms", q] as const,
  instructors: (q: InstructorHeatQuery) => ["analytics", "heat-instructors", q] as const,
};

/** 4xx answers are final (wrong pair, exam-only term …): no retry, the page shows the backend's words */
export const noRetry = (n: number, e: unknown) => !(e instanceof HttpError && e.status >= 400 && e.status < 500) && n < 2;

export function useCompare(a: number | null, b: number | null, week: number | null) {
  return useQuery({
    queryKey: ak.compare(a ?? 0, b ?? 0, week),
    queryFn: () => analyticsApi.compare(a ?? 0, b ?? 0, week),
    enabled: a !== null && b !== null && a !== b,
    retry: noRetry,
    staleTime: 60_000,
  });
}

export function useRoomHeatmap(q: RoomHeatQuery | null) {
  return useQuery({
    queryKey: ak.rooms(q ?? ({} as RoomHeatQuery)),
    queryFn: () => analyticsApi.rooms(q!),
    enabled: q !== null && (q.run_id !== undefined || q.term_id !== undefined),
    retry: noRetry,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });
}

export function useInstructorHeatmap(q: InstructorHeatQuery | null) {
  return useQuery({
    queryKey: ak.instructors(q ?? ({} as InstructorHeatQuery)),
    queryFn: () => analyticsApi.instructors(q!),
    enabled: q !== null && (q.run_id !== undefined || q.term_id !== undefined),
    retry: noRetry,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });
}

/**
 * The words of a backend refusal in the UI language: `detail: {tr, en}` (analytics, invigilation), a plain
 * string, or `{tr, en, problems[]}` (reassign). Falls back to the HTTP message.
 */
export function errorText(e: unknown, lang: "tr" | "en"): string {
  if (!(e instanceof HttpError)) return e instanceof Error ? e.message : String(e);
  const raw = e.detail as unknown;
  const body = raw && typeof raw === "object" && !Array.isArray(raw) && "detail" in (raw as Record<string, unknown>) ? (raw as Record<string, unknown>).detail : raw;
  if (typeof body === "string" && body) return body;
  if (body && typeof body === "object" && !Array.isArray(body)) {
    const b = body as Record<string, unknown>;
    const text = typeof b[lang] === "string" ? (b[lang] as string) : typeof b.tr === "string" ? (b.tr as string) : typeof b.en === "string" ? (b.en as string) : null;
    if (text) return text;
  }
  return e.message;
}

/** `problems[]` of a 409 reassign refusal (the hard rules the swap would break), else [] */
export function errorProblems(e: unknown): string[] {
  if (!(e instanceof HttpError)) return [];
  const raw = e.detail as unknown;
  const body = raw && typeof raw === "object" && "detail" in (raw as Record<string, unknown>) ? (raw as Record<string, unknown>).detail : raw;
  if (!body || typeof body !== "object" || Array.isArray(body)) return [];
  const p = (body as Record<string, unknown>).problems;
  return Array.isArray(p) ? p.map(String) : [];
}

export const pairOf = (p: Pair | null | undefined, lang: "tr" | "en"): string => (p ? p[lang] || p.tr || p.en || "" : "");
