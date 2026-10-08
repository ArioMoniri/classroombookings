"use client";
/**
 * Booking enhancements wave 1 (docs/product/wave1-api.md): P10 typed room features, T1 find a room, P7 audit
 * log + undo, P1 approvals and the in-app notifications. Shapes follow `app/schemas/{features,find_room,
 * approvals,audit}.py`; every request is `silent` (callers show the backend's `message_tr` / `message`).
 *
 * T1 reuses the reservation panel's `crbs.rooms.find` result schema (`FindResult`) and only widens it here
 * (reasons, per-date status, alternatives, summary), so the "other available rooms" block and /find-room read
 * one contract.
 */
import { useInfiniteQuery, useQuery, type QueryKey } from "@tanstack/react-query";
import { z } from "zod";
import { request, type Query } from "./client";
import { BookingOut, crbsError, FindResult, type CrbsError } from "./crbs";

/* ------------------------------------------------------------------------------------------ errors */

export interface Wave1Error extends CrbsError {
  /** the backend's Turkish text (`detail.message_tr`), when it sent one */
  messageTr: string | null;
}

/** `{detail: {code, message, message_tr, …}}` → one object; `text(locale)` picks the language. */
export function wave1Error(err: unknown): Wave1Error {
  const base = crbsError(err);
  const tr = base.data.message_tr;
  const impact = base.data.impact as { message_tr?: unknown } | undefined;
  return { ...base, messageTr: typeof tr === "string" ? tr : typeof impact?.message_tr === "string" ? impact.message_tr : null };
}

/** The backend's own sentence in the user's language (Turkish when it sent one, else English). */
export function errorText(e: Wave1Error, locale: string): string {
  return locale === "tr" && e.messageTr ? e.messageTr : e.message;
}

/** `{tr, en}` pairs (find-a-room reasons): Turkish for tr, English for every other language. */
export const Bilingual = z.object({ tr: z.string(), en: z.string() });
export type Bilingual = z.infer<typeof Bilingual>;
export const pickLang = (b: Bilingual | null | undefined, locale: string): string => (b ? (locale === "tr" ? b.tr : b.en) : "");

/* --------------------------------------------------------------------------- P10 typed room features */

export const FEATURE_KINDS = ["BOOLEAN", "NUMBER", "SELECT", "MULTISELECT", "TEXT"] as const;
export type FeatureKind = (typeof FEATURE_KINDS)[number];
export const FEATURE_CATEGORIES = ["av", "seating", "accessibility", "lab", "other"] as const;
export type FeatureCategory = (typeof FEATURE_CATEGORIES)[number];

export const Feature = z.object({
  id: z.number(),
  name: z.string(),
  type: z.string(),
  kind: z.enum(FEATURE_KINDS).catch("TEXT"),
  options: z.array(z.object({ id: z.number(), value: z.string() })).default([]),
  filterable: z.boolean().default(true),
  public: z.boolean().default(true),
  icon: z.string().nullish(),
  unit: z.string().nullish(),
  solver_tag: z.string().nullish(),
  category: z.string().nullish(),
  pos: z.number().default(0),
  counts: z.record(z.string(), z.number()).nullish(),
});
export type Feature = z.infer<typeof Feature>;

export interface FeatureIn {
  name: string;
  type: FeatureKind;
  options: string[];
  filterable: boolean;
  public: boolean;
  icon: string | null;
  unit: string | null;
  solver_tag: string | null;
  category: FeatureCategory | null;
}

export const Impact = z.object({
  tag: z.string().nullish(),
  rooms: z.array(z.string()).default([]),
  room_count: z.number().default(0),
  requests_needing: z.number().default(0),
  message: z.string().nullish(),
  message_tr: z.string().nullish(),
});
export type Impact = z.infer<typeof Impact>;

