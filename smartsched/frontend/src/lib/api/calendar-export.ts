"use client";
/**
 * Calendar export (CAL-08 / CAL-09; docs/research/2026-10-17-calendar-export.md §3.4, backend lane CAL-B):
 * what an academician may add to a calendar (scopes), how (channels), the per-scope approval, and the manage list.
 *
 * - `GET /calendar/export/options`: per scope `available` + `reason`, the upcoming count, the departments the person
 *   may export, the configured channels, the field allow-list, the `calendar_sync` consent state, a real sample event.
 * - `GET /calendar/subscriptions` / `POST` / `DELETE /{id}` / `POST /{id}/rotate`: scope-bound links and push scopes.
 *   A link's token is shown once, in the POST answer (`urls {https, webcal, google, outlook}`).
 * - `GET /calendar/export/classes.ics`, `/department/{id}.ics`, `/bookings.ics`: one-off files (JWT through the
 *   panel's proxy cookie, `Content-Disposition: attachment`).
 * - `PUT /calendar/connectors/{provider}/scopes`: the push scopes of a connected account (queues a reconcile).
 * - Admin: `GET/PUT /calendar/admin/export-settings` (flat switches, push rules, status counts).
 * The contract is lane CAL-B's API.md (scratch cal/API.md, 2026-10-17); the adapters below read its shapes.
 *
 * Every schema is lenient (`.catch`, `.nullish`, defaults): an older backend answers without the new fields, and the
 * screens then show only what exists (no fake buttons).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { IntegrationSettings, afKeys } from "./approval-first";
import { HttpError, buildUrl, request } from "./client";

const s = { silent: true } as const;

/* ------------------------------------------------------------------------------------------- schemas */

export const SCOPE_KINDS = ["my_classes", "department_classes", "my_bookings"] as const;
export type ScopeKind = (typeof SCOPE_KINDS)[number];
export const PROVIDERS = ["google", "microsoft"] as const;
export type Provider = (typeof PROVIDERS)[number];
/** the reason codes the sheet has its own sentence for; any other code shows the backend's text or a generic line */
export const REASONS = ["department_not_allowed", "not_linked", "scope_disabled", "no_published_run", "sync_disabled"] as const;
export type Reason = (typeof REASONS)[number];
export const FIELD_KEYS = ["code", "title", "room", "time", "department", "co_instructors", "link", "booking_title"] as const;
export type FieldKey = (typeof FIELD_KEYS)[number];

const when = z.string().nullish();

export const SampleEvent = z
  .object({
    summary: z.string().nullish(),
    course_code: z.string().nullish(),
    section: z.string().nullish(),
    title: z.string().nullish(),
    location: z.string().nullish(),
    department: z.string().nullish(),
    starts_at: z.string(),
    ends_at: z.string(),
    /** the backend's own line ("PSY 262 · Şube 1 — A 308 — Pzt 13:30–15:50"), Istanbul time */
    text_tr: z.string().nullish(),
    text_en: z.string().nullish(),
  })
  .passthrough();
export type SampleEvent = z.infer<typeof SampleEvent>;

export const ExportDepartment = z.object({
  id: z.number(),
  name: z.string(),
  available: z.boolean().default(true),
  reason: z.string().nullish(),
  upcoming: z.number().nullish(),
  sample: SampleEvent.nullish(),
});
export type ExportDepartment = z.infer<typeof ExportDepartment>;

export const ScopeOption = z.object({
  kind: z.string(),
  available: z.boolean().default(false),
  reason: z.string().nullish(),
  reason_tr: z.string().nullish(),
  reason_en: z.string().nullish(),
  /** upcoming events in the horizon */
  upcoming: z.number().nullish(),
  /** this term's teaching hours ("bu dönem {n} ders saati"), when the backend counts them */
  hours: z.number().nullish(),
  departments: z.array(ExportDepartment).default([]),
  /** the fields that leave SmartSched for this scope (allow-list after the admin's settings) */
  fields: z.array(z.string()).nullish(),
  sample: SampleEvent.nullish(),
});
export type ScopeOption = z.infer<typeof ScopeOption>;

