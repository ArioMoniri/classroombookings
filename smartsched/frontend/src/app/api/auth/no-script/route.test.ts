// @vitest-environment node
/**
 * FIX-D / HB18-F02: the native-submit fallback of the credential forms. It never reads the body (the password) and
 * sends the browser back to the page it came from, same-origin only, with a 303 (so a reload does not re-post).
 */
import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";
import { GET, POST } from "./route";

const BASE = "http://app.test";
const req = (method: string, referer?: string) =>
  new NextRequest(new URL("/api/auth/no-script", BASE), { method, headers: referer ? { referer } : {}, body: method === "POST" ? "username=a&password=s3cret" : undefined });

describe("/api/auth/no-script", () => {
  it("303s back to the same-origin page, without the body", async () => {
    const res = POST(req("POST", `${BASE}/login?next=%2Ftimetable`));
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("/login?next=%2Ftimetable");
    expect(await res.text()).not.toContain("s3cret");
    expect(res.headers.get("cache-control")).toContain("no-store");
  });

  it("drops credential parameters from the way back", () => {
    expect(POST(req("POST", `${BASE}/login?username=a&password=x&next=%2F`)).headers.get("location")).toBe("/login?next=%2F");
  });

  it("never redirects off-site or to the API", () => {
    expect(POST(req("POST", "https://evil.example/login")).headers.get("location")).toBe("/login");
    expect(POST(req("POST", `${BASE}/api/v1/x`)).headers.get("location")).toBe("/login");
    expect(POST(req("POST")).headers.get("location")).toBe("/login");
    expect(GET(req("GET", `${BASE}/reset-password?token=abc`)).headers.get("location")).toBe("/reset-password?token=abc");
  });
});
