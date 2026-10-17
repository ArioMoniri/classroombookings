// @vitest-environment node
/**
 * docs/SECURITY.md F3: the same-origin API handler forwards the client address nginx wrote (`x-forwarded-for`,
 * `x-real-ip`) so the backend's per-address sign-in caps count the browser, not the frontend container.
 */
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => undefined }) }));

import { GET, POST } from "./route";

let seen: Request[] = [];
beforeEach(() => {
  seen = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (req: Request) => {
      seen.push(req);
      return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function ctx(...path: string[]) {
  return { params: Promise.resolve({ path }) };
}

describe("API proxy route: client address", () => {
  it("forwards x-forwarded-for and x-real-ip as nginx sent them", async () => {
    const req = new NextRequest("http://app.test/api/v1/auth/password-reset/confirm", {
      method: "POST",
      headers: { "content-type": "application/json", "x-forwarded-for": "203.0.113.9", "x-real-ip": "203.0.113.9" },
      body: JSON.stringify({ token: "t", password: "p" }),
    });
    await POST(req, ctx("auth", "password-reset", "confirm"));
    expect(seen).toHaveLength(1);
    expect(seen[0]!.headers.get("x-forwarded-for")).toBe("203.0.113.9");
    expect(seen[0]!.headers.get("x-real-ip")).toBe("203.0.113.9");
  });

  it("sends nothing it did not receive", async () => {
    await GET(new NextRequest("http://app.test/api/v1/health"), ctx("health"));
    expect(seen[0]!.headers.get("x-forwarded-for")).toBeNull();
    expect(seen[0]!.headers.get("x-real-ip")).toBeNull();
  });
});