export const PushChannel = z.object({
  provider: z.string(),
  configured: z.boolean().default(false),
  connected: z.boolean().default(false),
  account_email: z.string().nullish(),
  /** CAL-07: how the account was verified (`sso_identity` | `domain` | `tenant`), `none` for old connections */
  account_verified: z.string().nullish(),
  status: z.string().nullish(),
  /** an old grant (Google `calendar.events`): offer "Daha az izinle yeniden bağlan" */
  legacy_scope: z.boolean().nullish(),
  scopes: z.array(z.string()).default([]),
});
export type PushChannel = z.infer<typeof PushChannel>;

const Consent = z.object({ purpose: z.string().default("calendar_sync"), required: z.boolean().default(false), granted: z.boolean().default(false) });

export const ExportOptions = z.object({
  /** the organisation's KVKK switch (`integrations.calendar_sync_enabled`) */
  enabled: z.boolean().default(true),
  term: z.object({ id: z.number(), name: z.string().nullish(), slug: z.string().nullish() }).nullish(),
  /** the person's login is linked to at least one instructor record */
  linked: z.boolean().nullish(),
  scopes: z.array(ScopeOption).default([]),
  channels: z
    .object({
      link: z.boolean().default(true),
      file: z.boolean().default(true),
      push: z.array(PushChannel).default([]),
    })
    .default({ link: true, file: true, push: [] }),
  fields: z.record(z.string(), z.boolean()).nullish(),
  consent: Consent.nullish(),
  /** where "Planlama ofisine yaz" writes to (the organisation's contact address) */
  contact_email: z.string().nullish(),
});
export type ExportOptions = z.infer<typeof ExportOptions>;

export const Subscription = z.object({
  id: z.union([z.number(), z.string()]),
  scope_kind: z.string(),
  scope_id: z.number().nullish(),
  scope_label: z.string().nullish(),
  scope_label_en: z.string().nullish(),
  channel: z.enum(["link", "push"]).catch("link"),
  provider: z.string().nullish(),
  hint: z.string().nullish(),
  created_at: when,
  /** links: when a calendar app last fetched the feed ("Takviminiz en son … çekti") */
  last_used_at: when,
  /** push: "Son eşitleme" */
  last_synced_at: when,
  status: z.string().nullish(),
  account_email: z.string().nullish(),
  account_verified: z.string().nullish(),
  legacy_scope: z.boolean().nullish(),
  pending_jobs: z.number().nullish(),
  failed_jobs: z.number().nullish(),
  synced: z.number().nullish(),
  total: z.number().nullish(),
  last_error: z.string().nullish(),
});
export type Subscription = z.infer<typeof Subscription>;

export const SubscriptionUrls = z.object({ https: z.string(), webcal: z.string().nullish(), google: z.string().nullish(), outlook: z.string().nullish() });
export type SubscriptionUrls = z.infer<typeof SubscriptionUrls>;
export const SubscriptionCreated = z
  .object({
    id: z.union([z.number(), z.string()]),
    urls: SubscriptionUrls,
    preview: z.object({ fields: z.array(z.string()).nullish(), sample: SampleEvent.nullish() }).passthrough().nullish(),
  })
  .passthrough();
export type SubscriptionCreated = z.infer<typeof SubscriptionCreated>;

/* ------------------------------------------------------------------------------------------- adapters */

type Raw = Record<string, unknown>;
const isObj = (v: unknown): v is Raw => !!v && typeof v === "object" && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);

/** backend field keys (calendar_classes.FIELD_KEYS) → the sheet's bullets; code + section are one bullet */
const FIELD_ALIASES: Record<string, FieldKey> = { course_code: "code", section: "code", course_title: "title", code: "code", title: "title", room: "room", time: "time", department: "department", co_instructors: "co_instructors", link: "link", booking_title: "booking_title" };

