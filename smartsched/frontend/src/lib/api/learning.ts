"use client";
/**
 * Learned suggestions and resettable memory (backend app/api/v1/learning.py + app/services/learning.py; spec
 * docs/design/v2/phase19-suggestions.md). Nothing here applies a suggestion by itself: accepting one writes a
 * single SOFT targeted LEARNED rule (weight ≤ 5), for this term or (planning.admin) remembered as the person's
 * preference so the same suggestion in a later term is marked, never applied by itself. Every decision can be
 * undone (`restore`). Reset person / term / all and the KVKK erasure are
 * planning.admin only; a reset can be undone for 30 days, an erasure is immediate.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { HttpError, request } from "./client";
import { Pair } from "./moderation";

export const SuggestionState = z.enum(["open", "accepted", "dismissed", "snoozed", "hidden"]).catch("open");
export type SuggestionState = z.infer<typeof SuggestionState>;

export const EvidenceTerm = z.object({ term_id: z.number().nullable(), code: z.string(), pos: z.number().default(0), total: z.number().default(0) });
export type EvidenceTerm = z.infer<typeof EvidenceTerm>;

export const Suggestion = z.object({
  id: z.number(),
  term_id: z.number(),
  subject: z.object({ type: z.string(), id: z.union([z.number(), z.string()]), label: z.string() }),
  attribute: z.string(),
  value: z.string(),
  value_label: Pair.nullable().optional(),
  claim: Pair,
  explanation: Pair,
  if_accepted: Pair,
  proposal: z.object({ kind: z.string().nullable(), params: z.record(z.string(), z.unknown()).default({}), hardness: z.literal("soft").catch("soft"), weight: z.number() }),
  support: z.object({ rows: z.number().default(0), total: z.number().default(0), seen_terms: z.number().default(0) }),
  score: z.number().default(0),
  confidence: z.number(),
  level: z.object({ code: z.enum(["high", "medium", "low"]).catch("low"), tr: z.string(), en: z.string() }).nullable(),
  cross_season: z.boolean().default(false),
  evidence: z
    .object({
      terms: z.array(EvidenceTerm).default([]),
      request_ids: z.array(z.number()).default([]),
      excluded: z.array(z.record(z.string(), z.unknown())).default([]),
    })
    .partial()
    .default({}),
  impact: z.object({ request_ids: z.array(z.number()).default([]), covered_request_ids: z.array(z.number()).default([]) }).default({ request_ids: [], covered_request_ids: [] }),
  state: SuggestionState,
  hidden_reason: z.string().nullable().default(null),
  snoozed_until: z.string().nullable().default(null),
  snooze_mode: z.string().nullable().default(null),
  constraint_id: z.number().nullable().default(null),
  decided_at: z.string().nullable().default(null),
  decided_by: z.number().nullable().default(null),
  /** how an accept was scoped: this term, or remembered as the person's preference (planning.admin) */
  scope: z.enum(["term", "persistent"]).nullable().catch(null).default(null),
  /** accepted as persistent in another term: listed first, still waits for a person to accept it here */
  persistent_accept: z.object({ term_id: z.number(), accepted_at: z.string().nullable().optional(), by: z.number().nullable().optional() }).nullable().catch(null).default(null),
});
export type Suggestion = z.infer<typeof Suggestion>;

export const AcceptOut = z.object({ constraint_id: z.number(), kind: z.string(), weight: z.number(), hardness: z.literal("soft"), scope: z.enum(["term", "persistent"]).catch("term").optional() }).passthrough();
export const RestoreOut = z.object({ id: z.number(), state: z.literal("open").catch("open"), undone: z.enum(["accepted", "dismissed", "snoozed"]).catch("dismissed"), disabled_constraint_id: z.number().nullable().default(null) });
export type RestoreOut = z.infer<typeof RestoreOut>;
export type AcceptScope = "term" | "persistent";

export const MemorySummary = z.object({
  terms: z.array(z.object({ term_id: z.number().nullable(), code: z.string().nullable(), observations: z.number() })).default([]),
  observations: z.number().default(0),
  hidden_by_reset: z.number().default(0),
  term_id: z.number().optional(),
  suggestions: z.record(z.string(), z.number()).optional(),
});
export type MemorySummary = z.infer<typeof MemorySummary>;

export const ResetRow = z.object({
  id: z.number(),
  kind: z.enum(["RESET", "ERASURE"]).catch("RESET"),
  scope: z.enum(["person", "term", "all", "intake"]).catch("all"),
  value: z.string().nullable(),
  reason: z.string().nullable().default(null),
  actor_id: z.number().nullable().default(null),
  created_at: z.string(),
  undo_until: z.string().nullable().default(null),
  days_left: z.number().default(0),
  undoable: z.boolean().default(false),
  undone_at: z.string().nullable().default(null),
  purged_at: z.string().nullable().default(null),
  counts: z.record(z.string(), z.number()).default({}),
});
export type ResetRow = z.infer<typeof ResetRow>;

