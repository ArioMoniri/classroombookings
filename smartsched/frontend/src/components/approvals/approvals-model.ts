/**
 * Approval workflows (P1, docs/product/wave1-api.md §4): what a request says and how its timeline reads.
 * Pure functions (no React), unit-tested in approvals-model.test.ts.
 */
import type { ApprovalRequest, Decision, RequestBooking, Rule, RuleSnapshot, Scope, Suggested } from "@/lib/api/wave1";

export type RequestStatus = "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | "WITHDRAWN";
export type Tone = "pending" | "ok" | "bad" | "muted";

export function statusTone(status: string): Tone {
  if (status === "PENDING") return "pending";
  if (status === "APPROVED" || status === "BOOKED") return "ok";
  if (status === "REJECTED") return "bad";
  return "muted";
}

export const isOpen = (r: Pick<ApprovalRequest, "status">) => r.status === "PENDING";

/** The request's dates (sorted, unique) and the period span of its first booking. */
export function requestSlots(r: Pick<ApprovalRequest, "bookings">): { dates: string[]; first: RequestBooking | null; periods: string } {
  const rows = [...r.bookings].sort((a, b) => (a.date === b.date ? a.start_period - b.start_period : a.date < b.date ? -1 : 1));
  const dates = [...new Set(rows.map((b) => b.date))];
  const first = rows[0] ?? null;
  const periods = first ? (first.period_name ?? (first.start_period === first.end_period ? `P${first.start_period}` : `P${first.start_period}–P${first.end_period}`)) : "";
  return { dates, first, periods };
}

/** Bookings of the request that are still open (a series may have dates the approver can pick). */
export function openDates(r: Pick<ApprovalRequest, "bookings">): string[] {
  return [...new Set(r.bookings.filter((b) => b.status === "PENDING").map((b) => b.date))].sort();
}

export type TimelineEntry =
  | { kind: "requested"; at: string | null; by: string | null }
  | { kind: "decision"; at: string | null; by: string | null; decision: "approve" | "reject"; note: string | null; reasonCode: string | null; step: number; alternative: Record<string, unknown> | null }
  | { kind: "waiting"; step: number; steps: number; approvers: string[]; expires: string | null }
  | { kind: "final"; at: string | null; status: Exclude<RequestStatus, "PENDING"> };

/**
 * Requested → each decision (per step) → either "waiting for step n" (open) or the final state. Decisions
 * come in the order the backend recorded them; the final entry repeats the decision time when it was the
 * last decision that closed the request.
 */
export function timeline(r: ApprovalRequest): TimelineEntry[] {
  const out: TimelineEntry[] = [{ kind: "requested", at: r.requested_at ?? null, by: r.requester_name ?? null }];
  for (const d of r.decisions as Decision[]) {
    out.push({
      kind: "decision",
      at: d.decided_at ?? null,
      by: d.approver_name ?? null,
      decision: d.decision === "APPROVED" || d.decision === "approve" ? "approve" : "reject",
      note: d.note ?? null,
      reasonCode: d.reason_code ?? null,
      step: d.step,
      alternative: (d.alternative as Record<string, unknown> | null | undefined) ?? null,
    });
  }
  if (r.status === "PENDING") {
    out.push({ kind: "waiting", step: r.step, steps: r.steps, approvers: r.approvers.map((a) => a.name ?? "").filter(Boolean), expires: r.expires_at ?? null });
  } else if (r.status === "APPROVED" || r.status === "REJECTED" || r.status === "EXPIRED" || r.status === "WITHDRAWN") {
    out.push({ kind: "final", at: r.decided_at ?? null, status: r.status });
  }
  return out;
}

/** The suggestions a rejected request carries (the approver's one, or the service's free rooms). */
export function suggestionRooms(s: Suggested[]): { roomId: number; name: string; date: string | null; start: number | null; end: number | null; reason: Suggested["reason"] }[] {
  return s.map((x) => ({ roomId: x.room_id, name: x.room_name ?? x.name ?? x.code ?? `#${x.room_id}`, date: x.date ?? null, start: x.start_period ?? null, end: x.end_period ?? null, reason: x.reason ?? null }));
}

