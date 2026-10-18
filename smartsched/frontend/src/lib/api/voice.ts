"use client";
/**
 * Voice input (VO-03 / VO-04; contract from lane VO-B, 2026-10-18; design in docs/research/2026-10-17-voice-ai.md §3).
 * Speech becomes text through an admin-moderated cloud speech API (owner decision 2026-10-18: no on-prem Whisper,
 * never the browser's cloud Web Speech). The text lands in the box the user would type in and is sent, after review,
 * through the box's own endpoint and guardrails. There is no "send directly": review is always required.
 *
 * Every signed-in user:
 * - `GET /ai/voice/status` → `{available, reason, hide_mic, consent, targets[], provider_label(_en), region,
 *   max_seconds, live_captions, usage {day_s, day_limit_s, month_s, month_limit_s}, …}`. `reason` in order:
 *   `not_configured | disabled | provider_unusable | transfer_basis_missing` (hide_mic) · `not_permitted` (targets
 *   empty) · `consent_required` (the first press opens the consent sheet) · `limit_reached` (a disabled mic with the
 *   minutes). The mic shows only on a surface whose target is in `targets`.
 * - `POST /ai/voice/transcribe?feature=<chat|rules|guard>&lang=<tr|en>` with the **raw clip** as the body and its
 *   `Content-Type` → `{text, duration_s, language, provider, model, target, review_required, warnings[]}`
 *   (`warnings`: `empty`, `truncated`). Errors `{detail: {code, message_tr, message_en, …}}`: see
 *   components/voice/voice-errors.ts.
 * - `POST /me/consents/voice` / `DELETE /me/consents/voice` (KVKK purpose `voice`).
 *
 * Administrators (`planning.admin` / `setup.settings`): `GET/PUT /ai/admin/voice` → `{settings {enabled, language,
 * max_seconds, vocabulary, live_captions, prices_per_min}, fixed {retention_days, review_before_send, max_seconds_cap,
 * consent}, route {provider, model, source, label_tr, label_en, usable, transfer_ok}, languages, vocabulary_options,
 * live_captions_options}`; `PUT` takes any subset of `settings` (audited `ai.voice`, one shared settings row).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { buildUrl, HttpError, request } from "./client";

const s = { silent: true } as const;

export const VOICE_TARGETS = ["chat", "rules", "guard"] as const;
export type VoiceTarget = (typeof VOICE_TARGETS)[number];

const Usage = z.object({ day_s: z.number().default(0), day_limit_s: z.number().default(0), month_s: z.number().default(0), month_limit_s: z.number().default(0) });

export const VoiceStatus = z.object({
  available: z.boolean(),
  reason: z.string().nullish(),
  hide_mic: z.boolean().default(false),
  consent: z.boolean().default(false),
  targets: z.array(z.string()).nullish(),
  provider_label: z.string().nullish(),
  provider_label_en: z.string().nullish(),
  region: z.string().nullish(),
  max_seconds: z.number().int().positive().default(120),
  live_captions: z.enum(["on_device", "off"]).catch("off").default("off"),
  usage: Usage.nullish(),
});
export type VoiceStatus = z.infer<typeof VoiceStatus>;

export const Transcript = z.object({
  text: z.string(),
  duration_s: z.number().nullish(),
  language: z.string().nullish(),
  warnings: z.array(z.string()).default([]),
});
export type Transcript = z.infer<typeof Transcript>;

/** Hide the mic: voice not set up (or not for this surface / person), or the status cannot be read (no voice backend). */
export function hidesMic(status: VoiceStatus | undefined, error: unknown, target?: VoiceTarget): boolean {
  if (error || !status) return true;
  if (status.hide_mic) return true;
  if (target && status.targets && !status.targets.includes(target)) return true;
  if (status.available) return false;
  return status.reason !== "consent_required" && status.reason !== "limit_reached";
}

/** The user must agree (the consent sheet) before the first recording. */
export function needsConsent(status: VoiceStatus | undefined): boolean {
  return !!status && (status.reason === "consent_required" || !status.consent);
}

