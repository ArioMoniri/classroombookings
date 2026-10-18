/**
 * The sign-in steps around the password (docs/design/v3/auth.md §4–§5, AU-B API.md §1–§7; AUX-03/04/05). The page
 * never sees a token: this handler keeps
 * - the challenge / setup token of the second step in the httpOnly `ss_mfa` cookie (never in the URL),
 * - the passkey-only sign-in challenge in `ss_pk`,
 * - the "Bu cihazı hatırla" token in `ss_td` (sent back as `X-Trusted-Device` on the password step),
 * and stores the session JWT in the auth cookie exactly as the generic proxy does for `auth/login`.
 *
 * Steps (POST unless noted): `login`, `state` (GET), `verify`, `passkey-options`, `passkey-verify`,
 * `signin-passkey-options`, `signin-passkey-verify`, `setup-totp-start`, `setup-totp-confirm`,
 * `setup-passkey-options`, `setup-passkey-verify`, `reset-confirm`, `invite-password`, `cancel`.
 * Refusals pass through with their status, body and `Retry-After`.
 */
import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";
import { classifyToken, decodePending, encodePending, endsChallenge, MFA_COOKIE, PASSKEY_COOKIE, TRUSTED_COOKIE, type MfaPending, type TokenAnswer } from "@/components/auth/mfa-model";
import { safeNext } from "@/components/auth/signin-model";
import { maskIdentifier } from "@/lib/api/auth-security";
import { AUTH_COOKIE, COOKIE_MAX_AGE, backendBaseUrl } from "@/lib/server/config";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ step: string }> };
type Json = Record<string, unknown>;

const secure = process.env.NODE_ENV === "production";
const FORWARD = ["accept-language", "x-forwarded-for", "x-real-ip", "user-agent", "origin"];

async function backend(req: NextRequest, path: string, body: unknown, extra: Record<string, string> = {}): Promise<Response> {
  const headers = new Headers({ "content-type": "application/json", accept: "application/json", ...extra });
  for (const name of FORWARD) {
    const v = req.headers.get(name);
    if (v) headers.set(name, v);
  }
  try {
    return await fetch(`${backendBaseUrl()}/api/v1${path}`, { method: "POST", headers, body: JSON.stringify(body ?? {}), cache: "no-store", redirect: "manual" });
  } catch (e) {
    return new Response(JSON.stringify({ detail: `Backend unreachable: ${e instanceof Error ? e.message : "unknown"}` }), { status: 502, headers: { "content-type": "application/json" } });
  }
}

function passthrough(upstream: Response, json: unknown): NextResponse {
  const res = NextResponse.json(json ?? {}, { status: upstream.status });
  const retry = upstream.headers.get("retry-after");
  if (retry) res.headers.set("retry-after", retry);
  return res;
}

const code = (json: unknown): string | null => {
  const d = (json as { detail?: unknown } | null)?.detail;
  return d && typeof d === "object" && typeof (d as Json).code === "string" ? String((d as Json).code) : null;
};

