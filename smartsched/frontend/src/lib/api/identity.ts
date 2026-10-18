/**
 * Sign-in with Microsoft (Entra ID) and the identity administration (`/api/v1/auth/sso/*`; backend
 * app/api/v1/sso.py, contract docs/design/v2/sign-in.md §14). Hand-written against the backend's pydantic
 * schemas (app/schemas/sso.py): zod parses every response, so a contract drift fails loudly in one place.
 *
 * Errors of the administration routes are `{detail: {code, en, tr}}`; `identityErrorText` picks the language.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { z } from "zod";
import { HttpError, request } from "./client";

/* ------------------------------------------------------------------------------------------ public */

export const MicrosoftAuth = z.object({
  enabled: z.boolean().default(false),
  label: z.string().default("Microsoft"),
  start_url: z.string().default("/api/v1/auth/sso/entra/start"),
  domain_hint: z.string().nullish(),
  self_signup: z.boolean().default(true),
});

/** One sign-in button of /login (wave 3b W3-IDP: every enabled provider, in the administrators' order). */
export const ProviderButton = z.object({
  name: z.string(),
  kind: z.string(),
  label: z.string(),
  label_en: z.string().optional(),
  badge: z.string().optional(),
  start_url: z.string(),
  domain_hint: z.string().nullish(),
  self_signup: z.boolean().default(false),
});
export type ProviderButton = z.infer<typeof ProviderButton>;

/** The login page's `auth` block (`GET /org/public` → `auth`, also `GET /auth/sso/providers` → `auth`). */
export const PublicAuth = z.object({
  microsoft: MicrosoftAuth,
  providers: z.array(ProviderButton).optional(),
  local_enabled: z.boolean().default(true),
  ldap_enabled: z.boolean().default(false),
  self_signup_role_name: z.string().nullish(),
  /** T-R1-30: the role's code (`TEACHER`) and its TR/EN label (built-in names localised); the hint reads these */
  self_signup_role_code: z.string().nullish(),
  self_signup_role_label: z.record(z.string(), z.string()).nullish(),
});
export type PublicAuth = z.infer<typeof PublicAuth>;

/** `GET /org/public` with the `auth` block (the login page reads it on the server, sign-in.md §4.3). */
export const OrgPublicAuth = z.object({
  name: z.string().nullish(),
  logo_url: z.string().nullish(),
  login_message: z.string().nullish(),
  maintenance_mode: z.boolean().default(false),
  maintenance_message: z.string().nullish(),
  ldap_enabled: z.boolean().default(false),
  setup_required: z.boolean().default(false),
  default_language: z.string().nullish(),
  languages: z.array(z.string()).nullish(),
  auth: PublicAuth.nullish(),
  /** the institution's KVKK notice (footer link); rendered only when the backend provides it */
  kvkk_notice_url: z.string().nullish(),
  /** AU-B / AUX-03 (auth.md §4.1): passkeys on, passwordless passkey sign-in, "Bu cihazı hatırla" days */
  passkeys: z.object({ enabled: z.boolean().default(false), sign_in: z.boolean().default(false), trusted_device_days: z.number().default(30) }).nullish(),
});
export type OrgPublicAuth = z.infer<typeof OrgPublicAuth>;

/** `GET /auth/sso/invites/{token}`: the banner of `/login?invite=<token>`. */
export const PublicInvite = z.object({
  kind: z.string(),
  inviter_name: z.string().nullish(),
  role_name: z.string().nullish(),
  invited_masked: z.string().nullish(),
  login_hint: z.string(),
  days_left: z.number(),
  expires_at: z.string(),
});
export type PublicInvite = z.infer<typeof PublicInvite>;

export const ExchangeOut = z.object({
  user: z.unknown().nullish(),
  password_change_required: z.boolean().default(false),
  next: z.string().nullish(),
  welcome: z.enum(["self", "invited", "bound"]).nullish(),
  inviter_name: z.string().nullish(),
  /** AU-16: the policy wants 2FA for the role and the provider asserted none (step-up notice, shown once) */
  idp_mfa_missing: z.boolean().default(false),
  idp_mfa_message_tr: z.string().nullish(),
  idp_mfa_message_en: z.string().nullish(),
});
export type ExchangeOut = z.infer<typeof ExchangeOut>;

/** One-time ticket → session cookie (the Next proxy stores the token, like `/auth/login`). */
export function exchangeTicket(ticket: string): Promise<ExchangeOut> {
  return request("/auth/sso/exchange", { method: "POST", body: { ticket }, schema: ExchangeOut, silent: true });
}

/* -------------------------------------------------------------------------------------- signed in */

export const SsoMe = z.object({
  linked: z.boolean(),
  email_at_login: z.string().nullish(),
  display_name: z.string().nullish(),
  linked_at: z.string().nullish(),
  last_login_at: z.string().nullish(),
  pending_bind: z.boolean().default(false),
  has_password: z.boolean().default(false),
});
export type SsoMe = z.infer<typeof SsoMe>;

