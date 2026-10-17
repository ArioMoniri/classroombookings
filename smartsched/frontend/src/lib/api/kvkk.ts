"use client";
/**
 * A4 KVKK (Law 6698; `app/api/v1/kvkk.py`, service `app/services/kvkk.py`).
 *
 * Signed-in user (Profil › Gizlilik):
 * - `GET /me/privacy`: the current notice (my language, else Turkish), `needs_ack`, my consents, my requests, `due_days`.
 * - `POST /me/privacy/ack {notice_id}`.
 * - `POST /me/consents/{purpose}` / `DELETE /me/consents/{purpose}` (`sms`, `photo`, `calendar_sync`, `ai_personal`);
 *   a withdrawal applies at once and answers the counts (`removed_channels`, `removed_photo`, `revoked_feeds`,
 *   `disconnected_calendars`), `ai_excluded` and `effects[]` (`{code, count, message_en, message_tr}`, one sentence per
 *   consequence: `phones_deleted | phones_none | photo_deleted | photo_none | feeds_revoked | calendars_disconnected |
 *   calendar_none | ai_excluded`); the Gizlilik toast shows those sentences.
 * - `POST /me/data-requests {kind: export|erase|rectify|info, note?}` (409 `duplicate` with `id`); `GET /me/data-requests`;
 *   `GET /me/data-requests/{id}/download` (the export zip, built at download time, 7 days; 410 `expired`).
 * No sign-in: `GET /public/privacy-notice?lang=` (404 while nothing is published).
 *
 * Administrators: `setup.users` for the request queue (`GET /admin/dsr?status=open|all|OPEN|IN_PROGRESS|DONE|REFUSED`,
 * default `open` = OPEN + IN_PROGRESS; `POST /admin/dsr/{id}/complete {note?}` — 409 `own_request | last_admin | closed |
 * gone` —, `POST /admin/dsr/{id}/refuse {reason}`); `setup.settings` for retention (`GET /admin/retention`,
 * `PUT /admin/retention/{data_class}` — 422 `{code, field, message_en, message_tr, errors[]}`, every error with its
 * `field` (`retain_days | action | enabled | legal_hold | legal_hold_reason | data_class`) and `floor_days` / `max_days`
 * / `allowed` when they apply —, `POST /admin/retention/run`), the inventory (`GET /admin/kvkk/inventory`) and the notices
 * (`GET/POST /admin/privacy-notices`, `PUT/DELETE /admin/privacy-notices/{id}` drafts only, `POST …/{id}/publish`).
 *
 * Consent gates (2026-10-16): `GET /me/privacy` also says what a never-given `ai_personal` consent means here
 * (`ai_personal_default`: included | excluded) and whether this person is kept out of AI requests now (`ai_excluded`).
 * Role ADMIN reads / sets that default through `GET /settings` / `PUT /settings {extra: {"kvkk.ai_personal_default"}}`
 * (422 `{code, field, message_en, message_tr, allowed}`). A completed erasure's `result` carries `calendar[]` (each push
 * calendar disconnected: events, events_removed, events_failed, revoke) and `failures[]` (`{provider, code, message_en,
 * message_tr, count?, error?}`; codes `grant_unreadable | events_not_removed | revoke_failed | provider_timeout |
 * disconnect_failed`).
 *
 * Nothing here ships a notice text or a retention period: administrators write them (the backend's retention rows are
 * disabled until someone turns them on).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { API_PREFIX, HttpError, request } from "./client";

const s = { silent: true } as const;

export const PURPOSES = ["sms", "photo", "calendar_sync", "ai_personal"] as const;
export type Purpose = (typeof PURPOSES)[number];
export const KINDS = ["export", "erase", "rectify", "info"] as const;
export type DsrKind = (typeof KINDS)[number];
export const DSR_STATUSES = ["OPEN", "IN_PROGRESS", "DONE", "REFUSED"] as const;
/** `GET /admin/dsr?status=`: `open` (OPEN + IN_PROGRESS, the default), `all`, or one status */
export const QUEUE_FILTERS = ["open", "all", ...DSR_STATUSES] as const;
export type QueueFilter = (typeof QUEUE_FILTERS)[number];

