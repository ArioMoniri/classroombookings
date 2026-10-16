"use client";
/**
 * Yönetim › KVKK › Yapay zekâ ve kişisel veri (consent gates 2026-10-16): what a never-given `ai_personal` consent
 * means for the whole institution, `kvkk.ai_personal_default`:
 * - `included` (the default, how SmartSched always worked): only a person who withdrew the consent is replaced with
 *   a placeholder in AI requests;
 * - `excluded`: "not granted = excluded", only a person who gave the consent appears by name.
 * Read from `GET /settings`, saved with `PUT /settings {extra: {"kvkk.ai_personal_default": …}}` (role ADMIN; the
 * backend audits it as a tracked setting). A 422 `message_tr` / `message_en` is shown next to the field. Saving
 * refreshes everyone's Gizlilik text (`GET /me/privacy` `ai_personal_default`, `ai_excluded`).
 */
import { useId, useState } from "react";
import { toast } from "sonner";
import { Alert, Loading } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { AI_DEFAULTS, useAiDefault, useSaveAiDefault, type AiDefault } from "@/lib/api/kvkk";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";

export function AiDefaultEditor() {
  const { t, locale } = useI18n();
  const q = useAiDefault();
  const save = useSaveAiDefault();
  const name = useId();
  const errId = useId();
  const [picked, setPicked] = useState<AiDefault | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stored = q.data ?? null;
  const value = picked ?? stored;
  const dirty = !!picked && picked !== stored;
  const forbidden = q.isError && wave1Error(q.error).status === 403;

  const submit = () => {
    if (!picked) return;
    setError(null);
    save.mutate(picked, {
      onSuccess: () => {
        setPicked(null);
        toast.success(t("kvkk.ai.saved"));
      },
      onError: (e) => {
        const err = wave1Error(e);
        const en = typeof err.data.message_en === "string" ? err.data.message_en : err.message;
        setError(locale === "tr" ? (err.messageTr ?? en) : en);
      },
    });
  };

  const OPTIONS: Record<AiDefault, { title: string; hint: string }> = {
    included: { title: t("kvkk.ai.included"), hint: t("kvkk.ai.includedHint") },
    excluded: { title: t("kvkk.ai.excluded"), hint: t("kvkk.ai.excludedHint") },
  };

  return (
    <Card variant="glass" className="max-w-3xl gap-3 px-4" data-testid="kvkk-ai-default">
      <div>
        <p className="type-headline text-label-1">{t("kvkk.ai.title")}</p>
        <p className="type-callout text-label-2">{t("kvkk.ai.lead")}</p>
      </div>
      {q.isLoading ? <Loading /> : null}
      {forbidden ? <Alert tone="warning">{t("kvkk.ai.forbidden")}</Alert> : q.isError ? <Alert tone="error">{errorText(wave1Error(q.error), locale)}</Alert> : null}
      {value ? (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <fieldset className="flex flex-col gap-2" aria-describedby={error ? errId : undefined} aria-invalid={error ? true : undefined}>
            <legend className="mb-1.5 type-footnote font-medium text-label-2">{t("kvkk.ai.legend")}</legend>
            {AI_DEFAULTS.map((v) => (
              <label key={v} className="flex cursor-pointer items-start gap-3 rounded-xl bg-(--mat-thick) px-3 py-2.5 edge-hairline has-checked:bg-tint-soft has-checked:edge-tint has-focus-visible:outline-2 has-focus-visible:outline-solid has-focus-visible:outline-(--focus) pointer-coarse:min-h-11" data-testid={`kvkk-ai-option-${v}`}>
                <input
                  type="radio"
                  name={name}
                  value={v}
                  checked={value === v}
                  onChange={() => {
                    setError(null);
                    setPicked(v);
                  }}
                  disabled={save.isPending}
                  className="mt-1 accent-(--accent)"
                  data-testid={`kvkk-ai-${v}`}
                />
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-2 type-callout font-semibold text-label-1">
                    {OPTIONS[v].title}
                    {stored === v ? <span className="rounded-full bg-fill-2 px-2 type-caption font-normal text-label-2">{t("kvkk.ai.current")}</span> : null}
                  </span>
                  <span className="block type-footnote text-label-2">{OPTIONS[v].hint}</span>
                </span>
              </label>
            ))}
          </fieldset>
          {error ? (
            <p id={errId} role="alert" className="type-footnote text-status-infeasible-fg" data-testid="kvkk-ai-error">
              {error}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" className="pointer-coarse:min-h-11" {...busyProps(save.isPending, !dirty)} data-testid="kvkk-ai-save">
              <BusyLabel busy={save.isPending} label={t("busy.saving")}>
                {t("kvkk.ai.save")}
              </BusyLabel>
            </Button>
            <p className="type-footnote text-label-3">{t("kvkk.ai.audited")}</p>
          </div>
        </form>
      ) : null}
    </Card>
  );
}
