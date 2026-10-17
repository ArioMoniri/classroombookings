import "server-only";
import { cookies } from "next/headers";
import { OrgPublicAuth, PublicInvite, type OrgPublicAuth as OrgPublicAuthT } from "@/lib/api/identity";
import { LAST_METHOD_COOKIE, type InviteState } from "@/components/auth/signin-model";
import { backendBaseUrl } from "./config";

/**
 * The login page's server data (sign-in.md §4.3): `GET /org/public` (with `auth`) and, for `?invite=`, the banner
 * (`GET /auth/sso/invites/{token}`), read before the first paint so the doors never swap after hydration.
 * A failed `/org/public` returns `null`: the page then renders door 2 open with the offline notice.
 */
async function get(path: string): Promise<Response | null> {
  try {
    return await fetch(`${backendBaseUrl()}/api/v1${path}`, { cache: "no-store", headers: { accept: "application/json" }, signal: AbortSignal.timeout(4000) });
  } catch {
    return null;
  }
}

export async function loadOrgPublic(): Promise<OrgPublicAuthT | null> {
  const res = await get("/org/public");
  if (!res?.ok) return null;
  const parsed = OrgPublicAuth.safeParse(await res.json().catch(() => null));
  return parsed.success ? parsed.data : null;
}

export async function loadInvite(token: string | null): Promise<InviteState> {
  if (!token) return null;
  const res = await get(`/auth/sso/invites/${encodeURIComponent(token)}`);
  if (!res) return null;
  if (res.status === 410) return { state: "expired", token };
  if (res.status === 404) return { state: "invalid", token };
  if (!res.ok) return null;
  const parsed = PublicInvite.safeParse(await res.json().catch(() => null));
  if (!parsed.success) return null;
  const d = parsed.data;
  return { state: "valid", token, inviter: d.inviter_name ?? null, role: d.role_name ?? null, masked: d.invited_masked ?? null, loginHint: d.login_hint, daysLeft: d.days_left };
}

/** `local` when the last sign-in on this browser used the password form (opens door 2, §4.1 item 5). */
export async function lastMethodLocal(): Promise<boolean> {
  return (await cookies()).get(LAST_METHOD_COOKIE)?.value === "local";
}
