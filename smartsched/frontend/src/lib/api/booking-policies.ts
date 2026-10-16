"use client";
/**
 * P8 booking policies and exam-period mode (`app/api/v1/booking_policies.py`, service `app/services/booking_policies.py`).
 *
 * - `GET /booking-policies` (setup.settings): every rule plus the exam-period setting.
 * - `POST /booking-policies`, `PUT /booking-policies/{id}`, `DELETE /booking-policies/{id}` (setup.settings; 422
 *   `{code: name|scope_type|scope_id|tag|term_id|effect|<limit>|quiet_hours|blackouts|time|empty}` with TR/EN text).
 * - `PUT /booking-policies/exam-period {mode: off|request|closed, from_exam_timetable?, room_ids?}`.
 * - `GET /booking-policies/effective?room_id=&date=&period_id=&term_id=` (any signed-in user): the rules that bind the
 *   caller in that room and, with a date and a period, the verdict `book | request | refuse` with the reasons
 *   ("Neden?").
 *
 * Booking refusals are 409 `policy_<rule>` with `message_tr` / `message_en`, `policy {id, name, rule}` and `why`; the
 * grid marks slots `reason: "policy"` (refused) or `request_only: true` with `policy` (a Violation); find-a-room
 * answers `status: "policy"` or `"requestable"`.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";

const s = { silent: true } as const;

export const SCOPE_TYPES = ["all", "room", "room_group", "tag"] as const;
export type ScopeType = (typeof SCOPE_TYPES)[number];
export const EFFECTS = ["refuse", "request"] as const;
export type PolicyEffect = (typeof EFFECTS)[number];
export const EXAM_MODES = ["off", "request", "closed"] as const;
export type ExamMode = (typeof EXAM_MODES)[number];
export const RULES = ["min_notice", "max_advance", "max_duration", "max_active", "buffer", "quiet_hours", "blackout", "exam_period"] as const;
export type PolicyRule = (typeof RULES)[number];
/** the numeric limits of a rule, in the order the form lists them (with the backend's bounds) */
export const LIMITS = [
  { key: "min_notice_workdays", min: 0, max: 365 },
  { key: "max_advance_days", min: 0, max: 3650 },
  { key: "max_duration_minutes", min: 10, max: 1440 },
  { key: "max_active_bookings", min: 0, max: 10000 },
  { key: "buffer_minutes", min: 0, max: 240 },
] as const;
export type LimitKey = (typeof LIMITS)[number]["key"];

export const QuietWindow = z.object({ weekdays: z.array(z.number()).default([1, 2, 3, 4, 5, 6, 7]), start: z.string(), end: z.string() });
export type QuietWindow = z.infer<typeof QuietWindow>;
export const Blackout = z.object({ from: z.string(), to: z.string().nullish(), label: z.string().nullish() });
export type Blackout = z.infer<typeof Blackout>;

export const Policy = z.object({
  id: z.number(),
  name: z.string(),
  enabled: z.boolean(),
  term_id: z.number().nullish(),
  scope_type: z.enum(SCOPE_TYPES).catch("all"),
  scope_id: z.number().nullish(),
  tag: z.string().nullish(),
  role_codes: z.array(z.string()).default([]),
  effect: z.enum(EFFECTS).catch("refuse"),
  min_notice_workdays: z.number().nullish(),
  max_advance_days: z.number().nullish(),
  max_duration_minutes: z.number().nullish(),
  max_active_bookings: z.number().nullish(),
  buffer_minutes: z.number().nullish(),
  quiet_hours: z.array(QuietWindow).default([]),
  blackouts: z.array(Blackout).default([]),
  note: z.string().nullish(),
  summary: z.object({ tr: z.array(z.string()).default([]), en: z.array(z.string()).default([]) }).default({ tr: [], en: [] }),
  created_at: z.string().nullish(),
  updated_at: z.string().nullish(),
});
export type Policy = z.infer<typeof Policy>;

export const ExamPeriod = z.object({ mode: z.enum(EXAM_MODES).catch("off"), from_exam_timetable: z.boolean().default(true), room_ids: z.array(z.number()).default([]) });
export type ExamPeriod = z.infer<typeof ExamPeriod>;

