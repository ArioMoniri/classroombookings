// AUX-01 (docs/design/v3/auth.md §4.2, §4.3, §4.6, §6.4): the browser side of passkeys, with a mocked
// navigator.credentials. An abort cancels a pending conditional get; Conditional Create failures are silent;
// the DOMException names map to the copy keys.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  aaguidFromAuthData,
  b64urlToBytes,
  bytesToB64url,
  conditionalCreate,
  credentialToJSON,
  getPasskey,
  passkeyErrorKey,
  passkeyErrorKind,
  passkeySupport,
  signalAccepted,
  signalUnknown,
  startConditionalGet,
  toCreationOptions,
  toRequestOptions,
} from "./passkey";

const enc = (s: string) => new TextEncoder().encode(s);

function fakeAssertion(id = "AQIDBA") {
  const raw = b64urlToBytes(id);
  return {
    id,
    rawId: raw.buffer,
    type: "public-key",
    authenticatorAttachment: "platform",
    response: { clientDataJSON: enc("{}").buffer, authenticatorData: new Uint8Array([1, 2]).buffer, signature: new Uint8Array([3]).buffer, userHandle: null },
    getClientExtensionResults: () => ({}),
  };
}

const REQUEST = { publicKey: { challenge: "AAEC", rpId: "localhost", timeout: 300000, allowCredentials: [{ id: "AQIDBA", type: "public-key", transports: ["internal"] }], userVerification: "preferred" } };
const CREATION = {
  publicKey: {
    challenge: "AAEC",
    rp: { id: "localhost", name: "SmartSched" },
    user: { id: "BQYH", name: "ayse", displayName: "Ayşe" },
    pubKeyCredParams: [{ type: "public-key", alg: -7 }],
    excludeCredentials: [{ id: "AQIDBA", type: "public-key" }],
    authenticatorSelection: { residentKey: "preferred", userVerification: "preferred" },
    attestation: "none",
  },
};

let get: ReturnType<typeof vi.fn>;
let create: ReturnType<typeof vi.fn>;

