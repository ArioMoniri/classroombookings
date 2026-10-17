/**
 * Route guard (Next 16 "proxy", formerly middleware): app routes need the auth cookie;
 * an authenticated visit to /login bounces to the dashboard.
 *
 * - SIGNED_OUT_ONLY: the sign-in page (a signed-in visit goes to /dashboard)
 * - PUBLIC: pages that must work without a session, signed in or not: the password reset
 *   (`/reset-password`, a forgotten password), the first-run wizard (`/setup`, before any user exists) and the
 *   Microsoft sign-in landing page (`/login/sso?ticket=…`, it creates the session)
 * - PUBLIC_PREFIX: the V2 public day view (`/public`, `/public/rooms/A101`, `/public/buildings/A`): a wall screen with
 *   no session; the backend answers 404 while an administrator has it off
 * - everything else, including `/login/change-password` (it calls the authenticated
 *   `POST /auth/change-password`), needs the cookie and otherwise redirects to /login?next=…
 *
 * Every page response also carries a per-request nonce Content-Security-Policy (docs/SECURITY.md F9, the Next.js
 * CSP guide for this version): `script-src 'nonce-…' 'strict-dynamic'` instead of `'unsafe-inline'`. The renderer
 * reads the nonce from the request's CSP header and stamps it on its own scripts; the root layout passes `x-nonce`
 * to the inline appearance script and next-themes. Every page is dynamic (the root layout reads cookies), so no
 * prerendered page lacks the nonce. nginx adds its own policy only when this one is missing.
 */
import { NextResponse, type NextRequest } from "next/server";

const AUTH_COOKIE = "smartsched_token";
const SIGNED_OUT_ONLY = new Set(["/login"]);
const PUBLIC = new Set(["/reset-password", "/setup", "/login/sso"]);
const PUBLIC_PREFIX = "/public";

/** 128 random bits, base64 (a CSP nonce must be unguessable and new for every response). */
function makeNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return btoa(String.fromCharCode(...bytes));
}

/** The page policy; it keeps every rule nginx's fallback policy had (deploy/nginx/default.conf), minus
 *  `'unsafe-inline'` for scripts. Styles keep `'unsafe-inline'`: motion and the glass surfaces set style attributes,
 *  which a nonce cannot allow. */
export function contentSecurityPolicy(nonce: string, dev = process.env.NODE_ENV === "development"): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "media-src 'self' blob:",
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "frame-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self' https://login.microsoftonline.com",
    "frame-ancestors 'none'",
  ].join("; ");
}

function guard(request: NextRequest, headers: Headers): NextResponse {
  const { pathname, search } = request.nextUrl;
  const token = request.cookies.get(AUTH_COOKIE)?.value;
  const pass = () => NextResponse.next({ request: { headers } });
  if (PUBLIC.has(pathname)) return pass();
  if (pathname === PUBLIC_PREFIX || pathname.startsWith(`${PUBLIC_PREFIX}/`)) return pass();
  if (SIGNED_OUT_ONLY.has(pathname)) {
    if (token) return NextResponse.redirect(new URL("/dashboard", request.url));
    return pass();
  }
  if (!token) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(login);
  }
  return pass();
}

export function proxy(request: NextRequest): NextResponse {
  const nonce = makeNonce();
  const csp = contentSecurityPolicy(nonce);
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("content-security-policy", csp);
  const res = guard(request, headers);
  res.headers.set("content-security-policy", csp);
  return res;
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
