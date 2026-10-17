/**
 * The sign-in page's URL contract and doors (docs/design/v2/sign-in.md §4.2, §6, §12, §14). Pure functions: the
 * server page and the client components share them, and the tests pin the contract.
 */

import { ADMIN_SECTIONS } from "@/lib/permissions";

/** SSO callback codes the page renders (§6.3, §14). Anything else renders `failed` (no enumeration, §15 #16).
 *  `not_enabled` (T-R1-35 / T-R1-09): Microsoft sign-in is switched off: a state, shown without a support code. */
export const SSO_ERROR_CODES = ["tenant", "cancelled", "failed", "unavailable", "not_enabled", "signup_closed", "invite_expired", "invite_invalid", "invite_mismatch", "domain", "invite_provider"] as const;
export type SsoErrorCode = (typeof SSO_ERROR_CODES)[number];

/** `/profile?error=` codes after a profile link (§14): the sign-in codes plus `already_linked`. */
export const PROFILE_SSO_CODES = ["already_linked", "failed", "cancelled", "tenant", "unavailable"] as const;
export type ProfileSsoCode = (typeof PROFILE_SSO_CODES)[number];

export const REASONS = ["expired", "signed_out", "password"] as const;
export type Reason = (typeof REASONS)[number];

export const START_PATH = "/api/v1/auth/sso/entra/start";
/** remembered sign-in method (R3 "You used email to log in last time"): read on the server, so no flash */
export const LAST_METHOD_COOKIE = "smartsched_last_signin";
/** the one-time welcome flag handed from /login/sso to /welcome (sessionStorage) */
export const WELCOME_KEY = "smartsched.welcome";

type Raw = string | string[] | null | undefined;
const first = (v: Raw): string | null => (Array.isArray(v) ? (v[0] ?? null) : (v ?? null));

/** A same-origin path (`/timetable?week=3`), never another origin (`//evil`, `/\evil`, `https://…`). */
export function safeNext(value: Raw): string | null {
  const v = first(value)?.trim();
  if (!v || !v.startsWith("/") || v.startsWith("//") || v.includes("\\") || v.includes("://") || v.length > 255) return null;
  for (const ch of v) {
    const c = ch.charCodeAt(0);
    if (c < 32 || c === 127) return null;
  }
  // back to the sign-in pages would loop
  if (v === "/login" || v.startsWith("/login?") || v.startsWith("/login/")) return null;
  return v;
}

/** `null` = no error; a known code as is; any other non-empty value = `failed`. */
export function normalizeSsoError(value: Raw): SsoErrorCode | null {
  const v = first(value)?.trim();
  if (!v) return null;
  return (SSO_ERROR_CODES as readonly string[]).includes(v) ? (v as SsoErrorCode) : "failed";
}

export function normalizeProfileSsoError(value: Raw): ProfileSsoCode | null {
  const v = first(value)?.trim();
  if (!v) return null;
  return (PROFILE_SSO_CODES as readonly string[]).includes(v) ? (v as ProfileSsoCode) : "failed";
}

/** The support code of a `failed` error: the audit row id (`S-123`) or a short code (`7F3A-21C`); else null. */
export function safeRef(value: Raw): string | null {
  const v = first(value)?.trim() ?? "";
  return /^[A-Za-z0-9][A-Za-z0-9-]{0,31}$/.test(v) ? v : null;
}

/** Masked addresses echoed by the callback (`ay•••@uni.edu.tr`); plain text, bounded. */
function safeMasked(value: Raw): string | null {
  const v = first(value)?.trim() ?? "";
  if (!v || v.length > 120 || !v.includes("@")) return null;
  for (const ch of v) {
    const c = ch.charCodeAt(0);
    if (c < 32 || c === 127) return null;
  }
  return v;
}

function safeToken(value: Raw): string | null {
  const v = first(value)?.trim() ?? "";
  return /^[A-Za-z0-9_-]{8,256}$/.test(v) ? v : null;
}

export interface SignInParams {
  next: string | null;
  reason: Reason | null;
  error: SsoErrorCode | null;
  ref: string | null;
  invite: string | null;
  /** `?method=local`: open door 2 on load; the only way to the form when `local_enabled = false` */
  methodLocal: boolean;
  invitedMasked: string | null;
  signedIn: string | null;
}

export function readSignInParams(sp: URLSearchParams | Record<string, Raw>): SignInParams {
  const get = (k: string): Raw => (sp instanceof URLSearchParams ? sp.get(k) : sp[k]);
  const reason = first(get("reason"));
  return {
    next: safeNext(get("next")),
    reason: reason && (REASONS as readonly string[]).includes(reason) ? (reason as Reason) : null,
    error: normalizeSsoError(get("error")),
    ref: safeRef(get("ref")),
    invite: safeToken(get("invite")),
    methodLocal: first(get("method")) === "local",
    invitedMasked: safeMasked(get("invited_masked")),
    signedIn: safeMasked(get("signed_in")),
  };
}

