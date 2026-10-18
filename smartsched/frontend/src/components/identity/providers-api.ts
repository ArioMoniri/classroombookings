/**
 * Identity providers administration (wave 3b W3-IDP; backend app/api/v1/sso.py `/auth/sso/admin/providers*`,
 * app/services/identity/**). zod parses every answer. The client secret and the SAML SP private key are write-only:
 * no schema has a field for them, only `client_secret_set` / `saml.sp_private_key_set`.
 */
import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "@/lib/api/client";
import { RoleRef } from "@/lib/api/identity";

export const ProviderKind = z.enum(["entra", "google_workspace", "oidc", "saml"]);
export type ProviderKind = z.infer<typeof ProviderKind>;
export const ProviderStatus = z.enum(["connected", "not_configured", "error", "disabled"]).catch("not_configured");
export type ProviderStatus = z.infer<typeof ProviderStatus>;

export const Check = z.object({
  key: z.string(),
  ok: z.boolean(),
  tr: z.string(),
  en: z.string(),
  detail: z.string().nullish(),
});
export type Check = z.infer<typeof Check>;

/** What the screen shows of a certificate (app/services/identity/saml_crypto.py `cert_info`); never the PEM. */
export const CertInfo = z.object({
  subject: z.string(),
  not_after: z.string(),
  sha256: z.string(),
});
export type CertInfo = z.infer<typeof CertInfo>;

export const Provider = z.object({
  id: z.number(),
  name: z.string(),
  kind: ProviderKind,
  badge: z.string(),
  label: z.string(),
  label_en: z.string(),
  display_name: z.string().nullish(),
  preset: z.string().nullish(),
  enabled: z.boolean(),
  configured: z.boolean(),
  status: ProviderStatus,
  sort_order: z.number(),
  allowed_domains: z.array(z.string()).default([]),
  invite_only: z.boolean(),
  self_signup: z.boolean(),
  default_role: RoleRef.nullish(),
  role_mapping_enabled: z.boolean(),
  allow_admin_mapping: z.boolean(),
  oidc_only_non_admins: z.boolean(),
  invite_days: z.number(),
  domain_hint: z.string().nullish(),
  client_id: z.string().nullish(),
  client_secret_set: z.boolean(),
  from_environment: z.array(z.string()).default([]),
  secret_expires: z.string().nullish(),
  tenant_id: z.string().nullish(),
  issuer: z.string().nullish(),
  hosted_domains: z.array(z.string()).default([]),
  groups_claim: z.string().default("groups"),
  roles_claim: z.string().default("roles"),
  trust_email: z.boolean().default(false),
  scopes: z.array(z.string()).default([]),
  discovery: z.object({
    ok: z.boolean().nullish(),
    checks: z.array(Check).default([]),
    fetched_at: z.string().nullish(),
  }),
  saml: z
    .object({
      metadata_url: z.string().nullish(),
      idp_entity_id: z.string().nullish(),
      sso_url: z.string().nullish(),
      certificates: z.number().default(0),
      cert_not_after: z.string().nullish(),
      email_attribute: z.string().nullish(),
      name_attribute: z.string().nullish(),
      groups_attribute: z.string().nullish(),
      subject_attribute: z.string().nullish(),
      // RF-12 (idp-2026-10-18): the federation certificate and the SP key pair; the private key is write-only
      metadata_signing_cert: CertInfo.nullish(),
      metadata_signed: z.boolean().default(false),
      sp_certificate: CertInfo.nullish(),
      sp_private_key_set: z.boolean().default(false),
      sign_requests: z.boolean().default(false),
    })
    .nullish(),
  library_required: z.boolean().default(false),
  redirect_uri: z.string().nullish(),
  start_url: z.string(),
  identities: z.number().default(0),
  test_ok: z.boolean().nullish(),
  test_at: z.string().nullish(),
  last_check_at: z.string().nullish(),
  last_check_ok: z.boolean().nullish(),
  last_check_detail: z.string().nullish(),
  changed_by: z.string().nullish(),
  changed_at: z.string().nullish(),
  version: z.string(),
});
export type Provider = z.infer<typeof Provider>;

export const ProvidersList = z.object({
  providers: z.array(Provider),
  ldap: z.object({
    kind: z.literal("ldap"),
    badge: z.string(),
    label: z.string(),
    label_en: z.string(),
    enabled: z.boolean(),
    configured: z.boolean(),
    settings_href: z.string(),
  }),
  break_glass_admins: z.number(),
  saml_available: z.boolean(),
});
export type ProvidersList = z.infer<typeof ProvidersList>;

const Bi = z.object({ tr: z.string(), en: z.string() });
export const KindCard = z.object({
  kind: z.enum(["entra", "google_workspace", "oidc", "saml", "ldap"]),
  badge: z.string(),
  label: Bi,
  description: Bi,
  presets: z.array(z.object({ key: z.string(), label: z.string() })).default([]),
  fields: z
    .array(
      z.object({
        key: z.string(),
        required: z.boolean(),
        secret: z.boolean(),
      }),
    )
    .default([]),
  available: z.boolean(),
  library_required: z.boolean().default(false),
});
export type KindCard = z.infer<typeof KindCard>;

