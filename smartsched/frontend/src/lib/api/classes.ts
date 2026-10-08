"use client";
/**
 * All-classes read model (backend `GET /terms/{id}/classes`, app/services/calendar_views.py): one row per weekly
 * meeting (or exam) = request + placement in the selected run + issues + provenance (file · sheet · row).
 */
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { buildUrl, request } from "./client";
import { Issue } from "./calendar";

export const ClassChange = z.object({ field: z.string(), source: z.enum(["import", "manual", "run", "compare"]), from: z.unknown().optional(), to: z.unknown().optional() });
export type ClassChange = z.infer<typeof ClassChange>;

export const PlacementStatus = z.enum(["placed", "partial", "unplaced", "conflict", "no_room_needed", "no_run"]);
export type PlacementStatus = z.infer<typeof PlacementStatus>;

export const ClassRow = z.object({
  id: z.number(),
  kind: z.enum(["meeting", "exam"]),
  course_code: z.string(),
  course_name: z.string().nullable().optional(),
  section: z.string().nullable().optional(),
  faculty_id: z.number().nullable().optional(),
  faculty_name: z.string().nullable().optional(),
  faculty_slot: z.number().default(8),
  program_id: z.number().nullable().optional(),
  program_name: z.string().nullable().optional(),
  is_evening: z.boolean().default(false),
  class_years: z.array(z.number()).default([]),
  instructors: z.array(z.object({ id: z.number().nullable().optional(), name: z.string() })).default([]),
  enrolment: z.number().nullable().optional(),
  mode: z.string().default("F2F"),
  needs_room: z.boolean().default(true),
  merge_key: z.string().nullable().optional(),
  req: z.object({
    day: z.number().nullable().optional(),
    days: z.array(z.number()).default([]),
    date: z.string().nullable().optional(),
    start_period: z.number().nullable().optional(),
    end_period: z.number().nullable().optional(),
    weeks: z.array(z.number()).default([]),
    room_text: z.string().nullable().optional(),
    room_ids: z.array(z.number()).default([]),
    room_codes: z.array(z.string()).default([]),
    building: z.string().nullable().optional(),
    tags: z.array(z.string()).default([]),
    capacity: z.number().nullable().optional(),
    flexible_day: z.boolean().default(false),
    status: z.string().default("NEW"),
    warnings: z.array(z.string()).default([]),
    notes: z.string().nullable().optional(),
    room_count: z.number().nullable().optional(),
  }),
  definitive: z.object({ text: z.string().nullable().optional(), room_ids: z.array(z.number()).default([]), room_codes: z.array(z.string()).default([]) }),
  placement: z
    .object({
      assignment_ids: z.array(z.number()),
      day: z.number(),
      date: z.string().nullable().optional(),
      start_period: z.number(),
      end_period: z.number(),
      room_ids: z.array(z.number()),
      room_codes: z.array(z.string()),
      capacity: z.number().nullable().optional(),
      weeks_placed: z.array(z.number()).default([]),
      locked: z.boolean().default(false),
      origin: z.string().default("SOLVER"),
      matched: z.enum(["request", "board"]).default("request"),
    })
    .nullable(),
  placement_status: PlacementStatus,
  issues: z.array(Issue).default([]),
  changed: z.array(ClassChange).default([]),
  provenance: z.object({
    kind: z.string(),
    import_job_id: z.number().nullable().optional(),
    file_name: z.string().nullable().optional(),
    sheet: z.string().nullable().optional(),
    row: z.number().nullable().optional(),
    source_key: z.string().nullable().optional(),
  }),
  updated_at: z.string().nullable().optional(),
});
export type ClassRow = z.infer<typeof ClassRow>;

export const ClassesOut = z.object({
  term_id: z.number(),
  kind: z.enum(["meetings", "exams"]),
  run_id: z.number().nullable(),
  compare_run_id: z.number().nullable().optional(),
  total: z.number(),
  items: z.array(ClassRow),
  facets: z.record(z.string(), z.record(z.string(), z.number())),
});
export type ClassesOut = z.infer<typeof ClassesOut>;

export const ClassDetail = z.object({
  row: ClassRow,
  raw_row: z.record(z.string(), z.unknown()).nullable().optional(),
  checks: z.array(z.object({ key: z.string(), state: z.enum(["ok", "fail", "na"]), text: z.object({ tr: z.string(), en: z.string() }) })).default([]),
  history: z
    .array(
      z.object({
        run_id: z.number(),
        run_label: z.string().nullable().optional(),
        status: z.string(),
        is_active: z.boolean().default(false),
        room_codes: z.array(z.string()).default([]),
        day: z.number().nullable().optional(),
        start_period: z.number().nullable().optional(),
        end_period: z.number().nullable().optional(),
        locked: z.boolean().default(false),
      }),
    )
    .default([]),
});
export type ClassDetail = z.infer<typeof ClassDetail>;

export type ClassKind = "meetings" | "exams";

export const classesApi = {
  list: (termId: number, kind: ClassKind, runId: number | null, compareRunId?: number | null) =>
    request(`/terms/${termId}/classes`, { query: { kind, run_id: runId, compare_run_id: compareRunId }, schema: ClassesOut }),
  detail: (termId: number, id: number, kind: ClassKind, runId: number | null) =>
    request(`/terms/${termId}/classes/${id}`, { query: { kind, run_id: runId }, schema: ClassDetail, silent: true }),
  exportUrl: (termId: number, format: "planning-list" | "csv", kind: ClassKind, runId: number | null) =>
    buildUrl(`/terms/${termId}/classes/export`, { format, kind, run_id: runId }),
  importFileUrl: (jobId: number) => buildUrl(`/imports/${jobId}/file`),
};

export function useClasses(termId: number | null, kind: ClassKind, runId: number | null, compareRunId?: number | null) {
  return useQuery({
    queryKey: ["classes", termId, kind, runId, compareRunId ?? null],
    queryFn: () => classesApi.list(termId ?? 0, kind, runId, compareRunId),
    enabled: termId !== null,
    staleTime: 60_000,
    placeholderData: (prev) => (prev && prev.term_id === termId && prev.kind === kind ? prev : undefined),
  });
}

export function useClassDetail(termId: number | null, id: number | null, kind: ClassKind, runId: number | null) {
  return useQuery({
    queryKey: ["class-detail", termId, id, kind, runId],
    queryFn: () => classesApi.detail(termId ?? 0, id ?? 0, kind, runId),
    enabled: termId !== null && id !== null,
    staleTime: 30_000,
  });
}