/* --------------------------------------------------------------------------------------- rules */

export interface RuleLookups {
  room: (id: number) => string | undefined;
  group: (id: number) => string | undefined;
  term: (id: number) => string | undefined;
  user: (id: number) => string | undefined;
}

/** What a rule covers, in words the admin uses: "A 202", "Tıp Fakültesi (group)", "TIP rooms". */
export function ruleTarget(r: Pick<Rule | RuleSnapshot, "entity_type" | "entity_id" | "tag">, l: Pick<RuleLookups, "room" | "group">): { kind: "room" | "room_group" | "tag"; label: string } {
  if (r.entity_type === "tag") return { kind: "tag", label: r.tag ?? "" };
  if (r.entity_type === "room_group") return { kind: "room_group", label: (r.entity_id != null && l.group(r.entity_id)) || `#${r.entity_id ?? "?"}` };
  return { kind: "room", label: (r.entity_id != null && l.room(r.entity_id)) || `#${r.entity_id ?? "?"}` };
}

/** One approver step per rule step: "designated" or the named users. */
export function stepApprovers(step: { approvers: { type: string; ids?: number[] } }, l: Pick<RuleLookups, "user">): { designated: boolean; names: string[] } {
  if (step.approvers.type !== "users") return { designated: true, names: [] };
  return { designated: false, names: (step.approvers.ids ?? []).map((id) => l.user(id) ?? `#${id}`) };
}

/* -------------------------------------------------------------------------------------- scopes */

export function scopeKey(s: Pick<Scope, "type" | "id" | "tag">): string {
  return s.type === "all" ? "all" : s.type === "tag" ? `tag:${(s.tag ?? "").toUpperCase()}` : `${s.type}:${s.id ?? ""}`;
}

/** Adds or removes one scope; "all" replaces everything else (and is replaced by any narrower pick). */
export function toggleScope(list: Scope[], s: Scope, on: boolean): Scope[] {
  const key = scopeKey(s);
  const rest = list.filter((x) => scopeKey(x) !== key);
  if (!on) return rest;
  if (s.type === "all") return [{ type: "all" }];
  return [...rest.filter((x) => x.type !== "all"), s];
}

/** Clean scopes for `approves_for` / `PUT /approvals/approvers/{id}`: no duplicates, upper-case tags (solver tags are ASCII: TIP, not TİP). */
export function normaliseScopes(list: Scope[]): { type: Scope["type"]; id?: number | null; tag?: string | null }[] {
  const seen = new Set<string>();
  const out: { type: Scope["type"]; id?: number | null; tag?: string | null }[] = [];
  for (const s of list) {
    const k = scopeKey(s);
    if (seen.has(k)) continue;
    seen.add(k);
    if (s.type === "all") out.push({ type: "all" });
    else if (s.type === "tag") {
      if (s.tag?.trim()) out.push({ type: "tag", tag: s.tag.trim().toUpperCase() });
    } else if (s.id != null) out.push({ type: s.type, id: s.id });
  }
  return out.some((x) => x.type === "all") ? [{ type: "all" }] : out;
}

/* ------------------------------------------------------------------------------ decide errors */

export interface DecideAlternative {
  roomId: number;
  name: string;
  date: string | null;
  start: number;
  end: number;
  reason: { tr: string; en: string } | null;
}