export const ConsoleValue = z.object({
  key: z.string(),
  label_tr: z.string(),
  label_en: z.string(),
  value: z.string().nullish(),
});
export type ConsoleValue = z.infer<typeof ConsoleValue>;
export const Setup = z.object({
  provider: Provider,
  public_url: z.string().nullish(),
  public_url_source: z.string().nullish(),
  public_url_secure: z.boolean().default(false),
  console: z.array(ConsoleValue).default([]),
  steps: z.object({
    tr: z.array(z.string()).default([]),
    en: z.array(z.string()).default([]),
  }),
  fields: z
    .array(
      z.object({
        key: z.string(),
        required: z.boolean(),
        secret: z.boolean(),
      }),
    )
    .default([]),
  issuer_hint: z.string().nullish(),
  groups_claim_hint: z.string().nullish(),
});
export type Setup = z.infer<typeof Setup>;

export const Discovery = z.object({
  ok: z.boolean(),
  checks: z.array(Check).default([]),
});
export type Discovery = z.infer<typeof Discovery>;

export const TestStart = z.object({
  authorize_url: z.string(),
  test_id: z.string(),
});
export const TestResult = z.object({
  status: z.enum(["pending", "done"]),
  ok: z.boolean().nullish(),
  at: z.string().nullish(),
  code: z.string().nullish(),
  reason: z.string().nullish(),
  detail: z.string().nullish(),
  hint: z
    .object({
      tr: z.string(),
      en: z.string(),
      step: z.number().nullish(),
      raw: z.string().nullish(),
    })
    .nullish(),
  claims: z.record(z.string(), z.unknown()).nullish(),
  attributes: z.record(z.string(), z.array(z.string())).nullish(),
  verified_email: z.string().nullish(),
  subject: z.string().nullish(),
  groups: z.array(z.string()).default([]),
  roles: z.array(z.string()).default([]),
  domain_ok: z.boolean().nullish(),
  mapped_role: RoleRef.nullish(),
});
export type TestResult = z.infer<typeof TestResult>;

export const ProviderMapping = z.object({
  id: z.number(),
  claim: z.enum(["role", "group"]),
  value: z.string(),
  role: RoleRef,
  created_at: z.string(),
});
export type ProviderMapping = z.infer<typeof ProviderMapping>;

export const ProviderInvite = z.object({
  id: z.number(),
  user_id: z.number(),
  email: z.string(),
  kind: z.string(),
  provider: z.string().default("entra"),
  provider_kind: z.string().nullish(),
  provider_label: z.string().nullish(),
  email_status: z.string().nullish(),
  status: z.enum(["invited", "invite_expired"]),
  created_at: z.string(),
  expires_at: z.string(),
  created_by: z.number().nullish(),
  link: z.string().nullish(),
});
export type ProviderInvite = z.infer<typeof ProviderInvite>;

const BulkError = z.object({
  line: z.number(),
  email: z.string().nullish(),
  code: z.string(),
  tr: z.string(),
  en: z.string(),
});
export const BulkOut = z.object({
  created: z.array(ProviderInvite.extend({ line: z.number().nullish() })),
  errors: z.array(BulkError),
});
export type BulkOut = z.infer<typeof BulkOut>;

export type ProviderIn = Partial<{
  version: string;
  name: string;
  display_name: string;
  enabled: boolean;
  allowed_domains: string[];
  invite_only: boolean;
  self_signup: boolean;
  default_role_id: number;
  role_mapping_enabled: boolean;
  allow_admin_mapping: boolean;
  oidc_only_non_admins: boolean;
  invite_days: number;
  domain_hint: string;
  client_id: string;
  client_secret: string;
  secret_expires: string;
  tenant_id: string;
  issuer: string;
  hosted_domains: string[];
  groups_claim: string;
  roles_claim: string;
  trust_email: boolean;
  scopes: string[];
  metadata_url: string;
  metadata_xml: string;
  idp_entity_id: string;
  email_attribute: string;
  name_attribute: string;
  groups_attribute: string;
  /** PEM or base64; "" removes it */
  metadata_signing_cert: string;
  /** write-only: never in an answer, only `saml.sp_private_key_set` */
  sp_private_key: string;
  sp_certificate: string;
  sp_key_generate: boolean;
  sp_key_remove: boolean;
  sign_requests: boolean;
}>;

export interface ProviderInviteIn {
  email: string;
  full_name?: string | null;
  role_id?: number | null;
  provider: string;
  days?: number | null;
  send_email?: boolean;
  locale?: "tr" | "en";
}