export const Notice = z.object({
  id: z.number(),
  version: z.number(),
  language: z.string(),
  title: z.string(),
  body_md: z.string(),
  published_at: z.string().nullish(),
  created_at: z.string().nullish(),
});
export type Notice = z.infer<typeof Notice>;

export const Consent = z.object({
  purpose: z.string(),
  label_tr: z.string(),
  label_en: z.string(),
  granted: z.boolean(),
  granted_at: z.string().nullish(),
  withdrawn_at: z.string().nullish(),
});
export type Consent = z.infer<typeof Consent>;

export const Dsr = z.object({
  id: z.number(),
  kind: z.string(),
  status: z.string(),
  note: z.string().nullish(),
  created_at: z.string().nullish(),
  due_at: z.string().nullish(),
  overdue: z.boolean().default(false),
  days_left: z.number().nullish(),
  handled_at: z.string().nullish(),
  result: z.record(z.string(), z.unknown()).nullish(),
  refusal_reason: z.string().nullish(),
  download_expires_at: z.string().nullish(),
  downloadable: z.boolean().default(false),
  user_id: z.number().nullish(),
  subject: z.string().nullish(),
});
export type Dsr = z.infer<typeof Dsr>;

/** One consequence of a withdrawal, in both languages (`count` is null when nothing is counted, e.g. `ai_excluded`). */
export const ConsentEffect = z.object({ code: z.string(), count: z.number().nullish(), message_en: z.string(), message_tr: z.string() });
export type ConsentEffect = z.infer<typeof ConsentEffect>;
export const Withdrawal = z.object({
  removed_channels: z.number().default(0),
  removed_photo: z.number().default(0),
  revoked_feeds: z.number().default(0),
  disconnected_calendars: z.number().default(0),
  ai_excluded: z.boolean().default(false),
  effects: z.array(ConsentEffect).default([]),
  consents: z.array(Consent).default([]),
});
export type Withdrawal = z.infer<typeof Withdrawal>;

export const MyPrivacy = z.object({
  notice: Notice.nullish(),
  needs_ack: z.boolean().default(false),
  consents: z.array(Consent).default([]),
  requests: z.array(Dsr).default([]),
  due_days: z.number().default(30),
  /** what a never-given `ai_personal` consent means here (consent gates 2026-10-16; `kvkk.ai_personal_default`) */
  ai_personal_default: z.enum(["included", "excluded"]).catch("excluded").default("excluded"),
  /** this person's name and e-mail are replaced by a placeholder in AI requests right now */
  ai_excluded: z.boolean().default(false),
});
export type MyPrivacy = z.infer<typeof MyPrivacy>;

export const RetentionPolicy = z.object({
  data_class: z.string(),
  label_tr: z.string().nullish(),
  label_en: z.string().nullish(),
  retain_days: z.number(),
  floor_days: z.number().nullish(),
  action: z.enum(["delete", "anonymise"]).catch("delete"),
  enabled: z.boolean(),
  legal_hold: z.boolean(),
  legal_hold_reason: z.string().nullish(),
  last_run_at: z.string().nullish(),
  last_result: z.record(z.string(), z.unknown()).nullish(),
  updated_at: z.string().nullish(),
});
export type RetentionPolicy = z.infer<typeof RetentionPolicy>;

export interface RetentionIn {
  retain_days?: number;
  action?: "delete" | "anonymise";
  enabled?: boolean;
  legal_hold?: boolean;
  legal_hold_reason?: string | null;
}

export const InventoryClass = z.object({
  code: z.string(),
  label_tr: z.string(),
  label_en: z.string(),
  tables: z.array(z.string()).default([]),
  rows: z.record(z.string(), z.number()).default({}),
  legal_basis: z.string(),
  retention: RetentionPolicy.nullish(),
  kept: z.string().nullish(),
});
export type InventoryClass = z.infer<typeof InventoryClass>;
export const Inventory = z.object({ generated_at: z.string().nullish(), classes: z.array(InventoryClass).default([]) });
export type Inventory = z.infer<typeof Inventory>;

export interface NoticeIn {
  language: "tr" | "en";
  title: string;
  body_md: string;
  version?: number | null;
}