export const RoomFeatures = z.object({
  room_id: z.number(),
  code: z.string(),
  tags: z.array(z.string()).default([]),
  values: z.record(z.string(), z.unknown()).default({}),
  display: z.record(z.string(), z.unknown()).default({}),
});
export type RoomFeatures = z.infer<typeof RoomFeatures>;

export const BulkReport = z.object({
  dry_run: z.boolean(),
  rooms: z.number(),
  cells: z.number(),
  errors: z.number(),
  unknown_columns: z.array(z.string()).default([]),
  applied: z.number().default(0),
  report: z.array(
    z.object({ line: z.number().nullish(), room: z.string().nullish(), field: z.string().nullish(), value: z.unknown().optional(), status: z.string(), message: z.string().nullish() }),
  ),
});
export type BulkReport = z.infer<typeof BulkReport>;

/* --------------------------------------------------------------------------------- T1 find a room */

export const FindStatus = ["free", "requestable", "partial", "busy", "too_small", "feature_missing", "capacity_unknown", "closed"] as const;
export type FindStatus = (typeof FindStatus)[number];

export const FindRow = FindResult.extend({
  reasons: z.array(Bilingual).default([]),
  busy_with: z.string().nullish(),
  free_dates: z.number().default(0),
  open_dates: z.number().default(0),
  per_date: z.array(z.object({ date: z.string(), status: z.string(), reason: z.string().nullish() })).nullish(),
});
export type FindRow = z.infer<typeof FindRow>;

export const FindAlternative = z.object({
  kind: z.string(),
  room_id: z.number(),
  code: z.string(),
  name: z.string(),
  dates: z.array(z.string()).default([]),
  date: z.string().nullish(),
  start_period: z.number(),
  end_period: z.number(),
  reason: Bilingual.nullish(),
});
export type FindAlternative = z.infer<typeof FindAlternative>;

export const FindResponse = z.object({
  query_echo: z.record(z.string(), z.unknown()).optional(),
  term_id: z.number().nullish(),
  slots: z.array(z.object({ date: z.string(), start_period: z.number(), end_period: z.number() })).default([]),
  duration_periods: z.number().nullish(),
  time: z.object({ start: z.string(), end: z.string() }).nullish(),
  closed_dates: z.array(z.object({ date: z.string(), reason: z.string().nullish(), holiday: z.string().nullish() })).default([]),
  preferred_building: z.string().nullish(),
  summary: z.object({ rooms: z.number(), free: z.number(), dates: z.number(), open_dates: z.number(), text_tr: z.string(), text_en: z.string() }).nullish(),
  results: z.array(FindRow).default([]),
  alternatives: z.array(FindAlternative).default([]),
  timing_ms: z.number().nullish(),
});
export type FindResponse = z.infer<typeof FindResponse>;

export interface FeatureFilter {
  field: number | string;
  op?: "eq" | "gte" | "lte" | "in" | "has" | "contains";
  value?: unknown;
}

/** `POST /rooms/find` body (every field optional except `start` and one way of giving dates). */
export interface FindQuery {
  term_id?: number;
  date?: string;
  dates?: string[];
  date_from?: string;
  date_to?: string;
  weekdays?: number[];
  weekday?: number;
  weeks?: number[];
  start: string | number;
  end?: string | number;
  duration_periods?: number;
  duration_min?: number;
  window_end?: string | number;
  headcount?: number;
  purpose?: "teaching" | "exam";
  features?: FeatureFilter[];
  tags?: string[];
  buildings?: string[];
  preferred_building?: string;
  room_group_id?: number | null;
  text?: string;
  include_busy?: boolean;
  include_requestable?: boolean;
  flex?: { periods: number; other_days?: boolean };
  limit?: number;
}

/* ------------------------------------------------------------------------------------- P1 approvals */

export const Decision = z.object({
  step: z.number(),
  approver_user_id: z.number().nullish(),
  approver_name: z.string().nullish(),
  decision: z.string(),
  note: z.string().nullish(),
  alternative: z.record(z.string(), z.unknown()).nullish(),
  decided_at: z.string().nullish(),
});
export type Decision = z.infer<typeof Decision>;

