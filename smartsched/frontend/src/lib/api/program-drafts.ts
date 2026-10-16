"use client";
/**
 * Program wizard drafts (backend app/api/v1/program_drafts.py + app/services/program_drafts.py; spec
 * docs/design/v2/phase19-program-wizard.md §13). The wizard state is ONE server-side JSON payload per draft,
 * autosaved with field ops (`PATCH {ops, base_version}`: last write wins per field, `overwritten` names the
 * fields someone else wrote after our version), validated per step in TR + EN, pre-checked in a rolled-back
 * session, and written to the term only by `commit` (one transaction, 30-day undo with the blockers named).
 * Responses are the documented dicts of the service, mirrored here with zod.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { HttpError, request } from "./client";
import { Pair } from "./moderation";
import { PrecheckItem } from "./studio-schemas";

/* ------------------------------------------------------------------ validation */

export const DRAFT_STEPS = ["program", "courses", "sections", "instructors", "cohorts", "rooms", "constraints", "generate"] as const;
export type DraftStep = (typeof DRAFT_STEPS)[number];
export const DraftStepZ = z.enum(DRAFT_STEPS).catch("program");

export const DraftIssue = z.object({
  step: DraftStepZ,
  level: z.enum(["error", "warning", "info"]).catch("info"),
  code: z.string(),
  path: z.string().default(""),
  text: Pair,
  vars: z.record(z.string(), z.unknown()).default({}),
});
export type DraftIssue = z.infer<typeof DraftIssue>;

export const StepState = z.object({
  step: DraftStepZ,
  status: z.enum(["ok", "warning", "error", "empty"]).catch("empty"),
  errors: z.array(DraftIssue).default([]),
  warnings: z.array(DraftIssue).default([]),
  info: z.array(DraftIssue).default([]),
});
export type StepState = z.infer<typeof StepState>;

export const DraftSummary = z.object({
  courses: z.number().default(0),
  sections: z.number().default(0),
  joint_links: z.number().default(0),
  people: z.number().default(0),
  new_people: z.number().default(0),
  cohorts: z.number().default(0),
  weekly_hours: z.number().default(0),
  ects: z.number().default(0),
});
export type DraftSummary = z.infer<typeof DraftSummary>;

export const RoomFitClass = z.object({
  event_id: z.number(),
  label: z.string(),
  size: z.number().nullable().default(null),
  request_ids: z.array(z.number()).default([]),
  rooms: z.array(z.object({ id: z.number(), code: z.string(), capacity: z.number().nullable().default(null) })).default([]),
});
export type RoomFitClass = z.infer<typeof RoomFitClass>;

export const DraftPrecheck = z.object({
  readiness: z.enum(["ready", "needs_look", "blocked"]).catch("needs_look"),
  counts: z.object({ errors: z.number().default(0), warnings: z.number().default(0), events: z.number().default(0), requests: z.number().default(0) }),
  items: z.array(PrecheckItem).default([]),
  rooms_fit: z.array(RoomFitClass).default([]),
  joint_merged: z.array(z.number()).default([]),
});
export type DraftPrecheck = z.infer<typeof DraftPrecheck>;

export const Validation = z.object({
  draft_id: z.number(),
  version: z.number(),
  can_commit: z.boolean(),
  counts: z.object({ errors: z.number().default(0), warnings: z.number().default(0), info: z.number().default(0) }),
  steps: z.array(StepState).default([]),
  issues: z.array(DraftIssue).default([]),
  summary: DraftSummary,
  precheck: DraftPrecheck.nullable().default(null),
});
export type Validation = z.infer<typeof Validation>;

/* ------------------------------------------------------------------ drafts */

export const DraftStatus = z.enum(["draft", "committed", "undone"]).catch("draft");
export type DraftStatus = z.infer<typeof DraftStatus>;