function adaptSample(v: unknown): unknown {
  if (!isObj(v)) return v ?? null;
  return { ...v, starts_at: v.starts_at ?? v.start, ends_at: v.ends_at ?? v.end };
}

function adaptFields(v: unknown): string[] | null {
  if (!Array.isArray(v)) return null;
  const out: string[] = [];
  for (const f of v) {
    const key = FIELD_ALIASES[typeof f === "string" ? f : isObj(f) ? String(f.key) : ""];
    if (key && !out.includes(key)) out.push(key);
  }
  return out;
}

/** CAL-B `export_options` (reason `{code, message_tr, message_en}`, `preview {upcoming_count, sample, fields}`, the
 * department list of what the person may export with `default_department_id`) → the sheet's shape. */
function adaptScope(v: unknown): unknown {
  if (!isObj(v)) return v;
  const out: Raw = { ...v };
  if (isObj(v.reason)) {
    out.reason = str(v.reason.code);
    out.reason_tr = str(v.reason.message_tr);
    out.reason_en = str(v.reason.message_en) ?? str(v.reason.message);
  }
  const pv = isObj(v.preview) ? v.preview : null;
  if (pv) {
    out.upcoming = typeof pv.upcoming_count === "number" ? pv.upcoming_count : out.upcoming;
    out.sample = adaptSample(pv.sample);
    out.fields = adaptFields(pv.fields);
  } else if (v.sample !== undefined) out.sample = adaptSample(v.sample);
  if (Array.isArray(v.fields)) out.fields = adaptFields(v.fields);
  if (Array.isArray(v.departments)) {
    const dflt = typeof v.default_department_id === "number" ? v.default_department_id : null;
    out.departments = v.departments.map((d) => {
      if (!isObj(d)) return d;
      const own = d.id === dflt && pv;
      return { ...d, reason: isObj(d.reason) ? str(d.reason.code) : d.reason, sample: own ? out.sample : adaptSample(d.sample), upcoming: own ? out.upcoming : d.upcoming };
    });
  }
  return out;
}

export function adaptOptions(raw: unknown): unknown {
  if (!isObj(raw)) return raw;
  const out: Raw = { ...raw };
  if (Array.isArray(raw.scopes)) out.scopes = raw.scopes.map(adaptScope);
  const ch = raw.channels;
  if (isObj(ch) && ch.push !== undefined && !Array.isArray(ch.push)) {
    const push = isObj(ch.push)
      ? Object.entries(ch.push)
          .filter(([, p]) => isObj(p) && "configured" in p)
          .map(([provider, p]) => ({ provider, configured: !!(p as Raw).configured, connected: !!(p as Raw).connected }))
      : [];
    const avail = (c: unknown) => (typeof c === "boolean" ? c : isObj(c) ? c.available !== false : true);
    out.channels = { link: avail(ch.link), file: avail(ch.file), push };
  }
  return out;
}

/** A push scope as the connection stores it: "my_classes", "department_classes:7" or `{kind, id}`. */
export function parseScope(v: unknown): { kind: string; id: number | null } | null {
  if (typeof v === "string") {
    const [kind, id] = v.split(":");
    return kind ? { kind, id: id && /^\d+$/.test(id) ? Number(id) : null } : null;
  }
  if (isObj(v) && typeof (v.kind ?? v.scope_kind) === "string") {
    const id = v.id ?? v.scope_id;
    return { kind: String(v.kind ?? v.scope_kind), id: typeof id === "number" ? id : null };
  }
  return null;
}

/** CAL-B `GET /calendar/subscriptions` = `{links: [...], push: [{provider, export_scopes, ...}]}` → one manage row
 * per link and per push scope (`id` = `push:{provider}:{scope}`), plus the push connections. A plain array (older
 * contract) is the rows. */
