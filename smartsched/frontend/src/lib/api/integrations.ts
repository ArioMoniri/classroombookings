"use client";
/**
 * Integrations gallery (wave 3b W3-HUB; backend `app/api/v1/integrations.py`, docs/design/v3/integrations.md).
 *
 * `GET /integrations/status` (`setup.settings` or `planning.admin`): read-only, organisation-wide connector cards of
 * six areas — identity, email, calendar, channels, automation, ai. Each card: `status` (connected | not_configured |
 * error | disabled | unknown), last check, last change (who, when), the setup link and the owning area's own switch
 * (`toggle {method, path, field, enable_in_setup}`; the hub never writes settings itself — the switch calls that
 * area's endpoint with `{[field]: on}`). Secrets never appear in the answer.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";

const s = { silent: true } as const;

export const AREA_KEYS = ["identity", "email", "calendar", "channels", "automation", "ai"] as const;
export type AreaKey = (typeof AREA_KEYS)[number];
export const CARD_STATUSES = ["connected", "not_configured", "error", "disabled", "unknown"] as const;
export type CardStatus = (typeof CARD_STATUSES)[number];

export const Toggle = z.object({
  method: z.enum(["PUT", "PATCH", "POST"]).catch("PUT"),
  path: z.string(),
  field: z.string(),
  enable_in_setup: z.boolean().default(false),
});
export type Toggle = z.infer<typeof Toggle>;

export const ConnectorCard = z.object({
  key: z.string(),
  area: z.string(),
  name_tr: z.string(),
  name_en: z.string(),
  summary_tr: z.string(),
  summary_en: z.string(),
  status: z.enum(CARD_STATUSES).catch("unknown"),
  enabled: z.boolean().nullish(),
  detail_tr: z.string().nullish(),
  detail_en: z.string().nullish(),
  last_check_at: z.string().nullish(),
  last_check_ok: z.boolean().nullish(),
  changed_by: z.string().nullish(),
  changed_at: z.string().nullish(),
  setup_href: z.string(),
  toggle: Toggle.nullish(),
  ref: z.record(z.string(), z.union([z.number(), z.string()])).nullish(),
  source: z.enum(["contract", "builtin", "missing"]).catch("builtin"),
});
export type ConnectorCard = z.infer<typeof ConnectorCard>;

export const IntegrationArea = z.object({ key: z.string(), label_tr: z.string(), label_en: z.string(), cards: z.array(ConnectorCard) });
export type IntegrationArea = z.infer<typeof IntegrationArea>;

export const IntegrationsStatus = z.object({
  generated_at: z.string(),
  areas: z.array(IntegrationArea),
  counts: z.record(z.string(), z.number()).default({}),
  asks: z.array(z.object({ area: z.string(), lane: z.string(), function: z.string() })).default([]),
});
export type IntegrationsStatus = z.infer<typeof IntegrationsStatus>;

export const integrationsKeys = { status: ["integrations", "status"] as const };

export const integrationsApi = {
  status: () => request("/integrations/status", { ...s, schema: IntegrationsStatus }),
  /** the owning area's own endpoint (relative to /api/v1), body `{[field]: on}` */
  toggle: (t: Toggle, on: boolean) => request(t.path, { ...s, method: t.method, body: { [t.field]: on } }),
};

export function useIntegrationsStatus(enabled = true) {
  return useQuery({ queryKey: integrationsKeys.status, queryFn: integrationsApi.status, enabled, retry: false, refetchOnWindowFocus: true });
}

/** Switch a connector through its area's endpoint; refreshes the gallery and every admin query of that area. */
export function useToggleConnector() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ toggle, on }: { card: ConnectorCard; toggle: Toggle; on: boolean }) => integrationsApi.toggle(toggle, on),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: integrationsKeys.status });
      // the embedded admin panels keep their own caches (channels, calendar settings, webhooks)
      void qc.invalidateQueries({ predicate: (q) => ["af", "channels", "calendar"].includes(String(q.queryKey[0])) });
    },
  });
}