beforeEach(() => {
  get = vi.fn();
  create = vi.fn();
  Object.defineProperty(navigator, "credentials", { value: { get, create }, configurable: true });
  const PKC = function PublicKeyCredential() {} as unknown as Record<string, unknown>;
  PKC.isConditionalMediationAvailable = vi.fn(async () => true);
  PKC.isUserVerifyingPlatformAuthenticatorAvailable = vi.fn(async () => true);
  vi.stubGlobal("PublicKeyCredential", PKC);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("base64url", () => {
  it("round-trips bytes without padding", () => {
    const bytes = new Uint8Array([0, 1, 2, 250, 251, 252, 253, 254, 255]);
    const s = bytesToB64url(bytes);
    expect(s).not.toMatch(/[=+/]/);
    expect(Array.from(b64urlToBytes(s))).toEqual(Array.from(bytes));
  });
  it("accepts padded and standard base64 too", () => {
    expect(Array.from(b64urlToBytes("+/8="))).toEqual([251, 255]);
  });
});

describe("options from the server (py_webauthn JSON, {publicKey: …})", () => {
  it("decodes the challenge, the user id and the credential ids", () => {
    const req = toRequestOptions(REQUEST);
    expect(new Uint8Array(req.challenge as ArrayBuffer)).toEqual(new Uint8Array([0, 1, 2]));
    expect(new Uint8Array(req.allowCredentials![0].id as ArrayBuffer)).toEqual(new Uint8Array([1, 2, 3, 4]));
    const cr = toCreationOptions(CREATION);
    expect(new Uint8Array(cr.user.id as ArrayBuffer)).toEqual(new Uint8Array([5, 6, 7]));
    expect(cr.excludeCredentials).toHaveLength(1);
    expect(cr.attestation).toBe("none");
  });
});

describe("credentialToJSON", () => {
  it("encodes an assertion's buffers as base64url", () => {
    const json = credentialToJSON(fakeAssertion() as unknown as PublicKeyCredential);
    expect(json).toMatchObject({ id: "AQIDBA", rawId: "AQIDBA", type: "public-key", response: { clientDataJSON: bytesToB64url(enc("{}")), signature: "Aw" } });
    expect((json.response as Record<string, unknown>).userHandle).toBeUndefined();
  });
});

describe("feature detection", () => {
  it("prefers getClientCapabilities()", async () => {
    (globalThis.PublicKeyCredential as unknown as Record<string, unknown>).getClientCapabilities = vi.fn(async () => ({ conditionalGet: true, conditionalCreate: false, passkeyPlatformAuthenticator: true }));
    expect(await passkeySupport()).toEqual({ webauthn: true, conditionalGet: true, conditionalCreate: false, platform: true });
  });
  it("falls back to the older static checks", async () => {
    expect(await passkeySupport()).toEqual({ webauthn: true, conditionalGet: true, conditionalCreate: false, platform: true });
  });
  it("says no without PublicKeyCredential", async () => {
    vi.stubGlobal("PublicKeyCredential", undefined);
    expect(await passkeySupport()).toEqual({ webauthn: false, conditionalGet: false, conditionalCreate: false, platform: false });
  });
});

describe("conditional get", () => {
  it("passes mediation conditional with empty allowCredentials and resolves the credential", async () => {
    get.mockResolvedValue(fakeAssertion());
    const onCredential = vi.fn();
    const handle = startConditionalGet(async () => REQUEST, onCredential);
    await handle.done;
    expect(get).toHaveBeenCalledTimes(1);
    const arg = get.mock.calls[0][0] as CredentialRequestOptions;
    expect(arg.mediation).toBe("conditional");
    expect(arg.publicKey?.allowCredentials).toEqual([]);
    expect(arg.signal).toBeInstanceOf(AbortSignal);
    expect(onCredential).toHaveBeenCalledWith(expect.objectContaining({ id: "AQIDBA" }));
  });

  it("abort() cancels the pending request and never calls back", async () => {
    let signal: AbortSignal | undefined;
    get.mockImplementation((opts: CredentialRequestOptions) => {
      signal = opts.signal ?? undefined;
      return new Promise((_res, rej) => opts.signal?.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError"))));
    });
    const onCredential = vi.fn();
    const onError = vi.fn();
    const handle = startConditionalGet(async () => REQUEST, onCredential, onError);
    await vi.waitFor(() => expect(get).toHaveBeenCalled());
    handle.abort();
    await handle.done;
    expect(signal?.aborted).toBe(true);
    expect(onCredential).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it("does nothing when conditional mediation is unavailable", async () => {
    (globalThis.PublicKeyCredential as unknown as Record<string, ReturnType<typeof vi.fn>>).isConditionalMediationAvailable = vi.fn(async () => false);
    const options = vi.fn(async () => REQUEST);
    const handle = startConditionalGet(options, vi.fn());
    await handle.done;
    expect(options).not.toHaveBeenCalled();
    expect(get).not.toHaveBeenCalled();
  });
});

describe("modal get and errors", () => {
  it("maps NotAllowedError / InvalidStateError / AbortError", async () => {
    get.mockRejectedValue(new DOMException("no", "NotAllowedError"));
    await expect(getPasskey(REQUEST)).rejects.toMatchObject({ kind: "cancelled" });
    expect(passkeyErrorKind(new DOMException("x", "InvalidStateError"))).toBe("exists");
    expect(passkeyErrorKind(new DOMException("x", "AbortError"))).toBe("aborted");
    expect(passkeyErrorKind(new Error("boom"))).toBe("failed");
    expect(passkeyErrorKey("cancelled", "signin")).toBe("auth.passkey.cancelled");
    expect(passkeyErrorKey("cancelled", "add")).toBe("auth.passkey.addCancelled");
    expect(passkeyErrorKey("exists", "add")).toBe("auth.passkey.addExists");
    expect(passkeyErrorKey("failed", "signin")).toBe("auth.passkey.failed");
  });
});

describe("Conditional Create", () => {
  it("is silent on failure (resolves null, never throws)", async () => {
    (globalThis.PublicKeyCredential as unknown as Record<string, unknown>).getClientCapabilities = vi.fn(async () => ({ conditionalCreate: true }));
    create.mockRejectedValue(new DOMException("no", "NotAllowedError"));
    await expect(conditionalCreate(async () => CREATION)).resolves.toBeNull();
    expect((create.mock.calls[0][0] as CredentialCreationOptions & { mediation?: string }).mediation).toBe("conditional");
    const options = vi.fn(async () => {
      throw new Error("server said no");
    });
    await expect(conditionalCreate(options)).resolves.toBeNull();
  });
  it("is not attempted without the capability", async () => {
    const options = vi.fn(async () => CREATION);
    await expect(conditionalCreate(options)).resolves.toBeNull();
    expect(options).not.toHaveBeenCalled();
    expect(create).not.toHaveBeenCalled();
  });
});

describe("Signal API", () => {
  it("calls the signals when present and swallows their errors", async () => {
    const unknown = vi.fn(async () => {
      throw new Error("nope");
    });
    const all = vi.fn(async () => undefined);
    Object.assign(globalThis.PublicKeyCredential as object, { signalUnknownCredential: unknown, signalAllAcceptedCredentials: all });
    await expect(signalUnknown("localhost", "AQIDBA")).resolves.toBe(true);
    expect(unknown).toHaveBeenCalledWith({ rpId: "localhost", credentialId: "AQIDBA" });
    await signalAccepted("localhost", "BQYH", ["AQIDBA"]);
    expect(all).toHaveBeenCalledWith({ rpId: "localhost", userId: "BQYH", allAcceptedCredentialIds: ["AQIDBA"] });
  });
  it("is a no-op without the API", async () => {
    await expect(signalUnknown("localhost", "AQIDBA")).resolves.toBe(false);
  });
});

describe("AAGUID", () => {
  it("reads the 16 bytes after rpIdHash, flags and counter", () => {
    const auth = new Uint8Array(37 + 16);
    auth.set([0xea, 0x9b, 0x8d, 0x66, 0x4d, 0x01, 0x1d, 0x21, 0x3c, 0xe4, 0xb6, 0xb4, 0x8c, 0xb5, 0x75, 0xd4], 37);
    expect(aaguidFromAuthData(auth.buffer)).toBe("ea9b8d66-4d01-1d21-3ce4-b6b48cb575d4");
    expect(aaguidFromAuthData(new Uint8Array(10).buffer)).toBeNull();
  });
});
