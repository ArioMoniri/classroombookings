"use client";
/**
 * Voice input (VO-03 / VO-04, docs/research/2026-10-17-voice-ai.md §3). Speech becomes text through an
 * admin-moderated cloud speech API (owner decision 2026-10-18: no local Whisper, never the browser's cloud Web
 * Speech); the text lands in the box the user would type in and is sent, after review, through the same endpoint
 * and guardrails as typed text.
 *
 * Every signed-in user:
 * - `GET /ai/voice/status` → `{available, reason, consent, provider_local, provider_label, region, max_seconds,
 *   max_seconds_by_target, live_captions}`. `reason` says why voice is unavailable: config reasons hide the mic
 *   (see {@link hidesMic}); `consent_required` opens the consent sheet first.
 * - `POST /ai/voice/transcribe` multipart `audio`, `feature` (chat | rules | booking_nl | guard), `lang` (tr | en)
 *   → `{text, duration_s, language, provider_local, warnings}`. Errors `{code, message_tr, message_en}`: 403
 *   `voice_consent_required`, 403/409 `voice_disabled`, 409 `ai_transfer_basis_missing`, 413 `too_long` /
 *   `too_large`, 415 `unsupported_audio`, 429 `ai_voice_limit_reached` (`used_min`, `limit_min`), 502
 *   `provider_error`.
 * - `POST /me/consents/voice` / `DELETE /me/consents/voice` (KVKK purpose `voice`).
 *
 * Administrators (`planning.admin` / `setup.settings`): `GET/PUT /ai/admin/voice` (the settings below, shared by all
 * administrators through the `settings` table; audited `ai.voice_update`).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./client";

const s = { silent: true } as const;

export const VOICE_TARGETS = ["chat", "rules", "booking_nl", "guard"] as const;
export type VoiceTarget = (typeof VOICE_TARGETS)[number];

/** `consent` arrives as a boolean or as a state word (`granted | withdrawn | never`); both read as "given now?". */
const ConsentFlag = z
  .union([z.boolean(), z.string(), z.null()])
  .transform((v) => v === true || v === "granted" || v === "active")
  .default(false);

export const VoiceStatus = z.object({
  available: z.boolean(),
  reason: z.string().nullish(),
  consent: ConsentFlag,
  consent_required: z.boolean().default(true),
  provider_local: z.boolean().default(false),
  provider_label: z.string().nullish(),
  region: z.string().nullish(),
  max_seconds: z.number().int().positive().default(120),
  max_seconds_by_target: z.record(z.string(), z.number()).default({}),
  live_captions: z.enum(["on_device", "off"]).catch("off").default("off"),
  send_directly: z.boolean().default(false),
});
export type VoiceStatus = z.infer<typeof VoiceStatus>;

export const Transcript = z.object({
  text: z.string(),
  duration_s: z.number().nullish(),
  language: z.string().nullish(),
  provider_local: z.boolean().default(false),
  warnings: z.array(z.union([z.string(), z.object({ code: z.string() }).passthrough()])).default([]),
});
export type Transcript = z.infer<typeof Transcript>;

/** Reasons the mic stays visible while voice is unavailable: the consent sheet asks first, or the limit is shown
 * as a disabled mic with its sentence. Every other reason (voice off, no model, no permission, local only, no
 * transfer record) means "voice is not set up for you here" and the mic is not rendered at all. */
const SHOWN_REASONS = new Set(["consent_required", "voice_consent_required", "ai_voice_limit_reached"]);

/** Hide the mic: voice off or not set up for this user, or the status cannot be read (no voice backend). */
export function hidesMic(status: VoiceStatus | undefined, error: unknown): boolean {
  if (error || !status) return true;
  if (status.available) return false;
  return !SHOWN_REASONS.has(status.reason ?? "");
}

/** The cap for one clip on this surface (booking_nl is shorter so its transcript fits the field). */
export function maxSecondsFor(status: VoiceStatus | undefined, target: VoiceTarget): number {
  const base = status?.max_seconds ?? 120;
  const t = status?.max_seconds_by_target?.[target];
  return t && t > 0 ? Math.min(base, t) : base;
}

/** The user must agree (the consent sheet) before the first recording. */
export function needsConsent(status: VoiceStatus | undefined): boolean {
  if (!status) return false;
  return status.reason === "consent_required" || status.reason === "voice_consent_required" || (status.consent_required && !status.consent);
}

export const VOICE_VOCABULARY = ["catalog", "off"] as const;
export const VoiceSettings = z.object({
  enabled: z.boolean().default(false),
  consent_required: z.boolean().default(true),
  max_seconds: z.number().int().default(120),
  max_seconds_by_target: z.record(z.string(), z.number()).default({}),
  retention_days: z.number().default(0),
  local_only: z.boolean().default(false),
  vocabulary: z.enum(VOICE_VOCABULARY).catch("catalog").default("catalog"),
  live_captions: z.enum(["on_device", "off"]).catch("off").default("off"),
  send_directly: z.boolean().default(false),
  tts_enabled: z.boolean().default(false),
});
export type VoiceSettings = z.infer<typeof VoiceSettings>;
export type VoiceSettingsIn = Partial<Omit<VoiceSettings, "retention_days">>;

export const voiceApi = {
  status: () => request("/ai/voice/status", { schema: VoiceStatus, ...s }),
  transcribe: (audio: Blob, target: VoiceTarget, lang: "tr" | "en", signal?: AbortSignal) => {
    const fd = new FormData();
    const ext = audio.type.includes("mp4") ? "m4a" : audio.type.includes("ogg") ? "ogg" : "webm";
    fd.append("audio", audio, `voice.${ext}`);
    fd.append("feature", target);
    fd.append("lang", lang);
    return request("/ai/voice/transcribe", { method: "POST", formData: fd, schema: Transcript, signal, ...s });
  },
  grantConsent: () => request("/me/consents/voice", { method: "POST", ...s }),
  settings: () => request("/ai/admin/voice", { schema: VoiceSettings, ...s }),
  saveSettings: (body: VoiceSettingsIn) => request("/ai/admin/voice", { method: "PUT", body, schema: VoiceSettings, ...s }),
};

export const voiceKeys = {
  status: ["ai-voice", "status"] as const,
  settings: ["ai-admin", "voice"] as const,
};

/** The mic's status; one request per page (5 min stale), no retry: a missing voice backend just hides the mic. */
export const useVoiceStatus = (enabled = true) => useQuery({ queryKey: voiceKeys.status, queryFn: voiceApi.status, enabled, staleTime: 300_000, retry: false });

export function useGrantVoiceConsent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: voiceApi.grantConsent,
    onSuccess: () => {
      qc.setQueryData<VoiceStatus>(voiceKeys.status, (old) => (old ? { ...old, consent: true, available: old.available || needsConsent(old), reason: needsConsent(old) ? null : old.reason } : old));
      void qc.invalidateQueries({ queryKey: voiceKeys.status });
    },
  });
}

export const useVoiceSettings = () => useQuery({ queryKey: voiceKeys.settings, queryFn: voiceApi.settings });
export function useSaveVoiceSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: voiceApi.saveSettings,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["ai-admin"] });
      void qc.invalidateQueries({ queryKey: ["ai-voice"] });
    },
  });
}
