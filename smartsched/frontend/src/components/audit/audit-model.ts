/**
 * Audit log (P7, docs/product/wave1-api.md §3): the before/after diff of an event as rows, the filter
 * vocabulary and the undo refusal reasons. Pure functions, unit-tested in audit-model.test.ts.
 */
import type { AuditEvent } from "@/lib/api/wave1";
import type { MessageKey } from "@/lib/i18n";

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
  // T-R1-32 (R1-M-18): the records other screens write, so their rows and the filter read as domain words
  "program",
  "course",
  "section",
  "exam",
  "meeting",
  "faculty",
  "instructor",
  "run",
  "booking_policy",
  "webhook",
  "sso_provider",
  "sso_role_mapping",
  "notify_channel",
  "user_channel",
  "dsr_request",
  "privacy_notice",
  "consent",
  "retention_policy",
  "preset",
  "constraint",
  "invigilation_plan",
  "invigilation_duty",
  "invigilator_pool",
] as const;

/** A row's label is the same for the two spellings the backend uses for one record kind. */
export const ENTITY_ALIASES: Record<string, string> = { setting: "settings", schedule_run: "run", term_week: "timetable_week", session_schedule: "schedule", room_field_option: "room_field", booking_conflict: "booking", studio_draft: "run", meeting_request: "meeting", channel_department_target: "notify_channel" };

/**
 * Actions whose sentence is not "<entity> <verb>" (the KVKK, sign-in, channel and policy steps of F-11 S11):
 * action → `wave1.audit.act.<key>` message key suffix. Anything else reads `wave1.audit.verb.<verb>` with the entity.
 */
export const ACTION_SENTENCES: Record<string, string> = {
  "kvkk.dsr_refuse": "kvkk_dsr_refuse",
  "kvkk.dsr_complete": "kvkk_dsr_complete",
  "kvkk.dsr_download": "kvkk_dsr_download",
  "kvkk.erase": "kvkk_erase",
  "kvkk.consent_grant": "kvkk_consent_grant",
  "kvkk.consent_withdraw": "kvkk_consent_withdraw",
  "kvkk.notice_ack": "kvkk_notice_ack",
  "kvkk.notice_create": "kvkk_notice_create",
  "kvkk.notice_update": "kvkk_notice_update",
  "kvkk.notice_publish": "kvkk_notice_publish",
  "kvkk.notice_delete": "kvkk_notice_delete",
  "kvkk.retention": "kvkk_retention",
  "kvkk.retention_policy": "kvkk_retention",
  "kvkk.ai_personal_default": "kvkk_ai_default",
  "ai.policy": "ai_policy",
  "ai.key_status": "ai_key",
  "channels.config": "channels_config",
  "channels.kvkk_signoff": "channels_signoff",
  "channels.telegram_setup": "channels_telegram",
  "channels.vapid": "channels_vapid",
  "channels.bridge_connect": "channels_bridge_connect",
  "channels.bridge_logout": "channels_bridge_logout",
  "channels.department_target": "channels_target",
  "channels.department_target_delete": "channels_target_delete",
  "channel.link": "channel_link",
  "channel.unlink": "channel_unlink",
  "booking_policy.exam_period": "policy_exam_period",
  "public_schedule.settings": "public_settings",
  "integrations.calendar_sync": "calendar_sync",
  "sso.config_update": "sso_config",
  "sso.mapping_create": "sso_mapping_create",
  "sso.mapping_delete": "sso_mapping_delete",
  "sso.mapping_skipped": "sso_mapping_skipped",
  "sso.role_change": "sso_role_change",
  "sso.demotion_blocked": "sso_demotion_blocked",
  "auth.login": "auth_login",
  "auth.login_refused": "auth_login_refused",
  "auth.self_signup": "auth_self_signup",
  "auth.identity_bound": "auth_identity_bound",
  "auth.identity_unbound": "auth_identity_unbound",
  "user.invited": "user_invited",
  "user.invite_renewed": "user_invite_renewed",
  "user.invite_revoked": "user_invite_revoked",
  "user.invite_accepted": "user_invite_accepted",
  "user.reset_code": "user_reset_code",
  "user.instructor_link": "user_instructor_link",
  "user.logged_in": "auth_login",
  "approver.update": "approver_update",
  "webhook.secret": "webhook_secret",
  "webhook.disabled": "webhook_disabled",
  "room.features": "room_features",
  "run.hard_score": "run_hard_score",
  "booking_conflict.detect": "conflict_detect",
  "booking_conflict.resolve": "conflict_resolve",
  "constraint.waive": "constraint_waive",
  "preset.apply": "preset_apply",
  "program_draft.commit": "program_commit",
  "term.relaxation_policy": "term_relaxation",
  "settings.update": "settings_update",
  "studio.draft.update": "studio_draft",
  "studio.meetings.bulk": "studio_meetings_bulk",
  "studio.meetings.revert": "studio_meetings_revert",
  "studio.precheck.fix": "studio_precheck_fix",
  "studio.proposals.accept": "studio_proposals_accept",
  "studio.rules.copy": "studio_rules_copy",
  "invigilation.add_duty": "invigilation_add_duty",
  "invigilation.reassign": "invigilation_reassign",
};

