/**
 * Two-step sign-in, passkeys, trusted devices, the admin reset and the policy (AU-B: smartsched/backend
 * app/api/v1/mfa.py + app/services/mfa.py; UX docs/design/v3/auth.md; AUX-01). Hand-written against the backend's
 * return values (the routes answer `dict[str, Any]`, so the OpenAPI has no response models); the paths are pinned by
 * auth-security.test.ts against the generated OpenAPI subset `__fixtures__/au-b-openapi.json`.
 *
 * Two transports:
 * - signed-in calls go through the generic proxy (`request()`, `/api/v1/…`);
 * - the sign-in steps (password → second step / enrolment, passkey-only sign-in) go through the route handler
 *   `/api/auth/mfa/<step>` (app/api/auth/mfa/[step]/route.ts), which keeps the challenge token and the
 *   trusted-device token in httpOnly cookies and stores the session cookie, so neither token reaches the page.
 *
 * Refusals are `{detail: {code, message, message_en, message_tr, …}}`; `mfaErrorCode` / `mfaErrorText` read them.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { HttpError, request } from "./client";
import { refusalBody } from "./error-text";

/* ------------------------------------------------------------------------------------------------ helpers */

/** The backend writes naive UTC datetimes (`2026-10-18T09:00:00`): read them as UTC. */
export function utcDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const v = /[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "ay•••@ornek.edu.tr" / "fa•••" (§5.1 account line): never the full identifier on a shared screen. */
export function maskIdentifier(identifier: string): string {
  const id = identifier.trim();
  const at = id.indexOf("@");
  const local = at >= 0 ? id.slice(0, at) : id;
  const keep = local.length <= 2 ? 1 : 2;
  return `${local.slice(0, keep)}•••${at >= 0 ? id.slice(at) : ""}`;
}

/** §5.3: ignore case, spaces and hyphens, read O as 0 and I/L as 1, at most 16 characters, grouped by 4. */
export function normalizeRecoveryCode(raw: string): string {
  const clean = raw
    .toUpperCase()
    .replace(/[\s-]+/g, "")
    .replace(/O/g, "0")
    .replace(/[IL]/g, "1")
    .replace(/[^0-9A-Z]/g, "")
    .slice(0, 16);
  return clean.replace(/(.{4})(?=.)/g, "$1-");
}

export function mfaErrorCode(e: unknown): string | null {
  const b = refusalBody(e);
  return typeof b?.code === "string" ? b.code : null;
}

/** The server's sentence in the reader's language, or null. */
export function mfaErrorText(e: unknown, locale: string): string | null {
  const b = refusalBody(e);
  const v = locale === "tr" ? b?.message_tr : (b?.message_en ?? b?.message);
  return typeof v === "string" && v.trim() ? v : null;
}

/** `Retry-After` seconds of a refusal (the lockout carries it in the body as `retry_after` too). */
export function retryAfterSeconds(e: unknown): number | null {
  const b = refusalBody(e);
  return typeof b?.retry_after === "number" ? b.retry_after : null;
}

/* ------------------------------------------------------------------------------------------------ schemas */

/** `GET /org/public` → `passkeys` (ask A1e): decided on the server before the first paint. */
export const OrgPasskeys = z.object({ enabled: z.boolean().default(false), sign_in: z.boolean().default(false), trusted_device_days: z.number().default(30) });
export type OrgPasskeys = z.infer<typeof OrgPasskeys>;

const ts = z.string().nullish();

export const PasskeyRow = z.object({
  id: z.number(),
  name: z.string(),
  transports: z.array(z.string()).default([]),
  backed_up: z.boolean().default(false),
  created_at: z.string(),
  last_used_at: ts,
  /** ask AU-B: `passkey_out` carries the AAGUID for the provider icon (§6.4); optional until then */
  aaguid: z.string().nullish(),
});
export type PasskeyRow = z.infer<typeof PasskeyRow>;

export const TrustedDevice = z.object({ id: z.number(), label: z.string().default(""), created_at: z.string(), expires_at: z.string(), last_used_at: ts });
export type TrustedDevice = z.infer<typeof TrustedDevice>;

export const MFA_POLICIES = ["off", "optional", "required_for_roles"] as const;
export type MfaPolicyValue = (typeof MFA_POLICIES)[number];
export const MFA_ROLES = ["ADMIN", "PLANNER", "TEACHER", "VIEWER", "CUSTOM"] as const;
export type MfaRole = (typeof MFA_ROLES)[number];

export const MfaPolicy = z.object({
  mfa_policy: z.enum(MFA_POLICIES).default("optional"),
  mfa_roles: z.array(z.string()).default(["ADMIN"]),
  mfa_grace_days: z.number().default(14),
  passkeys_enabled: z.boolean().default(true),
  passkey_first_factor: z.boolean().default(false),
  /** "Bu cihazı hatırla": 0 (off), 7 or 30 days (ask A1d) */
  trusted_device_days: z.number().default(30),
});
export type MfaPolicy = z.infer<typeof MfaPolicy>;

export const AccountType = z.enum(["local", "ldap", "mixed", "sso"]);
export type AccountType = z.infer<typeof AccountType>;

export const MfaStatus = z.object({
  available: z.boolean(),
  reason: z.string().nullish(),
  account_type: AccountType,
  policy: MfaPolicy,
  passkeys_available: z.boolean().default(false),
  required: z.boolean().default(false),
  grace_until: ts,
  totp: z.object({ enabled: z.boolean(), enabled_at: ts }),
  recovery_codes: z.object({ remaining: z.number(), total: z.number() }),
  passkeys: z.array(PasskeyRow).default([]),
  trusted_devices: z.array(TrustedDevice).default([]),
  locked_until: ts,
});
export type MfaStatus = z.infer<typeof MfaStatus>;

export const TotpStart = z.object({
  secret: z.string(),
  otpauth_uri: z.string(),
  issuer: z.string(),
  account: z.string(),
  digits: z.number().default(6),
  period: z.number().default(30),
  algorithm: z.string().default("SHA1"),
  expires_in: z.number().default(900),
});
export type TotpStart = z.infer<typeof TotpStart>;

export const RecoveryCodesOut = z.object({ recovery_codes: z.array(z.string()) });
export const TotpConfirmOut = z.object({ enabled: z.literal(true), recovery_codes: z.array(z.string()) });
export const DisableOut = z.object({ disabled: z.boolean(), passkeys_remaining: z.number().default(0) });
export const RegisterOptionsOut = z.object({ challenge_token: z.string().optional(), options: z.record(z.string(), z.unknown()) });
export type RegisterOptionsOut = z.infer<typeof RegisterOptionsOut>;
export const RegisterOut = z.object({ passkey: PasskeyRow, recovery_codes: z.array(z.string()).optional() });

export const AdminMfa = z.object({
  user_id: z.number(),
  account_type: AccountType,
  totp_enabled: z.boolean(),
  totp_enabled_at: ts,
  recovery_codes_remaining: z.number(),
  passkeys: z.array(z.object({ name: z.string(), created_at: z.string(), last_used_at: ts })).default([]),
  trusted_devices: z.number().default(0),
  locked_until: ts,
  can_reset_mfa: z.boolean(),
  can_send_reset_link: z.boolean(),
});
export type AdminMfa = z.infer<typeof AdminMfa>;

export const IDENTITY_CHECKS = ["in_person", "video_call", "phone_callback", "other"] as const;
export type IdentityCheck = (typeof IDENTITY_CHECKS)[number];
export const AdminResetOut = z.object({ user_id: z.number(), removed: z.record(z.string(), z.unknown()).optional(), signed_out: z.boolean().optional() });
export const ResetLinkOut = z.object({ user_id: z.number(), emailed: z.boolean(), expires_at: ts });

/** Answers of the sign-in route handler (`/api/auth/mfa/<step>`); tokens never appear here. */
export const SignInStepOut = z.object({
  status: z.enum(["signed_in", "mfa", "setup", "none"]),
  user: z.unknown().optional(),
  password_change_required: z.boolean().optional(),
  methods: z.array(z.string()).optional(),
  setup_methods: z.array(z.string()).optional(),
  masked: z.string().nullish(),
  grace_until: ts,
  /** grace still running: signed in, with the enrolment notice offered (§5.6) */
  setup_due: z.boolean().optional(),
  recovery_codes_remaining: z.number().optional(),
  recovery_codes: z.array(z.string()).optional(),
  remember_days: z.number().optional(),
  options: z.record(z.string(), z.unknown()).optional(),
});
export type SignInStepOut = z.infer<typeof SignInStepOut>;

/* -------------------------------------------------------------------------------------------- the paths */

/** Every backend route this module reaches (directly or through the route handler); pinned by the test. */
export const AUTH_SECURITY_PATHS: ReadonlyArray<readonly ["GET" | "POST" | "PUT" | "PATCH" | "DELETE", string]> = [
  ["POST", "/auth/login"],
  ["GET", "/auth/mfa"],
  ["POST", "/auth/mfa/totp/start"],
  ["POST", "/auth/mfa/totp/confirm"],
  ["POST", "/auth/mfa/disable"],
  ["POST", "/auth/mfa/recovery-codes"],
  ["POST", "/auth/mfa/verify"],
  ["POST", "/auth/mfa/passkey/options"],
  ["POST", "/auth/mfa/passkey/verify"],
  ["POST", "/auth/mfa/setup/totp/start"],
  ["POST", "/auth/mfa/setup/totp/confirm"],
  ["POST", "/auth/mfa/setup/passkey/options"],
  ["POST", "/auth/mfa/setup/passkey/verify"],
  ["GET", "/auth/passkeys"],
  ["POST", "/auth/passkeys/register/options"],
  ["POST", "/auth/passkeys/register/verify"],
  ["PATCH", "/auth/passkeys/{passkey_id}"],
  ["POST", "/auth/passkeys/{passkey_id}/remove"],
  ["POST", "/auth/passkey/options"],
  ["POST", "/auth/passkey/verify"],
  ["GET", "/auth/trusted-devices"],
  ["DELETE", "/auth/trusted-devices/{device_id}"],
  ["DELETE", "/auth/trusted-devices"],
  ["GET", "/admin/auth/mfa-policy"],
  ["PUT", "/admin/auth/mfa-policy"],
  ["GET", "/admin/users/{user_id}/mfa"],
  ["POST", "/admin/users/{user_id}/mfa/reset"],
  ["POST", "/admin/users/{user_id}/password-reset-link"],
];

/* ------------------------------------------------------------------------------- sign-in steps (handler) */

export type SignInStep =
  | "login"
  | "state"
  | "verify"
  | "passkey-options"
  | "passkey-verify"
  | "signin-passkey-options"
  | "signin-passkey-verify"
  | "setup-totp-start"
  | "setup-totp-confirm"
  | "setup-passkey-options"
  | "setup-passkey-verify"
  | "cancel";

export const STEP_PREFIX = "/api/auth/mfa";

/** One sign-in step through the route handler. Throws an `HttpError` (status 0 offline) like `request()`. */
export async function signInStep<T = SignInStepOut>(step: SignInStep, body?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${STEP_PREFIX}/${step}`, {
      method: step === "state" ? "GET" : "POST",
      headers: { Accept: "application/json", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
      signal,
    });
  } catch (e) {
    throw new HttpError(0, e instanceof Error ? e.message : "Network error");
  }
  const json: unknown = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new HttpError(res.status, `${res.status}`, json, undefined);
  return json as T;
}

/* --------------------------------------------------------------------------------------- signed-in calls */

export const authSecurityKeys = {
  status: ["auth-security", "status"] as const,
  policy: ["auth-security", "policy"] as const,
  admin: (userId: number) => ["auth-security", "admin", userId] as const,
};

export const authSecurity = {
  status: () => request("/auth/mfa", { schema: MfaStatus, silent: true }),
  totpStart: (password?: string) => request("/auth/mfa/totp/start", { method: "POST", body: { password: password ?? "" }, schema: TotpStart, silent: true }),
  totpConfirm: (code: string) => request("/auth/mfa/totp/confirm", { method: "POST", body: { code }, schema: TotpConfirmOut, silent: true }),
  disable: (code: string, password?: string) => request("/auth/mfa/disable", { method: "POST", body: { password: password ?? "", code }, schema: DisableOut, silent: true }),
  regenerateCodes: (password?: string) => request("/auth/mfa/recovery-codes", { method: "POST", body: { password: password ?? "" }, schema: RecoveryCodesOut, silent: true }),
  passkeys: () => request("/auth/passkeys", { schema: z.array(PasskeyRow), silent: true }),
  registerOptions: (password?: string) => request("/auth/passkeys/register/options", { method: "POST", body: { password: password ?? "" }, schema: RegisterOptionsOut, silent: true }),
  registerVerify: (challenge_token: string, credential: unknown, name?: string | null) =>
    request("/auth/passkeys/register/verify", { method: "POST", body: { challenge_token, credential, name: name ?? null }, schema: RegisterOut, silent: true }),
  renamePasskey: (id: number, name: string) => request(`/auth/passkeys/${id}`, { method: "PATCH", body: { name }, schema: PasskeyRow, silent: true }),
  removePasskey: (id: number, password?: string) => request<void>(`/auth/passkeys/${id}/remove`, { method: "POST", body: { password: password ?? "" }, silent: true }),
  devices: () => request("/auth/trusted-devices", { schema: z.array(TrustedDevice), silent: true }),
  forgetDevice: (id: number) => request<void>(`/auth/trusted-devices/${id}`, { method: "DELETE", silent: true }),
  forgetAllDevices: () => request("/auth/trusted-devices", { method: "DELETE", schema: z.object({ revoked: z.number() }), silent: true }),
  policy: () => request("/admin/auth/mfa-policy", { schema: MfaPolicy, silent: true }),
  savePolicy: (body: Partial<MfaPolicy>) => request("/admin/auth/mfa-policy", { method: "PUT", body, schema: MfaPolicy, silent: true }),
  adminSummary: (userId: number) => request(`/admin/users/${userId}/mfa`, { schema: AdminMfa, silent: true }),
  adminReset: (userId: number, body: { reason: string; identity_check: IdentityCheck; keep_passkeys: boolean }) =>
    request(`/admin/users/${userId}/mfa/reset`, { method: "POST", body, schema: AdminResetOut, silent: true }),
  adminResetLink: (userId: number, reason?: string | null) => request(`/admin/users/${userId}/password-reset-link`, { method: "POST", body: { reason: reason ?? null }, schema: ResetLinkOut, silent: true }),
};

export function useMfaStatus(enabled = true) {
  return useQuery({ queryKey: authSecurityKeys.status, queryFn: authSecurity.status, enabled, staleTime: 30_000, retry: false });
}

export function useMfaPolicy(enabled = true) {
  return useQuery({ queryKey: authSecurityKeys.policy, queryFn: authSecurity.policy, enabled, retry: false });
}

export function useSaveMfaPolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: authSecurity.savePolicy,
    onSuccess: (data) => {
      qc.setQueryData(authSecurityKeys.policy, data);
      void qc.invalidateQueries({ queryKey: authSecurityKeys.status });
    },
  });
}

export function useAdminMfa(userId: number | null, enabled = true) {
  return useQuery({ queryKey: authSecurityKeys.admin(userId ?? 0), queryFn: () => authSecurity.adminSummary(userId!), enabled: enabled && userId != null, retry: false, staleTime: 15_000 });
}

/** Refresh the own status after any change in Profil › Giriş ve güvenlik. */
export function useInvalidateMfa() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: authSecurityKeys.status });
}
