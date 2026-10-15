"use client";
/**
 * Phase 19 moderation API (backend app/api/v1/moderation.py + app/services/moderation.py; specs
 * docs/design/v2/phase19-moderation.md, phase19-priority-policy.md). The responses are documented dicts, not
 * OpenAPI models, so the zod schemas here mirror `services/moderation.py` (`match_one`, `people`, `history`,
 * `resolve_diff`, `matching_action`). Publishing stays `POST /runs/{id}/activate` with its guard (409 reasons).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { HttpError, request } from "./client";
import { ScheduleRun } from "./schemas";

/* ------------------------------------------------------------------ shapes */

export const Pair = z.object({ tr: z.string().default(""), en: z.string().default("") });
export type Pair = z.infer<typeof Pair>;

export const VERDICTS = ["satisfied", "partial", "not_as_requested", "unplaced", "not_evaluated", "pending"] as const;
export const Verdict = z.enum(VERDICTS).catch("not_evaluated");
export type Verdict = (typeof VERDICTS)[number];

export const Place = z.object({
  day: z.number(),
  start_period: z.number(),
  end_period: z.number(),
  time: z.string().nullable().default(null),
  when: Pair.nullable().default(null),
  room_ids: z.array(z.number()).default([]),
  rooms: z.array(z.string()).default([]),
  weeks: z.array(z.number()).default([]),
  locked: z.boolean().default(false),
  origin: z.string().nullable().default(null),
});
export type Place = z.infer<typeof Place>;

export const Culprit = z.object({ request_id: z.number().nullable().optional(), label: z.string().default(""), room: z.string().nullable().optional() });
export const Reason = z.object({
  code: z.string().default("unplaced"),
  text: Pair,
  culprits: z.array(Culprit).default([]),
  policy_step: z.object({ step: z.number(), text: Pair }).nullable().default(null),
  policy_reason: z.string().nullable().optional(),
});
export type Reason = z.infer<typeof Reason>;

export const Priority = z.object({ value: z.number().default(0), source: z.enum(["request", "section", "default"]).catch("default") });
export type Priority = z.infer<typeof Priority>;

const Flag = z.boolean().nullable();
export const Matching = z.object({
  request_id: z.number(),
  section_id: z.number(),
  term_id: z.number(),
  course_code: z.string().nullable().default(null),
  course_name: z.string().nullable().default(null),
  section: z.string().nullable().default(null),
  label: z.string(),
  program: z.string().nullable().default(null),
  faculty: z.string().nullable().default(null),
  enrolment: z.number().nullable().default(null),
  instructors: z.array(z.object({ id: z.number(), name: z.string(), role: z.string().nullable().default(null) })).default([]),
  requested: z.object({
    day: z.number().nullable().default(null),
    days: z.array(z.number()).default([]),
    start_period: z.number().nullable().default(null),
    end_period: z.number().nullable().default(null),
    time: z.string().nullable().default(null),
    weeks: z.array(z.number()).default([]),
    room_text: z.string().nullable().default(null),
    rooms: z.array(z.string()).default([]),
    building: z.string().nullable().default(null),
    tags: z.array(z.string()).default([]),
    capacity: z.number().nullable().default(null),
    status: z.string().nullable().default(null),
  }),
  definitive: z.object({ text: z.string().nullable().default(null), room_ids: z.array(z.number()).default([]), rooms: z.array(z.string()).default([]) }),
  assigned: Place.nullable().default(null),
  satisfied: z.object({ room: Flag.default(null), building: Flag.default(null), tags: Flag.default(null), day: Flag.default(null), period: Flag.default(null) }).partial().default({}),
  verdict: Verdict,
  verdict_text: Pair,
  reason: Reason.nullable().default(null),
  priority: Priority,
  source: z.enum(["run", "planner"]).catch("run"),
  provenance: z.object({ row: z.number().nullable().default(null), source_key: z.string().nullable().default(null) }).default({ row: null, source_key: null }),
  placement_status: z.string().nullable().optional(),
  issues: z.array(z.record(z.string(), z.unknown())).nullable().optional(),
  findings: z.array(z.record(z.string(), z.unknown())).nullable().optional(),
});
export type Matching = z.infer<typeof Matching>;

