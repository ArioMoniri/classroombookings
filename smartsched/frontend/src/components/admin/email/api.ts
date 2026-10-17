/**
 * W3-MAIL admin API (backend `app/api/v1/mail_admin.py`, `setup.settings`): SMTP settings shared by every admin
 * (secrets write-only: `{set, masked}` back, `null` keeps, `""` clears), presets, the test e-mail with its transcript,
 * the SPF / DKIM / DMARC check, the e-mail templates (preview, overrides, test send) and the waiting mail.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "@/lib/api/client";

const s = { silent: true } as const;

export const Secret = z.union([z.object({ set: z.boolean(), masked: z.string().nullish() }), z.string(), z.null()]).nullish();
export type Secret = z.infer<typeof Secret>;
export const secretSet = (v: Secret): boolean => (typeof v === "object" && v ? v.set : !!v);

export const MailSettings = z.object({
  provider: z.string().nullish(),
  host: z.string().nullish(),
  port: z.number().nullish(),
  security: z.enum(["starttls", "ssl", "none"]).catch("starttls"),
  auth_mode: z.enum(["password", "xoauth2", "none"]).catch("password"),
  username: z.string().nullish(),
  password: Secret,
  oauth_provider: z.string().nullish(),
  oauth_tenant: z.string().nullish(),
  oauth_client_id: z.string().nullish(),
  oauth_client_secret: Secret,
  oauth_refresh_token: Secret,
  from_address: z.string().nullish(),
  from_name: z.string().nullish(),
  reply_to: z.string().nullish(),
  timeout_s: z.number().nullish(),
  dkim_selector: z.string().nullish(),
  abroad_ack: z.object({ by: z.string().nullish(), at: z.string().nullish(), provider: z.string().nullish() }).nullish(),
  configured: z.boolean(),
  status: z.enum(["connected", "not_configured", "error"]).catch("not_configured"),
  last_check: z.object({ at: z.string().nullish(), ok: z.boolean(), error: z.string().nullish() }).nullish(),
  last_change: z.object({ by: z.string().nullish(), at: z.string().nullish(), key: z.string().nullish() }).nullish(),
  unsent: z.number().default(0),
});
export type MailSettings = z.infer<typeof MailSettings>;

export type MailSettingsIn = Partial<{
  provider: string;
  host: string;
  port: number;
  security: "starttls" | "ssl" | "none";
  auth_mode: "password" | "xoauth2" | "none";
  username: string;
  password: string | null;
  oauth_provider: "" | "google" | "microsoft";
  oauth_tenant: string;
  oauth_client_id: string;
  oauth_client_secret: string | null;
  oauth_refresh_token: string | null;
  from_address: string;
  from_name: string;
  reply_to: string;
  timeout_s: number;
  dkim_selector: string;
  abroad_ack: boolean;
}>;

export const PresetStep = z.object({ tr: z.string(), en: z.string(), copy: z.string().nullish() });
export const Preset = z.object({
  id: z.string(),
  label: z.string(),
  host: z.string(),
  port: z.number(),
  security: z.enum(["starttls", "ssl", "none"]),
  auth_mode: z.enum(["password", "xoauth2", "none"]),
  username_hint_tr: z.string(),
  username_hint_en: z.string(),
  password_label_tr: z.string(),
  password_label_en: z.string(),
  oauth_provider: z.string(),
  console_url: z.string(),
  hosts: z.array(z.string()),
  steps: z.array(PresetStep),
  notes_tr: z.string(),
  notes_en: z.string(),
  extra: z.record(z.string(), z.unknown()).default({}),
  abroad: z.boolean().default(false),
});
export type Preset = z.infer<typeof Preset>;

export const TestOut = z.object({
  ok: z.boolean(),
  status: z.string(),
  error: z.string().nullish(),
  hint_tr: z.string().nullish(),
  hint_en: z.string().nullish(),
  transcript: z.array(z.string()).default([]),
  duration_ms: z.number().default(0),
  outbox_id: z.number().nullish(),
});
export type TestOut = z.infer<typeof TestOut>;

export const DnsCheck = z.object({
  check: z.enum(["spf", "dkim", "dmarc"]),
  status: z.enum(["ok", "warn", "error", "unknown"]),
  record: z.string().nullish(),
  message_tr: z.string(),
  message_en: z.string(),
  fix_tr: z.string().nullish(),
  fix_en: z.string().nullish(),
});
export const DnsOut = z.object({ domain: z.string(), status: z.string(), checks: z.array(DnsCheck) });
export type DnsOut = z.infer<typeof DnsOut>;

const Pair = z.object({ subject: z.string().nullish(), intro: z.string().nullish() });
export const Template = z.object({
  kind: z.string(),
  label_tr: z.string(),
  label_en: z.string(),
  audience_tr: z.string(),
  audience_en: z.string(),
  tone: z.string(),
  sender: z.string(),
  owner: z.string(),
  placeholders: z.array(z.string()),
  shipped: z.object({ tr: Pair, en: Pair }),
  overrides: z.object({ tr: Pair, en: Pair }),
});
export type Template = z.infer<typeof Template>;
export const Preview = z.object({ subject: z.string(), html: z.string(), text: z.string(), preheader: z.string() });
export type Preview = z.infer<typeof Preview>;

export type Locale = "tr" | "en";
export interface Draft {
  locale: Locale;
  subject?: string | null;
  intro?: string | null;
}

export const mailApi = {
  settings: () => request("/mail/settings", { schema: MailSettings, ...s }),
  put: (body: MailSettingsIn) => request("/mail/settings", { method: "PUT", body, schema: MailSettings, ...s }),
  presets: () => request("/mail/presets", { schema: z.array(Preset), ...s }),
  test: (to: string, locale?: Locale) => request("/mail/test", { method: "POST", body: { to, locale }, schema: TestOut, ...s }),
  dns: (body: { domain?: string; selector?: string }) => request("/mail/dns-check", { method: "POST", body, schema: DnsOut, ...s }),
  requeue: () => request("/mail/outbox/requeue", { method: "POST", body: {}, schema: z.object({ queued: z.number(), unsent: z.number() }), ...s }),
  templates: () => request("/mail/templates", { schema: z.array(Template), ...s }),
  preview: (kind: string, d: Draft) => request(`/mail/templates/${kind}/preview`, { method: "POST", body: d, schema: Preview, ...s }),
  save: (kind: string, d: Draft) => request(`/mail/templates/${kind}`, { method: "PUT", body: d, ...s }),
  testTemplate: (kind: string, d: Draft & { to: string }) => request(`/mail/templates/${kind}/test`, { method: "POST", body: d, schema: TestOut, ...s }),
};

export const mailKeys = {
  settings: ["mail", "settings"] as const,
  presets: ["mail", "presets"] as const,
  templates: ["mail", "templates"] as const,
};

export const useMailSettings = () => useQuery({ queryKey: mailKeys.settings, queryFn: mailApi.settings, retry: false });
export const usePresets = () => useQuery({ queryKey: mailKeys.presets, queryFn: mailApi.presets, retry: false, staleTime: Infinity });
export const useTemplates = () => useQuery({ queryKey: mailKeys.templates, queryFn: mailApi.templates, retry: false });

export function useSaveMail() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: mailApi.put,
    onSuccess: (data) => {
      qc.setQueryData(mailKeys.settings, data);
      void qc.invalidateQueries({ queryKey: ["crbs", "smtp"] });
      void qc.invalidateQueries({ queryKey: ["integrations"] });
    },
  });
}

/** `detail.message_tr` / `message_en` of a refused request, else the error text */
export function mailError(err: unknown, locale: string): string {
  const detail = (err as { detail?: unknown } | null)?.detail as { message_tr?: string; message_en?: string; message?: string } | undefined;
  if (detail && typeof detail === "object") {
    const msg = locale === "tr" ? detail.message_tr : detail.message_en;
    if (msg) return msg;
    if (detail.message) return detail.message;
  }
  return err instanceof Error ? err.message : String(err);
}