export const PolicyList = z.object({ policies: z.array(Policy).default([]), exam_period: ExamPeriod });
export type PolicyList = z.infer<typeof PolicyList>;

export interface PolicyIn {
  name: string;
  enabled: boolean;
  term_id: number | null;
  scope_type: ScopeType;
  scope_id: number | null;
  tag: string | null;
  role_codes: string[];
  effect: PolicyEffect;
  min_notice_workdays: number | null;
  max_advance_days: number | null;
  max_duration_minutes: number | null;
  max_active_bookings: number | null;
  buffer_minutes: number | null;
  quiet_hours: QuietWindow[];
  blackouts: { from: string; to?: string | null; label?: string | null }[];
  note: string | null;
}

/** One broken rule (`Violation.as_dict()`): what a refusal, a request-only slot and "Neden?" carry. */
export const Violation = z
  .object({
    rule: z.string(),
    effect: z.enum(EFFECTS).catch("refuse"),
    message_tr: z.string(),
    message_en: z.string(),
    policy_id: z.number().nullish(),
    policy_name: z.string().nullish(),
  })
  .passthrough();
export type Violation = z.infer<typeof Violation>;

export const Effective = z.object({
  room_id: z.number(),
  term_id: z.number(),
  exempt: z.boolean().default(false),
  policies: z.array(Policy).default([]),
  exam_period: z.object({ mode: z.enum(EXAM_MODES).catch("off"), exam_room: z.boolean().default(false) }).nullish(),
  date: z.string().nullish(),
  period_id: z.number().nullish(),
  violations: z.array(Violation).nullish(),
  verdict: z.enum(["book", "request", "refuse"]).nullish(),
});
export type Effective = z.infer<typeof Effective>;

export interface EffectiveQuery {
  room_id: number;
  date?: string | null;
  period_id?: number | null;
  term_id?: number | null;
}

export const policyKeys = {
  list: ["policies", "list"] as const,
  effective: (q: EffectiveQuery) => ["policies", "effective", q.room_id, q.date ?? null, q.period_id ?? null, q.term_id ?? null] as const,
};

export const policiesApi = {
  list: () => request("/booking-policies", { schema: PolicyList, ...s }),
  create: (body: PolicyIn) => request("/booking-policies", { method: "POST", body, schema: Policy, ...s }),
  update: (id: number, body: PolicyIn) => request(`/booking-policies/${id}`, { method: "PUT", body, schema: Policy, ...s }),
  remove: (id: number) => request<void>(`/booking-policies/${id}`, { method: "DELETE", ...s }),
  examPeriod: (body: Partial<ExamPeriod>) => request("/booking-policies/exam-period", { method: "PUT", body, schema: ExamPeriod, ...s }),
  effective: (q: EffectiveQuery) => request("/booking-policies/effective", { query: { room_id: q.room_id, date: q.date, period_id: q.period_id, term_id: q.term_id }, schema: Effective, ...s }),
};

export function usePolicies(enabled = true) {
  return useQuery({ queryKey: policyKeys.list, queryFn: policiesApi.list, enabled, retry: false });
}

/** "Neden?": fetched only when the popover opens (`enabled`). */
export function useEffectivePolicies(q: EffectiveQuery | null, enabled: boolean) {
  return useQuery({ queryKey: q ? policyKeys.effective(q) : ["policies", "effective", "none"], queryFn: () => policiesApi.effective(q!), enabled: enabled && !!q, staleTime: 30_000, retry: false });
}

export function useSavePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number | null; body: PolicyIn }) => (id ? policiesApi.update(id, body) : policiesApi.create(body)),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["policies"] });
      void qc.invalidateQueries({ queryKey: ["crbs", "grid"] });
    },
  });
}

export function useDeletePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => policiesApi.remove(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["policies"] });
      void qc.invalidateQueries({ queryKey: ["crbs", "grid"] });
    },
  });
}