export function adaptSubscriptions(raw: unknown): { rows: unknown[]; connections: unknown[] } {
  if (Array.isArray(raw)) return { rows: raw, connections: [] };
  if (!isObj(raw)) return { rows: [], connections: [] };
  if (Array.isArray(raw.items)) return { rows: raw.items, connections: [] };
  const links = (Array.isArray(raw.links) ? raw.links : []).map((l) => (isObj(l) ? { ...l, channel: "link" } : l));
  const rows: unknown[] = [...links];
  const connections: unknown[] = [];
  for (const c of Array.isArray(raw.push) ? raw.push : []) {
    if (!isObj(c)) continue;
    const provider = String(c.provider ?? "");
    const scopes = Array.isArray(c.export_scopes) ? c.export_scopes : Array.isArray(c.scopes) ? c.scopes : [];
    const legacy = c.least_privilege === false;
    connections.push({ provider, configured: true, connected: c.status !== "REVOKED", account_email: c.account_email, account_verified: c.account_verified, status: c.status, legacy_scope: legacy, scopes: scopes.map((x) => (typeof x === "string" ? x : JSON.stringify(x))) });
    for (const x of scopes) {
      const sc = parseScope(x);
      if (!sc) continue;
      rows.push({
        id: `push:${provider}:${sc.kind}${sc.id !== null ? `:${sc.id}` : ""}`,
        scope_kind: sc.kind,
        scope_id: sc.id,
        channel: "push",
        provider,
        last_synced_at: c.last_synced_at,
        status: c.status,
        account_email: c.account_email,
        account_verified: c.account_verified,
        legacy_scope: legacy,
        pending_jobs: c.pending_jobs,
        failed_jobs: c.failed_jobs,
        last_error: c.last_error,
      });
    }
  }
  return { rows, connections };
}

export const SubscriptionsOut = z.preprocess(adaptSubscriptions, z.object({ rows: z.array(Subscription), connections: z.array(PushChannel) }));
export type SubscriptionsOut = z.infer<typeof SubscriptionsOut>;
export const ExportOptionsIn = z.preprocess(adaptOptions, ExportOptions);

/* ------------------------------------------------------------------------------------------- admin */

export const ADMIN_SCOPE_KEYS = { my_classes: "export_my_classes", department_classes: "export_department_classes", my_bookings: "export_my_bookings" } as const;
export const ADMIN_FIELD_KEYS = { title: "export_field_course_title", department: "export_field_department", co_instructors: "export_field_co_instructors", link: "export_field_link" } as const;
export type AdminField = keyof typeof ADMIN_FIELD_KEYS;
export const ADMIN_FIELDS = Object.keys(ADMIN_FIELD_KEYS) as AdminField[];

const flag = z.boolean().nullish();
export const ExportAdminStatus = z
  .object({
    links: z.record(z.string(), z.number()).default({}),
    connections: z.record(z.string(), z.number()).default({}),
    connections_by_scope: z.record(z.string(), z.number()).default({}),
    needs_attention: z.number().default(0),
    least_privilege_flagged: z.number().default(0),
    failed_jobs: z.number().default(0),
    nightly_reconcile: z.object({ at: z.string().nullish(), queued: z.number().nullish() }).nullish(),
  })
  .passthrough();
export type ExportAdminStatus = z.infer<typeof ExportAdminStatus>;

/** `GET /calendar/admin/export-settings` (CAL-B API.md, `setup.settings`): flat switches, the push rules, the status. */
export const ExportAdminSettings = z
  .object({
    export_my_classes: flag,
    export_department_classes: flag,
    export_my_bookings: flag,
    export_field_course_title: flag,
    export_field_department: flag,
    export_field_co_instructors: flag,
    export_field_link: flag,
    push_verified_only: flag,
    push_allowed_domains: z.array(z.string()).nullish(),
    calendar_client_source: z.enum(["identity", "own"]).nullish().catch(null),
    fields_always: z.array(z.string()).default([]),
    identity_clients: z.record(z.string(), z.boolean()).default({}),
    status: ExportAdminStatus.nullish(),
  })
  .passthrough();