export const Suggested = z.object({
  room_id: z.number(),
  code: z.string().nullish(),
  name: z.string().nullish(),
  room_name: z.string().nullish(),
  capacity: z.number().nullish(),
  date: z.string().nullish(),
  start_period: z.number().nullish(),
  end_period: z.number().nullish(),
  reason: Bilingual.nullish(),
});
export type Suggested = z.infer<typeof Suggested>;

export const RequestBooking = BookingOut.extend({ headcount: z.number().nullish(), held_until: z.string().nullish() });
export type RequestBooking = z.infer<typeof RequestBooking>;

export const RuleSnapshot = z
  .object({
    rule_id: z.number().nullish(),
    name: z.string().nullish(),
    entity_type: z.string().nullish(),
    entity_id: z.number().nullish(),
    tag: z.string().nullish(),
    steps: z.array(z.record(z.string(), z.unknown())).default([]),
    hold_minutes: z.number().default(0),
    lead_time_workdays: z.number().default(0),
    expires_before_start_minutes: z.number().default(0),
    allow_self_approve: z.boolean().default(false),
  })
  .passthrough();
export type RuleSnapshot = z.infer<typeof RuleSnapshot>;

export const ApprovalRequest = z.object({
  id: z.number(),
  status: z.string(),
  step: z.number(),
  steps: z.number(),
  rule: RuleSnapshot.nullish(),
  room_id: z.number(),
  room_name: z.string().nullish(),
  term_id: z.number().nullish(),
  series_id: z.number().nullish(),
  booking_id: z.number().nullish(),
  requested_by: z.number().nullish(),
  requester_name: z.string().nullish(),
  requested_at: z.string().nullish(),
  expires_at: z.string().nullish(),
  decided_at: z.string().nullish(),
  note: z.string().nullish(),
  /** reject: the approver's alternative, or `{alternatives: [...]}` the service suggested */
  suggestion: z.union([z.object({ alternatives: z.array(Suggested) }), Suggested]).nullish(),
  bookings: z.array(RequestBooking).default([]),
  decisions: z.array(Decision).default([]),
  approvers: z.array(z.object({ id: z.number(), name: z.string().nullish() })).default([]),
  competing: z.array(z.number()).default([]),
});
export type ApprovalRequest = z.infer<typeof ApprovalRequest>;

/** The suggested rooms of a rejected request, whichever form the backend stored. */
export function suggestionsOf(req: Pick<ApprovalRequest, "suggestion">): Suggested[] {
  const s = req.suggestion;
  if (!s) return [];
  return "alternatives" in s ? s.alternatives : [s];
}

export const RuleCheck = z.object({
  room_id: z.number(),
  action: z.enum(["book", "request", "none"]).catch("none"),
  rule: RuleSnapshot.nullish(),
  approvers: z.array(z.object({ id: z.number(), name: z.string().nullish() })).default([]),
  summary_tr: z.string(),
  summary_en: z.string(),
});
export type RuleCheck = z.infer<typeof RuleCheck>;

export interface StepIn {
  approvers: { type: "designated" } | { type: "users"; ids: number[] };
  min_approvals: number;
}
export interface RuleIn {
  name: string | null;
  entity_type: "room" | "room_group" | "tag";
  entity_id: number | null;
  tag: string | null;
  term_id: number | null;
  steps: StepIn[];
  hold_minutes: number;
  lead_time_workdays: number;
  expires_before_start_minutes: number;
  allow_self_approve: boolean;
  active: boolean;
}
export const Rule = z.object({
  id: z.number(),
  name: z.string().nullish(),
  entity_type: z.enum(["room", "room_group", "tag"]).catch("room"),
  entity_id: z.number().nullish(),
  tag: z.string().nullish(),
  term_id: z.number().nullish(),
  steps: z.array(z.object({ approvers: z.object({ type: z.string(), ids: z.array(z.number()).optional() }).passthrough(), min_approvals: z.number().default(1) }).passthrough()),
  hold_minutes: z.number(),
  lead_time_workdays: z.number(),
  expires_before_start_minutes: z.number(),
  allow_self_approve: z.boolean(),
  active: z.boolean(),
  created_at: z.string().nullish(),
});
export type Rule = z.infer<typeof Rule>;

