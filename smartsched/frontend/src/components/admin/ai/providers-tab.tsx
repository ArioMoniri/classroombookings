"use client";
/**
 * Yapay zekâ › Sağlayıcılar: one card per provider (Anthropic, OpenAI, Azure OpenAI, OpenRouter, an OpenAI-compatible
 * server such as Ollama / vLLM, Gemini, Bedrock, Vertex). Keys are write-only (masked state only; the field is
 * cleared after saving), "Modelleri eşitle" lists the provider's models through its API, "Bağlantıyı test et" runs a
 * few-token call, and the KVKK transfer record (region, retention, legal mechanism, dates) decides whether requests
 * that may carry personal data can go to this provider (R-AI-03).
 */
import { PlugZap, RefreshCw, Save } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Alert, Field, Loading } from "@/components/admin/kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { type Provider, useAiProviders, useSaveProvider, useSyncProvider, useTestProvider } from "@/lib/api/ai-admin";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { StatusWord } from "./ai-kit";
import { errorMessage, providerLabel, providerStatus } from "./ai-model";

const SECRET_LABEL: Record<string, MessageKey> = {
  api_key: "aiAdmin.provider.key",
  aws_access_key_id: "aiAdmin.provider.keyAwsId",
  aws_secret_access_key: "aiAdmin.provider.keyAwsSecret",
};
const CONFIG_LABEL: Record<string, MessageKey> = {
  base_url: "aiAdmin.provider.baseUrl",
  region: "aiAdmin.provider.region",
  project_id: "aiAdmin.provider.projectId",
};

export function ProvidersTab({ canEdit }: { canEdit: boolean }) {
  const { t, locale } = useI18n();
  const q = useAiProviders();
  if (q.isLoading) return <Loading />;
  if (q.isError || !q.data) return <Alert tone="error">{errorMessage(q.error, locale, t("aiAdmin.error.load"))}</Alert>;
  return (
    <div className="flex flex-col gap-4" data-testid="ai-providers">
      <p className="type-callout text-label-2">{t("aiAdmin.provider.lead")}</p>
      {q.data.providers.map((p) => (
        <ProviderCard key={p.id} provider={p} mechanisms={q.data.kvkk_mechanisms} canEdit={canEdit} />
      ))}
    </div>
  );
}