export type ExportAdminSettings = z.infer<typeof ExportAdminSettings>;
export type ExportAdminSettingsIn = Partial<{
  export_my_classes: boolean;
  export_department_classes: boolean;
  export_my_bookings: boolean;
  export_field_course_title: boolean;
  export_field_department: boolean;
  export_field_co_instructors: boolean;
  export_field_link: boolean;
  push_verified_only: boolean;
  push_allowed_domains: string[];
  calendar_client_source: "identity" | "own";
}>;

/* ------------------------------------------------------------------------------------------- adapters */

type Raw = Record<string, unknown>;
const isObj = (v: unknown): v is Raw => !!v && typeof v === "object" && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === "string" ? v : null);

/** backend field keys (calendar_classes.FIELD_KEYS) → the sheet's bullets; code + section are one bullet */
const FIELD_ALIASES: Record<string, FieldKey> = { course_code: "code", section: "code", course_title: "title", code: "code", title: "title", room: "room", time: "time", department: "department", co_instructors: "co_instructors", link: "link", booking_title: "booking_title" };

function adaptSample(v: unknown): unknown {
  if (!isObj(v)) return v ?? null;
  return { ...v, starts_at: v.starts_at ?? v.start, ends_at: v.ends_at ?? v.end };
}

function adaptFields(v: unknown): string[] | null {
  if (!Array.isArray(v)) return null;
  const out: string[] = [];
  for (const f of v) {
    const key = FIELD_ALIASES[typeof f === "string" ? f : isObj(f) ? String(f.key) : ""];
    if (key && !out.includes(key)) out.push(key);
  }
  return out;
}

/** CAL-B `export_options` (reason `{code, message_tr, message_en}`, `preview {upcoming_count, sample, fields}`, the
 * department list of what the person may export with `default_department_id`) → the sheet's shape. */
function adaptScope(v: unknown): unknown {
  if (!isObj(v)) return v;
  const out: Raw = { ...v };
  if (isObj(v.reason)) {
    out.reason = str(v.reason.code);
    out.reason_tr = str(v.reason.message_tr);
    out.reason_en = str(v.reason.message_en) ?? str(v.reason.message);
  }
  const pv = isObj(v.preview) ? v.preview : null;
  if (pv) {
    out.upcoming = typeof pv.upcoming_count === "number" ? pv.upcoming_count : out.upcoming;
    out.sample = adaptSample(pv.sample);
    out.fields = adaptFields(pv.fields);
  } else if (v.sample !== undefined) out.sample = adaptSample(v.sample);
  if (Array.isArray(v.fields)) out.fields = adaptFields(v.fields);
  if (Array.isArray(v.departments)) {
    const dflt = typeof v.default_department_id === "number" ? v.default_department_id : null;
    out.departments = v.departments.map((d) => {
      if (!isObj(d)) return d;
      const own = d.id === dflt && pv;
      return { ...d, reason: isObj(d.reason) ? str(d.reason.code) : d.reason, sample: own ? out.sample : adaptSample(d.sample), upcoming: own ? out.upcoming : d.upcoming };
    });
  }
  return out;
}

export function adaptOptions(raw: unknown): unknown {
  if (!isObj(raw)) return raw;
  const out: Raw = { ...raw };
  if (Array.isArray(raw.scopes)) out.scopes = raw.scopes.map(adaptScope);
  const ch = raw.channels;
  if (isObj(ch) && ch.push !== undefined && !Array.isArray(ch.push)) {
    const push = isObj(ch.push)
      ? Object.entries(ch.push)
          .filter(([, p]) => isObj(p) && "configured" in p)
          .map(([provider, p]) => ({ provider, configured: !!(p as Raw).configured, connected: !!(p as Raw).connected }))
      : [];
    const avail = (c: unknown) => (typeof c === "boolean" ? c : isObj(c) ? c.available !== false : true);
    out.channels = { link: avail(ch.link), file: avail(ch.file), push };
  }
  return out;
}

