import { afterEach, describe, expect, it, vi } from "vitest";
import { changePassword } from "./shell-extra";

type Call = { url: string; body: unknown };

/** Routes fetch by path; the backend revokes tokens on a password change (`signed_out: true`). */
const backend = (signedOut: boolean, me: Record<string, unknown>) => {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ url, body });
      const json = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
      if (url.includes("/auth/me")) return json({ role: "ADMIN", permissions: [], ...me });
      if (url.includes("/auth/change-password")) return json({ ok: true, signed_out: signedOut });
      if (url.includes("/auth/login")) return json({ user: { id: 1, role: "ADMIN", permissions: [], ...me } });
      return new Response("not found", { status: 404 });
    }),
  );
  return calls;
};

afterEach(() => vi.unstubAllGlobals());

describe("changePassword keeps the session (backend revokes old tokens)", () => {
  it("signs in again with the new password when the backend signed the user out", async () => {
    const calls = backend(true, { id: 1, email: "ayse.kaya@uni.edu.tr", username: "ayse.kaya" });
    await changePassword({ current_password: "Eski-Parola-1", new_password: "Yeni-Parola-2026" });
    const login = calls.find((c) => c.url.includes("/auth/login"));
    expect(login?.body).toEqual({ email: "ayse.kaya@uni.edu.tr", password: "Yeni-Parola-2026" });
  });

  it("uses the username when the account has no e-mail", async () => {
    const calls = backend(true, { id: 2, email: null, username: "ilker.sahin" });
    await changePassword({ current_password: null, new_password: "Yeni-Parola-2026" });
    expect(calls.find((c) => c.url.includes("/auth/login"))?.body).toEqual({ username: "ilker.sahin", password: "Yeni-Parola-2026" });
  });

  it("does not sign in again when the backend kept the token", async () => {
    const calls = backend(false, { id: 3, email: "x@uni.edu.tr" });
    await changePassword({ current_password: "a", new_password: "Yeni-Parola-2026" });
    expect(calls.some((c) => c.url.includes("/auth/login"))).toBe(false);
  });
});
