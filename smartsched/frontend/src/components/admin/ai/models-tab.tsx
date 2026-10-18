"use client";
/**
 * Yapay zekâ › Modeller: which provider + model serves each AI feature (rules from text, chat edits, intake, scans,
 * explanations, plain-language bookings), with one global default and an optional fallback. Only models synced from a
 * provider are offered (the backend refuses anything else with `model_not_synced`); with nothing chosen the historic
 * default stays (Anthropic + the model of Ayarlar). Each row says where its effective route comes from.
 */
import { Save } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert, Loading } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { AI_FEATURES, EFFORTS, type Provider, type Route, type RouteFeature, type Routes, useAiProviders, useAiRoutes, useSaveRoutes } from "@/lib/api/ai-admin";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { useAiLabels } from "./ai-kit";
import { errorDetail, errorMessage, providerLabel, routableProviders, routeIssues, routesBody, speechProviders, syncedIds, textProviders, type RouteIssue } from "./ai-model";

type Draft = Partial<Route> | null;

export function ModelsTab({ canEdit }: { canEdit: boolean }) {
  const { t, locale } = useI18n();
  const providers = useAiProviders();
  const routes = useAiRoutes();
  if (providers.isLoading || routes.isLoading) return <Loading />;
  if (!providers.data || !routes.data) return <Alert tone="error">{errorMessage(providers.error ?? routes.error, locale, t("aiAdmin.error.load"))}</Alert>;
  // mounted once: after a save the draft already equals what was stored, and a remount would drop the focus
  return <RoutesEditor all={providers.data.providers} routes={routes.data} canEdit={canEdit} />;
}

