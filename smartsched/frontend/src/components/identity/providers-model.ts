/**
 * Pure logic of the identity provider screens (wave 3b W3-IDP; design docs/design/v3/integrations.md §5 and §6):
 * which guided-setup step is open, which values are missing, how the sign-in buttons are laid out, and the
 * normalisation of pasted values (NBSP, zero-width characters, quotes, the dotted capital İ).
 */

export const WIZARD_STEPS = ["preset", "console", "values", "test", "enable"] as const;
export type WizardStep = (typeof WIZARD_STEPS)[number];
export type StepState = "locked" | "open" | "done";

export interface ProviderLike {
  kind: "entra" | "google_workspace" | "oidc" | "saml";
  configured: boolean;
  enabled: boolean;
  client_id?: string | null;
  client_secret_set: boolean;
  issuer?: string | null;
  tenant_id?: string | null;
  hosted_domains?: string[];
  discovery?: { ok?: boolean | null };
  saml?: { idp_entity_id?: string | null; certificates?: number } | null;
  test_ok?: boolean | null;
  library_required?: boolean;
}

/** The values still missing before the provider can work (keys of the step-3 fields). */
export function missingFields(p: ProviderLike): string[] {
  const out: string[] = [];
  if (p.kind === "saml") {
    if (!p.saml?.idp_entity_id || !p.saml?.certificates) out.push("metadata");
    return out;
  }
  if (p.kind === "oidc" && !p.issuer) out.push("issuer");
  if (p.kind === "entra" && !p.tenant_id) out.push("tenant_id");
  if (!p.client_id) out.push("client_id");
  if (!p.client_secret_set) out.push("client_secret");
  if (p.kind === "google_workspace" && !(p.hosted_domains ?? []).length) out.push("hosted_domains");
  return out;
}

/** Step states: the console values need the public URL; the test needs a usable client; enabling needs the test. */
export function stepState(p: ProviderLike, ctx: { publicUrl: string | null | undefined }): Record<WizardStep, StepState> {
  const hasUrl = !!ctx.publicUrl;
  const ready = p.configured && !p.library_required;
  const tested = ready && p.test_ok === true;
  return {
    preset: "done",
    console: hasUrl ? (ready ? "done" : "open") : "locked",
    values: !hasUrl ? "locked" : ready ? "done" : "open",
    test: !hasUrl || !ready ? "locked" : tested ? "done" : "open",
    enable: tested ? (p.enabled ? "done" : "open") : "locked",
  };
}

/** The first step that still needs the administrator (where the sheet opens). */
export function firstOpenStep(states: Record<WizardStep, StepState>): WizardStep {
  return WIZARD_STEPS.find((s) => states[s] === "open") ?? (states.enable === "done" ? "enable" : "console");
}

export interface ButtonLike {
  name: string;
  kind: string;
  label: string;
  start_url: string;
}

/**
 * The /login buttons (design v3 §6): one provider alone keeps the single primary button; two or more are equal, at
 * most three visible, the rest behind "Diğer giriş yolları"; an invite link shows only the invited method.
 */
export function buttonLayout<T extends ButtonLike>(providers: T[], invited: string | null): { visible: T[]; more: T[]; single: boolean } {
  if (invited) {
    const only = providers.filter((p) => p.name === invited);
    return { visible: only, more: [], single: true };
  }
  if (providers.length <= 1) return { visible: providers, more: [], single: true };
  return { visible: providers.slice(0, 3), more: providers.slice(3), single: false };
}

const INVISIBLE = /[​‌‍⁠﻿]/g;

/** A pasted value: NBSP → space, zero-width characters removed, outer spaces and quotes trimmed. */
export function cleanPasted(raw: string): { value: string; trimmed: boolean } {
  const text = raw.normalize("NFKC").replace(INVISIBLE, "").replace(/ /g, " ");
  const value = text.trim().replace(/^["'`]+|["'`]+$/g, "").trim();
  return { value, trimmed: value !== raw };
}

const GUID = /^\{?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}?$/i;
/** "Bu bir kimliğe benziyor": a GUID pasted into the secret field is usually the secret's id, not its value. */
export function looksLikeGuid(value: string): boolean {
  return GUID.test(cleanPasted(value).value);
}

/** Domains from free text ("uni.edu.tr, @ogr.uni.edu.tr"): folded (İ/I/ı → i), the "@" dropped, unique. */
export function parseDomains(text: string): string[] {
  const out: string[] = [];
  for (const part of cleanPasted(text).value.split(/[\s,;]+/)) {
    const d = part.replace(/[İIı]/g, "i").toLowerCase().replace(/^.*@/, "").replace(/^\.+|\.+$/g, "");
    if (d && !out.includes(d)) out.push(d);
  }
  return out;
}

/** "Tümünü kopyala": every console value as `Label: value` lines (never a secret: the console values hold none). */
export function copyAllText(values: { key?: string; label_tr: string; label_en: string; value?: string | null }[], locale: "tr" | "en"): string {
  return values
    .filter((v) => v.value)
    .map((v) => `${locale === "tr" ? v.label_tr : v.label_en}: ${v.value}`)
    .join("\n");
}

/** Permissions the server refuses on a self sign-up role (`sso._too_privileged_for_default`; T-R1-35). */
const NOT_FOR_NEW_ACCOUNTS: ReadonlySet<string> = new Set(["planning.admin", "planning.edit", "setup.users", "setup.roles"]);
export function signupRoleEligible(role: { code?: string | null; permissions: readonly string[] }): boolean {
  return role.code !== "ADMIN" && !role.permissions.some((p) => NOT_FOR_NEW_ACCOUNTS.has(p));
}