/** A push scope as the connection stores it: "my_classes", "department_classes:7" or `{kind, id}`. */
export function parseScope(v: unknown): { kind: string; id: number | null } | null {
  if (typeof v === "string") {
    const [kind, id] = v.split(":");
    return kind ? { kind, id: id && /^\d+$/.test(id) ? Number(id) : null } : null;
  }
  if (isObj(v) && typeof (v.kind ?? v.scope_kind) === "string") {
    const id = v.id ?? v.scope_id;
    return { kind: String(v.kind ?? v.scope_kind), id: typeof id === "number" ? id : null };
  }
  return null;
}

/** CAL-B `GET /calendar/subscriptions` = `{links: [...], push: [{provider, export_scopes, ...}]}` → one manage row
 * per link and per push scope (`id` = `push:{provider}:{scope}`), plus the push connections. A plain array (older
 * contract) is the rows. */
export function adaptSubscriptions(raw: unknown): { rows: unknown[]; connections: unknown[] } {
  if (Array.isArray(raw)) return { rows: raw, connections: [] };
  if (!isObj(raw)) return { rows: [], connections: [] };
  if (Array.isArray(raw.items)) return { rows: raw.items, connections: [] };
  const links = (Array.isArray(raw.links) ? raw.links : []).map((l) => (isObj(l) ? { ...l, channel: "link" } : l));
  const rows: unknown[] = [...links];
  const connections: unknown[] = [];
  for (const c of Array.isArray(raw.push) ? raw.push : []) {
    if (!isObj(c)) continue;
    const provider = String(c.provider ?? "");
    const scopes = Array.isArray(c.export_scopes) ? c.export_scopes : Array.isArray(c.scopes) ? c.scopes : [];
    const legacy = c.least_privilege === false;
    connections.push({ provider, configured: true, connected: c.status !== "REVOKED", account_email: c.account_email, account_verified: c.account_verified, status: c.status, legacy_scope: legacy, scopes: scopes.map((x) => (typeof x === "string" ? x : JSON.stringify(x))) });
    for (const x of scopes) {
      const sc = parseScope(x);
      if (!sc) continue;
      rows.push({
        id: `push:${provider}:${sc.kind}${sc.id !== null ? `:${sc.id}` : ""}`,
        scope_kind: sc.kind,
        scope_id: sc.id,
        channel: "push",
        provider,
        last_synced_at: c.last_synced_at,
        status: c.status,
        account_email: c.account_email,
        account_verified: c.account_verified,
        legacy_scope: legacy,
        pending_jobs: c.pending_jobs,
        failed_jobs: c.failed_jobs,
        last_error: c.last_error,
      });
    }
  }
  return { rows, connections };
}

export const SubscriptionsOut = z.preprocess(adaptSubscriptions, z.object({ rows: z.array(Subscription), connections: z.array(PushChannel) }));
export type SubscriptionsOut = z.infer<typeof SubscriptionsOut>;
export const ExportOptionsIn = z.preprocess(adaptOptions, ExportOptions);

/* ------------------------------------------------------------------------------------------- admin */

export const DEPARTMENT_RULES = ["own", "taught", "permission"] as const;
export type DepartmentRule = (typeof DEPARTMENT_RULES)[number];
export const ADMIN_FIELDS = ["title", "department", "co_instructors", "link"] as const;
export type AdminField = (typeof ADMIN_FIELDS)[number];

