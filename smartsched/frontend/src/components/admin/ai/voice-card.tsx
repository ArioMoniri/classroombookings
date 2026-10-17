"use client";
/**
 * Yapay zekâ › Koruma › Ses (VO-07): one switch that turns voice input on for everybody (`PUT /ai/admin/voice`,
 * shared by all administrators, audited), the two promises that cannot be switched off (the text is always shown
 * before it is sent; no recording is kept), and the rest behind "Gelişmiş": consent on first use, the longest
 * recording, in-house only, the vocabulary hint and on-device live captions. Without a speech route the card says
 * where to choose one. A backend without voice (404) shows nothing.
 */
import { Lock, Save } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Alert, Field, Loading } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { useAiRoutes } from "@/lib/api/ai-admin";
import { HttpError } from "@/lib/api/client";
import { useSaveVoiceSettings, useVoiceSettings, VOICE_VOCABULARY, type VoiceSettings } from "@/lib/api/voice";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { errorMessage } from "./ai-model";

export function VoiceCard({ canEdit }: { canEdit: boolean }) {
  const { t, locale } = useI18n();
  const q = useVoiceSettings();
  if (q.isLoading) return <Loading />;
  if (q.error instanceof HttpError && q.error.status === 404) return null;
  if (!q.data) return <Alert tone="error">{errorMessage(q.error, locale, t("aiAdmin.error.load"))}</Alert>;
  return <VoiceForm data={q.data} canEdit={canEdit} />;
}

function VoiceForm({ data, canEdit }: { data: VoiceSettings; canEdit: boolean }) {
  const { t, locale } = useI18n();
  const uid = useId();
  const save = useSaveVoiceSettings();
  const routes = useAiRoutes();
  const eff = routes.data?.effective.voice_stt;
  const noRoute = routes.data ? !eff || eff.source === "none" || !eff.provider : false;
  const [adv, setAdv] = useState({
    consent_required: data.consent_required,
    max_seconds: String(data.max_seconds),
    local_only: data.local_only,
    vocabulary: data.vocabulary,
    live_captions: data.live_captions,
  });
  const [error, setError] = useState<string | null>(null);
  const fail = (e: unknown) => setError(errorMessage(e, locale, t("aiAdmin.error.save")));

  const submit = () => {
    setError(null);
    const secs = Number(adv.max_seconds);
    if (!Number.isInteger(secs) || secs < 10 || secs > 120) return setError(t("voice.admin.card.invalidSeconds"));
    save.mutate({ ...adv, max_seconds: secs }, { onSuccess: () => toast.success(t("voice.admin.card.saved")), onError: fail });
  };

  return (
    <Card className="gap-3 px-4 py-4" data-testid="ai-voice-card">
      <h3 className="type-headline text-label-1">{t("voice.admin.card.title")}</h3>
      <p className="type-footnote text-label-2">{t("voice.admin.card.lead")}</p>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <Label htmlFor={`${uid}-on`} className="type-callout font-medium text-label-1">
            {t("voice.admin.card.enabled")}
          </Label>
          <p className="type-footnote text-label-2">{t("voice.admin.card.enabledHint")}</p>
        </div>
        <Switch
          id={`${uid}-on`}
          checked={data.enabled}
          disabled={!canEdit || save.isPending}
          onCheckedChange={(v) => save.mutate({ enabled: v }, { onSuccess: () => toast.success(t("voice.admin.card.saved")), onError: fail })}
          data-testid="ai-voice-enabled"
        />
      </div>
      {noRoute ? (
        <Alert tone="warning" testId="ai-voice-no-route">
          {t("voice.admin.card.noRoute")}{" "}
          <Link href="/admin/ai?tab=models" className="font-medium text-tint-text underline-offset-4 hover:underline pointer-coarse:inline-block pointer-coarse:min-h-11 pointer-coarse:py-3">
            {t("aiAdmin.tab.models")}
          </Link>
        </Alert>
      ) : null}
      <ul className="flex flex-col gap-1.5">
        {(["review", "retention"] as const).map((k) => (
          <li key={k} className="flex items-start gap-2 type-callout text-label-1">
            <Lock aria-hidden className="mt-0.5 size-4 shrink-0 text-label-2" />
            <span>{t(`voice.admin.card.${k}` as MessageKey)}</span>
          </li>
        ))}
      </ul>
      <details className="rounded-lg bg-fill-3 px-3 py-2" data-testid="ai-voice-advanced">
        <summary className="cursor-pointer py-1 type-callout font-medium text-label-1 pointer-coarse:min-h-11 pointer-coarse:py-3">{t("voice.admin.card.advanced")}</summary>
        <div className="mt-2 flex flex-col divide-y divide-hairline">
          {(["consent_required", "local_only"] as const).map((k) => (
            <div key={k} className="flex items-start justify-between gap-4 py-3">
              <div className="min-w-0">
                <Label htmlFor={`${uid}-${k}`} className="type-callout font-medium text-label-1">
                  {t(k === "consent_required" ? "voice.admin.card.consent" : "voice.admin.card.localOnly")}
                </Label>
                <p className="type-footnote text-label-2">{t(k === "consent_required" ? "voice.admin.card.consentHint" : "voice.admin.card.localOnlyHint")}</p>
              </div>
              <Switch id={`${uid}-${k}`} checked={adv[k]} disabled={!canEdit} onCheckedChange={(v) => setAdv((x) => ({ ...x, [k]: v }))} data-testid={`ai-voice-${k}`} />
            </div>
          ))}
          <div className="grid gap-3 py-3 sm:grid-cols-3">
            <Field label={t("voice.admin.card.maxSeconds")} htmlFor={`${uid}-max`} hint={t("voice.admin.card.maxSecondsHint")}>
              <Input id={`${uid}-max`} inputMode="numeric" value={adv.max_seconds} disabled={!canEdit} onChange={(e) => setAdv((x) => ({ ...x, max_seconds: e.target.value }))} data-testid="ai-voice-max" />
            </Field>
            <Field label={t("voice.admin.card.vocabulary")} htmlFor={`${uid}-vocab`} hint={t("voice.admin.card.vocabularyHint")}>
              <NativeSelect id={`${uid}-vocab`} value={adv.vocabulary} disabled={!canEdit} onChange={(e) => setAdv((x) => ({ ...x, vocabulary: e.target.value as VoiceSettings["vocabulary"] }))}>
                {VOICE_VOCABULARY.map((v) => (
                  <option key={v} value={v}>
                    {t(`voice.admin.card.vocab.${v}` as MessageKey)}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label={t("voice.admin.card.captions")} htmlFor={`${uid}-cap`} hint={t("voice.admin.card.captionsHint")}>
              <NativeSelect id={`${uid}-cap`} value={adv.live_captions} disabled={!canEdit} onChange={(e) => setAdv((x) => ({ ...x, live_captions: e.target.value as VoiceSettings["live_captions"] }))}>
                {(["on_device", "off"] as const).map((v) => (
                  <option key={v} value={v}>
                    {t(`voice.admin.card.captionsMode.${v}` as MessageKey)}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          </div>
          {canEdit ? (
            <div className="py-3">
              <Button variant="outline" onClick={submit} {...busyProps(save.isPending)} data-testid="ai-voice-save">
                <BusyLabel busy={save.isPending} label={t("busy.saving")} icon={<Save aria-hidden />}>
                  {t("voice.admin.card.save")}
                </BusyLabel>
              </Button>
            </div>
          ) : null}
        </div>
      </details>
      {error ? (
        <Alert tone="error" testId="ai-voice-error">
          {error}
        </Alert>
      ) : null}
    </Card>
  );
}