export type SnoozeUntil = "next_solve" | "P7D" | "next_term";
export type ResetScope = "person" | "term" | "all";

export const learningApi = {
  suggestions: (q: { term_id: number; person_id?: number; course_id?: number; state?: "open" | "accepted" | "dismissed" | "snoozed" | "hidden" | "all"; limit?: number }) =>
    request(`/learning/suggestions`, { query: { ...q }, schema: z.array(Suggestion), silent: true }),
  accept: (id: number, weight?: number, scope: AcceptScope = "term") => request(`/learning/suggestions/${id}/accept`, { method: "POST", body: { weight: weight ?? null, scope }, schema: AcceptOut, silent: true }),
  /** undo of a dismiss, snooze or accept (P19-S-03): back to open, the decision's evidence taken back, an accepted rule switched off */
  restore: (id: number) => request(`/learning/suggestions/${id}/restore`, { method: "POST", schema: RestoreOut, silent: true }),
  reject: (id: number, reason?: string) => request(`/learning/suggestions/${id}/reject`, { method: "POST", body: { reason: reason || null }, silent: true }),
  snooze: (id: number, until: SnoozeUntil) => request(`/learning/suggestions/${id}/snooze`, { method: "POST", body: { until }, silent: true }),
  summary: (termId?: number | null) => request(`/learning/memory/summary`, { query: { term_id: termId ?? undefined }, schema: MemorySummary, silent: true }),
  reset: (scope: ResetScope, value: number | null, reason: string) => request(`/learning/reset`, { method: "POST", body: { scope, value, reason }, schema: ResetRow, silent: true }),
  resets: () => request(`/learning/resets`, { schema: z.array(ResetRow), silent: true }),
  undoReset: (id: number) => request(`/learning/resets/${id}/undo`, { method: "POST", schema: ResetRow, silent: true }),
  erase: (instructorId: number, reason: string) => request(`/learning/erase`, { method: "POST", body: { instructor_id: instructorId, reason }, schema: ResetRow, silent: true }),
};

export const lk = {
  suggestions: (termId: number | null, personId?: number | null, state = "all") => ["learning", "suggestions", termId, personId ?? null, state] as const,
  summary: (termId?: number | null) => ["learning", "summary", termId ?? null] as const,
  resets: ["learning", "resets"] as const,
};

const noRetry = (n: number, e: unknown) => !(e instanceof HttpError && [401, 403, 404, 422].includes(e.status)) && n < 2;

/** every state at once: the card list splits Bekleyen / Geçmiş itself (one request, one cache entry) */
export function useSuggestions(termId: number | null, personId?: number | null, enabled = true) {
  return useQuery({
    queryKey: lk.suggestions(termId, personId),
    queryFn: () => learningApi.suggestions({ term_id: termId ?? 0, person_id: personId ?? undefined, state: "all", limit: 500 }),
    enabled: enabled && termId !== null,
    retry: noRetry,
    staleTime: 60_000,
  });
}
export function useMemorySummary(termId?: number | null, enabled = true) {
  return useQuery({ queryKey: lk.summary(termId), queryFn: () => learningApi.summary(termId), enabled, retry: noRetry });
}
export function useResets(enabled = true) {
  return useQuery({ queryKey: lk.resets, queryFn: learningApi.resets, enabled, retry: noRetry });
}

export function useSuggestionActions() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ["learning"] });
  return {
    accept: useMutation({ mutationFn: (v: { id: number; weight?: number; scope?: AcceptScope }) => learningApi.accept(v.id, v.weight, v.scope), onSuccess: () => { void done(); void qc.invalidateQueries({ queryKey: ["moderation"] }); } }),
    reject: useMutation({ mutationFn: (v: { id: number; reason?: string }) => learningApi.reject(v.id, v.reason), onSuccess: done }),
    snooze: useMutation({ mutationFn: (v: { id: number; until: SnoozeUntil }) => learningApi.snooze(v.id, v.until), onSuccess: done }),
    restore: useMutation({ mutationFn: (id: number) => learningApi.restore(id), onSuccess: () => { void done(); void qc.invalidateQueries({ queryKey: ["moderation"] }); } }),
  };
}

export function useMemoryActions() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ["learning"] });
  return {
    reset: useMutation({ mutationFn: (v: { scope: ResetScope; value: number | null; reason: string }) => learningApi.reset(v.scope, v.value, v.reason), onSuccess: done }),
    undo: useMutation({ mutationFn: (id: number) => learningApi.undoReset(id), onSuccess: done }),
    erase: useMutation({ mutationFn: (v: { instructorId: number; reason: string }) => learningApi.erase(v.instructorId, v.reason), onSuccess: done }),
  };
}