/* --------------------------------------------------------------------------------- administration */

export const RoleRef = z.object({ id: z.number(), code: z.string().nullish(), name: z.string() });

export const SsoConfig = z.object({
  enabled: z.boolean(),
  configured: z.boolean(),
  tenant_id: z.string().nullish(),
  client_id: z.string().nullish(),
  client_secret_set: z.boolean(),
  from_environment: z.array(z.string()).default([]),
  authority: z.string().nullish(),
  redirect_uri: z.string().nullish(),
  public_url_source: z.string().nullish(),
  self_signup: z.boolean(),
  domain_hint: z.string().nullish(),
  default_role: RoleRef.nullish(),
  oidc_only_non_admins: z.boolean(),
  role_mapping_enabled: z.boolean(),
  allow_admin_mapping: z.boolean(),
  invite_days: z.number(),
  break_glass_admins: z.number(),
  updated_at: z.string().nullish(),
});
export type SsoConfig = z.infer<typeof SsoConfig>;

export interface SsoConfigIn {
  enabled?: boolean;
  tenant_id?: string;
  client_id?: string;
  client_secret?: string;
  self_signup?: boolean;
  domain_hint?: string;
  default_role_id?: number;
  oidc_only_non_admins?: boolean;
  role_mapping_enabled?: boolean;
  allow_admin_mapping?: boolean;
  invite_days?: number;
}

export const Mapping = z.object({ id: z.number(), claim: z.enum(["role", "group"]), value: z.string(), role: RoleRef, created_at: z.string() });
export type Mapping = z.infer<typeof Mapping>;

export const Invite = z.object({
  id: z.number(),
  user_id: z.number(),
  email: z.string(),
  kind: z.string(),
  status: z.enum(["invited", "invite_expired"]),
  created_at: z.string(),
  expires_at: z.string(),
  created_by: z.number().nullish(),
  link: z.string().nullish(),
  /** RF-03: with `send_email`, whether the invitation e-mail went out (`SENT`, else `UNSENT` / `FAILED`) */
  email_status: z.string().nullish(),
});
export type Invite = z.infer<typeof Invite>;

export interface InviteIn {
  email: string;
  full_name?: string | null;
  role_id?: number | null;
  role?: string | null;
  department_id?: number | null;
  instructor_id?: number | null;
  days?: number | null;
  /** RF-03: e-mail the link at once (themed invitation e-mail); needs SMTP (`inviteMail().configured`) */
  send_email?: boolean;
  locale?: "tr" | "en";
}

export const IdentityStatus = z.enum(["linked", "invited", "invite_expired", "binding", "none"]);
export type IdentityStatus = z.infer<typeof IdentityStatus>;

export const UserIdentityStatus = z.object({
  status: IdentityStatus.catch("none"),
  auth_methods: z.array(z.string()).default([]),
  invite: z.object({ id: z.number(), kind: z.string(), expires_at: z.string(), invited_by: z.number().nullish() }).nullish(),
  binding_pending: z.boolean().default(false),
  self_signup_at: z.string().nullish(),
  break_glass: z.boolean().default(false),
  instructor_id: z.number().nullish(),
});
export type UserIdentityStatus = z.infer<typeof UserIdentityStatus>;
export const UserStatusMap = z.record(z.string(), UserIdentityStatus);
export type UserStatusMap = z.infer<typeof UserStatusMap>;

export const identity = {
  providers: () => request("/auth/sso/providers", { schema: z.object({ auth: PublicAuth }), silent: true }),
  invite: (token: string) => request(`/auth/sso/invites/${encodeURIComponent(token)}`, { schema: PublicInvite, silent: true }),
  me: () => request("/auth/sso/me", { schema: SsoMe, silent: true }),
  link: (password: string) => request("/auth/sso/entra/link", { method: "POST", body: { password, confirm: true }, schema: z.object({ authorize_url: z.string() }), silent: true }),
  unlink: () => request<void>("/auth/sso/entra/link", { method: "DELETE", silent: true }),
  config: () => request("/auth/sso/admin/entra", { schema: SsoConfig, silent: true }),
  putConfig: (body: SsoConfigIn) => request("/auth/sso/admin/entra", { method: "PUT", body, schema: SsoConfig, silent: true }),
  mappings: () => request("/auth/sso/admin/entra/mappings", { schema: z.array(Mapping), silent: true }),
  addMapping: (body: { claim: "role" | "group"; value: string; role_id: number }) => request("/auth/sso/admin/entra/mappings", { method: "POST", body, schema: Mapping, silent: true }),
  deleteMapping: (id: number) => request<void>(`/auth/sso/admin/entra/mappings/${id}`, { method: "DELETE", silent: true }),
  invites: () => request("/auth/sso/admin/invites", { schema: z.array(Invite), silent: true }),
  /** RF-03: whether SMTP is set up, so the users screen's invite sheet can e-mail the link (setup.users) */
  inviteMail: () => request("/auth/sso/admin/invite-mail", { schema: z.object({ configured: z.boolean() }), silent: true }),
  createInvite: (body: InviteIn) => request("/auth/sso/admin/invites", { method: "POST", body, schema: Invite, silent: true }),
  renewInvite: (id: number) => request(`/auth/sso/admin/invites/${id}/renew`, { method: "POST", schema: Invite, silent: true }),
  deleteInvite: (id: number) => request<void>(`/auth/sso/admin/invites/${id}`, { method: "DELETE", silent: true }),
  bind: (userId: number, body: { email?: string | null; days?: number | null } = {}) => request(`/auth/sso/admin/users/${userId}/bind`, { method: "POST", body, schema: Invite, silent: true }),
  unlinkUser: (userId: number) => request<void>(`/auth/sso/admin/users/${userId}/identity`, { method: "DELETE", silent: true }),
  setInstructor: (userId: number, instructorId: number | null) =>
    request(`/auth/sso/admin/users/${userId}/instructor`, { method: "PUT", body: { instructor_id: instructorId }, schema: z.object({ user_id: z.number(), instructor_id: z.number().nullish() }), silent: true }),
  userStatus: () => request("/auth/sso/admin/user-status", { schema: UserStatusMap, silent: true }),
  instructors: (search: string, limit = 20) =>
    request("/instructors", { query: { search: search || undefined, limit }, schema: z.object({ items: z.array(z.object({ id: z.number(), full_name: z.string(), title: z.string().nullish() })).default([]) }), silent: true }),
};