const Counts = z.record(z.string(), z.number());

export const MatchingsOut = z.object({
  term_id: z.number(),
  run_id: z.number().nullable(),
  source: z.enum(["run", "planner"]).catch("run"),
  visibility: z.enum(["all", "own"]).catch("all"),
  counts: Counts,
  match_rate: z.number().nullable(),
  planner_check: z.record(z.string(), z.unknown()).nullable().optional(),
  total: z.number(),
  offset: z.number(),
  items: z.array(Matching),
});
export type MatchingsOut = z.infer<typeof MatchingsOut>;

export const MatchingDetail = Matching.extend({ detail: z.record(z.string(), z.unknown()).optional() });
export type MatchingDetail = z.infer<typeof MatchingDetail>;

export const PersonRow = z.object({
  id: z.number(),
  name: z.string(),
  title: z.string().nullable().default(null),
  unit: z.string().nullable().default(null),
  roles: z.array(z.string()).default([]),
  sections: z.number().default(0),
  requests: z.number().default(0),
  counts: Counts.default({}),
  match_rate: z.number().nullable().default(null),
  active_preferences: z.number().default(0),
  learned_priors: z.number().nullable().default(null),
  priority_max: z.number().default(0),
  accessibility: z.enum(["yes", "no"]).catch("no"),
  unsatisfied_streak: z.number().default(0),
  badge: Pair.nullable().default(null),
  linked_user: z.boolean().default(false),
});
export type PersonRow = z.infer<typeof PersonRow>;

export const PeopleOut = z.object({
  term_id: z.number(),
  term_code: z.string(),
  run_id: z.number().nullable(),
  source: z.enum(["run", "planner"]).catch("run"),
  visibility: z.enum(["all", "own"]).catch("all"),
  learning_available: z.boolean().default(false),
  total: z.number(),
  items: z.array(PersonRow),
});
export type PeopleOut = z.infer<typeof PeopleOut>;

export const PlannerEdit = z.object({
  kind: z.string(),
  entity: z.string().optional(),
  at: z.string().nullable().optional(),
  changes: z.record(z.string(), z.object({ imported: z.unknown(), current: z.unknown() })).optional(),
  action: z.string().optional(),
  actor: z.string().nullable().optional(),
  reason: z.string().nullable().optional(),
});
export type PlannerEdit = z.infer<typeof PlannerEdit>;

export const HistoryItem = Matching.extend({
  role: z.string().nullable().default(null),
  raw: z.object({ room_text: z.string().nullable().default(null), notes: z.string().nullable().default(null), row: z.number().nullable().default(null), source_row: z.record(z.string(), z.unknown()).nullable().default(null) }).default({ room_text: null, notes: null, row: null, source_row: null }),
  parsed: z.object({
    day: z.number().nullable().default(null),
    days: z.array(z.number()).default([]),
    start_period: z.number().nullable().default(null),
    end_period: z.number().nullable().default(null),
    start_time: z.string().nullable().default(null),
    end_time: z.string().nullable().default(null),
    weeks: z.array(z.number()).default([]),
    rooms: z.array(z.string()).default([]),
    building: z.string().nullable().default(null),
    tags: z.array(z.string()).default([]),
    capacity: z.number().nullable().default(null),
    status: z.string().nullable().default(null),
    warnings: z.array(z.string()).default([]),
  }).partial().default({}),
  planner_edits: z.array(PlannerEdit).default([]),
});
export type HistoryItem = z.infer<typeof HistoryItem>;

/** one learned prior as `learning.priors_for` renders it (the profile's "learned habits") */
export const LearnedPrior = z.object({
  id: z.number(),
  attribute: z.string().default(""),
  value: z.string().default(""),
  value_label: Pair.nullable().optional(),
  score: z.number().default(0),
  support: z.number().default(0),
  total: z.number().default(0),
  terms_count: z.number().default(0),
  confidence: z.number().default(0),
  suggestible: z.boolean().default(false),
  explanation: Pair.default({ tr: "", en: "" }),
});
export type LearnedPrior = z.infer<typeof LearnedPrior>;

