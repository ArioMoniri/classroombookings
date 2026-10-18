/**
 * The browser side of passkeys (docs/design/v3/auth.md §4.2, §4.3, §4.6, §6.4; AUX-01). No library: the server
 * (py_webauthn, AU-B) sends `{publicKey: …}` JSON with base64url buffers; this module turns it into the
 * `navigator.credentials` arguments and the answer back into JSON.
 *
 * - `passkeySupport()`: `getClientCapabilities()` where the browser has it, else the older static checks.
 * - `startConditionalGet()`: the identifier field's autofill (`mediation: "conditional"`, empty
 *   `allowCredentials`), cancelled with an AbortController when the form submits or door 2 closes.
 * - `getPasskey()` (modal), `createPasskey()`, `conditionalCreate()` (silent: resolves `null` on any failure).
 * - `signalUnknown()` / `signalAccepted()`: the WebAuthn Signal API, when present; errors are swallowed.
 * - `passkeyErrorKind()` / `passkeyErrorKey()`: DOMException names → the copy keys of §4.6 / §6.4.
 */

/* ---------------------------------------------------------------------------------------------- base64url */

export function bytesToB64url(input: ArrayBuffer | ArrayBufferView): string {
  // ArrayBuffer.isView, not instanceof: buffers from another realm (iframes, jsdom) fail instanceof
  const bytes = ArrayBuffer.isView(input) ? new Uint8Array(input.buffer, input.byteOffset, input.byteLength) : new Uint8Array(input);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** base64url (or standard base64, padded or not) → bytes. */
export function b64urlToBytes(text: string): Uint8Array<ArrayBuffer> {
  const std = text.replace(/-/g, "+").replace(/_/g, "/").replace(/=+$/, "");
  const bin = atob(std + "=".repeat((4 - (std.length % 4)) % 4));
  const out = new Uint8Array(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

const buf = (s: string): ArrayBuffer => b64urlToBytes(s).buffer;

/* ------------------------------------------------------------------------------------- server options JSON */

type Json = Record<string, unknown>;
export type ServerOptions = { publicKey?: Json } | Json;
type Descriptor = { id: string; type?: string; transports?: string[] };

const inner = (o: ServerOptions): Json => ((o as { publicKey?: Json }).publicKey ?? (o as Json)) as Json;
const descriptors = (list: unknown): PublicKeyCredentialDescriptor[] =>
  Array.isArray(list) ? (list as Descriptor[]).map((d) => ({ id: buf(d.id), type: "public-key", ...(d.transports?.length ? { transports: d.transports as AuthenticatorTransport[] } : {}) })) : [];

export function toRequestOptions(options: ServerOptions): PublicKeyCredentialRequestOptions {
  const o = inner(options);
  return {
    ...(o as unknown as PublicKeyCredentialRequestOptions),
    challenge: buf(String(o.challenge)),
    allowCredentials: descriptors(o.allowCredentials),
  };
}

export function toCreationOptions(options: ServerOptions): PublicKeyCredentialCreationOptions {
  const o = inner(options);
  const user = o.user as { id: string; name: string; displayName: string };
  return {
    ...(o as unknown as PublicKeyCredentialCreationOptions),
    challenge: buf(String(o.challenge)),
    user: { ...user, id: buf(user.id) },
    excludeCredentials: descriptors(o.excludeCredentials),
  };
}

/** The credential as the JSON py_webauthn verifies (`id`, `rawId`, `type`, `response.*` base64url). */
export function credentialToJSON(cred: PublicKeyCredential): Json {
  const r = cred.response as AuthenticatorResponse & Partial<AuthenticatorAssertionResponse & AuthenticatorAttestationResponse>;
  const response: Json = { clientDataJSON: bytesToB64url(r.clientDataJSON) };
  if (r.attestationObject) response.attestationObject = bytesToB64url(r.attestationObject);
  if (r.authenticatorData) response.authenticatorData = bytesToB64url(r.authenticatorData);
  if (r.signature) response.signature = bytesToB64url(r.signature);
  if (r.userHandle) response.userHandle = bytesToB64url(r.userHandle);
  if (typeof r.getTransports === "function") {
    try {
      response.transports = r.getTransports();
    } catch {
      /* older browsers */
    }
  }
  return {
    id: cred.id,
    rawId: bytesToB64url(cred.rawId),
    type: cred.type,
    authenticatorAttachment: (cred as PublicKeyCredential & { authenticatorAttachment?: string | null }).authenticatorAttachment ?? undefined,
    response,
    clientExtensionResults: typeof cred.getClientExtensionResults === "function" ? cred.getClientExtensionResults() : {},
  };
}

/** The AAGUID in a registration's authenticator data (bytes 37–52), as a UUID; `null` when absent or all zero. */
export function aaguidFromAuthData(authData: ArrayBuffer | null | undefined): string | null {
  if (!authData || authData.byteLength < 53) return null;
  const b = new Uint8Array(authData, 37, 16);
  if (b.every((x) => x === 0)) return null;
  const hex = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** The AAGUID of a freshly created credential (`getAuthenticatorData()`), or `null`. */
export function aaguidOf(cred: PublicKeyCredential): string | null {
  const r = cred.response as Partial<AuthenticatorAttestationResponse>;
  try {
    return typeof r.getAuthenticatorData === "function" ? aaguidFromAuthData(r.getAuthenticatorData()) : null;
  } catch {
    return null;
  }
}

/* -------------------------------------------------------------------------------------------- detection */

export interface PasskeySupport {
  webauthn: boolean;
  conditionalGet: boolean;
  conditionalCreate: boolean;
  platform: boolean;
}

type PKCStatic = {
  getClientCapabilities?: () => Promise<Record<string, boolean | undefined>>;
  isConditionalMediationAvailable?: () => Promise<boolean>;
  isUserVerifyingPlatformAuthenticatorAvailable?: () => Promise<boolean>;
  signalUnknownCredential?: (o: { rpId: string; credentialId: string }) => Promise<void>;
  signalAllAcceptedCredentials?: (o: { rpId: string; userId: string; allAcceptedCredentialIds: string[] }) => Promise<void>;
};

function pkc(): PKCStatic | null {
  const g = globalThis as unknown as { PublicKeyCredential?: PKCStatic };
  return typeof window !== "undefined" && g.PublicKeyCredential ? g.PublicKeyCredential : null;
}

const NONE: PasskeySupport = { webauthn: false, conditionalGet: false, conditionalCreate: false, platform: false };

export async function passkeySupport(): Promise<PasskeySupport> {
  const P = pkc();
  if (!P || typeof navigator === "undefined" || !navigator.credentials) return NONE;
  try {
    if (typeof P.getClientCapabilities === "function") {
      const c = await P.getClientCapabilities();
      return { webauthn: true, conditionalGet: Boolean(c.conditionalGet), conditionalCreate: Boolean(c.conditionalCreate), platform: Boolean(c.passkeyPlatformAuthenticator ?? c.userVerifyingPlatformAuthenticator) };
    }
  } catch {
    /* fall through to the static checks */
  }
  const safe = async (f?: () => Promise<boolean>) => {
    try {
      return f ? Boolean(await f.call(P)) : false;
    } catch {
      return false;
    }
  };
  return { webauthn: true, conditionalGet: await safe(P.isConditionalMediationAvailable), conditionalCreate: false, platform: await safe(P.isUserVerifyingPlatformAuthenticatorAvailable) };
}

/* -------------------------------------------------------------------------------------------------- errors */

export type PasskeyErrorKind = "cancelled" | "exists" | "aborted" | "failed";

export class PasskeyError extends Error {
  readonly kind: PasskeyErrorKind;
  constructor(kind: PasskeyErrorKind, message?: string) {
    super(message ?? kind);
    this.name = "PasskeyError";
    this.kind = kind;
  }
}

export function passkeyErrorKind(e: unknown): PasskeyErrorKind {
  if (e instanceof PasskeyError) return e.kind;
  const name = (e as { name?: string } | null)?.name;
  if (name === "NotAllowedError") return "cancelled";
  if (name === "InvalidStateError") return "exists";
  if (name === "AbortError") return "aborted";
  return "failed";
}

/** The message key for a failure: sign-in (§4.6) or adding a passkey (§6.4). */
export function passkeyErrorKey(kind: PasskeyErrorKind, where: "signin" | "add"): "auth.passkey.cancelled" | "auth.passkey.failed" | "auth.passkey.addCancelled" | "auth.passkey.addExists" | "auth.passkey.addFailed" {
  if (where === "add") return kind === "exists" ? "auth.passkey.addExists" : kind === "cancelled" || kind === "aborted" ? "auth.passkey.addCancelled" : "auth.passkey.addFailed";
  return kind === "cancelled" || kind === "aborted" ? "auth.passkey.cancelled" : "auth.passkey.failed";
}

/* ---------------------------------------------------------------------------------------------- ceremonies */

/** Modal `get()` (the "Geçiş anahtarıyla giriş yap" button, the second step). Throws a `PasskeyError`. */
export async function getPasskey(options: ServerOptions, signal?: AbortSignal): Promise<Json> {
  if (!pkc()) throw new PasskeyError("failed", "WebAuthn unavailable");
  try {
    const cred = (await navigator.credentials.get({ publicKey: toRequestOptions(options), signal })) as PublicKeyCredential | null;
    if (!cred) throw new PasskeyError("cancelled");
    return credentialToJSON(cred);
  } catch (e) {
    throw e instanceof PasskeyError ? e : new PasskeyError(passkeyErrorKind(e), (e as Error)?.message);
  }
}

/** `create()` with the server's options; the JSON plus the AAGUID (for the provider name, §6.4). */
export async function createPasskey(options: ServerOptions, signal?: AbortSignal): Promise<{ credential: Json; aaguid: string | null }> {
  if (!pkc()) throw new PasskeyError("failed", "WebAuthn unavailable");
  try {
    const cred = (await navigator.credentials.create({ publicKey: toCreationOptions(options), signal })) as PublicKeyCredential | null;
    if (!cred) throw new PasskeyError("cancelled");
    return { credential: credentialToJSON(cred), aaguid: aaguidOf(cred) };
  } catch (e) {
    throw e instanceof PasskeyError ? e : new PasskeyError(passkeyErrorKind(e), (e as Error)?.message);
  }
}

export interface ConditionalHandle {
  abort: () => void;
  /** settles when the request ended (credential, abort or error) */
  done: Promise<void>;
}

/**
 * The identifier field's passkey autofill. `loadOptions` is called only when conditional mediation exists;
 * `onCredential` gets the JSON when the person picks a passkey; an abort is silent, other failures go to `onError`.
 */
export function startConditionalGet(loadOptions: (signal: AbortSignal) => Promise<ServerOptions>, onCredential: (credential: Json) => void, onError?: (kind: PasskeyErrorKind) => void): ConditionalHandle {
  const ctl = new AbortController();
  const done = (async () => {
    const support = await passkeySupport();
    if (!support.conditionalGet || ctl.signal.aborted) return;
    let options: ServerOptions;
    try {
      options = await loadOptions(ctl.signal);
    } catch {
      return; // no options endpoint (offline, switched off): the field stays a plain username field
    }
    if (ctl.signal.aborted) return;
    try {
      const publicKey = { ...toRequestOptions(options), allowCredentials: [] };
      const cred = (await navigator.credentials.get({ publicKey, mediation: "conditional", signal: ctl.signal } as CredentialRequestOptions)) as PublicKeyCredential | null;
      if (cred && !ctl.signal.aborted) onCredential(credentialToJSON(cred));
    } catch (e) {
      if (ctl.signal.aborted) return;
      const kind = passkeyErrorKind(e);
      if (kind !== "aborted") onError?.(kind);
    }
  })();
  return { abort: () => ctl.abort(), done };
}

/**
 * Chrome Conditional Create (§4.3 item 4): after a password sign-in the browser may save a passkey without a
 * prompt. Silent: `null` on a missing capability or any failure, the credential JSON otherwise.
 */
export async function conditionalCreate(loadOptions: () => Promise<ServerOptions>, signal?: AbortSignal): Promise<{ credential: Json; aaguid: string | null } | null> {
  try {
    const support = await passkeySupport();
    if (!support.conditionalCreate) return null;
    const options = await loadOptions();
    const cred = (await navigator.credentials.create({ publicKey: toCreationOptions(options), mediation: "conditional", signal } as CredentialCreationOptions)) as PublicKeyCredential | null;
    return cred ? { credential: credentialToJSON(cred), aaguid: aaguidOf(cred) } : null;
  } catch {
    return null;
  }
}

/* ---------------------------------------------------------------------------------------------- Signal API */

/** The server does not know this credential: let the password manager hide it. `true` when the call was made. */
export async function signalUnknown(rpId: string, credentialId: string): Promise<boolean> {
  const P = pkc();
  if (typeof P?.signalUnknownCredential !== "function") return false;
  try {
    await P.signalUnknownCredential({ rpId, credentialId });
  } catch {
    /* best effort */
  }
  return true;
}

/** After a removal: the credentials still valid for this account (`userId` = the base64url user handle). */
export async function signalAccepted(rpId: string, userId: string, allAcceptedCredentialIds: string[]): Promise<boolean> {
  const P = pkc();
  if (typeof P?.signalAllAcceptedCredentials !== "function") return false;
  try {
    await P.signalAllAcceptedCredentials({ rpId, userId, allAcceptedCredentialIds });
  } catch {
    /* best effort */
  }
  return true;
}