export type ScopeType = "all" | "room" | "room_group" | "tag";
export const Scope = z.object({ type: z.enum(["all", "room", "room_group", "tag"]), id: z.number().nullish(), tag: z.string().nullish() });
export type Scope = z.infer<typeof Scope>;
export const Approver = z.object({ user_id: z.number(), name: z.string().nullish(), email: z.string().nullish(), can_decide: z.boolean(), scopes: z.array(Scope).default([]) });
export type Approver = z.infer<typeof Approver>;

export interface DecideIn {
  decision: "approve" | "reject";
  note?: string | null;
  alternative?: { room_id?: number; date?: string; period_id?: number; start_period?: number; end_period?: number } | null;
  instances?: string[] | null;
}

/* ------------------------------------------------------------------------------------- notifications */

export const Notification = z.object({
  id: z.number(),
  kind: z.string(),
  title: z.string(),
  body: z.string().default(""),
  link: z.string().nullish(),
  booking_id: z.number().nullish(),
  request_id: z.number().nullish(),
  read_at: z.string().nullish(),
  created_at: z.string().nullish(),
});
export type Notification = z.infer<typeof Notification>;

/* ---------------------------------------------------------------------------------------- P7 audit */

export const AuditEvent = z.object({
  id: z.number(),
  ts: z.string().nullish(),
  actor_type: z.string(),
  actor_id: z.number().nullish(),
  actor_label: z.string().nullish(),
  action: z.string(),
  entity_type: z.string(),
  entity_id: z.string().nullish(),
  term_id: z.number().nullish(),
  before: z.record(z.string(), z.unknown()).nullish(),
  after: z.record(z.string(), z.unknown()).nullish(),
  diff: z.record(z.string(), z.unknown()).nullish(),
  reason: z.string().nullish(),
  reversible: z.boolean().default(false),
  undo_of: z.number().nullish(),
  parent_id: z.number().nullish(),
  undone: z.boolean().default(false),
  request_id: z.string().nullish(),
  ip_hash: z.string().nullish(),
  children: z.array(z.record(z.string(), z.unknown())).nullish(),
});
export type AuditEvent = z.infer<typeof AuditEvent>;
export const AuditPage = z.object({ items: z.array(AuditEvent), next_cursor: z.number().nullish() });
export type AuditPage = z.infer<typeof AuditPage>;
export const UndoOut = z.object({ undone: z.number(), action: z.string(), booking_ids: z.array(z.number()).default([]) });
export type UndoOut = z.infer<typeof UndoOut>;

export interface AuditFilters {
  actor_id?: number;
  entity_type?: string;
  entity_id?: string;
  action?: string;
  from?: string;
  to?: string;
}

/* ---------------------------------------------------------------------------------------- requests */

const s = { silent: true } as const;
const get = <T>(path: string, schema: z.ZodType<T>, query?: Query) => request(path, { ...s, query, schema });
const send = <T>(method: "POST" | "PUT" | "DELETE", path: string, body?: unknown, schema?: z.ZodType<T>, query?: Query) => request<T>(path, { ...s, method, body, schema, query });