export const kvkkKeys = {
  me: ["kvkk", "me"] as const,
  queue: (status: QueueFilter) => ["kvkk", "dsr", status] as const,
  retention: ["kvkk", "retention"] as const,
  inventory: ["kvkk", "inventory"] as const,
  notices: ["kvkk", "notices"] as const,
  aiDefault: ["kvkk", "ai-personal-default"] as const,
};

/** `kvkk.ai_personal_default` (consent gates 2026-10-16): `excluded` (default, owner decision 2026-10-17) = a consent
 * that was never given counts as no (only a grant lets a person in); `included` = only an explicit withdrawal keeps a
 * person out of AI requests (an admin's choice). */
export const AI_DEFAULTS = ["included", "excluded"] as const;
export type AiDefault = (typeof AI_DEFAULTS)[number];
export const AI_DEFAULT_KEY = "kvkk.ai_personal_default";

/** The stored value from a `GET/PUT /settings` answer (`excluded` when missing or unreadable, as the backend reads it). */
export function aiDefaultOf(settings: unknown): AiDefault {
  const v = settings && typeof settings === "object" ? (settings as Record<string, unknown>)[AI_DEFAULT_KEY] : null;
  return v === "included" ? "included" : "excluded";
}

export const kvkkApi = {
  me: () => request("/me/privacy", { schema: MyPrivacy, ...s }),
  ack: (noticeId: number) => request<{ notice_id: number; acked_at: string }>("/me/privacy/ack", { method: "POST", body: { notice_id: noticeId }, ...s }),
  grant: (purpose: Purpose) => request(`/me/consents/${purpose}`, { method: "POST", schema: z.array(Consent), ...s }),
  withdraw: (purpose: Purpose) => request(`/me/consents/${purpose}`, { method: "DELETE", schema: Withdrawal, ...s }),
  createRequest: (kind: DsrKind, note: string | null) => request("/me/data-requests", { method: "POST", body: { kind, note }, schema: Dsr, ...s }),
  downloadUrl: (id: number) => `${API_PREFIX}/me/data-requests/${id}/download`,
  queue: (status: QueueFilter) => request("/admin/dsr", { query: { status }, schema: z.array(Dsr), ...s }),
  complete: (id: number, note: string | null) => request(`/admin/dsr/${id}/complete`, { method: "POST", body: { note }, schema: Dsr, ...s }),
  refuse: (id: number, reason: string) => request(`/admin/dsr/${id}/refuse`, { method: "POST", body: { reason }, schema: Dsr, ...s }),
  retention: () => request("/admin/retention", { schema: z.array(RetentionPolicy), ...s }),
  saveRetention: (dataClass: string, body: RetentionIn) => request(`/admin/retention/${encodeURIComponent(dataClass)}`, { method: "PUT", body, schema: RetentionPolicy, ...s }),
  runRetention: () => request<Record<string, unknown>>("/admin/retention/run", { method: "POST", ...s }),
  inventory: () => request("/admin/kvkk/inventory", { schema: Inventory, ...s }),
  notices: () => request("/admin/privacy-notices", { schema: z.array(Notice), ...s }),
  createNotice: (body: NoticeIn) => request("/admin/privacy-notices", { method: "POST", body, schema: Notice, ...s }),
  updateNotice: (id: number, body: NoticeIn) => request(`/admin/privacy-notices/${id}`, { method: "PUT", body, schema: Notice, ...s }),
  deleteNotice: (id: number) => request<void>(`/admin/privacy-notices/${id}`, { method: "DELETE", ...s }),
  publishNotice: (id: number) => request(`/admin/privacy-notices/${id}/publish`, { method: "POST", schema: Notice, ...s }),
  /** `GET /settings` (role ADMIN): only the KVKK AI default is read here */
  aiDefault: () => request<unknown>("/settings", s).then(aiDefaultOf),
  /** `PUT /settings {extra: {"kvkk.ai_personal_default": …}}`; 422 `{code, field, message_en, message_tr, allowed}`; audited server-side */
  saveAiDefault: (value: AiDefault) => request<unknown>("/settings", { method: "PUT", body: { extra: { [AI_DEFAULT_KEY]: value } }, ...s }).then(aiDefaultOf),
};