/** The CAL-09 part of `GET /calendar/admin/settings`; every key is optional (absent = the backend lacks it). */
export const ExportAdminSettings = z
  .object({
    export_scopes: z.record(z.string(), z.boolean()).nullish(),
    department_rule: z.record(z.string(), z.boolean()).nullish(),
    export_fields: z.record(z.string(), z.boolean()).nullish(),
    feed_past_days: z.number().nullish(),
    feed_future_days: z.number().nullish(),
    feed_cancelled_grace_days: z.number().nullish(),
    push_verified_only: z.boolean().nullish(),
    push_allowed_domains: z.array(z.string()).nullish(),
    calendar_client_source: z.enum(["identity", "own"]).nullish().catch(null),
    google_scope_mode: z.enum(["app_created", "events"]).nullish().catch(null),
  })
  .passthrough();
export type ExportAdminSettings = z.infer<typeof ExportAdminSettings>;
export type ExportAdminSettingsIn = Partial<{
  export_scopes: Record<string, boolean>;
  department_rule: Record<string, boolean>;
  export_fields: Record<string, boolean>;
  feed_past_days: number;
  feed_future_days: number;
  feed_cancelled_grace_days: number;
  push_verified_only: boolean;
  push_allowed_domains: string[];
  calendar_client_source: "identity" | "own";
  google_scope_mode: "app_created" | "events";
}>;

export const ExportAdminStatus = z
  .object({
    active_links: z.number().default(0),
    links_by_scope: z.record(z.string(), z.number()).default({}),
    connections: z.array(z.object({ provider: z.string(), count: z.number().default(0), by_scope: z.record(z.string(), z.number()).default({}) })).default([]),
    failed_jobs: z.number().default(0),
    last_reconcile_at: when,
  })
  .passthrough();
export type ExportAdminStatus = z.infer<typeof ExportAdminStatus>;

/* ------------------------------------------------------------------------------------------- calls */

/** The one-off file path for a scope (relative to /api/v1). */
export function filePath(kind: ScopeKind, departmentId?: number | null): string {
  if (kind === "my_classes") return "/calendar/export/classes.ics";
  if (kind === "department_classes") return `/calendar/export/department/${departmentId ?? 0}.ics`;
  return "/calendar/export/bookings.ics";
}

/** `Content-Disposition: attachment; filename="derslerim-2026-bahar.ics"` → the name (RFC 6266, `filename*` first). */
export function dispositionName(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const star = /filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i.exec(header);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
    } catch {
      /* fall through */
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header);
  return plain?.[1]?.trim() || fallback;
}

/** Downloads a one-off file; errors are the client's HttpError (403 `department_not_allowed`, 409 `consent_required`). */
async function download(path: string, fallback: string): Promise<{ name: string; size: number }> {
  const res = await fetch(buildUrl(path), { credentials: "same-origin", headers: { Accept: "text/calendar" } });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = undefined;
    }
    const d = detail as { detail?: unknown; message?: string } | undefined;
    const code = typeof d?.detail === "object" && d.detail !== null ? (d.detail as Record<string, unknown>) : undefined;
    throw new HttpError(res.status, typeof code?.message === "string" ? code.message : typeof d?.detail === "string" ? d.detail : `${res.status}`, detail);
  }
  const blob = await res.blob();
  const name = dispositionName(res.headers.get("Content-Disposition"), fallback);
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return { name, size: blob.size };
}

