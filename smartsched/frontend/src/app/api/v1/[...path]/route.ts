/**
 * Same-origin proxy for the FastAPI backend (`/api/v1/*` → `${NEXT_PUBLIC_API_URL}/api/v1/*`).
 * - attaches `Authorization: Bearer <jwt>` from the httpOnly cookie
 * - `auth/login` stores the JWT in the cookie and returns only the user
 * - in mock mode (NEXT_PUBLIC_API_MOCK=1) answers from the MSW handlers in src/mocks
 */
import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";
import { AUTH_COOKIE, COOKIE_MAX_AGE, backendBaseUrl, isMockMode } from "@/lib/server/config";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path: string[] }> };

async function resolve(request: Request): Promise<Response> {
  if (isMockMode()) {
    const { getResponse } = await import("msw");
    const { handlers } = await import("@/mocks/handlers");
    const res = await getResponse(handlers, request);
    return res ?? new Response(JSON.stringify({ detail: `No mock for ${request.method} ${new URL(request.url).pathname}` }), { status: 501, headers: { "Content-Type": "application/json" } });
  }
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
  for (const name of ["content-type", "accept", "accept-language"]) {
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

  if (segment === "auth/login") {
    if (!upstream.ok) return passthrough(upstream);
    const data = (await upstream.json()) as { access_token?: string; user?: unknown };
    if (!data.access_token) return NextResponse.json({ detail: "Login response missing token" }, { status: 502 });
    let user: unknown = data.user ?? null;
    if (!user) {
      // FastAPI's TokenOut carries no user: resolve it with the fresh token.
      const me = await resolve(new Request(new URL(`${backendBaseUrl()}/api/v1/auth/me`), { headers: { authorization: `Bearer ${data.access_token}`, accept: "application/json" } }));
      if (me.ok) user = await me.json();
    }
    const res = NextResponse.json({ user });
    res.cookies.set({ name: AUTH_COOKIE, value: data.access_token, httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production", path: "/", maxAge: COOKIE_MAX_AGE });
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
  for (const name of ["content-type", "content-disposition", "cache-control"]) {
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
