/**
 * Pure helpers of the e-mail setup (W3-MAIL; docs/design/v3/integrations.md §7): what a preset fills, which wizard
 * steps are done, the changed fields to save, paste clean-up of secrets and the DNS row tone.
 */
import type { MailSettings, MailSettingsIn, Preset } from "./api";

export const STEPS = ["provider", "connection", "sender", "domain", "test", "enable"] as const;
export type Step = (typeof STEPS)[number];

/** the fields a preset fills (host, port, TLS, sign-in method, OAuth provider, fixed username) */
export function presetFill(p: Preset): MailSettingsIn {
  const out: MailSettingsIn = { provider: p.id, port: p.port, security: p.security, auth_mode: p.auth_mode };
  if (p.host) out.host = p.host;
  if (p.oauth_provider === "google" || p.oauth_provider === "microsoft") out.oauth_provider = p.oauth_provider;
  const user = p.extra?.username;
  if (typeof user === "string") out.username = user;
  return out;
}

/** whether the stored + drafted values differ from the preset's locked ones (host / port / security) */
export function leavesPreset(p: Preset | undefined, v: { host?: string | null; port?: number | null; security?: string | null }): boolean {
  if (!p || p.id === "custom") return false;
  return (!!v.host && !p.hosts.includes(v.host) && v.host !== p.host) || (v.port != null && v.port !== p.port) || (!!v.security && v.security !== p.security);
}

/** NBSP / spaces / quotes around a pasted secret; `trimmed` tells the UI to say so */
export function cleanSecret(raw: string): { value: string; trimmed: boolean } {
  const value = raw.replace(/ /g, " ").trim().replace(/^["']|["']$/g, "");
  return { value, trimmed: value !== raw };
}

/** only the keys the admin changed, secrets only when typed (never sends a masked value back) */
export function changes(stored: MailSettings, draft: MailSettingsIn): MailSettingsIn {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(draft)) {
    if (v === undefined) continue;
    const before = (stored as Record<string, unknown>)[k];
    if (k === "password" || k === "oauth_client_secret" || k === "oauth_refresh_token") {
      if (typeof v === "string") out[k] = v;
      continue;
    }
    if (k === "abroad_ack") {
      if (v) out[k] = true;
      continue;
    }
    if ((before ?? "") !== (v ?? "")) out[k] = v;
  }
  return out as MailSettingsIn;
}

export function stepDone(step: Step, v: MailSettings, extra: { dnsChecked?: boolean; testOk?: boolean } = {}): boolean {
  switch (step) {
    case "provider":
      return !!v.provider;
    case "connection":
      return !!v.host && !!v.port;
    case "sender":
      return !!v.from_address;
    case "domain":
      return !!extra.dnsChecked;
    case "test":
      return !!extra.testOk || (v.last_check?.ok ?? false);
    case "enable":
      return v.configured;
  }
}

export type DnsTone = "success" | "warning" | "error" | "neutral";
export const dnsTone = (status: string): DnsTone => (status === "ok" ? "success" : status === "warn" ? "warning" : status === "error" ? "error" : "neutral");

/** the from-domain of an address (`bildirim@Uni.edu.tr` → `uni.edu.tr`, Turkish İ kept as i) */
export function domainOf(address: string | null | undefined): string {
  const d = (address ?? "").replace(/ /g, " ").trim().split("@").pop() ?? "";
  return d.replace(/İ/g, "i").toLowerCase();
}

/** the preset steps as `Label: value` lines for an e-mail to IT ("Tümünü kopyala"; never a secret) */
export function stepsText(p: Preset, locale: "tr" | "en"): string {
  return p.steps.map((s, i) => `${i + 1}. ${locale === "tr" ? s.tr : s.en}${s.copy ? `\n   ${s.copy}` : ""}`).join("\n");
}