/** Download the export zip through the same-origin proxy; a 410 (expired) or 404 comes back as an HttpError. */
export async function downloadExport(id: number): Promise<void> {
  const res = await fetch(kvkkApi.downloadUrl(id), { credentials: "same-origin" });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      /* not JSON */
    }
    throw new HttpError(res.status, `${res.status}`, detail);
  }
  const blob = await res.blob();
  const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? `smartsched-verilerim-${id}.zip`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function useMyPrivacy(enabled = true) {
  return useQuery({ queryKey: kvkkKeys.me, queryFn: kvkkApi.me, enabled, staleTime: 60_000, retry: false });
}

function useInvalidate(...keys: readonly (readonly unknown[])[]) {
  const qc = useQueryClient();
  return () => Promise.all(keys.map((k) => qc.invalidateQueries({ queryKey: k })));
}

export function useAckNotice() {
  const done = useInvalidate(kvkkKeys.me);
  return useMutation({ mutationFn: kvkkApi.ack, onSuccess: () => void done() });
}
/** Grant (answers no effects) or withdraw a consent. A withdrawal changed other screens at once: the linked phones
 * (`channels`), the profile photo (`me`) and the calendar links / connections (every query key naming a calendar). */
export function useConsent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ purpose, grant }: { purpose: Purpose; grant: boolean }): Promise<Withdrawal | null> => (grant ? kvkkApi.grant(purpose).then(() => null) : kvkkApi.withdraw(purpose)),
    onSuccess: (_res, { purpose }) => {
      void qc.invalidateQueries({ queryKey: kvkkKeys.me });
      if (purpose === "sms") void qc.invalidateQueries({ queryKey: ["channels"] });
      if (purpose === "photo") void qc.invalidateQueries({ queryKey: ["me"] });
      if (purpose === "calendar_sync") void qc.invalidateQueries({ predicate: (q) => q.queryKey.some((k) => typeof k === "string" && /calendar|connector/i.test(k)) });
    },
  });
}
export function useCreateDataRequest() {
  const done = useInvalidate(kvkkKeys.me, ["kvkk", "dsr"]);
  return useMutation({ mutationFn: ({ kind, note }: { kind: DsrKind; note: string | null }) => kvkkApi.createRequest(kind, note), onSuccess: () => void done() });
}

export function useDsrQueue(status: QueueFilter, enabled = true) {
  return useQuery({ queryKey: kvkkKeys.queue(status), queryFn: () => kvkkApi.queue(status), enabled, retry: false });
}
export function useDecideDsr() {
  const done = useInvalidate(["kvkk", "dsr"], kvkkKeys.me);
  return useMutation({ mutationFn: ({ id, refuse, text }: { id: number; refuse: boolean; text: string | null }) => (refuse ? kvkkApi.refuse(id, text ?? "") : kvkkApi.complete(id, text)), onSuccess: () => void done() });
}

export function useRetention(enabled = true) {
  return useQuery({ queryKey: kvkkKeys.retention, queryFn: kvkkApi.retention, enabled, retry: false });
}
export function useSaveRetention() {
  const done = useInvalidate(kvkkKeys.retention, kvkkKeys.inventory);
  return useMutation({ mutationFn: ({ dataClass, body }: { dataClass: string; body: RetentionIn }) => kvkkApi.saveRetention(dataClass, body), onSuccess: () => void done() });
}
export function useRunRetention() {
  const done = useInvalidate(kvkkKeys.retention, kvkkKeys.inventory);
  return useMutation({ mutationFn: kvkkApi.runRetention, onSuccess: () => void done() });
}

export function useInventory(enabled = true) {
  return useQuery({ queryKey: kvkkKeys.inventory, queryFn: kvkkApi.inventory, enabled, retry: false });
}

export function useNotices(enabled = true) {
  return useQuery({ queryKey: kvkkKeys.notices, queryFn: kvkkApi.notices, enabled, retry: false });
}
export function useSaveNotice() {
  const done = useInvalidate(kvkkKeys.notices);
  return useMutation({ mutationFn: ({ id, body }: { id: number | null; body: NoticeIn }) => (id ? kvkkApi.updateNotice(id, body) : kvkkApi.createNotice(body)), onSuccess: () => void done() });
}
export function useDeleteNotice() {
  const done = useInvalidate(kvkkKeys.notices);
  return useMutation({ mutationFn: kvkkApi.deleteNotice, onSuccess: () => void done() });
}
export function useAiDefault(enabled = true) {
  return useQuery({ queryKey: kvkkKeys.aiDefault, queryFn: kvkkApi.aiDefault, enabled, retry: false });
}
/** Saving changes what everyone's Gizlilik text says (`GET /me/privacy`) and the Settings screen's cache. */
export function useSaveAiDefault() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: kvkkApi.saveAiDefault,
    onSuccess: (value) => {
      qc.setQueryData(kvkkKeys.aiDefault, value);
      void qc.invalidateQueries({ queryKey: kvkkKeys.me });
      void qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}

