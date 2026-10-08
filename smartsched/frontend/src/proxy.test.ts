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
  it.each(["/reset-password", "/setup"])("lets a signed-out visitor open %s", (path) => {
    expect(target(path)).toBeNull();
  });

  it.each(["/reset-password", "/setup"])("lets a signed-in visitor open %s too", (path) => {
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

  it("sends a signed-out visit to an app page to /login with the return path", () => {
    expect(target("/timetable?week=3")).toBe(`/login?next=${encodeURIComponent("/timetable?week=3")}`);
    expect(target("/timetable", "jwt")).toBeNull();
  });

  it("does not treat look-alike paths as public", () => {
    expect(target("/setup-admin")).toBe(`/login?next=${encodeURIComponent("/setup-admin")}`);
    expect(target("/reset-password/extra")).toBe(`/login?next=${encodeURIComponent("/reset-password/extra")}`);
  });
});