/** The Microsoft start URL: a real navigation (`<a href>`, §4.2), never `fetch`. */
export function startUrl(opts: { base?: string | null; next?: string | null; invite?: string | null; prompt?: "select_account" | "login" | null; loginHint?: string | null } = {}): string {
  const base = opts.base && opts.base.startsWith("/") && !opts.base.startsWith("//") ? opts.base : START_PATH;
  const q = new URLSearchParams();
  if (opts.next) q.set("next", opts.next);
  if (opts.invite) q.set("invite", opts.invite);
  if (opts.prompt) q.set("prompt", opts.prompt);
  if (opts.loginHint) q.set("login_hint", opts.loginHint);
  const qs = q.toString();
  return qs ? `${base}?${qs}` : base;
}

/**
 * Where a signed-in person lands without `next` (the login form's rule, T-R1-09 / R1-M-21): the first page their
 * permissions let them use. Planners the dashboard; people who can book, the bookings grid; approvers who cannot
 * book, their inbox; a user administrator (setup.users) the user list, any other setup right its own section
 * (lib/permissions ADMIN_SECTIONS order); room.view alone the read-only grid; nobody gets a grid of locks or a
 * 403 toast on arrival. No permission list (an old backend) keeps the dashboard.
 */
export function homeFor(permissions: readonly string[] | null | undefined): string {
  if (!permissions) return "/dashboard";
  const has = (...p: string[]) => p.some((x) => permissions.includes(x));
  if (has("planning.view")) return "/dashboard";
  if (has("book_single.create", "book_recur.create")) return "/bookings";
  if (has("approvals.decide")) return "/approvals";
  const section = ADMIN_SECTIONS.find((s) => has(...s.permission));
  if (section) return section.href;
  if (has("room.view")) return "/bookings";
  return "/profile";
}

/** The invite banner's input: valid (from `GET /auth/sso/invites/{token}`), refused (404 / 410) or unknown. */
export type InviteState =
  | { state: "valid"; token: string; inviter: string | null; role: string | null; masked: string | null; loginHint: string; daysLeft: number }
  | { state: "invalid" | "expired"; token: string }
  | null;

export interface Doors {
  /** the Microsoft button (door 1) */
  microsoft: boolean;
  /** the disclosure row of door 2 */
  disclosure: boolean;
  /** door 2 open on first paint */
  formOpenInitially: boolean;
  /** the form is the page's primary action (Microsoft off or unreachable) */
  formPrimary: boolean;
  /** "Parolamı unuttum" (local accounts exist) */
  resetLink: boolean;
  /** hint 2: the first sign-in creates an account (self sign-up on) */
  selfSignup: boolean;
  /** the backend could not be reached when the page rendered */
  offline: boolean;
}

export interface DoorInput {
  /** `null`: `GET /org/public` failed (offline) */
  auth: { microsoft: { enabled: boolean; self_signup: boolean }; local_enabled: boolean } | null | undefined;
  reachable: boolean;
  params: Pick<SignInParams, "methodLocal">;
  invite: InviteState;
  lastMethodLocal: boolean;
}

/** §4.3, §6.5, §12: which doors render, decided once on the server (no flash). */
export function doorsFor({ auth, reachable, params, invite, lastMethodLocal }: DoorInput): Doors {
  if (!reachable) return { microsoft: false, disclosure: false, formOpenInitially: true, formPrimary: true, resetLink: true, selfSignup: false, offline: true };
  const ms = Boolean(auth?.microsoft.enabled);
  const localEnabled = auth ? auth.local_enabled : true;
  if (!ms) return { microsoft: false, disclosure: false, formOpenInitially: true, formPrimary: true, resetLink: localEnabled, selfSignup: false, offline: false };
  const invited = invite?.state === "valid";
  const disclosure = !invited && (localEnabled || params.methodLocal);
  return {
    microsoft: true,
    disclosure,
    formOpenInitially: disclosure && (params.methodLocal || lastMethodLocal),
    formPrimary: false,
    resetLink: localEnabled,
    selfSignup: Boolean(auth?.microsoft.self_signup),
    offline: false,
  };
}

/** Minutes to show for a 429 (`Retry-After` seconds), at least 1. */
export function retryMinutes(retryAfter: string | null | undefined): number {
  const s = Number(retryAfter);
  return Number.isFinite(s) && s > 0 ? Math.max(1, Math.ceil(s / 60)) : 5;
}

export type WelcomeKind = "self" | "invited" | "bound";
export interface WelcomeFlag {
  kind: WelcomeKind;
  inviter: string | null;
  next: string | null;
}

export function parseWelcomeFlag(raw: string | null | undefined): WelcomeFlag | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<WelcomeFlag>;
    if (v.kind !== "self" && v.kind !== "invited" && v.kind !== "bound") return null;
    return { kind: v.kind, inviter: typeof v.inviter === "string" ? v.inviter : null, next: safeNext(typeof v.next === "string" ? v.next : null) };
  } catch {
    return null;
  }
}

/** `/welcome`, `/welcome?invited=1`, `/welcome?bound=1` (§14). */
export function welcomePath(kind: WelcomeKind): string {
  return kind === "invited" ? "/welcome?invited=1" : kind === "bound" ? "/welcome?bound=1" : "/welcome";
}