async function me(token: string): Promise<unknown> {
  try {
    const r = await fetch(`${backendBaseUrl()}/api/v1/auth/me`, { headers: { authorization: `Bearer ${token}`, accept: "application/json" }, cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

function setSession(res: NextResponse, token: string, expiresIn: number) {
  res.cookies.set({ name: AUTH_COOKIE, value: token, httpOnly: true, sameSite: "lax", secure, path: "/", maxAge: expiresIn > 0 ? expiresIn : COOKIE_MAX_AGE });
}

function setPending(res: NextResponse, p: MfaPending, maxAge: number) {
  res.cookies.set({ name: MFA_COOKIE, value: encodePending(p), httpOnly: true, sameSite: "lax", secure, path: "/", maxAge });
}

function clear(res: NextResponse, ...names: string[]) {
  for (const name of names) res.cookies.set({ name, value: "", httpOnly: true, sameSite: "lax", secure, path: "/", maxAge: 0 });
}

/** A TokenOut-shaped answer → the page's answer + cookies (session, second step or enrolment). */
async function settle(answer: TokenAnswer, ctx: { masked: string | null; next: string | null }, extra: Json = {}): Promise<NextResponse> {
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
    clear(res, MFA_COOKIE, PASSKEY_COOKIE);
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

async function readBody(req: NextRequest): Promise<Json> {
  try {
    const v = (await req.json()) as unknown;
    return v && typeof v === "object" && !Array.isArray(v) ? (v as Json) : {};
  } catch {
    return {};
  }
}

const str = (v: unknown, max = 4096) => (typeof v === "string" ? v.slice(0, max) : "");

export async function GET(_req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  const { step } = await ctx.params;
  if (step !== "state") return NextResponse.json({ detail: "not found" }, { status: 404 });
  const p = decodePending((await cookies()).get(MFA_COOKIE)?.value);
  if (!p) return NextResponse.json({ status: "none" });
  return NextResponse.json({ status: p.k, methods: p.k === "mfa" ? p.m : undefined, setup_methods: p.k === "setup" ? p.m : undefined, masked: p.a, grace_until: p.g ?? null });
}

export async function POST(req: NextRequest, ctx: Ctx): Promise<NextResponse> {
  const { step } = await ctx.params;
  const jar = await cookies();
  const body = await readBody(req);
  const pending = decodePending(jar.get(MFA_COOKIE)?.value);
  const next = safeNext(str(body.next, 255)) ?? pending?.n ?? null;

  const needPending = (kind: "mfa" | "setup") => {
    if (pending?.k === kind) return null;
    const res = NextResponse.json({ detail: { code: "challenge_expired", message: "This verification step has expired. Sign in again.", message_en: "This verification step has expired. Sign in again.", message_tr: "Doğrulama adımının süresi doldu. Yeniden giriş yapın." } }, { status: 401 });
    clear(res, MFA_COOKIE);
    return res;
  };

  /** a second-step / setup call: pass refusals through, end the challenge on the codes that end it */
  const challengeCall = async (path: string, payload: Json, kind: "mfa" | "setup", extraOk?: (j: Json) => Json) => {
    const missing = needPending(kind);
    if (missing) return missing;
    const up = await backend(req, path, { ...payload, challenge_token: pending!.t });
    const json = (await up.json().catch(() => null)) as Json | null;
    if (!up.ok) {
      const res = passthrough(up, json);
      if (endsChallenge(up.status, code(json))) clear(res, MFA_COOKIE);
      return res;
    }
    return { json: json ?? {}, extra: extraOk ? extraOk(json ?? {}) : {} };
  };

  switch (step) {
    case "login": {
      const identifier = str(body.identifier, 320).trim();
      const password = str(body.password, 256);
      const payload = identifier.includes("@") ? { email: identifier, password } : { username: identifier, password };
      const trusted = jar.get(TRUSTED_COOKIE)?.value;
      const up = await backend(req, "/auth/login", payload, trusted ? { "x-trusted-device": trusted } : {});
      const json = (await up.json().catch(() => null)) as TokenAnswer | null;
      if (!up.ok) return passthrough(up, json);
      return settle(json ?? {}, { masked: identifier ? maskIdentifier(identifier) : null, next });
    }
    case "verify": {
      const method = body.method === "recovery" ? "recovery" : "totp";
      const r = await challengeCall("/auth/mfa/verify", { method, code: str(body.code, 64), trust_device: body.trust_device === true }, "mfa");
      if (r instanceof NextResponse) return r;
      return settle(r.json as TokenAnswer, { masked: pending!.a, next });
    }
    case "passkey-options": {
      const r = await challengeCall("/auth/mfa/passkey/options", {}, "mfa");
      return r instanceof NextResponse ? r : NextResponse.json({ options: r.json.options });
    }
    case "passkey-verify": {
      const r = await challengeCall("/auth/mfa/passkey/verify", { credential: body.credential ?? {}, trust_device: body.trust_device === true }, "mfa");
      if (r instanceof NextResponse) return r;
      return settle(r.json as TokenAnswer, { masked: pending!.a, next });
    }
    case "signin-passkey-options": {
      const up = await backend(req, "/auth/passkey/options", {});
      const json = (await up.json().catch(() => null)) as Json | null;
      if (!up.ok) return passthrough(up, json);
      const res = NextResponse.json({ options: json?.options ?? {} });
      const exp = typeof json?.challenge_expires_in === "number" ? Math.floor(json.challenge_expires_in) : 300;
      res.cookies.set({ name: PASSKEY_COOKIE, value: str(json?.challenge_token, 2048), httpOnly: true, sameSite: "lax", secure, path: "/", maxAge: exp });
      return res;
    }
    case "signin-passkey-verify": {
      const token = jar.get(PASSKEY_COOKIE)?.value;
      if (!token) return NextResponse.json({ detail: { code: "challenge_expired", message: "Sign in again.", message_en: "Sign in again.", message_tr: "Yeniden giriş yapın." } }, { status: 401 });
      const up = await backend(req, "/auth/passkey/verify", { challenge_token: token, credential: body.credential ?? {} });
      const json = (await up.json().catch(() => null)) as TokenAnswer | null;
      if (!up.ok) {
        const res = passthrough(up, json);
        clear(res, PASSKEY_COOKIE);
        return res;
      }
      return settle(json ?? {}, { masked: null, next });
    }
    case "setup-totp-start": {
      const r = await challengeCall("/auth/mfa/setup/totp/start", {}, "setup");
      return r instanceof NextResponse ? r : NextResponse.json(r.json);
    }
    case "setup-totp-confirm": {
      const r = await challengeCall("/auth/mfa/setup/totp/confirm", { code: str(body.code, 64) }, "setup");
      if (r instanceof NextResponse) return r;
      return settle(r.json as TokenAnswer, { masked: pending!.a, next }, { recovery_codes: r.json.recovery_codes });
    }
    case "setup-passkey-options": {
      const r = await challengeCall("/auth/mfa/setup/passkey/options", {}, "setup");
      return r instanceof NextResponse ? r : NextResponse.json({ options: r.json.options });
    }
    case "setup-passkey-verify": {
      const r = await challengeCall("/auth/mfa/setup/passkey/verify", { credential: body.credential ?? {}, name: typeof body.name === "string" ? body.name.slice(0, 64) : null }, "setup");
      if (r instanceof NextResponse) return r;
      return settle(r.json as TokenAnswer, { masked: pending!.a, next }, { recovery_codes: r.json.recovery_codes, passkey: r.json.passkey });
    }
    case "reset-confirm":
    case "invite-password": {
      const token = str(body.token, 1024);
      const password = str(body.password, 256);
      const up =
        step === "reset-confirm"
          ? await backend(req, "/auth/password-reset/confirm", { token, password })
          : await backend(req, `/auth/sso/invites/${encodeURIComponent(token.slice(0, 256))}/password`, { password });
      const json = (await up.json().catch(() => null)) as (Json & { session?: TokenAnswer }) | null;
      if (!up.ok) return passthrough(up, json);
      if (!json?.session) return NextResponse.json({ status: "none", ok: true });
      return settle(json.session, { masked: typeof body.identifier === "string" ? maskIdentifier(body.identifier) : null, next }, { ok: true });
    }
    case "cancel": {
      const res = NextResponse.json({ status: "none" });
      clear(res, MFA_COOKIE, PASSKEY_COOKIE);
      return res;
    }
    default:
      return NextResponse.json({ detail: "not found" }, { status: 404 });
  }
}