function RoutesEditor({ all, routes, canEdit }: { all: Provider[]; routes: Routes; canEdit: boolean }) {
  const { t, locale } = useI18n();
  const labels = useAiLabels();
  const save = useSaveRoutes();
  const [def, setDef] = useState<Draft>(routes.default ?? null);
  const [features, setFeatures] = useState<Partial<Record<RouteFeature, Draft>>>(() => ({ ...(routes.features as Partial<Record<RouteFeature, Draft>>) }));
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  // text rows offer text models only; the voice row only speech-to-text models (VO-B: model_not_text / model_not_speech)
  const providers = useMemo(() => textProviders(all), [all]);
  const routable = useMemo(() => routableProviders(providers), [providers]);
  const speech = useMemo(() => speechProviders(all), [all]);
  const speechRoutable = useMemo(() => routableProviders(speech), [speech]);
  const issueText = (i: RouteIssue) => t(`aiAdmin.models.issue.${i}` as MessageKey);
  const anyIssue = [routeIssues(def, providers), ...AI_FEATURES.map((f) => routeIssues(features[f], providers, f)), routeIssues(features.voice_stt, speech, "voice_stt")].some((x) => x.filter((i) => i !== "transferMissing").length);

  const submit = () => {
    setServerErrors({});
    save.mutate(routesBody(def, features), {
      onSuccess: () => toast.success(t("aiAdmin.models.saved")),
      onError: (e) => {
        const d = errorDetail(e);
        const by: Record<string, string> = {};
        for (const err of d?.errors ?? []) by[err.route ?? "default"] = (locale === "tr" ? err.message_tr : err.message_en) ?? "";
        setServerErrors(by);
        if (!d?.errors?.length) toast.error(errorMessage(e, locale, t("aiAdmin.error.save")));
      },
    });
  };

  return (
    <div className="flex flex-col gap-4" data-testid="ai-models">
      <p className="type-callout text-label-2">{t("aiAdmin.models.lead")}</p>
      {!routable.length ? <Alert tone="warning">{t("aiAdmin.models.noSynced")}</Alert> : null}
      <RouteRow
        id="default"
        title={t("aiAdmin.models.default")}
        hint={t("aiAdmin.models.legacyNote", { model: routes.legacy_model })}
        draft={def}
        onChange={setDef}
        providers={providers}
        routable={routable}
        canEdit={canEdit}
        allowFollow={false}
        issues={routeIssues(def, providers).map(issueText)}
        serverError={serverErrors.default}
        effective={null}
      />
      {AI_FEATURES.map((f) => {
        const eff = routes.effective[f];
        return (
          <RouteRow
            key={f}
            id={f}
            title={labels.feature(f)}
            hint={t(`aiAdmin.models.need.${f}` as MessageKey)}
            draft={features[f] ?? null}
            onChange={(d) => setFeatures((x) => ({ ...x, [f]: d }))}
            providers={providers}
            routable={routable}
            canEdit={canEdit}
            allowFollow
            issues={routeIssues(features[f], providers, f).map(issueText)}
            serverError={serverErrors[f]}
            effective={eff ? t(`aiAdmin.models.source.${eff.source}` as MessageKey, { provider: providerLabel(providers.find((p) => p.id === eff.provider) ?? { label_tr: eff.provider, label_en: eff.provider }, locale), model: eff.model }) : null}
          />
        );
      })}
      <RouteRow
        id="voice_stt"
        title={t("voice.admin.feature")}
        hint={t("voice.admin.need")}
        draft={features.voice_stt ?? null}
        onChange={(d) => setFeatures((x) => ({ ...x, voice_stt: d }))}
        providers={speech}
        routable={speechRoutable}
        canEdit={canEdit}
        allowFollow
        followLabel={t("voice.admin.unset")}
        noEffort
        issues={routeIssues(features.voice_stt, speech, "voice_stt").map(issueText)}
        serverError={serverErrors.voice_stt}
        effective={(() => {
          const eff = routes.effective.voice_stt;
          if (!eff || eff.source === "none" || !eff.provider) return null;
          return t(`aiAdmin.models.source.${eff.source}` as MessageKey, { provider: providerLabel(all.find((p) => p.id === eff.provider) ?? { label_tr: eff.provider, label_en: eff.provider }, locale), model: eff.model });
        })()}
        note={!speechRoutable.length ? t("voice.admin.noSpeechModels") : !features.voice_stt?.provider ? t("voice.admin.noModel") : null}
      />
      {canEdit ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={submit} {...busyProps(save.isPending, anyIssue)} data-testid="ai-routes-save">
            <BusyLabel busy={save.isPending} label={t("busy.saving")} icon={<Save aria-hidden />}>
              {t("aiAdmin.models.save")}
            </BusyLabel>
          </Button>
          {anyIssue ? <p className="type-footnote text-label-2">{t("aiAdmin.models.fixFirst")}</p> : null}
        </div>
      ) : null}
    </div>
  );
}

