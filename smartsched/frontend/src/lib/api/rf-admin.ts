"use client";
/**
 * RF-06 / RF-08 / RF-09 clients (backend rf-b-2026-10-18): the import preview and its one apply, the import file
 * download, the university period grid (P1-P18 clock times) and the term week calendar (one week at a time).
 * Errors keep the server's `{code, message_tr, message_en}` detail: callers show it with `serverMessage`.
 */
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import * as adapt from "./adapters";
import { API_PREFIX, request } from "./client";
import { ImportJob } from "./schemas";
import { waitForImport } from "./shell-extra";

const ImportOne = z.preprocess(adapt.importJob, ImportJob);

/* ------------------------------------------------------------------ import preview (RF-06) */

export type OnConflict = "keep" | "take";

const DiffConflict = z.object({
  field: z.string().nullable().optional(),
  planner: z.unknown().optional(),
  file: z.unknown().optional(),
  previous_import: z.unknown().optional(),
  resolution: z.string().nullable().optional(),
});
const DiffRow = z.object({
  change: z.enum(["create", "update", "conflict"]),
  entity: z.string(),
  id: z.union([z.number(), z.string()]).nullable().optional(),
  key: z.string().nullable().optional(),
  fields: z.array(z.object({ field: z.string(), from: z.unknown().optional(), to: z.unknown().optional() })).optional().default([]),
  conflicts: z.array(DiffConflict).optional().default([]),
});
const DiffCounts = z.object({ create: z.number().default(0), update: z.number().default(0), unchanged: z.number().default(0), conflict: z.number().default(0) });
export const ImportDiff = z.object({
  on_conflict: z.string().nullable().optional(),
  counts: z.record(z.string(), DiffCounts).default({}),
  rows: z.array(DiffRow).default([]),
  rows_total: z.number().default(0),
  conflicts_total: z.number().default(0),
});
export type ImportDiff = z.infer<typeof ImportDiff>;
export type ImportDiffRow = z.infer<typeof DiffRow>;

/** `summary.diff` of a finished preview, or null when the job has none (an older job, a failed parse). */
export function importDiff(job: Pick<ImportJob, "summary"> | null | undefined): ImportDiff | null {
  const parsed = ImportDiff.safeParse(job?.summary.diff);
  return parsed.success ? parsed.data : null;
}

/** Totals over every entity of the diff. */
export function diffTotals(diff: ImportDiff): { create: number; update: number; unchanged: number; conflict: number } {
  const out = { create: 0, update: 0, unchanged: 0, conflict: 0 };
  for (const c of Object.values(diff.counts)) {
    out.create += c.create;
    out.update += c.update;
    out.unchanged += c.unchanged;
    out.conflict += c.conflict;
  }
  return out;
}

export const importPreviewApi = {
  get: (id: number) => request(`/imports/${id}`, { schema: ImportOne, silent: true }),
  /** `POST /imports/{id}/apply` once, then wait for the new job to finish (its report). Refusals are thrown. */
  apply: async (previewId: number, onConflict: OnConflict | null, signal?: AbortSignal) => {
    const job = await request(`/imports/${previewId}/apply`, { method: "POST", body: { on_conflict: onConflict }, schema: ImportOne, silent: true, signal });
    return waitForImport(job, signal);
  },
  /** the workbook of an import (upload, CLI or seed); planners only */
  fileUrl: (id: number) => `${API_PREFIX}/imports/${id}/file`,
};

/* ------------------------------------------------------------------ period grid (RF-09) */

const GridPeriod = z.object({ index: z.number(), start: z.string(), end: z.string(), label: z.string().optional() });
export const PeriodGrid = z.object({
  source: z.string(),
  count: z.number(),
  periods: z.array(GridPeriod),
  default: z.array(GridPeriod),
  booking_periods_updated: z.number().optional(),
});
export type PeriodGrid = z.infer<typeof PeriodGrid>;
export const PERIOD_COUNT = 18;

export const periodGridKey = ["period-grid"] as const;
export const periodGridApi = {
  get: () => request("/period-grid", { schema: PeriodGrid }),
  save: (periods: { start: string; end: string }[]) => request("/period-grid", { method: "PUT", body: { periods }, schema: PeriodGrid, silent: true }),
  reset: () => request("/period-grid", { method: "DELETE", schema: PeriodGrid, silent: true }),
};
export const usePeriodGrid = () => useQuery({ queryKey: periodGridKey, queryFn: periodGridApi.get, retry: false });

/** The period a grid refusal names ("P3 …" in `message_tr` / `message_en`), or null. */
export function periodOfMessage(message: string | null | undefined): number | null {
  const m = /\bP(\d{1,2})\b/.exec(message ?? "");
  const n = m ? Number(m[1]) : NaN;
  return n >= 1 && n <= PERIOD_COUNT ? n : null;
}

/* ------------------------------------------------------------------ term week calendar (RF-09) */

export const TERM_WEEK_KINDS = ["LECTURE", "EXAM", "HOLIDAY", "MAKEUP"] as const;
export type TermWeekKind = (typeof TERM_WEEK_KINDS)[number];
export const TermWeek = z.object({
  id: z.number(),
  term_id: z.number(),
  index: z.number(),
  start_date: z.string().nullable(),
  kind: z.string(),
  label: z.string().nullable(),
  edited: z.boolean().optional().default(false),
});
export type TermWeek = z.infer<typeof TermWeek>;
export interface TermWeekIn {
  index: number;
  start_date: string | null;
  kind: string;
  label: string | null;
}

/** under the shared ["weeks", termId] prefix: a change invalidates the timetable's week list too */
export const termWeeksKey = (termId: number) => ["weeks", termId, "admin"] as const;
export const termWeeksApi = {
  list: (termId: number) => request(`/terms/${termId}/weeks`, { schema: z.array(TermWeek) }),
  patch: (termId: number, index: number, body: Partial<Pick<TermWeekIn, "kind" | "label" | "start_date">>) =>
    request(`/terms/${termId}/weeks/${index}`, { method: "PATCH", body, schema: TermWeek, silent: true }),
  replace: (termId: number, weeks: TermWeekIn[]) => request(`/terms/${termId}/weeks`, { method: "PUT", body: weeks, schema: z.array(TermWeek), silent: true }),
};
export const useTermWeeks = (termId: number | undefined) =>
  useQuery({ queryKey: termWeeksKey(termId ?? 0), queryFn: () => termWeeksApi.list(termId ?? 0), enabled: termId !== undefined, retry: false });
