// AU-17 (AU-B API.md §1, §5, §7): the generic proxy no longer answers 502 for a second step; the challenge goes into
// the httpOnly ss_mfa cookie, verify / reset / invite answers set the session, and ss_td travels as X-Trusted-Device.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const jar = new Map<string, string>();
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (n: string) => (jar.has(n) ? { value: jar.get(n) } : undefined) }) }));
vi.mock("@/lib/server/config", () => ({ AUTH_COOKIE: "smartsched_token", COOKIE_MAX_AGE: 43200, backendBaseUrl: () => "http://api.test" }));

const { POST } = await import("@/app/api/v1/[...path]/route");
const { NextRequest } = await import("next/server");

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const call = (path: string, body: unknown) => POST(new NextRequest(`http://web.test/api/v1/${path}`, { method: "POST", body: JSON.stringify(body), headers: { "content-type": "application/json", origin: "http://web.test" } }), { params: Promise.resolve({ path: path.split("/") }) });
const cookieOf = (res: Response, name: string) => res.headers.getSetCookie().find((c) => c.startsWith(`${name}=`)) ?? null;

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  jar.clear();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const sentHeaders = (i = 0) => new Headers((fetchMock.mock.calls[i][0] as Request).headers);

describe("generic proxy (AU-17)", () => {
  it("auth/login with a second step: 200, methods only, the challenge in ss_mfa; ss_td forwarded", async () => {
    jar.set("ss_td", "TD1");
    fetchMock.mockResolvedValueOnce(json(200, { access_token: null, expires_in: 0, mfa_required: true, challenge_token: "SECRET-CH", mfa_methods: ["totp"] }));
    const res = await call("auth/login", { username: "fatih", password: "x" });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toMatchObject({ status: "mfa", methods: ["totp"], masked: "fa•••" });
    expect(JSON.stringify(body)).not.toContain("SECRET");
    expect(cookieOf(res, "ss_mfa")).toMatch(/HttpOnly/i);
    expect(sentHeaders().get("x-trusted-device")).toBe("TD1");
    expect(sentHeaders().get("origin")).toBe("http://web.test");
  });

  it("verify answers set the session and ss_td and strip the tokens", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { access_token: "JWT", expires_in: 3600, trusted_device_token: "TD2", trusted_device_days: 7 })).mockResolvedValueOnce(json(200, { id: 5 }));
    const res = await call("auth/mfa/verify", { challenge_token: "c", code: "123456" });
    const body = await res.json();
    expect(body).toMatchObject({ status: "signed_in", user: { id: 5 } });
    expect(JSON.stringify(body)).not.toMatch(/JWT|TD2/);
    expect(cookieOf(res, "smartsched_token")).toMatch(/smartsched_token=JWT/);
    expect(cookieOf(res, "ss_td")).toMatch(/Max-Age=604800/);
  });

  it("reset confirm and invite acceptance: session.access_token becomes the cookie", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { ok: true, user_id: 3, session: { access_token: "JWT3", expires_in: 3600 } })).mockResolvedValueOnce(json(200, { id: 3 }));
    let res = await call("auth/password-reset/confirm", { token: "abcdefgh", password: "a long sentence" });
    expect(await res.json()).toMatchObject({ status: "signed_in", ok: true });
    expect(cookieOf(res, "smartsched_token")).toMatch(/JWT3/);
    fetchMock.mockResolvedValueOnce(json(200, { ok: true, email: "a@b.c", session: { access_token: "JWT4", expires_in: 3600 } })).mockResolvedValueOnce(json(200, { id: 4 }));
    res = await call("auth/sso/invites/tok123/password", { password: "a long sentence" });
    expect(cookieOf(res, "smartsched_token")).toMatch(/JWT4/);
  });

  it("auth/login in the grace period: the session cookie plus mfa_setup_required / grace passed through", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { access_token: "JWT5", expires_in: 3600, mfa_setup_required: true, mfa_grace_until: "2026-11-01T00:00:00", mfa_setup_methods: ["totp", "passkey"] })).mockResolvedValueOnce(json(200, { id: 5 }));
    const res = await call("auth/login", { username: "fatih", password: "x" });
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ user: { id: 5 }, mfa_setup_required: true, mfa_grace_until: "2026-11-01T00:00:00", mfa_setup_methods: ["totp", "passkey"] });
    expect(cookieOf(res, "smartsched_token")).toMatch(/JWT5/);
  });

  it("auth/login with neither a token nor a second step is still a 502", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { access_token: null }));
    const res = await call("auth/login", { username: "fatih", password: "x" });
    expect(res.status).toBe(502);
  });
});