export const HistoryTerm = z.object({
  term_id: z.number(),
  term_code: z.string(),
  term_name: z.string().nullable().default(null),
  run: z.object({ id: z.number(), label: z.string().nullable().default(null), status: z.string(), published: z.boolean() }).nullable().default(null),
  source: z.enum(["run", "planner"]).catch("planner"),
  counts: Counts.default({}),
  match_rate: z.number().nullable().default(null),
  items: z.array(HistoryItem),
  bookings: z.array(z.record(z.string(), z.unknown())).default([]),
  learned: z.array(LearnedPrior).nullable().default([]),
});
export type HistoryTerm = z.infer<typeof HistoryTerm>;

export const HistoryOut = z.object({
  instructor: z.object({ id: z.number(), name: z.string(), title: z.string().nullable().default(null), linked_user: z.boolean().default(false) }),
  accessibility: z.enum(["yes", "no"]).catch("no"),
  terms: z.array(HistoryTerm),
});
export type HistoryOut = z.infer<typeof HistoryOut>;

const DiffBase = z.object({ request_id: z.number(), label: z.string(), in_scope: z.boolean().default(false), instructor_ids: z.array(z.number()).default([]) });
export const DiffMoved = DiffBase.extend({ from: Place, to: Place, causes: z.array(z.object({ code: z.string(), text: Pair, request_id: z.number().optional(), label: z.string().optional() })).default([]) });
export type DiffMoved = z.infer<typeof DiffMoved>;
export const DiffNew = DiffBase.extend({ to: Place });
export type DiffNew = z.infer<typeof DiffNew>;
export const DiffUnplaceable = DiffBase.extend({ was_placed: z.boolean().default(false), from: Place.nullable().optional(), reason: Reason });
export type DiffUnplaceable = z.infer<typeof DiffUnplaceable>;

const Score = z.object({ before: z.number().nullable().optional(), after: z.number().nullable().optional() });
export const DiffOut = z.object({
  run_id: z.number(),
  base_run_id: z.number(),
  status: z.string(),
  mode: z.string().nullable().optional(),
  changed_request_ids: z.array(z.number()).default([]),
  is_active: z.boolean().default(false),
  ready: z.boolean(),
  counts: z
    .object({
      moved: z.number().default(0),
      moved_outside_scope: z.number().default(0),
      moved_unexplained: z.number().default(0),
      unchanged: z.number().default(0),
      newly_placed: z.number().default(0),
      unplaceable: z.number().default(0),
      newly_unplaced: z.number().default(0),
      affected_people: z.number().default(0),
    })
    .optional(),
  moved: z.array(DiffMoved).default([]),
  newly_placed: z.array(DiffNew).default([]),
  unplaceable: z.array(DiffUnplaceable).default([]),
  affected_instructor_ids: z.array(z.number()).default([]),
  scores: z.object({ hard: Score, soft: Score, placed: Score.extend({ total: z.number().nullable().optional() }) }).partial().optional(),
  waived_rules: z.array(z.unknown()).default([]),
  diagnosis: z.array(z.object({ code: z.string().nullable().optional(), text: Pair.nullable().optional(), message: z.string().nullable().optional() })).default([]),
});
export type DiffOut = z.infer<typeof DiffOut>;

export const PriorityOut = z.object({ priority: z.number().nullable(), previous: z.number().nullable() }).passthrough();
export const ResolveQueued = z.object({ run_id: z.number(), status: z.string(), base_run_id: z.number() });
export const MatchingActionOut = z.object({
  request_id: z.number(),
  run_id: z.number(),
  action: z.enum(["pin", "prefer", "unlock"]),
  constraint_ids: z.array(z.number()).default([]),
  disabled_constraint_ids: z.array(z.number()).default([]),
  effective: Pair.optional(),
});
export type MatchingActionOut = z.infer<typeof MatchingActionOut>;

