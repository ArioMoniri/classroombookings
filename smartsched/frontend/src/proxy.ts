/**
 * Route guard (Next 16 "proxy", formerly middleware): app routes need the auth cookie;
 * an authenticated visit to /login bounces to the dashboard.
 */
import { NextResponse, type NextRequest } from "next/server";

const AUTH_COOKIE = "smartsched_token";
const PUBLIC = new Set(["/login"]);

export function proxy(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;
  const token = request.cookies.get(AUTH_COOKIE)?.value;
  if (PUBLIC.has(pathname)) {
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
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|mockServiceWorker.js|.*\\..*).*)"],
};
