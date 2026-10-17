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
 * - Admin: the new fields of `GET/PUT /calendar/admin/settings` and `GET /calendar/admin/status`.
 *
 * Every schema is lenient (`.catch`, `.nullish`, defaults): an older backend answers without the new fields, and the
 * screens then show only what exists (no fake buttons).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { IntegrationSettings, afKeys, approvalFirst } from "./approval-first";
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

const SubscriptionList = z.union([z.array(Subscription), z.object({ items: z.array(Subscription) }).transform((o) => o.items)]);

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
  options: () => request("/calendar/export/options", { ...s, schema: ExportOptions }),
  subscriptions: () => request("/calendar/subscriptions", { ...s, schema: SubscriptionList }),
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
    /** the same call (and cache entry) as the KVKK / push panels: the answer is parsed as theirs, the CAL-09 part is read with `select` */
    get: () => approvalFirst.integrations.get(),
    put: (body: ExportAdminSettingsIn) => request("/calendar/admin/settings", { ...s, method: "PUT", body, schema: IntegrationSettings }),
    status: () => request("/calendar/admin/status", { ...s, schema: ExportAdminStatus }),
  },
};

/* ------------------------------------------------------------------------------------------- hooks */

/** "calendar" in every key: a calendar_sync consent withdrawal (lib/api/kvkk.ts) refreshes them all. */
export const calendarExportKeys = {
  options: ["calendar-export", "options"] as const,
  subscriptions: ["calendar-export", "subscriptions"] as const,
  adminStatus: ["calendar-export", "admin-status"] as const,
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

/** The CAL-09 settings share the cache entry of the KVKK / push panels (same endpoint). */
export function useExportAdminSettings(enabled = true) {
  return useQuery({ queryKey: afKeys.integrations, queryFn: calendarExportApi.admin.get, enabled, retry: false, select: (d) => ExportAdminSettings.parse(d) });
}

export function useSaveExportAdminSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: calendarExportApi.admin.put,
    onSuccess: (data) => {
      qc.setQueryData(afKeys.integrations, data);
      void qc.invalidateQueries({ queryKey: calendarExportKeys.adminStatus });
    },
  });
}

export function useExportAdminStatus(enabled = true) {
  return useQuery({ queryKey: calendarExportKeys.adminStatus, queryFn: calendarExportApi.admin.status, enabled, retry: false, staleTime: 30_000 });
}
