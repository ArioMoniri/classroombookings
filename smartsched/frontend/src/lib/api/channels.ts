/**
 * Notification channels ("Bildirim kanalları"; backend app/api/v1/channels.py, docs/deploy/notification-channels.md).
 * Administrator: per-channel switch, write-only sender secrets (only "configured" flags come back), content mode,
 * KVKK sign-off, WhatsApp Web risk acknowledgement + bridge QR, Teams/Slack department targets, delivery log.
 * Signed-in user: the channels the administrator switched on, the own linked addresses, Telegram deep link,
 * SMS/WhatsApp phone + code, browser push subscription, test, unlink.
 * Errors are `{detail: {code, message, message_tr}}` (see `apiProblem` in ./identity).
 */
import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";

export const CHANNEL_KINDS = ["webpush", "telegram", "whatsapp", "whatsapp_web", "sms", "teams", "slack"] as const;
export type ChannelKind = (typeof CHANNEL_KINDS)[number];

export const Signoff = z
  .object({
    signed: z.boolean().default(false),
    by: z.string().nullish(),
    at: z.string().nullish(),
    legal_basis: z.string().nullish(),
    officer: z.string().nullish(),
  })
  .passthrough();
export type Signoff = z.infer<typeof Signoff>;

export const ChannelConfig = z.object({
  kind: z.string(),
  label_tr: z.string(),
  label_en: z.string(),
  link: z.string(),
  enabled: z.boolean(),
  enabled_requested: z.boolean(),
  configured: z.boolean(),
  content_mode: z.enum(["full", "link_only"]).catch("link_only"),
  options: z.record(z.string(), z.unknown()).default({}),
  secrets: z.record(z.string(), z.boolean()).default({}),
  kvkk_signoff: Signoff.nullish(),
  missing: z.array(z.string()).default([]),
  updated_at: z.string().nullish(),
  department_targets: z.number().optional(),
  risk_ack: z.object({ acknowledged: z.boolean().optional(), by: z.string().nullish(), at: z.string().nullish() }).passthrough().nullish(),
  risk_tr: z.string().optional(),
  risk_en: z.string().optional(),
  bridge_url_configured: z.boolean().optional(),
});
export type ChannelConfig = z.infer<typeof ChannelConfig>;

export const ChannelsAdmin = z.object({
  channels: z.array(ChannelConfig),
  public_url: z.string().nullish(),
  telegram_webhook_url: z.string().nullish(),
});
export type ChannelsAdmin = z.infer<typeof ChannelsAdmin>;

export interface ChannelConfigIn {
  enabled?: boolean;
  content_mode?: "full" | "link_only";
  options?: Record<string, string | number | boolean | null>;
  /** name → value; "" or null clears; omitted keeps */
  secrets?: Record<string, string | null>;
  kvkk_signoff?: { signed: boolean; legal_basis?: string | null; officer?: string | null };
  risk_ack?: boolean;
}

export const DepartmentTarget = z
  .object({
    id: z.number(),
    kind: z.string(),
    department_id: z.number(),
    department: z.string().nullish(),
    /** only the host is ever shown: the URL is a bearer secret */
    host: z.string().nullish(),
    created_at: z.string().nullish(),
  })
  .passthrough();
export type DepartmentTarget = z.infer<typeof DepartmentTarget>;

export const Delivery = z.object({
  id: z.number(),
  kind: z.string(),
  event: z.string(),
  user_id: z.number().nullish(),
  status: z.string(),
  attempts: z.number().default(0),
  last_error: z.string().nullish(),
  created_at: z.string().nullish(),
  sent_at: z.string().nullish(),
  next_attempt_at: z.string().nullish(),
});
export type Delivery = z.infer<typeof Delivery>;

export const BridgeState = z.record(z.string(), z.unknown());
export type BridgeState = z.infer<typeof BridgeState>;

/* ------------------------------------------------------------------------------------------- user */

export const AvailableChannel = z.object({
  kind: z.string(),
  label_tr: z.string(),
  label_en: z.string(),
  link: z.string(),
  content_mode: z.string().nullish(),
  vapid_public_key: z.string().nullish(),
  opt_in_tr: z.string().nullish(),
  opt_in_en: z.string().nullish(),
  sender: z.string().nullish(),
  department_target: z.boolean().nullish(),
});
export type AvailableChannel = z.infer<typeof AvailableChannel>;

export const LinkedChannel = z.object({
  id: z.number(),
  kind: z.string(),
  display_hint: z.string().nullish(),
  label: z.string().nullish(),
  status: z.string(),
  last_error: z.string().nullish(),
  verified_at: z.string().nullish(),
  created_at: z.string().nullish(),
});
export type LinkedChannel = z.infer<typeof LinkedChannel>;

export const MyChannels = z.object({ available: z.array(AvailableChannel).default([]), linked: z.array(LinkedChannel).default([]) });
export type MyChannels = z.infer<typeof MyChannels>;

export interface PushSubscriptionJson {
  endpoint: string;
  keys: { p256dh: string; auth: string };
  expirationTime?: number | null;
}

