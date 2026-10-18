// @vitest-environment node
import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";
import { proxy } from "./proxy";

const BASE = "http://app.test";
function visit(path: string, token?: string) {
  const req = new NextRequest(new URL(path, BASE), token ? { headers: { cookie: `smartsched_token=${token}` } } : undefined);
  return proxy(req);
}
/** `null` = the request passes through; otherwise the redirect target (path + query). */
function target(path: string, token?: string): string | null {
  const res = visit(path, token);
  const loc = res.headers.get("location");
  if (!loc) return null;
  const url = new URL(loc);
  return `${url.pathname}${url.search}`;
}

describe("route guard (src/proxy.ts)", () => {
  it.each(["/reset-password", "/setup", "/login/sso?ticket=abc"])("lets a signed-out visitor open %s", (path) => {
    expect(target(path)).toBeNull();
  });

  it.each(["/reset-password", "/setup", "/login/sso?ticket=abc"])("lets a signed-in visitor open %s too", (path) => {
    expect(target(path, "jwt")).toBeNull();
  });

  it("shows /login when signed out and bounces a signed-in visit to the dashboard", () => {
    expect(target("/login")).toBeNull();
    expect(target("/login", "jwt")).toBe("/dashboard");
  });

  it("keeps /login/change-password behind the session (it calls an authenticated endpoint)", () => {
    expect(target("/login/change-password?next=%2Ftimetable")).toBe(`/login?next=${encodeURIComponent("/login/change-password?next=%2Ftimetable")}`);
    expect(target("/login/change-password", "jwt")).toBeNull();
  });

  it("keeps the first-login welcome page behind the session", () => {
    expect(target("/welcome")).toBe(`/login?next=${encodeURIComponent("/welcome")}`);
    expect(target("/welcome?invited=1", "jwt")).toBeNull();
  });

  it("sends a signed-out visit to an app page to /login with the return path", () => {
    expect(target("/timetable?week=3")).toBe(`/login?next=${encodeURIComponent("/timetable?week=3")}`);
    expect(target("/timetable", "jwt")).toBeNull();
  });

  it.each(["/public", "/public/rooms/A101?date=2026-02-18", "/public/buildings/A"])("lets anyone open the public day view %s", (path) => {
    expect(target(path)).toBeNull();
    expect(target(path, "jwt")).toBeNull();
  });

  it("does not treat look-alike paths as public", () => {
    expect(target("/publicity")).toBe(`/login?next=${encodeURIComponent("/publicity")}`);
    expect(target("/setup-admin")).toBe(`/login?next=${encodeURIComponent("/setup-admin")}`);
    expect(target("/reset-password/extra")).toBe(`/login?next=${encodeURIComponent("/reset-password/extra")}`);
  });
});

describe("nonce Content-Security-Policy (docs/SECURITY.md F9)", () => {
  const nonceOf = (csp: string | null) => /'nonce-([A-Za-z0-9+/=]+)'/.exec(csp ?? "")?.[1];

  it.each([
    ["/timetable", "jwt"],
    ["/timetable", undefined],
    ["/login", undefined],
    ["/login", "jwt"],
    ["/public", undefined],
  ])("sends a nonce policy on %s (token %s), passed through or redirected", (path, token) => {
    const res = visit(path, token);
    const csp = res.headers.get("content-security-policy");
    expect(csp).toBeTruthy();
    const directives = Object.fromEntries(csp!.split(";").map((d) => d.trim()).filter(Boolean).map((d) => [d.split(/\s+/)[0], d]));
    expect(directives["script-src"]).toMatch(/'nonce-[A-Za-z0-9+/=]{16,}'/);
    expect(directives["script-src"]).toContain("'strict-dynamic'");
    expect(directives["script-src"]).not.toContain("'unsafe-inline'");
    expect(directives["script-src"]).not.toContain("'unsafe-eval'");
    // the rules nginx's own policy carried (it steps aside when this one is present)
    expect(directives["object-src"]).toBe("object-src 'none'");
    expect(directives["base-uri"]).toBe("base-uri 'self'");
    expect(directives["frame-ancestors"]).toBe("frame-ancestors 'none'");
    expect(directives["form-action"]).toBe("form-action 'self' https://login.microsoftonline.com");
    expect(directives["default-src"]).toBe("default-src 'self'");
  });

  it("hands the nonce to the renderer (request headers) and makes a new one per request", () => {
    const a = visit("/timetable", "jwt");
    const b = visit("/timetable", "jwt");
    const na = nonceOf(a.headers.get("content-security-policy"));
    expect(na).toBeTruthy();
    expect(na).not.toBe(nonceOf(b.headers.get("content-security-policy")));
    // NextResponse.next({ request: { headers } }) carries the overridden request headers like this
    expect(a.headers.get("x-middleware-request-x-nonce")).toBe(na);
    expect(nonceOf(a.headers.get("x-middleware-request-content-security-policy"))).toBe(na);
  });
});

describe("credentials in the address (HB18-F02)", () => {
  it("a GET that carries a password is sent back without it (and without the username)", () => {
    expect(target("/login?username=ayse&password=s3cret")).toBe("/login");
    expect(target("/login?next=%2Ftimetable&password=s3cret")).toBe("/login?next=%2Ftimetable");
    expect(target("/reset-password?token=abc&new-password=x")).toBe("/reset-password?token=abc");
    const res = visit("/login?username=ayse&password=s3cret");
    expect(res.headers.get("cache-control") ?? "").toContain("no-store");
  });

  it("leaves ordinary query strings alone", () => {
    expect(target("/login?next=%2Ftimetable")).toBeNull();
    expect(target("/login/sso?ticket=abc")).toBeNull();
    expect(target("/reset-password?token=abc")).toBeNull();
  });
});