export const identityKeys = {
  providers: ["identity", "providers"] as const,
  me: ["identity", "me"] as const,
  config: ["identity", "config"] as const,
  mappings: ["identity", "mappings"] as const,
  invites: ["identity", "invites"] as const,
  userStatus: ["identity", "user-status"] as const,
  inviteMail: ["identity", "invite-mail"] as const,
  instructors: (q: string, limit: number) => ["identity", "instructors", q, limit] as const,
};

export const useSsoMe = (enabled = true) => useQuery({ queryKey: identityKeys.me, queryFn: identity.me, enabled, retry: false, staleTime: 30_000 });
export const useSsoConfig = (enabled = true) => useQuery({ queryKey: identityKeys.config, queryFn: identity.config, enabled, retry: false });
export const useSsoMappings = (enabled = true) => useQuery({ queryKey: identityKeys.mappings, queryFn: identity.mappings, enabled, retry: false });
export const useInvites = (enabled = true) => useQuery({ queryKey: identityKeys.invites, queryFn: identity.invites, enabled, retry: false });
export const useUserIdentityStatus = (enabled = true) => useQuery({ queryKey: identityKeys.userStatus, queryFn: identity.userStatus, enabled, retry: false, staleTime: 15_000 });
export const useAuthProviders = (enabled = true) => useQuery({ queryKey: identityKeys.providers, queryFn: identity.providers, enabled, retry: false, staleTime: 60_000 });
export const useInstructorSearch = (q: string, enabled = true, limit = 20) =>
  useQuery({ queryKey: identityKeys.instructors(q, limit), queryFn: () => identity.instructors(q, limit), enabled, retry: false, placeholderData: keepPreviousData, staleTime: 60_000 });

/** A mutation that refreshes the given identity / user queries on success. */
export function useIdentityMutation<TVars, TOut>(fn: (vars: TVars) => Promise<TOut>, invalidate: QueryKey[] = []) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      await Promise.all(invalidate.map((key) => qc.invalidateQueries({ queryKey: key })));
    },
  });
}

/* --------------------------------------------------------------------------------------- errors */

export interface ApiProblem {
  status: number;
  code: string | null;
  /** the backend's own text in the requested language, when it sent one */
  text: string | null;
}

/**
 * `{detail: {code, en, tr}}` (SSO), `{detail: {code, message, message_tr}}` (channels), `{detail: "…"}` or a
 * pydantic list → status, code and the text in `lang`.
 */
export function apiProblem(err: unknown, lang: "tr" | "en"): ApiProblem {
  if (!(err instanceof HttpError)) return { status: 0, code: null, text: null };
  let detail: unknown = err.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail) && "detail" in detail) detail = (detail as { detail: unknown }).detail;
  if (typeof detail === "string") return { status: err.status, code: null, text: detail };
  if (Array.isArray(detail)) {
    const msgs = detail.map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : "")).filter(Boolean);
    return { status: err.status, code: null, text: msgs.join("; ") || null };
  }
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    const code = typeof d.code === "string" ? d.code : null;
    const tr = typeof d.tr === "string" ? d.tr : typeof d.message_tr === "string" ? d.message_tr : null;
    const en = typeof d.en === "string" ? d.en : typeof d.message === "string" ? d.message : null;
    return { status: err.status, code, text: (lang === "tr" ? (tr ?? en) : (en ?? tr)) ?? null };
  }
  return { status: err.status, code: null, text: err.message || null };
}
