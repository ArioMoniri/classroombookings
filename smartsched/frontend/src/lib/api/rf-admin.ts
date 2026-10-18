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
/** a composite primary key (section_instructors) arrives as one "a:b" string; older previews sent an array (E2EA-F03) */
const DiffId = z.preprocess((v) => (Array.isArray(v) ? v.map(String).join(":") : v), z.union([z.number(), z.string()]).nullable().optional());
const DiffRow = z.object({
  /** archive (FIX-J E2EA2-F01): the file no longer has the row, so the import archives it */
  change: z.enum(["create", "update", "archive", "conflict"]),
  entity: z.string(),
  id: DiffId,
  key: z.string().nullable().optional(),
  fields: z.array(z.object({ field: z.string(), from: z.unknown().optional(), to: z.unknown().optional() })).optional().default([]),
  conflicts: z.array(DiffConflict).optional().default([]),
});
const DiffCounts = z.object({ create: z.number().default(0), update: z.number().default(0), archive: z.number().default(0), unchanged: z.number().default(0), conflict: z.number().default(0) });
export const ImportDiff = z.object({
  on_conflict: z.string().nullable().optional(),
  counts: z.record(z.string(), DiffCounts).default({}),
  rows: z.array(DiffRow).default([]),
  rows_total: z.number().default(0),
  conflicts_total: z.number().default(0),
});
export type ImportDiff = z.infer<typeof ImportDiff>;
export type ImportDiffRow = z.infer<typeof DiffRow>;

/** `summary.diff` of a finished preview, or null when the job has none (an older job, a failed parse). One
 * unreadable row never hides the counts: rows are read one by one and a bad one is left out (E2EA-F03). */
export function importDiff(job: Pick<ImportJob, "summary"> | null | undefined): ImportDiff | null {
  const raw = job?.summary.diff;
  const parsed = ImportDiff.safeParse(raw);
  if (parsed.success) return parsed.data;
  if (!raw || typeof raw !== "object") return null;
  const { rows, ...rest } = raw as Record<string, unknown>;
  const head = ImportDiff.safeParse({ ...rest, rows: [] });
  if (!head.success) return null;
  const good = (Array.isArray(rows) ? rows : []).flatMap((r) => {
    const one = DiffRow.safeParse(r);
    return one.success ? [one.data] : [];
  });
  return { ...head.data, rows: good };
}

/** Totals over every entity of the diff. */
export function diffTotals(diff: ImportDiff): { create: number; update: number; archive: number; unchanged: number; conflict: number } {
  const out = { create: 0, update: 0, archive: 0, unchanged: 0, conflict: 0 };
  for (const c of Object.values(diff.counts)) {
    out.create += c.create;
    out.update += c.update;
    out.archive += c.archive;
    out.unchanged += c.unchanged;
    out.conflict += c.conflict;
  }
  return out;
}

/** Above this share of an entity's rows in the term, archiving needs a deliberate confirm (E2EA2-F01). */
export const ARCHIVE_CONFIRM_SHARE = 0.2;
/** The entities whose archive share needs that confirm, largest share first. The term's rows of an entity are the
 * ones the file matched (update, unchanged, conflict) plus the ones it archives. */
export function largeArchives(diff: ImportDiff): { entity: string; archive: number; share: number }[] {
  return Object.entries(diff.counts)
    .map(([entity, c]) => ({ entity, archive: c.archive, share: c.archive / Math.max(1, c.archive + c.update + c.unchanged + c.conflict) }))
    .filter((e) => e.archive >= 5 && e.share > ARCHIVE_CONFIRM_SHARE)
    .sort((a, b) => b.share - a.share);
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