const DraftBase = z.object({
  id: z.number(),
  term_id: z.number(),
  owner_id: z.number().nullable().default(null),
  title: z.string().nullable().default(null),
  step: z.string().nullable().default(null),
  version: z.number(),
  status: DraftStatus,
  program_id: z.number().nullable().default(null),
  commit_audit_id: z.number().nullable().default(null),
  committed_at: z.string().nullable().default(null),
  created_at: z.string().nullable().default(null),
  updated_at: z.string().nullable().default(null),
  updated_by: z.number().nullable().default(null),
  summary: DraftSummary,
});

export const DraftListItem = DraftBase.extend({ term_code: z.string().nullable().default(null) });
export type DraftListItem = z.infer<typeof DraftListItem>;

export const CreatedIds = z
  .object({
    faculty_id: z.number().nullable().default(null),
    program_id: z.number().nullable().default(null),
    courses: z.array(z.number()).default([]),
    reused_courses: z.array(z.number()).default([]),
    people: z.array(z.number()).default([]),
    reused_people: z.array(z.number()).default([]),
    sections: z.array(z.number()).default([]),
    requests: z.array(z.number()).default([]),
    rules: z.array(z.number()).default([]),
    joint_links: z.array(z.record(z.string(), z.number())).default([]),
    warnings: z.array(z.string()).default([]),
  })
  .passthrough();
export type CreatedIds = z.infer<typeof CreatedIds>;

export const DraftOut = DraftBase.extend({
  payload: z.record(z.string(), z.unknown()).default({}),
  created: CreatedIds.nullable().default(null),
  validation: Validation,
});
export type DraftOut = z.infer<typeof DraftOut>;

export const Overwritten = z.object({ path: z.string(), by: z.number().nullable().default(null), at: z.string().nullable().default(null), previous: z.unknown().optional() });
export type Overwritten = z.infer<typeof Overwritten>;
export const PatchOut = z.object({ id: z.number(), version: z.number(), overwritten: z.array(Overwritten).default([]), validation: Validation });
export type PatchOut = z.infer<typeof PatchOut>;

export const PasteRow = z.object({
  line: z.number(),
  code: z.string(),
  code_error: z.string().nullable().default(null),
  name: z.string().default(""),
  t: z.number().nullable().default(null),
  u: z.number().nullable().default(null),
  l: z.number().nullable().default(null),
  credits: z.number().nullable().default(null),
  ects: z.number().nullable().default(null),
  year: z.number().nullable().default(null),
  enrolment: z.number().nullable().default(null),
});
export type PasteRow = z.infer<typeof PasteRow>;
export const PasteOut = z.object({ columns: z.array(z.string()).default([]), rows: z.array(PasteRow).default([]), ignored: z.array(z.object({ line: z.number(), reason: z.string() })).default([]) });
export type PasteOut = z.infer<typeof PasteOut>;

export const CommitOut = z.object({
  draft_id: z.number(),
  program_id: z.number().nullable().default(null),
  created: CreatedIds,
  counts: z.record(z.string(), z.number()).default({}),
  audit_id: z.number().nullable().default(null),
  warnings: z.array(z.string()).default([]),
  run_id: z.number().nullable().default(null),
  next: z.enum(["program", "moderation_preview", "studio"]).catch("program"),
  undo_until: z.string().nullable().default(null),
});
export type CommitOut = z.infer<typeof CommitOut>;

export const Blocker = z.object({ code: z.string(), text: Pair }).passthrough();
export type Blocker = z.infer<typeof Blocker>;
export const UndoCheck = z.object({ draft_id: z.number(), can_undo: z.boolean(), blockers: z.array(Blocker).default([]), undo_until: z.string().nullable().default(null) });
export type UndoCheck = z.infer<typeof UndoCheck>;
export const UndoOut = z.object({ draft_id: z.number(), program_id: z.number().nullable().default(null), archived: z.record(z.string(), z.array(z.number())).default({}), audit_id: z.number().nullable().default(null) });
export type UndoOut = z.infer<typeof UndoOut>;

/* ------------------------------------------------------------------ wizard reads */