export function usePublishNotice() {
  const done = useInvalidate(kvkkKeys.notices, kvkkKeys.me);
  return useMutation({ mutationFn: kvkkApi.publishNotice, onSuccess: () => void done() });
}

/* ------------------------------------------------------------------------------------- pure helpers */

/** The sentences of a withdrawal's effects in the reader's language (Turkish for tr, English otherwise), each
 * starting with a capital letter (Turkish-aware: "i" → "İ") and ending with a full stop. */
export function effectSentences(effects: readonly ConsentEffect[], locale: string): string[] {
  const tr = locale === "tr";
  return effects
    .map((e) => (tr ? e.message_tr : e.message_en).trim())
    .filter(Boolean)
    .map((m) => {
      const s = m.charAt(0).toLocaleUpperCase(tr ? "tr-TR" : "en-GB") + m.slice(1);
      return /[.!?]$/.test(s) ? s : `${s}.`;
    });
}

export const RETENTION_FIELDS = ["retain_days", "action", "enabled", "legal_hold", "legal_hold_reason", "data_class"] as const;
export type RetentionField = (typeof RETENTION_FIELDS)[number];
/** One retention 422 entry (`detail.errors[]`, or the detail itself when an older backend sent no list). */
export interface RetentionFieldError {
  code: string;
  field: RetentionField;
  message_en: string;
  message_tr: string;
  floor_days?: number;
  max_days?: number;
  allowed?: string[];
}

/** `PUT /admin/retention/{class}` 422 detail → the errors by field (the first one per field wins); others → `{}`. */
export function retentionErrors(detail: Record<string, unknown> | null | undefined): Partial<Record<RetentionField, RetentionFieldError>> {
  if (!detail || typeof detail !== "object") return {};
  const list = Array.isArray(detail.errors) ? (detail.errors as unknown[]) : typeof detail.field === "string" ? [detail] : [];
  const out: Partial<Record<RetentionField, RetentionFieldError>> = {};
  for (const raw of list) {
    if (!raw || typeof raw !== "object") continue;
    const e = raw as Record<string, unknown>;
    const field = e.field as RetentionField;
    if (!RETENTION_FIELDS.includes(field) || out[field]) continue;
    const en = typeof e.message_en === "string" ? e.message_en : typeof e.message === "string" ? e.message : "";
    out[field] = {
      code: typeof e.code === "string" ? e.code : field,
      field,
      message_en: en,
      message_tr: typeof e.message_tr === "string" ? e.message_tr : en,
      ...(typeof e.floor_days === "number" ? { floor_days: e.floor_days } : {}),
      ...(typeof e.max_days === "number" ? { max_days: e.max_days } : {}),
      ...(Array.isArray(e.allowed) ? { allowed: e.allowed.map(String) } : {}),
    };
  }
  return out;
}

export type DueTone = "overdue" | "soon" | "ok" | "closed";

/** Red when past due, amber in the last 7 days, neutral otherwise; closed requests carry no deadline. */
export function dueTone(r: Pick<Dsr, "status" | "overdue" | "days_left">): DueTone {
  if (r.status !== "OPEN" && r.status !== "IN_PROGRESS") return "closed";
  if (r.overdue || (r.days_left ?? 0) < 0) return "overdue";
  if ((r.days_left ?? 99) <= 7) return "soon";
  return "ok";
}

/** Erasure counts the backend returns in `result.counts` (table → rows), the non-zero ones first. */
export function erasureCounts(result: Dsr["result"]): { key: string; n: number }[] {
  const counts = result && typeof result === "object" && "counts" in result ? (result.counts as Record<string, unknown>) : null;
  if (!counts || typeof counts !== "object") return [];
  return Object.entries(counts)
    .filter((e): e is [string, number] => typeof e[1] === "number")
    .map(([key, n]) => ({ key, n }))
    .sort((a, b) => b.n - a.n || a.key.localeCompare(b.key));
}