export const wave1 = {
  features: {
    list: () => get("/room-admin/features", z.array(Feature)),
    facets: () => get("/rooms/facets", z.array(Feature)),
    create: (body: FeatureIn) => send("POST", "/room-admin/features", body, Feature),
    update: (id: number, body: FeatureIn, confirm = false) => send("PUT", `/room-admin/features/${id}`, body, Feature, { confirm: confirm || undefined }),
    remove: (id: number, confirm = false) => send("DELETE", `/room-admin/features/${id}`, undefined, z.object({ deleted: z.number(), impact: Impact.nullish() }), { confirm: confirm || undefined }),
    impact: (id: number) => get(`/room-admin/features/${id}/impact`, Impact),
    adoptTags: () => send("POST", "/room-admin/features/adopt-tags", undefined, z.array(Feature)),
    template: () => send("POST", "/room-admin/features/template", undefined, z.array(Feature)),
    bulk: (file: File, dryRun: boolean, skipErrors: boolean) => {
      const fd = new FormData();
      fd.append("file", file);
      return request("/room-admin/features/bulk-values", { ...s, method: "POST", formData: fd, schema: BulkReport, query: { dry_run: dryRun, skip_errors: skipErrors } });
    },
    roomValues: (roomId: number) => get(`/room-admin/rooms/${roomId}/features`, RoomFeatures),
    putRoomValues: (roomId: number, body: Record<string, unknown>) => send("PUT", `/room-admin/rooms/${roomId}/features`, body, RoomFeatures),
  },
  find: {
    search: (body: FindQuery) => send("POST", "/rooms/find", body, FindResponse),
    recent: () => get("/rooms/find/recent", z.array(z.record(z.string(), z.unknown()))),
  },
  approvals: {
    check: (roomId: number, termId?: number) => get(`/approvals/rooms/${roomId}/check`, RuleCheck, { term_id: termId }),
    inbox: (status: "open" | "decided" | "all" = "open") => get("/approvals/inbox", z.array(ApprovalRequest), { status }),
    mine: () => get("/approvals/mine", z.array(ApprovalRequest)),
    get: (id: number) => get(`/approvals/${id}`, ApprovalRequest),
    decide: (id: number, body: DecideIn) => send("POST", `/approvals/${id}/decide`, body, ApprovalRequest),
    withdraw: (id: number) => send("POST", `/approvals/${id}/withdraw`, undefined, ApprovalRequest),
    approvers: () => get("/approvals/approvers", z.array(Approver)),
    setApprover: (userId: number, scopes: Scope[]) => send("PUT", `/approvals/approvers/${userId}`, { scopes }, Approver),
    rules: () => get("/approval-rules", z.array(Rule)),
    createRule: (body: RuleIn) => send("POST", "/approval-rules", body, Rule),
    updateRule: (id: number, body: RuleIn) => send("PUT", `/approval-rules/${id}`, body, Rule),
    deleteRule: (id: number) => send("DELETE", `/approval-rules/${id}`),
  },
  notifications: {
    list: (q: { unread?: boolean; limit?: number } = {}) => get("/me/notifications", z.array(Notification), { unread: q.unread || undefined, limit: q.limit }),
    read: (body: { ids: number[] } | { all: true }) => send("POST", "/me/notifications/read", body, z.object({ read: z.number() })),
  },
  audit: {
    list: (f: AuditFilters & { cursor?: number; limit?: number }) => get("/audit", AuditPage, { ...f }),
    get: (id: number) => get(`/audit/${id}`, AuditEvent),
    undo: (id: number) => send("POST", `/audit/${id}/undo`, undefined, UndoOut),
    /** same-origin link (the Next proxy adds the session); a plain download, no fetch */
    exportUrl: (f: Pick<AuditFilters, "from" | "to" | "entity_type">) => {
      const qs = new URLSearchParams(Object.entries(f).filter((e): e is [string, string] => typeof e[1] === "string" && e[1] !== "")).toString();
      return `/api/v1/audit/export.csv${qs ? `?${qs}` : ""}`;
    },
  },
};

/* ------------------------------------------------------------------------------------------- hooks */