function RouteRow({
  id,
  title,
  hint,
  draft,
  onChange,
  providers,
  routable,
  canEdit,
  allowFollow,
  issues,
  serverError,
  effective,
  followLabel,
  noEffort,
  note,
}: {
  id: string;
  title: string;
  hint: string;
  draft: Draft;
  onChange: (d: Draft) => void;
  providers: Provider[];
  routable: Provider[];
  canEdit: boolean;
  allowFollow: boolean;
  issues: string[];
  serverError?: string;
  effective: string | null;
  /** the empty choice's label when it does not follow the default (voice: "not chosen, mic hidden") */
  followLabel?: string;
  /** no effort select (speech-to-text has no reasoning effort) */
  noEffort?: boolean;
  /** one plain line under the hint (voice: no model → mic hidden) */
  note?: string | null;
}) {
  const { t, locale } = useI18n();
  const uid = useId();
  const set = (patch: Partial<Route>) => onChange({ ...(draft ?? {}), ...patch });
  const models = syncedIds(providers, draft?.provider);
  const fbModels = syncedIds(providers, draft?.fallback_provider);
  const providerOptions = (selected?: string | null) => {
    const list = [...routable];
    const cur = providers.find((p) => p.id === selected);
    if (cur && !list.includes(cur)) list.push(cur); // keep a saved choice visible even when it became unusable
    return list;
  };
  return (
    <Card className="gap-3 px-4 py-4" data-testid={`ai-route-${id}`}>
      <div className="flex flex-col gap-0.5">
        <h3 className="type-headline text-label-1">{title}</h3>
        <p className="type-footnote text-label-2">{hint}</p>
        {effective ? (
          <p className="type-footnote text-label-3" data-testid={`ai-route-effective-${id}`}>
            {effective}
          </p>
        ) : null}
        {note ? (
          <p className="type-footnote text-label-2" data-testid={`ai-route-note-${id}`}>
            {note}
          </p>
        ) : null}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${uid}-p`} className="type-footnote font-medium text-label-2">
            {t("aiAdmin.models.provider")}
          </Label>
          <NativeSelect id={`${uid}-p`} value={draft?.provider ?? ""} disabled={!canEdit} onChange={(e) => (e.target.value ? onChange({ ...(draft ?? {}), provider: e.target.value, model: syncedIds(providers, e.target.value)[0] ?? "" }) : onChange(null))} data-testid={`ai-route-provider-${id}`}>
            <option value="">{followLabel ?? (allowFollow ? t("aiAdmin.models.followDefault") : t("aiAdmin.models.legacy"))}</option>
            {providerOptions(draft?.provider).map((p) => (
              <option key={p.id} value={p.id}>
                {providerLabel(p, locale)}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${uid}-m`} className="type-footnote font-medium text-label-2">
            {t("aiAdmin.models.model")}
          </Label>
          <NativeSelect id={`${uid}-m`} value={draft?.model ?? ""} disabled={!canEdit || !draft?.provider} onChange={(e) => set({ model: e.target.value })} data-testid={`ai-route-model-${id}`}>
            {draft?.model && !models.includes(draft.model) ? <option value={draft.model}>{draft.model}</option> : null}
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className={noEffort ? "hidden" : "flex flex-col gap-1.5"}>
          <Label htmlFor={`${uid}-e`} className="type-footnote font-medium text-label-2">
            {t("aiAdmin.models.effort")}
          </Label>
          <NativeSelect id={`${uid}-e`} value={draft?.effort ?? ""} disabled={!canEdit || !draft?.provider} onChange={(e) => set({ effort: e.target.value || null })} data-testid={`ai-route-effort-${id}`}>
            <option value="">{t("aiAdmin.models.effortNone")}</option>
            {EFFORTS.map((x) => (
              <option key={x} value={x}>
                {t(`aiAdmin.effort.${x}` as MessageKey)}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${uid}-f`} className="type-footnote font-medium text-label-2">
            {t("aiAdmin.models.fallback")}
          </Label>
          <NativeSelect
            id={`${uid}-f`}
            value={draft?.fallback_provider && draft.fallback_model ? `${draft.fallback_provider}::${draft.fallback_model}` : ""}
            disabled={!canEdit || !draft?.provider}
            onChange={(e) => {
              const [fp, fm] = e.target.value ? e.target.value.split("::") : [null, null];
              set({ fallback_provider: fp ?? null, fallback_model: fm ?? null });
            }}
            data-testid={`ai-route-fallback-${id}`}
          >
            <option value="">{t("aiAdmin.models.fallbackNone")}</option>
            {routable.flatMap((p) =>
              p.models.map((m) => (
                <option key={`${p.id}::${m.id}`} value={`${p.id}::${m.id}`}>
                  {providerLabel(p, locale)} · {m.id}
                </option>
              )),
            )}
            {draft?.fallback_provider && draft.fallback_model && !fbModels.includes(draft.fallback_model) ? <option value={`${draft.fallback_provider}::${draft.fallback_model}`}>{draft.fallback_model}</option> : null}
          </NativeSelect>
        </div>
      </div>
      {issues.length ? (
        <ul className="flex flex-col gap-1" data-testid={`ai-route-issues-${id}`}>
          {issues.map((i) => (
            <li key={i} className="type-footnote text-status-warning-fg">
              {i}
            </li>
          ))}
        </ul>
      ) : null}
      {serverError ? (
        <p className="type-footnote text-status-infeasible-fg" role="alert">
          {serverError}
        </p>
      ) : null}
    </Card>
  );
}
