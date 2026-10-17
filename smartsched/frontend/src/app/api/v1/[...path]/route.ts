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
  for (const name of ["content-type", "accept", "accept-language", "x-forwarded-for", "x-real-ip"]) {
    const v = req.headers.get(name);
    if (v) headers.set(name, v);
  }
  if (token) headers.set("authorization", `Bearer ${token}`);

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const upstreamReq = new Request(url, {
    method: req.method,
    headers,
    body: hasBody ? await req.arrayBuffer() : undefined,
    redirect: "manual",
  });
  const upstream = await resolve(upstreamReq);

  if (segment === "auth/login" || segment === "auth/sso/exchange") {
    if (!upstream.ok) return passthrough(upstream);
    const data = (await upstream.json()) as { access_token?: string; user?: unknown; expires_in?: number; password_change_required?: boolean; next?: string | null; welcome?: string | null; inviter_name?: string | null };
    if (!data.access_token) return NextResponse.json({ detail: "Login response missing token" }, { status: 502 });
    let user: unknown = data.user ?? null;
    if (!user) {
      // FastAPI's TokenOut carries no user: resolve it with the fresh token.
      const me = await resolve(new Request(new URL(`${backendBaseUrl()}/api/v1/auth/me`), { headers: { authorization: `Bearer ${data.access_token}`, accept: "application/json" } }));
      if (me.ok) user = await me.json();
    }
    const extra = segment === "auth/sso/exchange" ? { next: data.next ?? null, welcome: data.welcome ?? null, inviter_name: data.inviter_name ?? null } : {};
    const res = NextResponse.json({ user, password_change_required: Boolean(data.password_change_required), ...extra });
    // the cookie must not outlive the JWT (backend TokenOut.expires_in, seconds)
    const maxAge = typeof data.expires_in === "number" && data.expires_in > 0 ? Math.floor(data.expires_in) : COOKIE_MAX_AGE;
    res.cookies.set({ name: AUTH_COOKIE, value: data.access_token, httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production", path: "/", maxAge });
    return res;
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