export function useSaveExamPeriod() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<ExamPeriod>) => policiesApi.examPeriod(body),
    onSuccess: (exam) => {
      qc.setQueryData<PolicyList>(policyKeys.list, (prev) => (prev ? { ...prev, exam_period: exam } : prev));
      void qc.invalidateQueries({ queryKey: ["crbs", "grid"] });
    },
  });
}

/* ------------------------------------------------------------------------------- pure form helpers */

/** A blank rule: no limit set (the backend refuses a rule without one, 422 `empty`). */
export function emptyPolicy(): PolicyIn {
  return {
    name: "",
    enabled: true,
    term_id: null,
    scope_type: "all",
    scope_id: null,
    tag: null,
    role_codes: [],
    effect: "refuse",
    min_notice_workdays: null,
    max_advance_days: null,
    max_duration_minutes: null,
    max_active_bookings: null,
    buffer_minutes: null,
    quiet_hours: [],
    blackouts: [],
    note: null,
  };
}

export function policyToInput(p: Policy): PolicyIn {
  return {
    name: p.name,
    enabled: p.enabled,
    term_id: p.term_id ?? null,
    scope_type: p.scope_type,
    scope_id: p.scope_id ?? null,
    tag: p.tag ?? null,
    role_codes: [...p.role_codes],
    effect: p.effect,
    min_notice_workdays: p.min_notice_workdays ?? null,
    max_advance_days: p.max_advance_days ?? null,
    max_duration_minutes: p.max_duration_minutes ?? null,
    max_active_bookings: p.max_active_bookings ?? null,
    buffer_minutes: p.buffer_minutes ?? null,
    quiet_hours: p.quiet_hours.map((w) => ({ ...w, weekdays: [...w.weekdays] })),
    blackouts: p.blackouts.map((b) => ({ from: b.from, to: b.to ?? b.from, label: b.label ?? null })),
    note: p.note ?? null,
  };
}

export type PolicyFormError = "name" | "scope_id" | "tag" | "empty" | "quiet" | "blackout";

/**
 * The checks the form makes before it sends (the backend checks again and answers 422 with its own words): a name,
 * the scope's target, at least one limit, every quiet window with a start, an end and a weekday, every blackout with a
 * start not after its end.
 */
export function validatePolicy(p: PolicyIn): PolicyFormError[] {
  const out: PolicyFormError[] = [];
  if (!p.name.trim()) out.push("name");
  if ((p.scope_type === "room" || p.scope_type === "room_group") && p.scope_id == null) out.push("scope_id");
  if (p.scope_type === "tag" && !(p.tag ?? "").trim()) out.push("tag");
  const anyLimit = LIMITS.some((l) => p[l.key] != null) || p.quiet_hours.length > 0 || p.blackouts.length > 0;
  if (!anyLimit) out.push("empty");
  if (p.quiet_hours.some((w) => !w.start || !w.end || w.start === w.end || w.weekdays.length === 0)) out.push("quiet");
  if (p.blackouts.some((b) => !b.from || (b.to && b.to < b.from))) out.push("blackout");
  return out;
}

/** The body the backend takes: scope fields only for their scope, trimmed text, a blackout without an end ends on its start. */
export function toPayload(p: PolicyIn): PolicyIn {
  return {
    ...p,
    name: p.name.trim(),
    scope_id: p.scope_type === "room" || p.scope_type === "room_group" ? p.scope_id : null,
    tag: p.scope_type === "tag" ? (p.tag ?? "").trim() || null : null,
    role_codes: [...new Set(p.role_codes.map((r) => r.trim().toUpperCase()).filter(Boolean))],
    blackouts: p.blackouts.map((b) => ({ from: b.from, to: b.to || b.from, label: (b.label ?? "").trim() || null })),
    note: (p.note ?? "").trim() || null,
  };
}

/** `"8"` → 8, `""` → null (an emptied limit field removes the limit). */
export function parseLimit(text: string): number | null {
  const t = text.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

/** The violation in the reader's language. */
export function violationText(v: Pick<Violation, "message_tr" | "message_en">, locale: string): string {
  return locale === "tr" ? v.message_tr : v.message_en;
}
