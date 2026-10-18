/**
 * HB-23d (KVKK re-check N5): a person has one live stage, so the hand-over sends exactly one `upload_token`, also on
 * /council/jobs and /imports/crbs (the list fields are gone from the contract; two tokens → 422 one_upload_token).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { councilApi } from "./council";

let forms: FormData[];
beforeEach(() => {
  forms = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.body instanceof FormData) forms.push(init.body);
      return new Response(JSON.stringify({ id: 1, status: "QUEUED" }), { status: 202, headers: { "content-type": "application/json" } });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("one upload_token on the hand-over (N5)", () => {
  it("/council/jobs sends the staged file as upload_token, never upload_tokens", async () => {
    await councilApi.create([], { uploadTokens: ["tok.sig"] }).catch(() => undefined);
    expect(forms[0]!.getAll("upload_token")).toEqual(["tok.sig"]);
    expect(forms[0]!.getAll("upload_tokens")).toEqual([]);
  });
});