export const channels = {
  admin: () => request("/channels/admin", { schema: ChannelsAdmin, silent: true }),
  put: (kind: string, body: ChannelConfigIn) => request(`/channels/admin/${kind}`, { method: "PUT", body, schema: ChannelConfig, silent: true }),
  vapid: (rotate = false) => request("/channels/admin/webpush/vapid", { method: "POST", body: { rotate }, schema: ChannelConfig, silent: true }),
  telegramSetup: () =>
    request("/channels/admin/telegram/setup", { method: "POST", schema: z.object({ bot_username: z.string().nullish(), mode: z.string().nullish(), webhook_set: z.boolean().default(false), webhook_url: z.string().nullish() }), silent: true }),
  departments: (kind?: "teams" | "slack") => request("/channels/admin/departments", { query: { kind }, schema: z.array(DepartmentTarget), silent: true }),
  putDepartment: (kind: "teams" | "slack", departmentId: number, url: string) => request(`/channels/admin/${kind}/departments/${departmentId}`, { method: "PUT", body: { url }, schema: DepartmentTarget, silent: true }),
  deleteDepartment: (kind: "teams" | "slack", departmentId: number) => request<void>(`/channels/admin/${kind}/departments/${departmentId}`, { method: "DELETE", silent: true }),
  deliveries: (q: { status?: string; kind?: string; limit?: number } = {}) => request("/channels/admin/deliveries", { query: q, schema: z.array(Delivery), silent: true }),
  bridgeConnect: () => request("/channels/admin/whatsapp_web/connect", { method: "POST", schema: BridgeState, silent: true }),
  bridgeStatus: () => request("/channels/admin/whatsapp_web/status", { schema: BridgeState, silent: true }),
  bridgeLogout: () => request("/channels/admin/whatsapp_web/logout", { method: "POST", schema: BridgeState, silent: true }),
  mine: () => request("/me/channels", { schema: MyChannels, silent: true }),
  telegramLink: () => request("/me/channels/telegram/link", { method: "POST", schema: z.object({ deep_link: z.string(), expires_at: z.string().nullish() }), silent: true }),
  telegramCheck: () => request("/me/channels/telegram/check", { method: "POST", schema: z.object({ linked: z.boolean(), channels: z.array(LinkedChannel).default([]) }), silent: true }),
  phoneLink: (kind: "sms" | "whatsapp", phone: string, consent: boolean) =>
    request(`/me/channels/${kind}/link`, { method: "POST", body: { phone, consent }, schema: z.object({ display_hint: z.string().nullish(), expires_at: z.string().nullish(), sender: z.string().nullish() }), silent: true }),
  phoneVerify: (kind: "sms" | "whatsapp", code: string) => request(`/me/channels/${kind}/verify`, { method: "POST", body: { code }, schema: LinkedChannel, silent: true }),
  pushSubscribe: (subscription: PushSubscriptionJson, label: string | null) => request("/me/channels/webpush", { method: "POST", body: { subscription, label }, schema: LinkedChannel, silent: true }),
  test: (id: number) => request(`/me/channels/${id}/test`, { method: "POST", schema: z.object({ queued: z.boolean(), delivery_id: z.number().nullish() }), silent: true }),
  unlink: (id: number) => request<void>(`/me/channels/${id}`, { method: "DELETE", silent: true }),
};

export const channelKeys = {
  admin: ["channels", "admin"] as const,
  departments: (kind?: string) => ["channels", "departments", kind ?? "all"] as const,
  deliveries: (q: object) => ["channels", "deliveries", q] as const,
  bridge: ["channels", "bridge"] as const,
  mine: ["channels", "mine"] as const,
};

export const useChannelsAdmin = (enabled = true) => useQuery({ queryKey: channelKeys.admin, queryFn: channels.admin, enabled, retry: false });
export const useChannelDepartments = (kind: "teams" | "slack", enabled = true) => useQuery({ queryKey: channelKeys.departments(kind), queryFn: () => channels.departments(kind), enabled, retry: false });
export const useDeliveries = (q: { status?: string; kind?: string; limit?: number }, enabled = true) => useQuery({ queryKey: channelKeys.deliveries(q), queryFn: () => channels.deliveries(q), enabled, retry: false, refetchInterval: enabled ? 30_000 : false });
export const useMyChannels = (enabled = true) => useQuery({ queryKey: channelKeys.mine, queryFn: channels.mine, enabled, retry: false, staleTime: 15_000 });

export function useChannelMutation<TVars, TOut>(fn: (vars: TVars) => Promise<TOut>, invalidate: QueryKey[] = []) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await Promise.all(invalidate.map((key) => qc.invalidateQueries({ queryKey: key })));
    },
  });
}

/** The label in the interface language (`label_tr` / `label_en` from the backend). */
export function channelLabel(c: { label_tr: string; label_en: string }, locale: "tr" | "en"): string {
  return locale === "tr" ? c.label_tr : c.label_en;
}