/** The fields a snapshot names a record by, in the order a reader expects (a room by its code, a person by name). */
const SUBJECT_FIELDS = ["display_name", "displayname", "full_name", "name", "display_code", "code", "title", "email", "username", "key", "url", "kind"] as const;

/** "TST 101", "D. S.", "booking_policy.exam_period": the record's own name from the event's snapshots, else null. */
export function auditSubject(e: Pick<AuditEvent, "after" | "before" | "entity_id" | "entity_type">): string | null {
  for (const snap of [e.after, e.before]) {
    if (!snap) continue;
    for (const f of SUBJECT_FIELDS) {
      const v = snap[f];
      if (typeof v === "string" && v.trim() && v !== "***") return v.trim();
    }
  }
  return null;
}

/** "name · #id" / "#id" / "" for the row's tail; the id alone when the snapshot already names the record. */
/** `undo_of:<audit id>`: the coded cancel reason an undo writes on the booking and its audit row
 * (`bookings_undo.undo_reason`); null for a reason a person typed. */
export function undoReasonId(reason: string | null | undefined): number | null {
  const m = /^undo_of:(\d+)$/.exec(reason ?? "");
  return m ? Number(m[1]) : null;
}

/** The reason line of a row: a coded reason in the UI language ("Geri alma: #164"), free text as typed, else null. */
/** The cancel reason as the reader should see it: the backend's *codes* (`undo_of:<audit id>`, `replaced_by_series:<id>`,
 *  round 2 sweeper 3) in the UI language with the wording of components/bookings/cancel-reason.ts; typed words as they are. */
export function auditReason(reason: string | null | undefined, t: (key: MessageKey, vars?: Record<string, string | number>) => string): string | null {
  if (!reason) return null;
  const id = undoReasonId(reason);
  if (id !== null) return t("wave1.audit.reasonUndoOf", { id });
  const series = /^replaced_by_series:(\d+)$/.exec(reason);
  if (series) return t("crbs.cancel.replacedBySeries", { id: Number(series[1]) });
  return reason;
}

export function auditTail(e: Pick<AuditEvent, "after" | "before" | "entity_id" | "entity_type">): string {
  const subject = auditSubject(e);
  const id = e.entity_id ? `#${e.entity_id}` : "";
  if (subject && id && subject !== e.entity_id) return `${subject} · ${id}`;
  return subject || id;
}

/** Options without repeated labels: a second person with the same display name gets the username / e-mail added. */
export function dedupeOptions<T extends { value: string; label: string; hint?: string | null }>(items: readonly T[]): T[] {
  const counts = new Map<string, number>();
  for (const it of items) counts.set(it.label, (counts.get(it.label) ?? 0) + 1);
  const seen = new Set<string>();
  const out: T[] = [];
  for (const it of items) {
    if (seen.has(it.value)) continue;
    seen.add(it.value);
    out.push((counts.get(it.label) ?? 0) > 1 && it.hint ? { ...it, label: `${it.label} (${it.hint})` } : it);
  }
  return out;
}

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