/** The limit that stopped voice for today / this month, in whole minutes (for "{used}/{limit} dk"). */
export function limitMinutes(status: VoiceStatus | undefined): { used: number; limit: number; month: boolean } | null {
  const u = status?.usage;
  if (!u) return null;
  const day = u.day_limit_s > 0 && u.day_s >= u.day_limit_s;
  const [used, limit] = day ? [u.day_s, u.day_limit_s] : [u.month_s, u.month_limit_s];
  if (!(limit > 0)) return null;
  return { used: Math.round(used / 60), limit: Math.round(limit / 60), month: !day };
}

export const VOICE_VOCABULARY = ["catalog", "off"] as const;
export const VOICE_CAPTIONS = ["on_device", "off"] as const;
export const VoiceSettings = z.object({
  enabled: z.boolean().default(false),
  language: z.string().default("tr"),
  max_seconds: z.number().int().default(120),
  vocabulary: z.enum(VOICE_VOCABULARY).catch("catalog").default("catalog"),
  live_captions: z.enum(VOICE_CAPTIONS).catch("off").default("off"),
});
export type VoiceSettings = z.infer<typeof VoiceSettings>;
export const VoiceAdmin = z.object({
  settings: VoiceSettings,
  fixed: z.object({ retention_days: z.number().default(0), review_before_send: z.boolean().default(true), max_seconds_cap: z.number().default(120) }).partial().default({}),
  route: z
    .object({ provider: z.string().nullish(), model: z.string().nullish(), source: z.string().nullish(), label_tr: z.string().nullish(), label_en: z.string().nullish(), usable: z.boolean().nullish(), transfer_ok: z.boolean().nullish() })
    .nullish(),
  languages: z.array(z.string()).default(["tr", "en"]),
});
export type VoiceAdmin = z.infer<typeof VoiceAdmin>;
export type VoiceSettingsIn = Partial<VoiceSettings>;

/** The admin route is in place and usable (else the card points to Modeller). */
export function voiceRouteReady(v: VoiceAdmin | undefined): boolean {
  const r = v?.route;
  return !!r?.provider && !!r.model && r.source !== "none" && r.usable !== false;
}

/** `POST /ai/voice/transcribe`: the clip itself is the body (not multipart), typed by its MIME type. */
async function transcribe(audio: Blob, target: VoiceTarget, lang: "tr" | "en", signal?: AbortSignal): Promise<Transcript> {
  let res: Response;
  try {
    res = await fetch(buildUrl("/ai/voice/transcribe", { feature: target, lang }), {
      method: "POST",
      body: audio,
      headers: { Accept: "application/json", "Content-Type": audio.type || "audio/webm" },
      credentials: "same-origin",
      signal,
    });
  } catch (e) {
    throw new HttpError(0, e instanceof Error ? e.message : "Network error");
  }
  if (!res.ok) {
    let detail: unknown;
    try {
      const j = (await res.json()) as { detail?: unknown };
      detail = j?.detail ?? j;
    } catch {
      // nginx 413 without JSON
    }
    throw new HttpError(res.status, `${res.status} ${res.statusText}`, detail);
  }
  return Transcript.parse(await res.json());
}

export const voiceApi = {
  status: () => request("/ai/voice/status", { schema: VoiceStatus, ...s }),
  transcribe,
  grantConsent: () => request("/me/consents/voice", { method: "POST", ...s }),
  settings: () => request("/ai/admin/voice", { schema: VoiceAdmin, ...s }),
  saveSettings: (body: VoiceSettingsIn) => request("/ai/admin/voice", { method: "PUT", body, schema: VoiceAdmin, ...s }),
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
      qc.setQueryData<VoiceStatus>(voiceKeys.status, (old) => (old ? { ...old, consent: true, available: old.available || old.reason === "consent_required", reason: old.reason === "consent_required" ? null : old.reason } : old));
      void qc.invalidateQueries({ queryKey: voiceKeys.status });
    },
  });
}

export const useVoiceSettings = () => useQuery({ queryKey: voiceKeys.settings, queryFn: voiceApi.settings });
export function useSaveVoiceSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: voiceApi.saveSettings,
    onSuccess: (data) => {
      qc.setQueryData(voiceKeys.settings, data);
      void qc.invalidateQueries({ queryKey: ["ai-voice"] });
    },
  });
}
