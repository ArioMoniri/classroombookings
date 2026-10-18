/**
 * Voice input error codes and their Turkish / English copy (`voice.error.*`, research §3.7). One function turns
 * whatever went wrong — a `getUserMedia` DOMException, the site's Permissions-Policy, a coded backend refusal —
 * into one code; the UI shows `voice.error.<code>` with its params. No React here (vitest: voice-errors.test.ts).
 */
import { HttpError } from "@/lib/api/client";

export const VOICE_ERRORS = [
  "permission_denied",
  "policy_blocked",
  "no_device",
  "device_busy",
  "insecure",
  "unsupported",
  "too_long",
  "empty",
  "consent_required",
  "ai_voice_limit_reached",
  "voice_off",
  "not_configured",
  "ai_transfer_basis_missing",
  "not_permitted",
  "unsupported_audio",
  "rate_limited",
  "ai_budget_exceeded",
  "truncated",
  "provider_error",
] as const;
export type VoiceErrorCode = (typeof VOICE_ERRORS)[number];

export interface VoiceError {
  code: VoiceErrorCode;
  params?: Record<string, string | number>;
}

/** `false` when the page's Permissions-Policy turns the microphone off (`microphone=()`); `null` when unknown. */
export function micAllowedByPolicy(doc: Document | undefined = typeof document === "undefined" ? undefined : document): boolean | null {
  if (!doc) return null;
  const d = doc as Document & { permissionsPolicy?: { allowsFeature(f: string): boolean }; featurePolicy?: { allowsFeature(f: string): boolean } };
  const policy = d.permissionsPolicy ?? d.featurePolicy;
  if (!policy || typeof policy.allowsFeature !== "function") return null;
  try {
    return policy.allowsFeature("microphone");
  } catch {
    return null;
  }
}

/** Why recording cannot start before we even ask (no secure context, no API, the site policy), else null. */
export function preflightError(win: (Window & typeof globalThis) | undefined = typeof window === "undefined" ? undefined : window): VoiceError | null {
  if (!win) return { code: "unsupported" };
  if (win.isSecureContext === false) return { code: "insecure" };
  if (micAllowedByPolicy(win.document) === false) return { code: "policy_blocked" };
  if (!win.navigator.mediaDevices?.getUserMedia || typeof win.MediaRecorder === "undefined") return { code: "unsupported" };
  return null;
}

/** A `getUserMedia` / `MediaRecorder` failure. Chromium answers a policy block with NotAllowedError too, so the
 *  policy is checked again to tell it apart from the user's "Block". */
export function mediaError(e: unknown, doc?: Document): VoiceError {
  const name = e && typeof e === "object" && "name" in e ? String((e as { name: unknown }).name) : "";
  if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") {
    return { code: micAllowedByPolicy(doc) === false ? "policy_blocked" : "permission_denied" };
  }
  if (name === "NotFoundError" || name === "OverconstrainedError" || name === "DevicesNotFoundError") return { code: "no_device" };
  if (name === "NotReadableError" || name === "TrackStartError" || name === "AbortError") return { code: "device_busy" };
  if (name === "NotSupportedError" || name === "TypeError") return { code: "unsupported" };
  return { code: "provider_error" };
}

/** `detail.code` of `POST /ai/voice/transcribe` (VO-B API.md §2) → the code shown. */
const SERVER_CODES: Record<string, VoiceErrorCode> = {
  voice_consent_required: "consent_required",
  ai_voice_limit_reached: "ai_voice_limit_reached",
  too_long: "too_long",
  too_large: "too_long",
  voice_not_configured: "not_configured",
  not_permitted: "not_permitted",
  unknown_target: "not_permitted",
  ai_transfer_basis_missing: "ai_transfer_basis_missing",
  empty_audio: "empty",
  unsupported_audio: "unsupported_audio",
  rate_limited: "rate_limited",
  too_many_concurrent: "rate_limited",
  ai_budget_exceeded: "ai_budget_exceeded",
  provider_error: "provider_error",
};

/** The `{code, …}` of a FastAPI error body, `detail` nested or not. */
function detailOf(e: HttpError): Record<string, unknown> {
  const outer = (e.detail && typeof e.detail === "object" ? e.detail : {}) as Record<string, unknown>;
  return (outer.detail && typeof outer.detail === "object" ? outer.detail : outer) as Record<string, unknown>;
}

/** A failed `POST /ai/voice/transcribe` → one code (+ params). Unknown codes are a provider error. */
export function serverError(e: unknown, maxSeconds: number): VoiceError {
  if (!(e instanceof HttpError)) return { code: "provider_error" };
  const d = detailOf(e);
  const raw = typeof d.code === "string" ? d.code : "";
  // nginx answers an oversized body with a 413 page and no JSON
  const code = SERVER_CODES[raw] ?? (e.status === 413 ? "too_long" : e.status === 429 ? "rate_limited" : "provider_error");
  if (code === "too_long") return { code, params: { n: Number(d.max_seconds ?? maxSeconds) } };
  if (code === "ai_voice_limit_reached") {
    const used = Number(d.used_min ?? NaN);
    const limit = Number(d.limit_min ?? NaN);
    const scope = String(d.scope ?? "user_daily");
    return Number.isFinite(used) && Number.isFinite(limit) ? { code, params: { used, limit, scope } } : { code, params: { scope } };
  }
  return { code };
}

/** The message key of a code. The limit without numbers has its own shorter sentence. */
export function errorKey(err: VoiceError): string {
  if (err.code === "ai_voice_limit_reached") {
    if (err.params?.scope === "org_audio") return "voice.error.ai_voice_limit_reached_org";
    if (err.params?.used === undefined || err.params?.limit === undefined) return "voice.error.ai_voice_limit_reached_plain";
    if (err.params?.scope === "user_monthly") return "voice.error.ai_voice_limit_reached_month";
  }
  return `voice.error.${err.code}`;
}

/** Browser-specific steps to turn the microphone back on (the permission-denied state). */
export function permissionHelpKey(ua: string = typeof navigator === "undefined" ? "" : navigator.userAgent): "voice.help.firefox" | "voice.help.safari" | "voice.help.chrome" {
  if (/firefox|fxios/i.test(ua)) return "voice.help.firefox";
  if (/safari/i.test(ua) && !/chrome|crios|chromium|edg/i.test(ua)) return "voice.help.safari";
  return "voice.help.chrome";
}
