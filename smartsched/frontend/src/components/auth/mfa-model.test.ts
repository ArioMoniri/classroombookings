// AUX-03/04: the password step's outcomes and the route handler that keeps every token in httpOnly cookies (never in
// the URL or the page's JSON).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { classifyToken, daysLeft, decodePending, encodePending, endsChallenge, firstMethod, readMfaNotice } from "./mfa-model";

describe("classifyToken (API.md §1)", () => {
  it("session, second step, enrolment, malformed", () => {
    expect(classifyToken({ access_token: "jwt", expires_in: 3600 })).toMatchObject({ kind: "session", token: "jwt", expiresIn: 3600, setupDue: false });
    expect(classifyToken({ access_token: "jwt", expires_in: 3600, mfa_setup_required: true, mfa_grace_until: "2026-11-01T00:00:00" })).toMatchObject({ kind: "session", setupDue: true, graceUntil: "2026-11-01T00:00:00" });
    expect(classifyToken({ access_token: null, mfa_required: true, challenge_token: "c", challenge_expires_in: 300, mfa_methods: ["totp", "recovery"] })).toEqual({ kind: "mfa", challenge: "c", expiresIn: 300, methods: ["totp", "recovery"] });
    expect(classifyToken({ access_token: null, mfa_setup_required: true, challenge_token: "s", mfa_setup_methods: ["totp", "passkey"] })).toMatchObject({ kind: "setup", challenge: "s", methods: ["totp", "passkey"] });
    expect(classifyToken({ access_token: null })).toEqual({ kind: "invalid" });
    expect(classifyToken(null)).toEqual({ kind: "invalid" });
  });
  it("pending cookie round-trips and rejects junk", () => {
    const p = { k: "mfa" as const, t: "tok", m: ["totp"], a: "ay•••@x.tr", g: null, n: "/bookings" };
    expect(decodePending(encodePending(p))).toEqual(p);
    expect(decodePending("not-base64-json")).toBeNull();
    expect(decodePending(Buffer.from(JSON.stringify({ k: "x", t: "y" })).toString("base64url"))).toBeNull();
  });
  it("which refusals end the challenge", () => {
    expect(endsChallenge(429, "mfa_locked")).toBe("locked");
    expect(endsChallenge(401, "challenge_expired")).toBe("expired");
    expect(endsChallenge(401, "invalid_code")).toBeNull();
    expect(readMfaNotice("tooMany")).toBe("tooMany");
    expect(readMfaNotice("evil")).toBeNull();
  });
  it("days left and the first method", () => {
    const now = Date.parse("2026-10-18T00:00:00Z");
    expect(daysLeft("2026-11-01T00:00:00", now)).toBe(14);
    expect(daysLeft("2026-10-01T00:00:00", now)).toBe(0);
    expect(firstMethod(["recovery", "passkey"])).toBe("passkey");
    expect(firstMethod(["totp", "passkey"])).toBe("totp");
  });
});

/* ------------------------------------------------------------------------------------------- the handler */

const jar = new Map<string, string>();
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (n: string) => (jar.has(n) ? { value: jar.get(n) } : undefined) }) }));
vi.mock("@/lib/server/config", () => ({ AUTH_COOKIE: "smartsched_token", COOKIE_MAX_AGE: 43200, backendBaseUrl: () => "http://api.test" }));

const { POST, GET } = await import("@/app/api/auth/mfa/[step]/route");
const { NextRequest } = await import("next/server");

const call = (step: string, body?: unknown, headers: Record<string, string> = {}) =>
  POST(new NextRequest(`http://web.test/api/auth/mfa/${step}`, { method: "POST", body: JSON.stringify(body ?? {}), headers: { "content-type": "application/json", origin: "http://web.test", ...headers } }), { params: Promise.resolve({ step }) });

const cookieOf = (res: Response, name: string) => res.headers.getSetCookie().find((c) => c.startsWith(`${name}=`)) ?? null;

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  jar.clear();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const json = (status: number, body: unknown, headers: Record<string, string> = {}) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });

describe("route handler /api/auth/mfa/[step]", () => {
  it("login with a second step: the challenge goes into ss_mfa, never into the answer", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { access_token: null, expires_in: 0, mfa_required: true, challenge_token: "CHALLENGE-123", challenge_expires_in: 300, mfa_methods: ["totp", "recovery"] }));
    const res = await call("login", { identifier: "ayse@ornek.edu.tr", password: "pw", next: "/bookings" });
    const body = await res.json();
    expect(body).toEqual({ status: "mfa", methods: ["totp", "recovery"], masked: "ay•••@ornek.edu.tr" });
    expect(JSON.stringify(body)).not.toContain("CHALLENGE");
    const c = cookieOf(res, "ss_mfa")!;
    expect(c).toMatch(/HttpOnly/i);
    expect(c).toMatch(/Max-Age=300/);
    expect(cookieOf(res, "smartsched_token")).toBeNull();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/auth/login");
    expect(JSON.parse(String(init.body))).toEqual({ email: "ayse@ornek.edu.tr", password: "pw" });
    expect(new Headers(init.headers).get("origin")).toBe("http://web.test");
  });

  it("login sends the remembered-device cookie as X-Trusted-Device", async () => {
    jar.set("ss_td", "TRUSTED");
    fetchMock.mockResolvedValueOnce(json(200, { access_token: "JWT", expires_in: 3600 })).mockResolvedValueOnce(json(200, { id: 1 }));
    const res = await call("login", { identifier: "fatih", password: "pw" });
    expect(new Headers((fetchMock.mock.calls[0] as [string, RequestInit])[1].headers).get("x-trusted-device")).toBe("TRUSTED");
    expect(await res.json()).toMatchObject({ status: "signed_in", user: { id: 1 } });
    expect(cookieOf(res, "smartsched_token")).toMatch(/smartsched_token=JWT/);
  });

  it("verify: the challenge from the cookie, the session + trusted cookie on success", async () => {
    jar.set("ss_mfa", encodePending({ k: "mfa", t: "CH", m: ["totp"], a: "fa•••", n: null }));
    fetchMock.mockResolvedValueOnce(json(200, { access_token: "JWT", expires_in: 3600, trusted_device_token: "TD", trusted_device_days: 30 })).mockResolvedValueOnce(json(200, { id: 2 }));
    const res = await call("verify", { method: "totp", code: "123456", trust_device: true });
    expect(JSON.parse(String((fetchMock.mock.calls[0] as [string, RequestInit])[1].body))).toEqual({ method: "totp", code: "123456", trust_device: true, challenge_token: "CH" });
    const body = await res.json();
    expect(body.status).toBe("signed_in");
    expect(JSON.stringify(body)).not.toContain("TD");
    expect(cookieOf(res, "ss_td")).toMatch(/Max-Age=2592000/);
    expect(cookieOf(res, "ss_mfa")).toMatch(/Max-Age=0/);
  });

  it("verify: a wrong code passes through and keeps the challenge; an expired one clears it", async () => {
    jar.set("ss_mfa", encodePending({ k: "mfa", t: "CH", m: ["totp"], a: null }));
    fetchMock.mockResolvedValueOnce(json(401, { detail: { code: "invalid_code" } }));
    let res = await call("verify", { code: "000000" });
    expect(res.status).toBe(401);
    expect(cookieOf(res, "ss_mfa")).toBeNull();
    fetchMock.mockResolvedValueOnce(json(401, { detail: { code: "challenge_expired" } }));
    res = await call("verify", { code: "000000" });
    expect(cookieOf(res, "ss_mfa")).toMatch(/Max-Age=0/);
    fetchMock.mockResolvedValueOnce(json(429, { detail: { code: "mfa_locked", retry_after: 900 } }, { "retry-after": "900" }));
    res = await call("verify", { code: "000000" });
    expect(res.headers.get("retry-after")).toBe("900");
  });

  it("verify without a pending challenge answers challenge_expired", async () => {
    const res = await call("verify", { code: "123456" });
    expect(res.status).toBe(401);
    expect((await res.json()).detail.code).toBe("challenge_expired");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("passkey-only sign-in keeps its challenge in ss_pk", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { challenge_token: "PK", challenge_expires_in: 300, options: { publicKey: { challenge: "AA" } } }));
    const res = await call("signin-passkey-options");
    expect(await res.json()).toEqual({ options: { publicKey: { challenge: "AA" } } });
    expect(cookieOf(res, "ss_pk")).toMatch(/ss_pk=PK/);
  });

  it("state (GET) reads the pending step without the token", async () => {
    jar.set("ss_mfa", encodePending({ k: "setup", t: "SETUP", m: ["totp", "passkey"], a: "ay•••", g: "2026-11-01T00:00:00" }));
    const res = await GET(new NextRequest("http://web.test/api/auth/mfa/state"), { params: Promise.resolve({ step: "state" }) });
    const body = await res.json();
    expect(body).toMatchObject({ status: "setup", setup_methods: ["totp", "passkey"], masked: "ay•••", grace_until: "2026-11-01T00:00:00" });
    expect(JSON.stringify(body)).not.toContain("SETUP");
  });

  it("reset-confirm signs in through the session of the answer", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { ok: true, user_id: 3, session: { access_token: null, mfa_required: true, challenge_token: "C2", mfa_methods: ["totp"] } }));
    const res = await call("reset-confirm", { token: "abcdefgh123", password: "a long sentence" });
    expect(await res.json()).toMatchObject({ status: "mfa", ok: true });
    expect(cookieOf(res, "ss_mfa")).toBeTruthy();
  });
});
