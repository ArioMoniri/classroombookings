/**
 * Same-origin proxy for the FastAPI backend (`/api/v1/*` → `${NEXT_PUBLIC_API_URL}/api/v1/*`).
 * - attaches `Authorization: Bearer <jwt>` from the httpOnly cookie
 * - `auth/login` and `auth/sso/exchange` (the Microsoft sign-in ticket) store the JWT in the cookie and return the
 *   user (plus the exchange's `next` / `welcome` / `inviter_name`), never the token
 * - forwards the client address from nginx (`x-forwarded-for`, `x-real-ip`; docs/SECURITY.md F3)
 * - redirects pass through (`auth/sso/entra/start` → Microsoft, `…/callback` → the panel), with `Location`
 * There is no mock mode: every request goes to the real backend.
 */
import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";
import { AUTH_COOKIE, COOKIE_MAX_AGE, backendBaseUrl } from "@/lib/server/config";
import { TRUSTED_COOKIE, type TokenAnswer } from "@/components/auth/mfa-model";
import { maskIdentifier } from "@/lib/api/auth-security";
import { settle } from "@/lib/server/mfa-session";

/** AU-17 (AU-B API.md §1–§7): answers that carry a session after a second step / enrolment / reset / invite. The
 *  page's own sign-in steps go through app/api/auth/mfa/[step]; these keep direct callers working the same way. */
const SESSION_AFTER = new Set(["auth/mfa/verify", "auth/mfa/passkey/verify", "auth/passkey/verify", "auth/mfa/setup/totp/confirm", "auth/mfa/setup/passkey/verify"]);
const NESTED_SESSION = (segment: string) => segment === "auth/password-reset/confirm" || /^auth\/sso\/invites\/[^/]+\/password$/.test(segment);

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path: string[] }> };

async function resolve(request: Request): Promise<Response> {
  try {
    return await fetch(request, { redirect: "manual" });
  } catch (e) {
    return new Response(JSON.stringify({ detail: `Backend unreachable: ${e instanceof Error ? e.message : "unknown"}` }), { status: 502, headers: { "Content-Type": "application/json" } });
  }
}

