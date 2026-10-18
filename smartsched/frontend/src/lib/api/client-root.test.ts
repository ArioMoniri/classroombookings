/**
 * F-CH-1 (fix-c-2026-10-18): `instrumentation-client.ts` → `ops.ts` → `client.ts` is in every page's root main
 * chunk. client.ts must not pull zod and the shared schema module in with it (34 kB gz in the root main files);
 * its error-body check is plain code, with the same results.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpError, request } from "./client";

describe("client.ts stays out of zod at runtime", () => {
  it("has no runtime import of zod or ./schemas", () => {
    const text = readFileSync(path.resolve(import.meta.dirname, "client.ts"), "utf8");
    expect(text).not.toMatch(/^import\s+(?!type\b)[^;]*from\s+"zod"/m);
    expect(text).not.toMatch(/^import\s+(?!type\b)[^;]*from\s+"\.\/schemas"/m);
  });
});

describe("error bodies", () => {
  afterEach(() => vi.unstubAllGlobals());
  const fail = (status: number, body: unknown) => vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })));

  it("a string detail is the message (pydantic prefix removed) and the error id is kept", async () => {
    fail(422, { detail: "Value error, Salon dolu", error_id: "E1" });
    const err = (await request("/x", { silent: true }).catch((e: unknown) => e)) as HttpError;
    expect(err).toBeInstanceOf(HttpError);
    expect(err.message).toBe("Salon dolu");
    expect(err.errorId).toBe("E1");
    expect(err.detail).toBe("Value error, Salon dolu");
  });

  it("a validation list joins its messages; any other body is kept as the detail", async () => {
    fail(422, { detail: [{ msg: "Value error, a", loc: ["body", 1] }, { msg: "b" }] });
    const list = (await request("/x", { silent: true }).catch((e: unknown) => e)) as HttpError;
    expect(list.message).toBe("a; b");
    fail(409, { detail: { code: "stale", message_tr: "Değişti" } });
    const obj = (await request("/x", { silent: true }).catch((e: unknown) => e)) as HttpError;
    expect(obj.message).toBe("409 ");
    expect(obj.detail).toEqual({ detail: { code: "stale", message_tr: "Değişti" } });
  });
});