export const InstructorLoad = z.object({
  instructor_id: z.number(),
  full_name: z.string(),
  title: z.string().nullable().default(null),
  periods_per_week: z.number().default(0),
  meetings: z.number().default(0),
  sections: z.number().default(0),
  over_limit: z.boolean().default(false),
});
export type InstructorLoad = z.infer<typeof InstructorLoad>;
export const LoadOut = z.object({ term_id: z.number(), limit: z.number(), items: z.array(InstructorLoad) });
export type LoadOut = z.infer<typeof LoadOut>;

export const FoundSection = z.object({
  section_id: z.number(),
  course_id: z.number().nullable().default(null),
  course_code: z.string().nullable().default(null),
  course_name: z.string().nullable().default(null),
  label: z.string().nullable().default(null),
  program_id: z.number().nullable().default(null),
  program_name: z.string().nullable().default(null),
  class_years: z.array(z.number()).default([]),
  enrolment: z.number().nullable().default(null),
  mode: z.string().nullable().default(null),
  periods_per_week: z.number().default(0),
  instructors: z.array(z.object({ id: z.number(), full_name: z.string(), role: z.string().nullable().default(null) })).default([]),
  meetings: z.array(z.record(z.string(), z.unknown())).default([]),
  placement: z.unknown().nullable().default(null),
});
export type FoundSection = z.infer<typeof FoundSection>;
export const SectionSearchOut = z.object({ term_id: z.number(), total: z.number(), items: z.array(FoundSection) });

export const FitRoom = z.object({ id: z.number(), code: z.string(), display_name: z.string(), capacity: z.number(), tags: z.array(z.string()).default([]), bookable: z.boolean().default(true) });
export type FitRoom = z.infer<typeof FitRoom>;
export const RoomsFitOut = z.object({ capacity: z.number(), count: z.number(), items: z.array(FitRoom) });
export type RoomsFitOut = z.infer<typeof RoomsFitOut>;

/* ------------------------------------------------------------------ endpoints */

export interface DraftOp {
  path: string;
  value?: unknown;
  op?: "set" | "remove";
}

export const draftsApi = {
  list: (q: { term_id?: number; status?: DraftStatus; mine?: boolean } = {}) =>
    request(`/program-drafts`, { query: { term_id: q.term_id, status: q.status ?? "draft", mine: q.mine ?? true }, schema: z.object({ items: z.array(DraftListItem), total: z.number() }), silent: true }),
  create: (termId: number, payload?: Record<string, unknown>, step?: string) =>
    request(`/program-drafts`, { method: "POST", body: { term_id: termId, payload: payload ?? null, step: step ?? null }, schema: DraftOut, silent: true }),
  get: (id: number) => request(`/program-drafts/${id}`, { schema: DraftOut, silent: true }),
  patch: (id: number, body: { ops?: DraftOp[]; payload?: Record<string, unknown>; base_version?: number; step?: string }) =>
    request(`/program-drafts/${id}`, { method: "PATCH", body, schema: PatchOut, silent: true }),
  remove: (id: number) => request(`/program-drafts/${id}`, { method: "DELETE", silent: true }),
  validate: (id: number, step?: string, precheck = false) => request(`/program-drafts/${id}/validate`, { method: "POST", query: { step, precheck }, schema: Validation, silent: true }),
  precheck: (id: number) => request(`/program-drafts/${id}/precheck`, { method: "POST", schema: DraftPrecheck, silent: true }),
  paste: (id: number, tsv: string, step: "courses" | "sections" = "courses") => request(`/program-drafts/${id}/paste`, { method: "POST", body: { step, tsv }, schema: PasteOut, silent: true }),
  commit: (id: number, solve: "none" | "minimal") => request(`/program-drafts/${id}/commit`, { method: "POST", body: { solve }, schema: CommitOut, silent: true }),
  undoCheck: (id: number) => request(`/program-drafts/${id}/undo`, { schema: UndoCheck, silent: true }),
  undo: (id: number) => request(`/program-drafts/${id}/undo`, { method: "POST", schema: UndoOut, silent: true }),
  load: (termId: number, q: { ids?: number[]; q?: string; limit?: number }) =>
    request(`/terms/${termId}/instructors/load`, { query: { ids: q.ids?.length ? q.ids.join(",") : undefined, q: q.q, limit: q.limit ?? 20 }, schema: LoadOut, silent: true }),
  sections: (termId: number, q: string) => request(`/terms/${termId}/sections/search`, { query: { q, limit: 20 }, schema: SectionSearchOut, silent: true }),
  roomsFit: (termId: number, capacity: number, tags: readonly string[], building?: string) =>
    request(`/terms/${termId}/rooms/fit`, { query: { capacity, tags: tags.length ? tags.join(",") : undefined, building: building || undefined }, schema: RoomsFitOut, silent: true }),
};