async function handle(req: NextRequest, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  const segment = path.join("/");
  const url = new URL(`${backendBaseUrl()}/api/v1/${segment}`);
  url.search = req.nextUrl.search;

  const jar = await cookies();
  const token = jar.get(AUTH_COOKIE)?.value;

  const headers = new Headers();
  // x-forwarded-for / x-real-ip: the client address nginx wrote ($remote_addr), so the backend's per-address
  // sign-in caps count the browser and not this container (docs/SECURITY.md F3). The backend believes them only
  // from a proxy hop (app/core/security_http.py client_address); Next itself sets x-forwarded-for to the socket
  // peer when nothing in front of it did.
  // origin: the passkey ceremonies check it when no public URL is set (AU-B passkeys.relying_party); user-agent: the
  // device label of the security e-mails and the remembered devices
  for (const name of ["content-type", "accept", "accept-language", "x-forwarded-for", "x-real-ip", "origin", "user-agent"]) {
    const v = req.headers.get(name);
    if (v) headers.set(name, v);
  }
  if (token) headers.set("authorization", `Bearer ${token}`);
  // "Bu cihazı hatırla" (AU-B §5): the remembered-device token lives in an httpOnly cookie, sent only to the password step
  const trusted = jar.get(TRUSTED_COOKIE)?.value;
  if (segment === "auth/login" && trusted) headers.set("x-trusted-device", trusted);

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const raw = hasBody ? await req.arrayBuffer() : undefined;
  const upstreamReq = new Request(url, {
    method: req.method,
    headers,
    body: raw,
    redirect: "manual",
  });
  const upstream = await resolve(upstreamReq);

  if (segment === "auth/login" || segment === "auth/sso/exchange") {
    if (!upstream.ok) return passthrough(upstream);
    const data = (await upstream.json()) as TokenAnswer & { user?: unknown; next?: string | null; welcome?: string | null; inviter_name?: string | null; idp_mfa_missing?: boolean; idp_mfa_message_tr?: string | null; idp_mfa_message_en?: string | null };
    if (!data.access_token) {
      // AU-17: a second step or the enrolment the policy requires: the challenge goes into the httpOnly `ss_mfa`
      // cookie (the /login/verify and /login/setup-2fa pages read it), the page gets the methods, never the token
      if (segment === "auth/login" && (data.mfa_required || data.mfa_setup_required)) {
        let identifier = "";
        try {
          const b = JSON.parse(new TextDecoder().decode(raw)) as { email?: string; username?: string };
          identifier = (b.username || b.email || "").trim();
        } catch {
          /* no identifier: no account line */
        }
        return settle(data, { masked: identifier ? maskIdentifier(identifier) : null, next: null });
      }
      return NextResponse.json({ detail: "Login response missing token" }, { status: 502 });
    }
    let user: unknown = data.user ?? null;
    if (!user) {
      // FastAPI's TokenOut carries no user: resolve it with the fresh token.
      const me = await resolve(new Request(new URL(`${backendBaseUrl()}/api/v1/auth/me`), { headers: { authorization: `Bearer ${data.access_token}`, accept: "application/json" } }));
      if (me.ok) user = await me.json();
    }
    // AU-16: the one-time "IdP asserted no MFA" notice travels with the exchange answer
    const idpMfa = data.idp_mfa_missing ? { idp_mfa_missing: true, idp_mfa_message_tr: data.idp_mfa_message_tr ?? null, idp_mfa_message_en: data.idp_mfa_message_en ?? null } : {};
    const extra = segment === "auth/sso/exchange" ? { next: data.next ?? null, welcome: data.welcome ?? null, inviter_name: data.inviter_name ?? null, ...idpMfa } : {};
    // AU-17: a policy that requires 2FA, still in grace, signs in and offers the enrolment (auth.md §5.6)
    const setup = data.mfa_setup_required ? { mfa_setup_required: true, mfa_grace_until: data.mfa_grace_until ?? null, mfa_setup_methods: data.mfa_setup_methods ?? ["totp"] } : {};
    const res = NextResponse.json({ user, password_change_required: Boolean(data.password_change_required), ...setup, ...extra });
    // the cookie must not outlive the JWT (backend TokenOut.expires_in, seconds)
    const maxAge = typeof data.expires_in === "number" && data.expires_in > 0 ? Math.floor(data.expires_in) : COOKIE_MAX_AGE;
    res.cookies.set({ name: AUTH_COOKIE, value: data.access_token, httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production", path: "/", maxAge });
    return res;
  }
  if (upstream.ok && req.method === "POST" && (SESSION_AFTER.has(segment) || NESTED_SESSION(segment))) {
    const data = (await upstream.json().catch(() => null)) as (TokenAnswer & { session?: TokenAnswer; recovery_codes?: unknown; passkey?: unknown; ok?: boolean }) | null;
    const answer = NESTED_SESSION(segment) ? data?.session : data;
    if (!answer) return NextResponse.json({ ...(data ?? {}), status: "none" });
    const extra: Record<string, unknown> = {};
    if (data?.recovery_codes) extra.recovery_codes = data.recovery_codes;
    if (data?.passkey) extra.passkey = data.passkey;
    if (NESTED_SESSION(segment)) extra.ok = true;
    return settle(answer, { masked: null, next: null }, extra);
  }
  if (upstream.status === 401 && token) {
    const res = passthrough(upstream);
    res.headers.append("set-cookie", `${AUTH_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax`);
    return res;
  }
  return passthrough(upstream);
}

function passthrough(upstream: Response): NextResponse {
  const headers = new Headers();
  // location: the SSO start / callback redirects; retry-after: the login rate limit (sign-in.md §6.3 "429")
  for (const name of ["content-type", "content-disposition", "cache-control", "location", "retry-after", "referrer-policy"]) {
    const v = upstream.headers.get(name);
    if (v) headers.set(name, v);
  }
  return new NextResponse(upstream.body, { status: upstream.status, headers });
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