function ProviderCard({ provider: p, mechanisms, canEdit }: { provider: Provider; mechanisms: string[]; canEdit: boolean }) {
  const { t, locale } = useI18n();
  const ids = { base: useId() };
  const save = useSaveProvider();
  const sync = useSyncProvider();
  const test = useTestProvider();
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [config, setConfig] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(p.config).filter(([k]) => k !== "enabled").map(([k, v]) => [k, String(v ?? "")])));
  const [transfer, setTransfer] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(p.transfer).map(([k, v]) => [k, String(v ?? "")])));
  const [error, setError] = useState<string | null>(null);
  const status = providerStatus(p);
  const statusTone = status === "ok" ? "ok" : status === "error" ? "error" : status;
  const fail = (e: unknown) => setError(errorMessage(e, locale, t("aiAdmin.error.save")));

  const submit = () => {
    setError(null);
    const body: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(secrets)) if (v.trim()) body[k] = v.trim();
    for (const k of p.config_fields) body[k] = (config[k] ?? "").trim();
    const tr = Object.fromEntries(Object.entries(transfer).filter(([, v]) => v.trim()));
    if (Object.keys(tr).length || Object.keys(p.transfer).length) body.transfer = tr;
    save.mutate(
      { p: p.id, body },
      {
        onSuccess: () => {
          setSecrets({});
          toast.success(t("aiAdmin.provider.saved"));
        },
        onError: fail,
      },
    );
  };
  const configFields = p.config_fields.filter((k) => k in CONFIG_LABEL);

  return (
    <Card className="gap-4 px-4 py-4" data-testid={`ai-provider-${p.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="type-headline text-label-1">{providerLabel(p, locale)}</h3>
          <div className="flex flex-wrap items-center gap-2">
            <StatusWord tone={statusTone} testId={`ai-provider-status-${p.id}`}>
              {t(`aiAdmin.provider.status.${status}` as MessageKey)}
            </StatusWord>
            {p.local ? <Badge tone="feasible">{t("aiAdmin.provider.local")}</Badge> : null}
            {p.keyless && !p.secrets.length ? <Badge variant="outline">{t("aiAdmin.provider.keyless")}</Badge> : null}
          </div>
        </div>
        {p.id !== "anthropic" ? (
          <div className="flex items-center gap-2">
            <Label htmlFor={`${ids.base}-on`} className="type-callout text-label-1">
              {t("aiAdmin.provider.enabled")}
            </Label>
            <Switch
              id={`${ids.base}-on`}
              checked={p.config.enabled !== false}
              disabled={!canEdit || save.isPending}
              onCheckedChange={(v) => save.mutate({ p: p.id, body: { enabled: v } }, { onError: fail })}
              data-testid={`ai-provider-enabled-${p.id}`}
            />
          </div>
        ) : null}
      </div>

      {p.warnings.map((w) => (
        <Alert key={w.code} tone="warning" testId={`ai-provider-warning-${p.id}`}>
          {locale === "tr" ? w.message_tr : w.message_en}
        </Alert>
      ))}
      {canEdit && p.id === "openai_compatible" ? (
        <div className="flex items-start justify-between gap-3 rounded-lg bg-fill-3 px-3 py-2">
          <div className="min-w-0">
            <Label htmlFor={`${ids.base}-local`} className="type-callout text-label-1">
              {t("aiAdmin.provider.allowLocal")}
            </Label>
            <p className="type-footnote text-label-3">{t("aiAdmin.provider.allowLocalHint")}</p>
          </div>
          <Switch
            id={`${ids.base}-local`}
            checked={p.allow_local}
            disabled={save.isPending}
            onCheckedChange={(v) => save.mutate({ p: p.id, body: { allow_local: v } }, { onError: fail })}
            data-testid={`ai-provider-allow-local-${p.id}`}
          />
        </div>
      ) : null}
      {canEdit ? (
        <div className="grid gap-3 md:grid-cols-2">
          {p.secrets.map((name) => {
            const state = p.keys[name];
            return (
              <Field
                key={name}
                label={t(SECRET_LABEL[name] ?? "aiAdmin.provider.key")}
                htmlFor={`${ids.base}-${name}`}
                hint={state?.set ? t("aiAdmin.provider.keySet", { masked: state.masked ?? "••••" }) : t("aiAdmin.provider.keyNone")}
              >
                <div className="flex gap-2">
                  <Input
                    id={`${ids.base}-${name}`}
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={secrets[name] ?? ""}
                    placeholder={t("aiAdmin.provider.keyPlaceholder")}
                    onChange={(e) => setSecrets((s) => ({ ...s, [name]: e.target.value }))}
                    data-testid={`ai-key-${p.id}-${name}`}
                  />
                  {state?.set ? (
                    <Button variant="ghost" onClick={() => save.mutate({ p: p.id, body: { clear: [name] } }, { onError: fail })} data-testid={`ai-key-clear-${p.id}-${name}`}>
                      {t("aiAdmin.provider.keyClear")}
                    </Button>
                  ) : null}
                </div>
              </Field>
            );
          })}
          {configFields.map((name) => (
            <Field key={name} label={t(CONFIG_LABEL[name]!)} htmlFor={`${ids.base}-${name}`} hint={name === "base_url" && p.default_base_url ? t("aiAdmin.provider.baseUrlHint", { url: p.default_base_url }) : undefined}>
              <Input id={`${ids.base}-${name}`} value={config[name] ?? ""} inputMode={name === "base_url" ? "url" : "text"} onChange={(e) => setConfig((c) => ({ ...c, [name]: e.target.value }))} data-testid={`ai-config-${p.id}-${name}`} />
            </Field>
          ))}
        </div>
      ) : null}
      {canEdit ? <p className="type-footnote text-label-3">{t("aiAdmin.provider.keyHint")}</p> : null}

      <details className="rounded-lg bg-fill-3 px-3 py-2" data-testid={`ai-transfer-${p.id}`}>
        <summary className="cursor-pointer py-1 type-callout font-medium text-label-1 pointer-coarse:min-h-11 pointer-coarse:py-3">
          {t("aiAdmin.transfer.title")} · {p.transfer_ok ? t("aiAdmin.transfer.ok") : t("aiAdmin.transfer.missing")}
        </summary>
        <p className="mt-1 type-footnote text-label-2">{t("aiAdmin.transfer.lead")}</p>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <Field label={t("aiAdmin.transfer.mechanism")} htmlFor={`${ids.base}-mech`}>
            <NativeSelect id={`${ids.base}-mech`} value={transfer.kvkk_mechanism ?? ""} disabled={!canEdit} onChange={(e) => setTransfer((x) => ({ ...x, kvkk_mechanism: e.target.value }))} data-testid={`ai-transfer-mech-${p.id}`}>
              <option value="">{t("aiAdmin.transfer.mech.none")}</option>
              {mechanisms.map((m) => (
                <option key={m} value={m}>
                  {t(`aiAdmin.transfer.mech.${m}` as MessageKey)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          {(["region", "retention", "contract_date", "notification_date", "note"] as const).map((k) => (
            <Field key={k} label={t(`aiAdmin.transfer.${k}` as MessageKey)} htmlFor={`${ids.base}-tr-${k}`}>
              <Input id={`${ids.base}-tr-${k}`} type={k.endsWith("_date") ? "date" : "text"} value={transfer[k] ?? ""} disabled={!canEdit} onChange={(e) => setTransfer((x) => ({ ...x, [k]: e.target.value }))} />
            </Field>
          ))}
        </div>
      </details>

      <div className="flex flex-col gap-1">
        <p className="type-footnote text-label-2" data-testid={`ai-sync-line-${p.id}`}>
          {p.fetched_at ? t("aiAdmin.provider.lastSync", { time: new Date(p.fetched_at).toLocaleString(locale === "tr" ? "tr-TR" : "en-GB"), n: p.models.length }) : t("aiAdmin.provider.neverSynced")}
        </p>
        {p.sync_error ? <p className="type-footnote text-status-infeasible-fg">{t("aiAdmin.provider.syncError", { error: p.sync_error })}</p> : null}
        {p.last_test?.at ? (
          <p className={p.last_test.ok ? "type-footnote text-label-2" : "type-footnote text-status-infeasible-fg"} data-testid={`ai-test-line-${p.id}`}>
            {p.last_test.ok ? t("aiAdmin.provider.testOk", { detail: p.last_test.detail ?? "" }) : t("aiAdmin.provider.testFail", { detail: p.last_test.detail ?? "" })}
          </p>
        ) : null}
      </div>
      {error ? (
        <Alert tone="error" testId={`ai-provider-error-${p.id}`}>
          {error}
        </Alert>
      ) : null}
      {canEdit ? (
        <div className="flex flex-wrap gap-2">
          <Button onClick={submit} {...busyProps(save.isPending)} data-testid={`ai-provider-save-${p.id}`}>
            <BusyLabel busy={save.isPending} label={t("busy.saving")} icon={<Save aria-hidden />}>
              {t("aiAdmin.provider.save")}
            </BusyLabel>
          </Button>
          <Button
            variant="outline"
            {...busyProps(sync.isPending, !p.has_credentials)}
            onClick={() =>
              sync.mutate(p.id, {
                onSuccess: (r) => (r.ok ? toast.success(t("aiAdmin.provider.synced", { n: r.models.length })) : setError(t("aiAdmin.provider.syncError", { error: r.error ?? "" }))),
                onError: fail,
              })
            }
            data-testid={`ai-provider-sync-${p.id}`}
          >
            <BusyLabel busy={sync.isPending} label={t("aiAdmin.provider.syncing")} icon={<RefreshCw aria-hidden />}>
              {t("aiAdmin.provider.sync")}
            </BusyLabel>
          </Button>
          <Button
            variant="outline"
            {...busyProps(test.isPending, !p.has_credentials)}
            onClick={() => test.mutate({ p: p.id }, { onSuccess: (r) => (r.ok ? toast.success(t("aiAdmin.provider.testOk", { detail: r.detail })) : setError(t("aiAdmin.provider.testFail", { detail: r.detail }))), onError: fail })}
            data-testid={`ai-provider-test-${p.id}`}
          >
            <BusyLabel busy={test.isPending} label={t("aiAdmin.provider.testing")} icon={<PlugZap aria-hidden />}>
              {t("aiAdmin.provider.test")}
            </BusyLabel>
          </Button>
        </div>
      ) : null}
    </Card>
  );
}
