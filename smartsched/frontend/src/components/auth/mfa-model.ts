/**
 * Pure rules of the two-step sign-in (docs/design/v3/auth.md §4.3, §5, §5.6; AU-B API.md §1–§7). The route handler
 * (app/api/auth/mfa/[step]/route.ts) and the pages share them; tests pin them.
 */

export const MFA_COOKIE = "ss_mfa";
export const PASSKEY_COOKIE = "ss_pk";
export const TRUSTED_COOKIE = "ss_td";

/** What the httpOnly `ss_mfa` cookie holds between the password and the second step (never readable by the page). */
export interface MfaPending {
  /** `mfa`: second factor; `setup`: the policy requires enrolment before a session */
  k: "mfa" | "setup";
  /** the challenge or setup token */
  t: string;
  /** second-step methods (`totp`, `recovery`, `passkey`) or the setup methods */
  m: string[];
  /** masked identifier for the account line */
  a: string | null;
  /** grace end (ISO), setup only */
  g?: string | null;
  /** where to go afterwards (a safe same-origin path) */
  n?: string | null;
}

export function encodePending(p: MfaPending): string {
  return Buffer.from(JSON.stringify(p), "utf8").toString("base64url");
}

export function decodePending(raw: string | null | undefined): MfaPending | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(Buffer.from(raw, "base64url").toString("utf8")) as Partial<MfaPending>;
    if ((v.k !== "mfa" && v.k !== "setup") || typeof v.t !== "string" || !v.t) return null;
    return { k: v.k, t: v.t, m: Array.isArray(v.m) ? v.m.filter((x): x is string => typeof x === "string") : [], a: typeof v.a === "string" ? v.a : null, g: typeof v.g === "string" ? v.g : null, n: typeof v.n === "string" ? v.n : null };
  } catch {
    return null;
  }
}

/** The backend's TokenOut (`POST /auth/login`, the verify routes, `session` of reset / invite). */
export interface TokenAnswer {
  access_token?: string | null;
  expires_in?: number;
  password_change_required?: boolean;
  mfa_required?: boolean;
  mfa_methods?: string[] | null;
  challenge_token?: string | null;
  challenge_expires_in?: number | null;
  mfa_setup_required?: boolean;
  mfa_setup_methods?: string[] | null;
  mfa_grace_until?: string | null;
  trusted_device_token?: string | null;
  trusted_device_days?: number | null;
  recovery_codes_remaining?: number | null;
}

export type LoginOutcome =
  | { kind: "session"; token: string; expiresIn: number; mustChangePassword: boolean; setupDue: boolean; graceUntil: string | null; setupMethods: string[] }
  | { kind: "mfa"; challenge: string; expiresIn: number; methods: string[] }
  | { kind: "setup"; challenge: string; expiresIn: number; methods: string[]; graceUntil: string | null }
  | { kind: "invalid" };

/** §1 of API.md: a session, a second step, an enrolment, or a malformed answer. */
export function classifyToken(d: TokenAnswer | null | undefined): LoginOutcome {
  if (!d) return { kind: "invalid" };
  if (d.access_token) {
    return {
      kind: "session",
      token: d.access_token,
      expiresIn: typeof d.expires_in === "number" && d.expires_in > 0 ? Math.floor(d.expires_in) : 0,
      mustChangePassword: Boolean(d.password_change_required),
      setupDue: Boolean(d.mfa_setup_required),
      graceUntil: d.mfa_grace_until ?? null,
      setupMethods: d.mfa_setup_methods ?? [],
    };
  }
  const exp = typeof d.challenge_expires_in === "number" && d.challenge_expires_in > 0 ? Math.floor(d.challenge_expires_in) : 300;
  if (d.mfa_required && d.challenge_token) return { kind: "mfa", challenge: d.challenge_token, expiresIn: exp, methods: d.mfa_methods ?? ["totp"] };
  if (d.mfa_setup_required && d.challenge_token) return { kind: "setup", challenge: d.challenge_token, expiresIn: Math.max(exp, 900), methods: d.mfa_setup_methods ?? ["totp"], graceUntil: d.mfa_grace_until ?? null };
  return { kind: "invalid" };
}

/** Refusal codes after which the challenge is gone: back to /login with a notice (§5.4). */
export function endsChallenge(status: number, code: string | null): "tooMany" | "expired" | "locked" | null {
  if (status === 429 || code === "mfa_locked") return "locked";
  if (code === "challenge_expired") return "expired";
  if (code === "too_many_attempts") return "tooMany";
  return null;
}

/** `/login` notice codes the second step sends people back with (`?mfa=`). */
export const MFA_NOTICES = ["tooMany", "expired", "locked"] as const;
export type MfaNotice = (typeof MFA_NOTICES)[number];

export function readMfaNotice(v: string | string[] | null | undefined): MfaNotice | null {
  const s = Array.isArray(v) ? v[0] : v;
  return s && (MFA_NOTICES as readonly string[]).includes(s) ? (s as MfaNotice) : null;
}

/** Whole days left until `until` (at least 0), counted from `now`. */
export function daysLeft(until: string | null | undefined, now: number = Date.now()): number {
  if (!until) return 0;
  const v = /[zZ]|[+-]\d\d:?\d\d$/.test(until) ? until : `${until}Z`;
  const t = new Date(v).getTime();
  if (Number.isNaN(t)) return 0;
  return Math.max(0, Math.ceil((t - now) / 86_400_000));
}

/** The second-step view to open first (§5.2): the app code when the account has it, else the passkey button. */
export function firstMethod(methods: readonly string[]): "totp" | "passkey" | "recovery" {
  if (methods.includes("totp")) return "totp";
  if (methods.includes("passkey")) return "passkey";
  return "recovery";
}

/** The recovery-code toast offers "Yeni kodlar oluştur" at 3 or fewer (§5.3, AU-B §4). */
export const LOW_CODES = 3;