const A = "/auth/sso/admin";
export const idp = {
  kinds: () => request(`${A}/kinds`, { schema: z.array(KindCard), silent: true }),
  list: () => request(`${A}/providers`, { schema: ProvidersList, silent: true }),
  create: (body: { kind: ProviderKind; preset?: string; display_name?: string; name?: string }) =>
    request(`${A}/providers`, {
      method: "POST",
      body,
      schema: Provider,
      silent: true,
    }),
  get: (id: number) => request(`${A}/providers/${id}`, { schema: Provider, silent: true }),
  put: (id: number, body: ProviderIn) =>
    request(`${A}/providers/${id}`, {
      method: "PUT",
      body,
      schema: Provider,
      silent: true,
    }),
  remove: (id: number) =>
    request<void>(`${A}/providers/${id}`, {
      method: "DELETE",
      silent: true,
    }),
  order: (ids: number[]) =>
    request(`${A}/providers/order`, {
      method: "PUT",
      body: { ids },
      schema: ProvidersList,
      silent: true,
    }),
  setup: (id: number) => request(`${A}/providers/${id}/setup`, { schema: Setup, silent: true }),
  discover: (id: number) =>
    request(`${A}/providers/${id}/discover`, {
      method: "POST",
      schema: Discovery,
      silent: true,
    }),
  startTest: (id: number) =>
    request(`${A}/providers/${id}/test`, {
      method: "POST",
      schema: TestStart,
      silent: true,
    }),
  testResult: (id: number, testId: string) =>
    request(`${A}/providers/${id}/test/${encodeURIComponent(testId)}`, {
      schema: TestResult,
      silent: true,
    }),
  mappings: (id: number) =>
    request(`${A}/providers/${id}/mappings`, {
      schema: z.array(ProviderMapping),
      silent: true,
    }),
  addMapping: (id: number, body: { claim: "role" | "group"; value: string; role_id: number }) =>
    request(`${A}/providers/${id}/mappings`, {
      method: "POST",
      body,
      schema: ProviderMapping,
      silent: true,
    }),
  deleteMapping: (id: number, mappingId: number) =>
    request<void>(`${A}/providers/${id}/mappings/${mappingId}`, {
      method: "DELETE",
      silent: true,
    }),
  invites: () =>
    request(`${A}/invites`, {
      schema: z.array(ProviderInvite),
      silent: true,
    }),
  invite: (body: ProviderInviteIn) =>
    request(`${A}/invites`, {
      method: "POST",
      body,
      schema: ProviderInvite,
      silent: true,
    }),
  bulk: (body: { csv: string; provider: string; role_id?: number | null; days?: number | null; send_email: boolean; locale?: "tr" | "en" }) =>
    request(`${A}/invites/bulk`, {
      method: "POST",
      body,
      schema: BulkOut,
      silent: true,
    }),
  resend: (id: number, locale?: "tr" | "en") =>
    request(`${A}/invites/${id}/resend`, {
      method: "POST",
      body: { locale },
      schema: z.object({
        sent: z.boolean(),
        status: z.string(),
        error: z.string().nullish(),
      }),
      silent: true,
    }),
  renew: (id: number) =>
    request(`${A}/invites/${id}/renew`, {
      method: "POST",
      schema: ProviderInvite,
      silent: true,
    }),
  revoke: (id: number) => request<void>(`${A}/invites/${id}`, { method: "DELETE", silent: true }),
  acceptLocal: (token: string, password: string) =>
    request(`/auth/sso/invites/${encodeURIComponent(token)}/password`, {
      method: "POST",
      body: { password },
      schema: z.object({ ok: z.boolean(), email: z.string().nullish() }),
      silent: true,
    }),
  publicInvite: (token: string) =>
    request(`/auth/sso/invites/${encodeURIComponent(token)}`, {
      schema: z.object({
        provider: z.string().default("entra"),
        provider_kind: z.string().nullish(),
        provider_label: z.string().nullish(),
        provider_label_en: z.string().nullish(),
        start_url: z.string().nullish(),
        login_hint: z.string(),
      }),
      silent: true,
    }),
};

export const idpKeys = {
  all: ["identity", "idp"] as const,
  kinds: ["identity", "idp", "kinds"] as const,
  list: ["identity", "idp", "list"] as const,
  setup: (id: number) => ["identity", "idp", "setup", id] as const,
  mappings: (id: number) => ["identity", "idp", "mappings", id] as const,
  invites: ["identity", "invites"] as const,
};

export const useKinds = () =>
  useQuery({
    queryKey: idpKeys.kinds,
    queryFn: idp.kinds,
    retry: false,
    staleTime: 300_000,
  });
export const useProviders = () => useQuery({ queryKey: idpKeys.list, queryFn: idp.list, retry: false });
export const useSetup = (id: number | null) =>
  useQuery({
    queryKey: idpKeys.setup(id ?? 0),
    queryFn: () => idp.setup(id ?? 0),
    enabled: id !== null,
    retry: false,
  });
export const useProviderMappings = (id: number) =>
  useQuery({
    queryKey: idpKeys.mappings(id),
    queryFn: () => idp.mappings(id),
    retry: false,
  });
export const useProviderInvites = () => useQuery({ queryKey: idpKeys.invites, queryFn: idp.invites, retry: false });

/** A mutation that refreshes the identity provider queries (every admin screen reads the same rows). */
export function useIdpMutation<TVars, TOut>(fn: (vars: TVars) => Promise<TOut>, invalidate: QueryKey[] = [idpKeys.all, idpKeys.invites]) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await Promise.all(invalidate.map((key) => qc.invalidateQueries({ queryKey: key })));
    },
  });
}
