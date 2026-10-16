/**
 * Audit log (P7, docs/product/wave1-api.md §3): the before/after diff of an event as rows, the filter
 * vocabulary and the undo refusal reasons. Pure functions, unit-tested in audit-model.test.ts.
 */
import type { AuditEvent } from "@/lib/api/wave1";

export const ENTITY_TYPES = [
  "booking",
  "approval_request",
  "approval_rule",
  "approver",
  "room",
  "room_feature",
  "room_group",
  "room_acl",
  "room_field",
  "user",
  "role",
  "settings",
  "schedule",
  "period",
  "session",
  "timetable_week",
  "holiday",
  "department",
  "translation",
  "building",
  "term",
  "user_constraints",
] as const;

/** Action prefixes the filter offers (`action` is a prefix on the backend: `booking.` matches all). */
export const ACTION_PREFIXES = ["booking.", "series.", "approval.", "approval_rule.", "approver.", "room.", "room_feature.", "user.", "role.", "room_acl.", "settings."] as const;

/** Actions the backend can undo (`POST /audit/{id}/undo`). */
export const UNDOABLE = new Set(["booking.create", "series.create", "booking.move", "booking.cancel"]);

/** A wizard programme (`program.create` / `program.restore`, `undo_via: "program_draft"`) is undone by the drafts undo. */
export const isProgramUndo = (e: Pick<AuditEvent, "undo_via">) => e.undo_via === "program_draft";

export const canUndo = (e: Pick<AuditEvent, "reversible" | "undone" | "action" | "undo_of" | "undo_via">) =>
  e.reversible && !e.undone && !e.undo_of && (UNDOABLE.has(e.action) || isProgramUndo(e));

/** Archived kinds in the order the success message lists them. */
export const ARCHIVED_KINDS = ["program", "faculty", "courses", "sections", "requests", "people", "rules"] as const;

/** `{sections: [ids], …}` → [["sections", 3], …] for the kinds with something archived, in ARCHIVED_KINDS order. */
export function archivedCounts(archived: Record<string, readonly number[]> | null | undefined): [string, number][] {
  if (!archived) return [];
  const known = ARCHIVED_KINDS.filter((k) => (archived[k]?.length ?? 0) > 0).map((k) => [k, archived[k]!.length] as [string, number]);
  const other = Object.entries(archived).filter(([k, v]) => !(ARCHIVED_KINDS as readonly string[]).includes(k) && v.length > 0).map(([k, v]) => [k, v.length] as [string, number]);
  return [...known, ...other];
}

/** 409 `blocked` on a programme undo: the blockers in the UI language. */
export function undoBlockers(data: Record<string, unknown>, locale: string): string[] {
  if (!Array.isArray(data.blockers)) return [];
  return data.blockers
    .map((b) => {
      if (!b || typeof b !== "object") return null;
      const text = (b as Record<string, unknown>).text;
      if (text && typeof text === "object") {
        const tx = text as Record<string, unknown>;
        const v = (locale === "tr" ? [tx.tr, tx.en] : [tx.en, tx.tr]).find((x): x is string => typeof x === "string" && !!x.trim());
        if (v) return v;
      }
      const code = (b as Record<string, unknown>).code;
      return typeof code === "string" ? code : null;
    })
    .filter((x): x is string => !!x);
}

export interface DiffRow {
  field: string;
  before: unknown;
  after: unknown;
  changed: boolean;
}

/**
 * Rows for the diff table: `diff` ({field: [old, new]}) when the backend computed one, else the union of
 * `before` and `after` keys (a create has only after, a delete only before). Secrets arrive as "***".
 */
export function diffRows(e: Pick<AuditEvent, "before" | "after" | "diff">): DiffRow[] {
  const diff = e.diff ?? null;
  if (diff && Object.keys(diff).length) {
    return Object.entries(diff).map(([field, v]) => {
      const pair = Array.isArray(v) && v.length === 2 ? v : [undefined, v];
      return { field, before: pair[0], after: pair[1], changed: true };
    });
  }
  const before = e.before ?? {};
  const after = e.after ?? {};
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])];
  return keys.map((field) => ({ field, before: before[field], after: after[field], changed: JSON.stringify(before[field]) !== JSON.stringify(after[field]) }));
}

/** A value as one line: null / empty → "—", objects as compact JSON, booleans as ✓ / ✗ words by the caller. */
export function valueText(v: unknown, words: { yes: string; no: string } = { yes: "true", no: "false" }): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? words.yes : words.no;
  if (typeof v === "string" || typeof v === "number") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

/** Filter state → `GET /audit` query (empty fields dropped; dates as ISO days). */
export interface AuditFilterForm {
  entityType: string;
  entityId: string;
  action: string;
  actorId: string;
  from: string;
  to: string;
}

export const emptyAuditFilters: AuditFilterForm = { entityType: "", entityId: "", action: "", actorId: "", from: "", to: "" };

export function auditQuery(f: AuditFilterForm): { entity_type?: string; entity_id?: string; action?: string; actor_id?: number; from?: string; to?: string } {
  const out: ReturnType<typeof auditQuery> = {};
  if (f.entityType) out.entity_type = f.entityType;
  if (f.entityId.trim()) out.entity_id = f.entityId.trim();
  if (f.action) out.action = f.action;
  if (f.actorId && Number(f.actorId) > 0) out.actor_id = Number(f.actorId);
  if (/^\d{4}-\d{2}-\d{2}$/.test(f.from)) out.from = f.from;
  if (/^\d{4}-\d{2}-\d{2}$/.test(f.to)) out.to = f.to;
  return out;
}

/** 409 on undo: `changed_since` (later edits) or `conflict` with T1 alternatives for a taken slot. */
export function undoReasons(data: Record<string, unknown>): { later: number | null; alternatives: string[] } {
  // changed_since: `later` = ids of the events after this one
  const later = Array.isArray(data.later) ? data.later.length : typeof data.later === "number" ? data.later : null;
  const alts = Array.isArray(data.alternatives)
    ? data.alternatives
        .map((a) => (a && typeof a === "object" ? ((a as Record<string, unknown>).name ?? (a as Record<string, unknown>).room_name ?? (a as Record<string, unknown>).code) : null))
        .filter((x): x is string => typeof x === "string")
    : [];
  return { later, alternatives: alts };
}
