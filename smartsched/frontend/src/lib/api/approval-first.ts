"use client";
/**
 * Approval-first bookings, the user side of the notification dispatcher and the integration admin screens
 * (owner requirement 2026-10-15: "it shows first to the admin and they approve or not and put reasons why they
 * didn't, and these get notified to users by the email or other connections they added").
 *
 * - Rejection reason codes: `app/services/approvals.py` REASON_CODES (the backend validates; 422 `reason_required`).
 * - `GET/PUT /me/notification-preferences` (`app/services/notify_dispatch.py`): channels with a master switch and
 *   whether the channel reaches the caller, and the event × channel matrix. Partial PUT.
 * - `GET/PUT /calendar/admin/settings` (`app/api/v1/calendar_sync.py`): calendar sync with its KVKK sign-off
 *   record (written by the backend on every change: who, when, legal basis), webhooks on/off.
 * - `/webhooks` (`app/api/v1/webhooks.py`): outgoing webhooks (setup.settings), the secret is shown once.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";

const s = { silent: true } as const;

/* ------------------------------------------------------------------------------------ reason codes */

/** The rejection reasons an approver may pick, in the order the dialog lists them. */
export const REASON_CODES = ["room_unavailable", "capacity", "policy", "other"] as const;
export type ReasonCode = (typeof REASON_CODES)[number];
/** set by the system (a competing request won the slot); shown, never offered */
export const SYSTEM_REASON_CODES = ["slot_taken"] as const;
export const REASON_MAX = 1000;

export const isReasonCode = (v: unknown): v is ReasonCode => typeof v === "string" && (REASON_CODES as readonly string[]).includes(v);

/* ------------------------------------------------------------------------- notification preferences */

export const ChannelPref = z.object({
  name: z.string(),
  label_tr: z.string(),
  label_en: z.string(),
  /** the user's master switch for the channel */
  enabled: z.boolean(),
  /** whether the channel can reach the user (e-mail: the account has an address; others: linked + switched on) */
  available: z.boolean(),
  default_enabled: z.boolean().default(false),
});
export type ChannelPref = z.infer<typeof ChannelPref>;

export const EventPref = z.object({
  event: z.string(),
  label_tr: z.string(),
  label_en: z.string(),
  /** channel name → on (master switch and the event's own switch together) */
  channels: z.record(z.string(), z.boolean()),
});
export type EventPref = z.infer<typeof EventPref>;

export const NotificationPrefs = z.object({ channels: z.array(ChannelPref), events: z.array(EventPref) });
export type NotificationPrefs = z.infer<typeof NotificationPrefs>;

export interface NotificationPrefsIn {
  channels?: Record<string, boolean>;
  events?: Record<string, Record<string, boolean>>;
}

/* ------------------------------------------------------------------- calendar sync + webhooks admin */

export const CalendarSignoff = z.object({
  enabled: z.boolean(),
  by: z.string().nullish(),
  by_user_id: z.number().nullish(),
  at: z.string(),
  features: z.array(z.string()).default([]),
  legal_basis: z.string().nullish(),
});
export type CalendarSignoff = z.infer<typeof CalendarSignoff>;

/** One push provider's OAuth client as `settings_out` (app/api/v1/calendar_sync.py) answers it: the id in clear, the
 * secret only as `{set, masked}` (write-only), `configured` = id + secret + a public panel URL. */
export const OAuthClientOut = z
  .object({
    client_id: z.string().default(""),
    client_secret: z.object({ set: z.boolean(), masked: z.string().nullish() }).passthrough().nullish(),
    configured: z.boolean(),
    redirect_uri: z.string(),
    tenant: z.string().nullish(),
  })
  .passthrough();
export type OAuthClientOut = z.infer<typeof OAuthClientOut>;

export const IntegrationSettings = z
  .object({
    google: OAuthClientOut.optional(),
    microsoft: OAuthClientOut.optional(),
    calendar_sync_enabled: z.boolean(),
    calendar_sync_signoff: CalendarSignoff.nullish(),
    webhooks_enabled: z.boolean(),
    public_url: z.string().nullish(),
    public_url_source: z.string().nullish(),
    feed_past_days: z.number().nullish(),
    feed_cancelled_grace_days: z.number().nullish(),
  })
  .passthrough();
export type IntegrationSettings = z.infer<typeof IntegrationSettings>;

export interface IntegrationSettingsIn {
  calendar_sync_enabled?: boolean;
  webhooks_enabled?: boolean;
  /** the panel's public address (the OAuth redirect URIs and the feed links are built from it); "" clears it */
  public_url?: string | null;
  /** "" removes the stored value; a secret is never read back */
  google_client_id?: string;
  google_client_secret?: string;
  microsoft_client_id?: string;
  microsoft_client_secret?: string;
  microsoft_tenant?: string;
}

