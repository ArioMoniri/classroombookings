import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { AUTH_COOKIE, backendBaseUrl } from "@/lib/server/config";

/**
 * Sign out: revoke the JWT on the backend (POST /api/v1/auth/logout bumps the user's token_version, so the token
 * stops working everywhere), then clear the httpOnly cookie. The cookie is cleared even if the backend is down.
 */
export async function POST(): Promise<NextResponse> {
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (token) {
    try {
      await fetch(`${backendBaseUrl()}/api/v1/auth/logout`, {
        method: "POST",
        headers: { authorization: `Bearer ${token}` },
        cache: "no-store",
        signal: AbortSignal.timeout(5000),
      });
    } catch {
      // backend unreachable: the cookie is still cleared below
    }
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.set({ name: AUTH_COOKIE, value: "", path: "/", maxAge: 0, httpOnly: true, sameSite: "lax" });
  return res;
}
