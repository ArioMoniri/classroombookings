/**
 * F-VO-1 (fix-c-2026-10-18): a provider's English failure text (`ProviderError`, e.g. "Deepgram rejected the API key
 * (authentication error)") is never put inside the Turkish sentence. It is mapped to a code with its own Turkish
 * and English text (`aiAdmin.provider.failure.<code>`).
 */
import { describe, expect, it } from "vitest";
import { translate, type MessageKey } from "@/lib/i18n";
import { PROVIDER_FAILURES, providerFailure, providerFailureText } from "./provider-failure";

const tr = (k: MessageKey, v?: Record<string, string | number>) => translate("tr", k, v);
const en = (k: MessageKey, v?: Record<string, string | number>) => translate("en", k, v);

describe("provider failure codes", () => {
  it.each([
    ["Deepgram rejected the API key (authentication error)", "auth"],
    ["the OpenAI key lacks permission for this model", "permission"],
    ["Gemini: model or endpoint not found", "not_found"],
    ["rate limited by Deepgram; retry later", "rate_limited"],
    ["Azure AI Speech rejected the request (bad request)", "bad_request"],
    ["Deepgram did not answer in time", "timeout"],
    ["could not reach Deepgram (ConnectError)", "unreachable"],
    ["Deepgram answered something that is not JSON", "bad_answer"],
    ["the provider answered without a transcript", "bad_answer"],
    ["Gemini declined to transcribe this recording", "declined"],
    ["no API key configured for Deepgram", "no_key"],
    ["Google Speech-to-Text needs the Google Cloud project id", "config"],
    ["anthropic cannot transcribe speech", "not_speech"],
    ["Deepgram API error 503", "server"],
    ["could not complete the test call (KeyError)", "unknown"],
    ["", "unknown"],
  ])("%s → %s", (detail, code) => {
    expect(providerFailure(detail).code).toBe(code);
  });

  it("every code has Turkish and English text, and the Turkish sentence carries no provider English", () => {
    for (const code of PROVIDER_FAILURES) {
      expect(tr(`aiAdmin.provider.failure.${code}` as MessageKey)).not.toBe(`aiAdmin.provider.failure.${code}`);
      expect(en(`aiAdmin.provider.failure.${code}` as MessageKey)).not.toBe(`aiAdmin.provider.failure.${code}`);
    }
    const text = providerFailureText("Deepgram rejected the API key (authentication error)", tr);
    expect(text).toBe("Sağlayıcı API anahtarını kabul etmedi. Anahtarı denetleyin.");
    expect(text).not.toMatch(/rejected|authentication/);
    expect(providerFailureText("Deepgram API error 503", tr)).toBe("Sağlayıcı bir hata döndürdü (503).");
  });
});