/** One follow-up of an erasure the administrator may need to act on (`result.failures[]`, TR/EN). */
export interface ErasureFailure {
  provider: string;
  code: string;
  message_en: string;
  message_tr: string;
  count?: number;
  error?: string;
}
/** One disconnected push calendar of an erasure (`result.calendar[]`). `revoke`: done | not_supported | failed |
 * queued | unreadable | none. */
export interface ErasureCalendar {
  provider: string;
  events: number | null;
  events_removed: number;
  events_failed: number | null;
  revoke: string;
}

const str = (v: unknown): string | undefined => (typeof v === "string" ? v : undefined);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** `result.failures` of a completed erasure (entries without a sentence are skipped; a missing language falls back). */
export function erasureFailures(result: Dsr["result"]): ErasureFailure[] {
  const list = result && Array.isArray(result.failures) ? (result.failures as unknown[]) : [];
  return list.flatMap((raw) => {
    if (!raw || typeof raw !== "object") return [];
    const f = raw as Record<string, unknown>;
    const en = str(f.message_en) ?? str(f.message) ?? str(f.message_tr) ?? "";
    const tr = str(f.message_tr) ?? en;
    if (!en && !tr) return [];
    const count = num(f.count);
    const error = str(f.error);
    return [{ provider: str(f.provider) ?? "", code: str(f.code) ?? "", message_en: en, message_tr: tr, ...(count !== null ? { count } : {}), ...(error ? { error } : {}) }];
  });
}

/** `result.calendar` of a completed erasure: what happened to each push calendar. */
export function erasureCalendars(result: Dsr["result"]): ErasureCalendar[] {
  const list = result && Array.isArray(result.calendar) ? (result.calendar as unknown[]) : [];
  return list.flatMap((raw) => {
    if (!raw || typeof raw !== "object") return [];
    const c = raw as Record<string, unknown>;
    const provider = str(c.provider);
    if (!provider) return [];
    return [{ provider, events: num(c.events), events_removed: num(c.events_removed) ?? 0, events_failed: num(c.events_failed), revoke: str(c.revoke) ?? "none" }];
  });
}

/** RFC 4180 CSV of the data inventory (UTF-8 BOM so Excel reads the Turkish letters). */
export function inventoryCsv(inv: Inventory, locale: string): string {
  const esc = (v: string) => (/[",\n;]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const head = locale === "tr" ? ["Kod", "Veri", "Tablolar", "Satır", "Hukuki dayanak", "Saklama", "İşlem", "Etkin", "Yasal saklama"] : ["Code", "Data", "Tables", "Rows", "Legal basis", "Retention", "Action", "Enabled", "Legal hold"];
  const lines = [head.map(esc).join(",")];
  for (const c of inv.classes) {
    const rows = Object.values(c.rows).reduce((a, b) => a + b, 0);
    const r = c.retention;
    const kept = r ? String(r.retain_days) : (c.kept ?? "");
    lines.push([c.code, locale === "tr" ? c.label_tr : c.label_en, c.tables.join(" "), String(rows), c.legal_basis, kept, r?.action ?? "", r ? (r.enabled ? "1" : "0") : "", r ? (r.legal_hold ? "1" : "0") : ""].map(esc).join(","));
  }
  return `﻿${lines.join("\r\n")}\r\n`;
}

/** The notices grouped by version (newest first), each with its TR and EN text when written. */
export function noticeVersions(list: readonly Notice[]): { version: number; tr: Notice | null; en: Notice | null; published: boolean }[] {
  const by = new Map<number, { version: number; tr: Notice | null; en: Notice | null; published: boolean }>();
  for (const n of list) {
    const v = by.get(n.version) ?? { version: n.version, tr: null, en: null, published: false };
    if (n.language === "tr") v.tr = n;
    else if (n.language === "en") v.en = n;
    v.published = v.published || !!n.published_at;
    by.set(n.version, v);
  }
  return [...by.values()].sort((a, b) => b.version - a.version);
}