export const Webhook = z.object({
  id: z.number(),
  url: z.string(),
  description: z.string().nullish(),
  events: z.array(z.string()).default([]),
  active: z.boolean(),
  consecutive_failures: z.number().default(0),
  disabled_reason: z.string().nullish(),
  secret_hint: z.string().nullish(),
  created_at: z.string().nullish(),
  updated_at: z.string().nullish(),
});
export type Webhook = z.infer<typeof Webhook>;
export const WebhookCreated = Webhook.extend({ secret: z.string() });

export const WebhookDelivery = z
  .object({
    id: z.number(),
    event_type: z.string().nullish(),
    status: z.string(),
    attempts: z.number().nullish(),
    response_status: z.number().nullish(),
    last_error: z.string().nullish(),
    created_at: z.string().nullish(),
  })
  .passthrough();
export type WebhookDelivery = z.infer<typeof WebhookDelivery>;

export interface WebhookIn {
  url: string;
  events: string[];
  description?: string | null;
  active?: boolean;
}

/* ------------------------------------------------------------------------------------------- calls */

export const approvalFirst = {
  prefs: {
    get: () => request("/me/notification-preferences", { ...s, schema: NotificationPrefs }),
    put: (body: NotificationPrefsIn) => request("/me/notification-preferences", { ...s, method: "PUT", body, schema: NotificationPrefs }),
  },
  integrations: {
    get: () => request("/calendar/admin/settings", { ...s, schema: IntegrationSettings }),
    put: (body: IntegrationSettingsIn) => request("/calendar/admin/settings", { ...s, method: "PUT", body, schema: IntegrationSettings }),
  },
  webhooks: {
    eventTypes: () => request("/webhooks/event-types", { ...s, schema: z.array(z.string()) }),
    list: () => request("/webhooks", { ...s, schema: z.array(Webhook) }),
    create: (body: WebhookIn) => request("/webhooks", { ...s, method: "POST", body, schema: WebhookCreated }),
    update: (id: number, body: Partial<WebhookIn>) => request(`/webhooks/${id}`, { ...s, method: "PUT", body, schema: Webhook }),
    remove: (id: number) => request(`/webhooks/${id}`, { ...s, method: "DELETE" }),
    rotate: (id: number) => request(`/webhooks/${id}/secret`, { ...s, method: "POST", schema: z.object({ secret: z.string() }) }),
    test: (id: number) => request(`/webhooks/${id}/test`, { ...s, method: "POST", schema: z.object({ delivery_id: z.number() }) }),
    deliveries: (id: number) => request(`/webhooks/${id}/deliveries`, { ...s, query: { limit: 20 }, schema: z.array(WebhookDelivery) }),
  },
};

export const afKeys = {
  prefs: ["af", "notification-prefs"] as const,
  integrations: ["af", "integrations"] as const,
  webhooks: ["af", "webhooks"] as const,
  webhookEvents: ["af", "webhook-events"] as const,
  deliveries: (id: number) => ["af", "webhooks", "deliveries", id] as const,
};

export const useNotificationPrefs = (enabled = true) => useQuery({ queryKey: afKeys.prefs, queryFn: approvalFirst.prefs.get, enabled, retry: false });

/** Saves one switch at a time; the answer (the whole matrix) replaces the cache. */
export function useSaveNotificationPrefs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: approvalFirst.prefs.put,
    onSuccess: (data) => qc.setQueryData(afKeys.prefs, data),
  });
}

export const useIntegrationSettings = (enabled = true) => useQuery({ queryKey: afKeys.integrations, queryFn: approvalFirst.integrations.get, enabled, retry: false });

export function useSaveIntegrationSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: approvalFirst.integrations.put,
    onSuccess: (data) => qc.setQueryData(afKeys.integrations, data),
  });
}

export const useWebhooks = (enabled = true) => useQuery({ queryKey: afKeys.webhooks, queryFn: approvalFirst.webhooks.list, enabled, retry: false });
export const useWebhookEventTypes = (enabled = true) => useQuery({ queryKey: afKeys.webhookEvents, queryFn: approvalFirst.webhooks.eventTypes, enabled, retry: false, staleTime: 300_000 });
export const useWebhookDeliveries = (id: number | null) =>
  useQuery({ queryKey: afKeys.deliveries(id ?? 0), queryFn: () => approvalFirst.webhooks.deliveries(id ?? 0), enabled: id !== null, retry: false });
