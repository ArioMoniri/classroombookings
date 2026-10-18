/**
 * F-VO-1 (fix-c-2026-10-18): the backend's `ProviderError` texts are English ("Deepgram rejected the API key
 * (authentication error)", app/ai/providers/openai_compat.py `_status_text`, app/ai/voice/*.py). Shown as they are,
 * they sat inside the Turkish sentence ("Test başarısız: Deepgram rejected…"). They are mapped here to one code each,
 * and the UI shows `aiAdmin.provider.failure.<code>` in the reader's language. No React here.
 */
import type { MessageKey } from "@/lib/i18n";

export const PROVIDER_FAILURES = [
  "auth",
  "permission",
  "not_found",
  "rate_limited",
  "bad_request",
  "timeout",
  "unreachable",
  "bad_answer",
  "declined",
  "no_key",
  "config",
  "not_speech",
  "server",
  "unknown",
] as const;
export type ProviderFailureCode = (typeof PROVIDER_FAILURES)[number];

/** first match wins; the patterns follow the backend's wording, which is stable (tests pin it) */
const PATTERNS: [RegExp, ProviderFailureCode][] = [
  [/rejected the API key|authentication|unauthori[sz]ed|invalid api key/i, "auth"],
  [/lacks permission|forbidden|permission denied/i, "permission"],
  [/not found/i, "not_found"],
  [/rate limit|too many requests/i, "rate_limited"],
  [/rejected the request|bad request/i, "bad_request"],
  [/did not answer in time|timed? ?out/i, "timeout"],
  [/could not reach|connection|unreachable/i, "unreachable"],
  [/not JSON|not a JSON|without a transcript|not a transcript/i, "bad_answer"],
  [/declined/i, "declined"],
  [/no API key|no credentials/i, "no_key"],
  [/needs a base URL|needs the .*project|location must|base url/i, "config"],
  [/cannot transcribe speech/i, "not_speech"],
  [/API error \d{3}/i, "server"],
];

export function providerFailure(detail: string | null | undefined): { code: ProviderFailureCode; status?: number } {
  const text = (detail ?? "").trim();
  for (const [re, code] of PATTERNS) {
    if (!re.test(text)) continue;
    if (code === "server") {
      const status = Number(/API error (\d{3})/i.exec(text)?.[1]);
      return Number.isFinite(status) ? { code, status } : { code };
    }
    return { code };
  }
  return { code: "unknown" };
}

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** The reader's sentence for a provider failure (`{detail}` of "Test başarısız: {detail}"). */
export function providerFailureText(detail: string | null | undefined, t: T): string {
  const f = providerFailure(detail);
  return t(`aiAdmin.provider.failure.${f.code}` as MessageKey, f.status ? { status: f.status } : undefined);
}