/** 409 `conflict` on approve carries T1 alternatives: the rooms the approver may approve in instead. */
export function conflictAlternatives(data: Record<string, unknown>): DecideAlternative[] {
  const raw = Array.isArray(data.alternatives) ? data.alternatives : [];
  const out: DecideAlternative[] = [];
  for (const a of raw) {
    if (!a || typeof a !== "object") continue;
    const x = a as Record<string, unknown>;
    if (typeof x.room_id !== "number") continue;
    const dates = Array.isArray(x.dates) ? x.dates.filter((d): d is string => typeof d === "string") : [];
    const reason = x.reason && typeof x.reason === "object" && "tr" in x.reason && "en" in x.reason ? (x.reason as { tr: string; en: string }) : null;
    out.push({
      roomId: x.room_id,
      name: String(x.name ?? x.room_name ?? x.code ?? `#${x.room_id}`),
      date: typeof x.date === "string" ? x.date : (dates[0] ?? null),
      start: typeof x.start_period === "number" ? x.start_period : 0,
      end: typeof x.end_period === "number" ? x.end_period : 0,
      reason,
    });
  }
  return out;
}

/** A-12: one inbox entry per submission. Requests of one multi-period submission (`group_id`) are shown as one
 *  row, in period order; a request without a group is its own entry. Order follows the first request. */
export interface InboxEntry {
  key: string;
  groupId: number | null;
  requests: ApprovalRequest[];
}

export function groupInbox(rows: readonly ApprovalRequest[]): InboxEntry[] {
  const out: InboxEntry[] = [];
  const byGroup = new Map<string, InboxEntry>();
  for (const r of rows) {
    const b = r.bookings[0];
    const key = r.group_id ? `g${r.group_id}|${b?.date ?? ""}|${r.room_id}` : `r${r.id}`;
    let entry = byGroup.get(key);
    if (!entry) {
      entry = { key, groupId: r.group_id ?? null, requests: [] };
      byGroup.set(key, entry);
      out.push(entry);
    }
    entry.requests.push(r);
  }
  for (const e of out) e.requests.sort((a, b) => (a.bookings[0]?.start_period ?? 0) - (b.bookings[0]?.start_period ?? 0) || a.id - b.id);
  return out;
}

/* ----------------------------------------------------------------------------- rejection reasons */

/** Blank as the backend reads it: spaces, NBSP and the zero-width characters a paste brings along. */
export function isBlank(text: string | null | undefined): boolean {
  return !text || text.replace(/[\s\u00a0\u200b\u200c\u200d\u2060\ufeff]+/g, "") === "";
}

export interface RejectDraft {
  code: string | null;
  text: string;
}
export interface RejectProblems {
  code?: "required";
  text?: "required" | "tooLong";
}

/**
 * Approval-first (owner requirement): a rejection carries a reason code AND a written reason, so the requester
 * always reads why. Stricter than the backend (which takes a code alone, except "other").
 */
export function rejectProblems(d: RejectDraft, max = 1000): RejectProblems {
  const out: RejectProblems = {};
  if (!d.code) out.code = "required";
  if (isBlank(d.text)) out.text = "required";
  else if (d.text.trim().length > max) out.text = "tooLong";
  return out;
}

/**
 * What the requester reads after "Gerekçe:": the code's label and the free text (mirrors the backend's
 * `reason_text`): "Oda uygun değil: Bu saatte bölüm sınavı var." — "other" and a missing label give the text
 * alone, a system reason (slot_taken) or a missing text the label alone.
 */
export function reasonLine(code: string | null | undefined, text: string | null | undefined, label: (code: string) => string | null): string | null {
  const l = code ? label(code) : null;
  const note = isBlank(text) ? null : text!.trim();
  if (code === "slot_taken" || !note) return l ?? note;
  return l && code !== "other" ? `${l}: ${note}` : note;
}

/** The request's own reason: the stored text and code, else the rejecting decision's (per period in a group). */
export function requestReason(r: Pick<ApprovalRequest, "status" | "note" | "reason" | "reason_code" | "decisions">): { code: string | null; text: string | null } | null {
  if (r.status !== "REJECTED") return null;
  const d = [...(r.decisions as Decision[])].reverse().find((x) => x.decision === "REJECTED" || x.decision === "reject");
  const code = r.reason_code ?? d?.reason_code ?? null;
  // `reason` falls back to the code in both languages when there is no text: prefer the plain note
  const text = r.note ?? d?.note ?? (code ? null : (r.reason ?? null));
  return code || text ? { code, text } : null;
}