/** a soft preference of the term (Tercihler): the constraint rows that are not built-in switches */
export const Preference = z.object({
  id: z.number(),
  term_id: z.number().nullable(),
  run_id: z.number().nullable(),
  kind: z.string(),
  params: z.record(z.string(), z.unknown()).default({}),
  hardness: z.string(),
  weight: z.number(),
  source: z.string(),
  nl_text: z.string().nullable(),
  enabled: z.boolean(),
  source_ref: z.record(z.string(), z.unknown()).nullable().optional(),
});
export type Preference = z.infer<typeof Preference>;

/* ------------------------------------------------------------------ endpoints */

export type TierCode = "high" | "normal" | "low";

export const moderationApi = {
  people: (termId: number, q?: string) => request(`/terms/${termId}/moderation/people`, { query: { q }, schema: PeopleOut, silent: true }),
  history: (instructorId: number, terms?: string) => request(`/moderation/people/${instructorId}/history`, { query: { terms }, schema: HistoryOut, silent: true }),
  matchings: (termId: number, q: { run_id?: number | null; verdict?: string; q?: string; check?: boolean; limit?: number } = {}) =>
    request(`/terms/${termId}/moderation/matchings`, { query: { run_id: q.run_id ?? undefined, verdict: q.verdict, q: q.q, check: q.check ?? false, limit: q.limit ?? 5000 }, schema: MatchingsOut, silent: true }),
  matching: (termId: number, requestId: number, runId?: number | null) => request(`/terms/${termId}/moderation/matchings/${requestId}`, { query: { run_id: runId ?? undefined }, schema: MatchingDetail, silent: true }),
  setSectionPriority: (sectionId: number, priority: TierCode | null, note?: string) => request(`/moderation/sections/${sectionId}/priority`, { method: "PUT", body: { priority, note: note || null }, schema: PriorityOut }),
  setRequestPriority: (requestId: number, priority: TierCode | null, note?: string) => request(`/moderation/requests/${requestId}/priority`, { method: "PUT", body: { priority, note: note || null }, schema: PriorityOut }),
  resolve: (termId: number, body: { base_run_id: number; changed_request_ids: number[]; mode: "repair" | "full"; time_limit_s?: number }) =>
    request(`/terms/${termId}/moderation/resolve`, { method: "POST", body, schema: ResolveQueued, silent: true }),
  diff: (runId: number) => request(`/moderation/runs/${runId}/diff`, { schema: DiffOut, silent: true }),
  matchingAction: (requestId: number, body: { run_id: number; action: "pin" | "prefer" | "unlock"; room_ids?: number[]; day?: number; start_period?: number; reason?: string }) =>
    request(`/moderation/matchings/${requestId}`, { method: "PUT", body, schema: MatchingActionOut, silent: true }),
  /** the publish guard (P19-01 / M-02 / M-04): 409 `{message, issues[]}` or a `scope_reduction` 409 */
  activate: (runId: number, confirmScopeReduction = false) =>
    request(`/runs/${runId}/activate`, { method: "POST", body: { confirm_scope_reduction: confirmScopeReduction }, schema: ScheduleRun, silent: true }),
  preferences: (termId: number) => request(`/constraints`, { query: { term_id: termId }, schema: z.array(Preference), silent: true }),
  runRules: (runId: number) => request(`/constraints`, { query: { run_id: runId, enabled: true }, schema: z.array(Preference), silent: true }),
};

/* ------------------------------------------------------------------ hooks */

export const mk = {
  people: (termId: number | null, q?: string) => ["moderation", "people", termId, q ?? ""] as const,
  history: (id: number) => ["moderation", "history", id] as const,
  matchings: (termId: number | null, runId: number | null | undefined) => ["moderation", "matchings", termId, runId ?? null] as const,
  matching: (termId: number, requestId: number, runId?: number | null) => ["moderation", "matching", termId, requestId, runId ?? null] as const,
  diff: (runId: number) => ["moderation", "diff", runId] as const,
  preferences: (termId: number | null) => ["moderation", "preferences", termId] as const,
  runRules: (runId: number) => ["moderation", "run-rules", runId] as const,
};

