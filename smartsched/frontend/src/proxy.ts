/**
 * Route guard (Next 16 "proxy", formerly middleware): app routes need the auth cookie;
 * an authenticated visit to /login bounces to the dashboard.
 *
 * - SIGNED_OUT_ONLY: the sign-in page (a signed-in visit goes to /dashboard)
 * - PUBLIC: pages that must work without a session, signed in or not: the password reset
 *   (`/reset-password`, a forgotten password) and the first-run wizard (`/setup`, before any user exists)
 * - everything else, including `/login/change-password` (it calls the authenticated
 *   `POST /auth/change-password`), needs the cookie and otherwise redirects to /login?next=…
 */
import { NextResponse, type NextRequest } from "next/server";

const AUTH_COOKIE = "smartsched_token";
const SIGNED_OUT_ONLY = new Set(["/login"]);
const PUBLIC = new Set(["/reset-password", "/setup"]);

export function proxy(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;
  const token = request.cookies.get(AUTH_COOKIE)?.value;
  if (PUBLIC.has(pathname)) return NextResponse.next();
  if (SIGNED_OUT_ONLY.has(pathname)) {
    if (token) return NextResponse.redirect(new URL("/dashboard", request.url));
    return NextResponse.next();
  }
  if (!token) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
