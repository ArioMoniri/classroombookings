/**
 * Session cookies of the sign-in steps (docs/design/v3/auth.md §4–§5, AU-B API.md §1–§7; AUX-04, AU-17), shared by
 * the generic proxy (app/api/v1/[...path]/route.ts) and the sign-in route handler (app/api/auth/mfa/[step]/route.ts):
 * a TokenOut-shaped answer becomes the session cookie, the pending second step / enrolment (`ss_mfa`) or the
 * remembered device (`ss_td`), and the page's JSON never carries a token.
 */
import { NextResponse } from "next/server";
import { classifyToken, encodePending, MFA_COOKIE, PASSKEY_COOKIE, TRUSTED_COOKIE, type MfaPending, type TokenAnswer } from "@/components/auth/mfa-model";
import { AUTH_COOKIE, COOKIE_MAX_AGE, backendBaseUrl } from "./config";

type Json = Record<string, unknown>;
const secure = process.env.NODE_ENV === "production";

export async function me(token: string): Promise<unknown> {
  try {
    const r = await fetch(`${backendBaseUrl()}/api/v1/auth/me`, { headers: { authorization: `Bearer ${token}`, accept: "application/json" }, cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

export function setSession(res: NextResponse, token: string, expiresIn: number) {
  res.cookies.set({ name: AUTH_COOKIE, value: token, httpOnly: true, sameSite: "lax", secure, path: "/", maxAge: expiresIn > 0 ? expiresIn : COOKIE_MAX_AGE });
}

export function setPending(res: NextResponse, p: MfaPending, maxAge: number) {
  res.cookies.set({ name: MFA_COOKIE, value: encodePending(p), httpOnly: true, sameSite: "lax", secure, path: "/", maxAge });
}

export function clearCookies(res: NextResponse, ...names: string[]) {
  for (const name of names) res.cookies.set({ name, value: "", httpOnly: true, sameSite: "lax", secure, path: "/", maxAge: 0 });
}

/** A TokenOut-shaped answer → the page's answer + cookies (session, second step or enrolment). */
export async function settle(answer: TokenAnswer, ctx: { masked: string | null; next: string | null }, extra: Json = {}): Promise<NextResponse> {
  const out = classifyToken(answer);
  if (out.kind === "session") {
    const res = NextResponse.json({
      status: "signed_in",
      user: await me(out.token),
      password_change_required: out.mustChangePassword,
      setup_due: out.setupDue || undefined,
      grace_until: out.graceUntil,
      setup_methods: out.setupMethods,
      recovery_codes_remaining: answer.recovery_codes_remaining ?? undefined,
      ...extra,
    });
    setSession(res, out.token, out.expiresIn);
    clearCookies(res, MFA_COOKIE, PASSKEY_COOKIE);
    if (answer.trusted_device_token) {
      const days = typeof answer.trusted_device_days === "number" && answer.trusted_device_days > 0 ? answer.trusted_device_days : 30;
      res.cookies.set({ name: TRUSTED_COOKIE, value: answer.trusted_device_token, httpOnly: true, sameSite: "lax", secure, path: "/", maxAge: days * 86_400 });
    }
    return res;
  }
  if (out.kind === "mfa") {
    const res = NextResponse.json({ status: "mfa", methods: out.methods, masked: ctx.masked, ...extra });
    setPending(res, { k: "mfa", t: out.challenge, m: out.methods, a: ctx.masked, n: ctx.next }, out.expiresIn);
    return res;
  }
  if (out.kind === "setup") {
    const res = NextResponse.json({ status: "setup", setup_methods: out.methods, grace_until: out.graceUntil, masked: ctx.masked, ...extra });
    setPending(res, { k: "setup", t: out.challenge, m: out.methods, a: ctx.masked, g: out.graceUntil, n: ctx.next }, out.expiresIn);
    return res;
  }
  return NextResponse.json({ detail: "Login response missing token" }, { status: 502 });
}

