/**
 * Users › identity columns (docs/design/v2/sign-in.md §13): the status "dot + word", the sign-in method, the
 * "Kendi kaydı" tag and the chip filters, computed from `GET /auth/sso/admin/user-status` joined to the user list
 * client-side (the backend's contract, §14). Pure, so the rules are pinned by tests.
 */
import type { Invite, UserIdentityStatus } from "@/lib/api/identity";

export const SELF_SIGNUP_WINDOW_DAYS = 7;
const DAY = 86_400_000;

export type StatusTone = "feasible" | "pending" | "warning" | "neutral";
export type StatusWord = "active" | "invited" | "binding" | "inviteExpired" | "disabled";

export interface StatusView {
  tone: StatusTone;
  word: StatusWord;
  /** days left on a pending invite / binding (ceil, ≥ 0) */
  daysLeft: number | null;
  /** when an expired invite expired (ISO) */
  expiredAt: string | null;
}

/** `false` for a disabled account wins over every identity state (it cannot sign in at all). */
export function statusView(s: UserIdentityStatus | undefined, active: boolean, now: number = Date.now()): StatusView {
  if (!active) return { tone: "neutral", word: "disabled", daysLeft: null, expiredAt: null };
  const expires = s?.invite?.expires_at ? Date.parse(s.invite.expires_at) : NaN;
  const daysLeft = Number.isFinite(expires) ? Math.max(0, Math.ceil((expires - now) / DAY)) : null;
  switch (s?.status) {
    case "invited":
      return { tone: "pending", word: "invited", daysLeft, expiredAt: null };
    case "binding":
      return { tone: "pending", word: "binding", daysLeft, expiredAt: null };
    case "invite_expired":
      return { tone: "warning", word: "inviteExpired", daysLeft: null, expiredAt: s.invite?.expires_at ?? null };
    default:
      return { tone: "feasible", word: "active", daysLeft: null, expiredAt: null };
  }
}

export type MethodView = "microsoft" | "microsoftInvite" | "binding" | "local" | "ldap" | "none";

/** "Microsoft" · "Microsoft · davet" · "Yerel → Microsoft" (binding scheduled) · "Yerel" · "LDAP". */
export function methodView(s: UserIdentityStatus | undefined, authSource?: string | null): MethodView {
  if (!s) return authSource === "ldap" ? "ldap" : "local";
  if (s.status === "invited" || s.status === "invite_expired") return s.invite?.kind === "bind" ? "binding" : "microsoftInvite";
  if (s.status === "binding" || s.binding_pending) return "binding";
  if (s.auth_methods.includes("microsoft")) return "microsoft";
  if (s.auth_methods.includes("ldap") || authSource === "ldap") return "ldap";
  if (s.auth_methods.includes("local")) return "local";
  return "none";
}

/** "Kendi kaydı" while the self sign-up is at most 7 days old (§13). */
export function selfSignupRecent(s: UserIdentityStatus | undefined, now: number = Date.now()): boolean {
  const at = s?.self_signup_at ? Date.parse(s.self_signup_at) : NaN;
  return Number.isFinite(at) && now - at <= SELF_SIGNUP_WINDOW_DAYS * DAY;
}

export type IdentityFilter = "all" | "invited" | "self";
export type MethodFilter = "" | "microsoft" | "local" | "ldap" | "binding";

export function matchesIdentity(s: UserIdentityStatus | undefined, filter: IdentityFilter, method: MethodFilter, authSource: string | null | undefined, now: number = Date.now()): boolean {
  if (filter === "invited" && !(s?.status === "invited" || s?.status === "invite_expired")) return false;
  if (filter === "self" && !selfSignupRecent(s, now)) return false;
  if (method) {
    const m = methodView(s, authSource);
    if (method === "microsoft" && !(m === "microsoft" || m === "microsoftInvite")) return false;
    if (method === "binding" && m !== "binding") return false;
    if (method === "local" && m !== "local") return false;
    if (method === "ldap" && m !== "ldap") return false;
  }
  return true;
}

export interface IdentityCounts {
  invited: number;
  selfRecent: number;
}

export function identityCounts(map: Record<string, UserIdentityStatus> | undefined, now: number = Date.now()): IdentityCounts {
  let invited = 0;
  let selfRecent = 0;
  for (const s of Object.values(map ?? {})) {
    if (s.status === "invited") invited++;
    if (selfSignupRecent(s, now)) selfRecent++;
  }
  return { invited, selfRecent };
}

/**
 * Break-glass warning (§13): Microsoft on, password sign-in off for everyone, and no active administrator with a
 * local password. `break_glass` per user comes from the status map.
 */
export function breakGlassMissing(auth: { microsoft: { enabled: boolean }; local_enabled: boolean } | undefined, map: Record<string, UserIdentityStatus> | undefined): boolean {
  if (!auth || !map) return false;
  if (!auth.microsoft.enabled || auth.local_enabled) return false;
  return !Object.values(map).some((s) => s.break_glass);
}

/** The newest invite per user (renewals replace the token, so one row per user is expected). */
export function invitesByUser(list: readonly Invite[] | undefined): Map<number, Invite> {
  const out = new Map<number, Invite>();
  for (const inv of list ?? []) {
    const prev = out.get(inv.user_id);
    if (!prev || prev.id < inv.id) out.set(inv.user_id, inv);
  }
  return out;
}

/** Lower-cases and trims a typed address; `domainMismatch` when it is not on the institution's domain (§12). */
export function cleanInviteEmail(value: string, domainHint: string | null | undefined): { email: string; valid: boolean; domainMismatch: boolean } {
  const email = value.normalize("NFKC").trim().toLocaleLowerCase("en-US");
  const valid = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email);
  const domain = (domainHint ?? "").trim().toLocaleLowerCase("en-US").replace(/^@/, "");
  const at = email.split("@")[1] ?? "";
  const domainMismatch = valid && !!domain && at !== domain && !at.endsWith(`.${domain}`);
  return { email, valid, domainMismatch };
}