/* ------------------------------------------------------------------ hooks */

export const dk = {
  list: (status: DraftStatus, termId?: number | null) => ["program-drafts", "list", status, termId ?? null] as const,
  draft: (id: number) => ["program-drafts", "draft", id] as const,
  undo: (id: number) => ["program-drafts", "undo", id] as const,
  load: (termId: number, key: string) => ["program-drafts", "load", termId, key] as const,
  fit: (termId: number, cap: number, tags: string, building: string) => ["program-drafts", "fit", termId, cap, tags, building] as const,
  sections: (termId: number, q: string) => ["program-drafts", "sections", termId, q] as const,
};

const noRetry = (n: number, e: unknown) => !(e instanceof HttpError && [401, 403, 404, 409, 422].includes(e.status)) && n < 2;

export function useDraftList(status: DraftStatus, enabled = true) {
  return useQuery({ queryKey: dk.list(status), queryFn: () => draftsApi.list({ status }), enabled, retry: noRetry, staleTime: 10_000 });
}
export function useUndoCheck(id: number | null) {
  return useQuery({ queryKey: dk.undo(id ?? 0), queryFn: () => draftsApi.undoCheck(id ?? 0), enabled: id !== null, retry: noRetry });
}
/** "Bu dönem 9 saat" next to each picked instructor (one request for the ids of the step) */
export function useInstructorLoads(termId: number | null, ids: readonly number[]) {
  const key = [...new Set(ids)].sort((a, b) => a - b).join(",");
  return useQuery({ queryKey: dk.load(termId ?? 0, `ids:${key}`), queryFn: () => draftsApi.load(termId ?? 0, { ids: key.split(",").map(Number), limit: 500 }), enabled: termId !== null && key !== "", retry: noRetry, staleTime: 60_000, placeholderData: keepPreviousData });
}
export function useInstructorSearch(termId: number | null, q: string) {
  const v = q.trim();
  return useQuery({ queryKey: dk.load(termId ?? 0, `q:${v}`), queryFn: () => draftsApi.load(termId ?? 0, { q: v, limit: 12 }), enabled: termId !== null && v.length >= 2, retry: noRetry, staleTime: 30_000 });
}
export function useSectionSearch(termId: number | null, q: string) {
  const v = q.trim();
  return useQuery({ queryKey: dk.sections(termId ?? 0, v), queryFn: () => draftsApi.sections(termId ?? 0, v), enabled: termId !== null && v.length >= 2, retry: noRetry, staleTime: 30_000 });
}
/** the live "sığan odalar" line of a course (rooms/fit, smallest first) */
export function useRoomsFit(termId: number | null, capacity: number, tags: readonly string[], building: string) {
  const t = [...tags].sort().join(",");
  return useQuery({ queryKey: dk.fit(termId ?? 0, capacity, t, building), queryFn: () => draftsApi.roomsFit(termId ?? 0, capacity, tags, building), enabled: termId !== null && capacity > 0, retry: noRetry, staleTime: 60_000, placeholderData: keepPreviousData });
}