export const w1Keys = {
  features: ["w1", "features"] as const,
  facets: ["w1", "facets"] as const,
  roomFeatures: (id: number) => ["w1", "room-features", id] as const,
  recent: ["w1", "find-recent"] as const,
  inbox: (status: string) => ["w1", "approvals", "inbox", status] as const,
  mine: ["w1", "approvals", "mine"] as const,
  request: (id: number) => ["w1", "approvals", "request", id] as const,
  check: (roomId: number, termId?: number) => ["w1", "approvals", "check", roomId, termId ?? null] as const,
  rules: ["w1", "approval-rules"] as const,
  approvers: ["w1", "approvers"] as const,
  notifications: ["w1", "notifications"] as const,
  audit: (f: AuditFilters) => ["w1", "audit", f] as const,
};

/** Everything that changes when a request is decided or withdrawn (inbox, timeline, bell, grid). */
export const APPROVAL_KEYS: QueryKey[] = [["w1", "approvals"], w1Keys.notifications, ["crbs", "grid"], ["crbs", "mine"], ["crbs", "booking"]];
export const FEATURE_KEYS: QueryKey[] = [["w1", "features"], w1Keys.facets, ["w1", "room-features"], ["crbs", "fields"], ["crbs", "room-fields"], ["crbs", "admin-rooms"], ["crbs", "booking-rooms"], ["rooms"]];

export const useFeatures = (enabled = true) => useQuery({ queryKey: w1Keys.features, queryFn: wave1.features.list, enabled, retry: false });
export const useFacets = (enabled = true) => useQuery({ queryKey: w1Keys.facets, queryFn: wave1.features.facets, enabled, retry: false, staleTime: 60_000 });
export const useRoomFeatures = (roomId: number | null) =>
  useQuery({ queryKey: w1Keys.roomFeatures(roomId ?? 0), queryFn: () => wave1.features.roomValues(roomId ?? 0), enabled: roomId !== null, retry: false });
export const useRecentSearches = (enabled = true) => useQuery({ queryKey: w1Keys.recent, queryFn: wave1.find.recent, enabled, retry: false, staleTime: 30_000 });
export const useApprovalInbox = (status: "open" | "decided" | "all", enabled = true) =>
  useQuery({ queryKey: w1Keys.inbox(status), queryFn: () => wave1.approvals.inbox(status), enabled, retry: false, refetchInterval: 60_000 });
export const useMyRequests = (enabled = true) => useQuery({ queryKey: w1Keys.mine, queryFn: wave1.approvals.mine, enabled, retry: false });
export const useApprovalRequest = (id: number | null) => useQuery({ queryKey: w1Keys.request(id ?? 0), queryFn: () => wave1.approvals.get(id ?? 0), enabled: id !== null, retry: false });
export const useRoomApprovalCheck = (roomId: number | null, termId?: number) =>
  useQuery({ queryKey: w1Keys.check(roomId ?? 0, termId), queryFn: () => wave1.approvals.check(roomId ?? 0, termId), enabled: roomId !== null, retry: false, staleTime: 60_000 });
export const useApprovalRules = (enabled = true) => useQuery({ queryKey: w1Keys.rules, queryFn: wave1.approvals.rules, enabled, retry: false });
export const useApprovers = (enabled = true) => useQuery({ queryKey: w1Keys.approvers, queryFn: wave1.approvals.approvers, enabled, retry: false });
/** The bell: the newest 30 (read and unread); polled every minute while the tab is open. */
export const useNotifications = (enabled = true) =>
  useQuery({ queryKey: w1Keys.notifications, queryFn: () => wave1.notifications.list({ limit: 30 }), enabled, retry: false, refetchInterval: 60_000, staleTime: 20_000 });

export function useAuditLog(filters: AuditFilters, enabled = true) {
  return useInfiniteQuery({
    queryKey: w1Keys.audit(filters),
    queryFn: ({ pageParam }) => wave1.audit.list({ ...filters, cursor: pageParam ?? undefined, limit: 50 }),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    enabled,
    retry: false,
  });
}