/** 403 / 404 are states of the screen ("no linked instructor", "not found"), not errors to retry */
const noRetry = (n: number, e: unknown) => !(e instanceof HttpError && [401, 403, 404, 422].includes(e.status)) && n < 2;

export function usePeople(termId: number | null, q?: string, enabled = true) {
  return useQuery({ queryKey: mk.people(termId, q), queryFn: () => moderationApi.people(termId ?? 0, q), enabled: enabled && termId !== null, retry: noRetry, placeholderData: keepPreviousData, staleTime: 30_000 });
}
export function useHistory(instructorId: number | null) {
  return useQuery({ queryKey: mk.history(instructorId ?? 0), queryFn: () => moderationApi.history(instructorId ?? 0), enabled: instructorId !== null, retry: noRetry, staleTime: 30_000 });
}
export function useMatchings(termId: number | null, runId?: number | null, enabled = true) {
  return useQuery({ queryKey: mk.matchings(termId, runId), queryFn: () => moderationApi.matchings(termId ?? 0, { run_id: runId }), enabled: enabled && termId !== null, retry: noRetry, staleTime: 30_000 });
}
export function useMatching(termId: number | null, requestId: number | null, runId?: number | null) {
  return useQuery({ queryKey: mk.matching(termId ?? 0, requestId ?? 0, runId), queryFn: () => moderationApi.matching(termId ?? 0, requestId ?? 0, runId), enabled: termId !== null && requestId !== null, retry: noRetry });
}
export function usePreferences(termId: number | null, enabled = true) {
  return useQuery({ queryKey: mk.preferences(termId), queryFn: () => moderationApi.preferences(termId ?? 0), enabled: enabled && termId !== null, retry: noRetry, staleTime: 30_000 });
}
export function useRunRules(runId: number | null) {
  return useQuery({ queryKey: mk.runRules(runId ?? 0), queryFn: () => moderationApi.runRules(runId ?? 0), enabled: runId !== null, retry: noRetry });
}

/** the preview polls until the child run finished (`ready`), then stops */
export function useDiff(runId: number | null) {
  return useQuery({
    queryKey: mk.diff(runId ?? 0),
    queryFn: () => moderationApi.diff(runId ?? 0),
    enabled: runId !== null,
    retry: noRetry,
    refetchInterval: (q) => (q.state.data && !q.state.data.ready ? 1500 : false),
  });
}

export function useSetPriority() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { kind: "request" | "section"; id: number; tier: TierCode | null; note?: string }) =>
      v.kind === "request" ? moderationApi.setRequestPriority(v.id, v.tier, v.note) : moderationApi.setSectionPriority(v.id, v.tier, v.note),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["moderation"] }),
  });
}

/* ------------------------------------------------------------------ errors */

/**
 * The text of a backend refusal, verbatim: `detail` as a string, `{message, issues[]}` (publish guard, pin
 * capacity, rule guard), `{message_tr, message}` (scope reduction), or FastAPI validation entries.
 */
export function refusal(e: unknown, lang: "tr" | "en"): { message: string; issues: string[]; scopeReduction: boolean } {
  if (!(e instanceof HttpError)) return { message: e instanceof Error ? e.message : String(e), issues: [], scopeReduction: false };
  const raw = e.detail as unknown;
  const body = raw && typeof raw === "object" && "detail" in (raw as Record<string, unknown>) ? (raw as Record<string, unknown>).detail : raw;
  if (typeof body === "string") return { message: body, issues: [], scopeReduction: false };
  if (body && typeof body === "object" && !Array.isArray(body)) {
    const b = body as Record<string, unknown>;
    const issues = Array.isArray(b.issues) ? b.issues.map((i) => (typeof i === "string" ? i : JSON.stringify(i))) : [];
    const msg = (lang === "tr" && typeof b.message_tr === "string" ? b.message_tr : null) ?? (typeof b.message === "string" ? b.message : e.message);
    return { message: msg, issues, scopeReduction: b.code === "scope_reduction" || "active" in b && "new" in b };
  }
  return { message: e.message, issues: [], scopeReduction: false };
}