export const calendarExportApi = {
  options: () => request("/calendar/export/options", { ...s, schema: ExportOptionsIn }),
  subscriptions: () => request("/calendar/subscriptions", { ...s, schema: SubscriptionsOut }),
  create: (body: { scope_kind: ScopeKind; scope_id?: number | null; channel: "link" }) => request("/calendar/subscriptions", { ...s, method: "POST", body, schema: SubscriptionCreated }),
  remove: (id: number | string) => request(`/calendar/subscriptions/${id}`, { ...s, method: "DELETE" }),
  /** "Bağlantıyı yenile": a new token for the same scope, the old one stops working. An older backend without the
   * rotate route (404 / 405) gets the same effect as create + delete. */
  rotate: async (sub: Subscription): Promise<SubscriptionCreated> => {
    try {
      return await request(`/calendar/subscriptions/${sub.id}/rotate`, { ...s, method: "POST", schema: SubscriptionCreated });
    } catch (e) {
      if (!(e instanceof HttpError) || (e.status !== 404 && e.status !== 405)) throw e;
      const made = await calendarExportApi.create({ scope_kind: sub.scope_kind as ScopeKind, scope_id: sub.scope_id ?? null, channel: "link" });
      await calendarExportApi.remove(sub.id);
      return made;
    }
  },
  download: (kind: ScopeKind, departmentId: number | null | undefined, fallback: string) => download(filePath(kind, departmentId), fallback),
  pushScopes: (provider: string, scopes: string[]) => request(`/calendar/connectors/${provider}/scopes`, { ...s, method: "PUT", body: { scopes } }),
  /** starts the provider's OAuth round trip; the scopes ride along so the backend can apply them on the callback */
  connect: (provider: string, returnPath: string, scopes: string[]) =>
    request(`/calendar/connectors/${provider}/connect`, { ...s, method: "POST", body: { return_path: returnPath, scopes }, schema: z.object({ authorize_url: z.string() }) }),
  resync: (provider: string) => request(`/calendar/connectors/${provider}/resync`, { ...s, method: "POST", schema: z.object({ queued: z.number() }).passthrough() }),
  disconnect: (provider: string) => request(`/calendar/connectors/${provider}`, { ...s, method: "DELETE" }),
  admin: {
    get: () => request("/calendar/admin/export-settings", { ...s, schema: ExportAdminSettings }),
    put: (body: ExportAdminSettingsIn) => request("/calendar/admin/export-settings", { ...s, method: "PUT", body, schema: ExportAdminSettings }),
  },
};

/* ------------------------------------------------------------------------------------------- hooks */

/** "calendar" in every key: a calendar_sync consent withdrawal (lib/api/kvkk.ts) refreshes them all. */
export const calendarExportKeys = {
  options: ["calendar-export", "options"] as const,
  subscriptions: ["calendar-export", "subscriptions"] as const,
  admin: ["calendar-export", "admin-settings"] as const,
};

export function useExportOptions(enabled = true) {
  return useQuery({ queryKey: calendarExportKeys.options, queryFn: calendarExportApi.options, enabled, retry: false, staleTime: 30_000 });
}

export function useSubscriptions(enabled = true, poll = false) {
  return useQuery({
    queryKey: calendarExportKeys.subscriptions,
    queryFn: calendarExportApi.subscriptions,
    enabled,
    retry: false,
    staleTime: 15_000,
    refetchInterval: poll ? 3_000 : false,
  });
}

/** Refresh every calendar query (options, subscriptions, the older `/calendar/sync` status). */
export function useRefreshCalendar() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ predicate: (q) => q.queryKey.some((k) => typeof k === "string" && /calendar/i.test(k)) });
}

/** CAL-09 settings; a backend without the endpoint answers 404 and the panels show nothing extra. */
export function useExportAdminSettings(enabled = true) {
  return useQuery({ queryKey: calendarExportKeys.admin, queryFn: calendarExportApi.admin.get, enabled, retry: false });
}

/** Past days and the cancelled grace days: `PUT /calendar/admin/settings` (the KVKK card's endpoint and cache). */
export function useSaveFeedHorizon() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { feed_past_days: number; feed_cancelled_grace_days: number }) => request("/calendar/admin/settings", { ...s, method: "PUT", body, schema: IntegrationSettings }),
    onSuccess: (data) => qc.setQueryData(afKeys.integrations, data),
  });
}

export function useSaveExportAdminSettings() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: calendarExportApi.admin.put, onSuccess: (data) => qc.setQueryData(calendarExportKeys.admin, data) });
}
