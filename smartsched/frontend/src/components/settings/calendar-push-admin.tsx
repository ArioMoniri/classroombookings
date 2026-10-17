"use client";
/**
 * Settings › Entegrasyonlar › Google Takvim ve Microsoft 365 aktarımı (docs/product/calendar-sync-api.md):
 * the organisation's own OAuth clients, `GET/PUT /calendar/admin/settings` (backend `app/api/v1/calendar_sync.py`,
 * `setup.settings`).
 *
 * - The client id is shown in clear; the secret is write-only: the backend answers `{set, masked}` and the field
 *   stays empty ("Kayıtlı (…abcd)" under it). Sending `""` removes a value (Kaldır).
 * - `configured` is the backend's own verdict (id + secret + a public panel address), never computed here.
 * - The redirect URI the administrator registers at Google / Microsoft is the backend's `redirect_uri`, built from
 *   the panel's public address; without one the card asks for it first (the address is editable here).
 * - The KVKK sign-off is the calendar-sync one (CalendarSyncAdmin, M-18): while sync is off the card says users
 *   cannot connect yet, and shows the sign-off record when there is one.
 */
import { CalendarCog, Check, Copy } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/common/status-badge";
import { ConfirmDialog } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useIntegrationSettings, useSaveIntegrationSettings, type IntegrationSettings, type IntegrationSettingsIn, type OAuthClientOut } from "@/lib/api/approval-first";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { SignoffRecord } from "./calendar-sync-admin";

export type PushProvider = "google" | "microsoft";
export const PUSH_PROVIDERS: readonly PushProvider[] = ["google", "microsoft"];

/** The request body that saves one provider's client: only the fields the administrator typed, trimmed; a blank
 * secret is left out (the stored one stays). `null` = nothing to send. */
export function clientBody(provider: PushProvider, form: { id: string; secret: string; tenant?: string }, stored: OAuthClientOut | undefined): IntegrationSettingsIn | null {
  const body: IntegrationSettingsIn = {};
  const id = form.id.trim();
  if (id !== (stored?.client_id ?? "")) body[`${provider}_client_id`] = id;
  if (form.secret.trim()) body[`${provider}_client_secret`] = form.secret.trim();
  if (provider === "microsoft" && form.tenant !== undefined) {
    const tenant = form.tenant.trim() || "organizations";
    if (tenant !== (stored?.tenant ?? "organizations")) body.microsoft_tenant = tenant;
  }
  return Object.keys(body).length ? body : null;
}

/** The redirect URI is only usable when the backend built it from an absolute panel address. */
export function redirectUsable(uri: string | undefined | null): boolean {
  return !!uri && /^https?:\/\/[^/]/.test(uri);
}

function CopyField({ id, label, value, testId }: { id: string; label: string; value: string; testId: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard?.writeText(value).then(() => {
      setCopied(true);
      toast.success(t("calendarPush.admin.copied"));
      window.setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex items-center gap-2">
        <Input id={id} readOnly value={value} className="font-mono" spellCheck={false} data-testid={testId} onFocus={(e) => e.currentTarget.select()} />
        <Button variant="outline" shape="rect" onClick={copy} aria-label={`${t("calendarPush.admin.copy")}: ${label}`}>
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
          <span className="max-sm:sr-only">{t("calendarPush.admin.copy")}</span>
        </Button>
      </div>
    </div>
  );
}

function ProviderClient({ provider, s }: { provider: PushProvider; s: IntegrationSettings }) {
  const { t, locale } = useI18n();
  const save = useSaveIntegrationSettings();
  const stored = s[provider];
  const [id, setId] = useState(stored?.client_id ?? "");
  const [secret, setSecret] = useState("");
  const [tenant, setTenant] = useState(stored?.tenant ?? "organizations");
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const name = t(`calendarPush.provider.${provider}`);
  const base = `cp-${provider}`;
  const secretSet = !!stored?.client_secret?.set;
  const fail = (e: unknown) => setError(t("calendarPush.admin.failed", { message: errorText(wave1Error(e), locale) }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!id.trim()) return setError(t("calendarPush.admin.needId"));
    if (!secretSet && !secret.trim()) return setError(t("calendarPush.admin.needSecret"));
    const body = clientBody(provider, { id, secret, tenant: provider === "microsoft" ? tenant : undefined }, stored);
    if (!body) return toast.message(t("calendarPush.admin.nothing"));
    save.mutate(body, {
      onSuccess: () => {
        setSecret("");
        toast.success(t("calendarPush.admin.saved", { provider: name }));
      },
      onError: fail,
    });
  };
  const remove = () => {
    const body: IntegrationSettingsIn = { [`${provider}_client_id`]: "", [`${provider}_client_secret`]: "" };
    save.mutate(body, {
      onSuccess: () => {
        setRemoving(false);
        setId("");
        setSecret("");
        toast.success(t("calendarPush.admin.removed", { provider: name }));
      },
      onError: (e) => {
        setRemoving(false);
        fail(e);
      },
    });
  };

  return (
    <section aria-labelledby={`${base}-title`} className="grid gap-3 rounded-xl bg-fill-3 p-3 sm:p-4" data-testid={`calendar-push-${provider}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={`${base}-title`} className="type-headline text-label-1">{name}</h3>
        <span data-testid={`calendar-push-${provider}-state`}>
          <StatusBadge kind={stored?.configured ? "feasible" : "locked"} label={t(stored?.configured ? "calendarPush.admin.configured" : "calendarPush.admin.notConfigured")} />
        </span>
      </div>
      {redirectUsable(stored?.redirect_uri) ? (
        <div className="grid gap-1">
          <CopyField id={`${base}-redirect`} label={t("calendarPush.admin.redirect")} value={stored?.redirect_uri ?? ""} testId={`calendar-push-${provider}-redirect`} />
          <p className="type-footnote text-label-2">{t(`calendarPush.admin.redirectHint.${provider}`)}</p>
        </div>
      ) : (
        <p className="type-footnote text-status-warning-fg" data-testid={`calendar-push-${provider}-no-redirect`}>{t("calendarPush.admin.redirectNeedsUrl")}</p>
      )}
      <form className="grid gap-3" onSubmit={submit} noValidate>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor={`${base}-id`}>{t("calendarPush.admin.clientId")}</Label>
            <Input id={`${base}-id`} value={id} onChange={(e) => setId(e.target.value)} autoComplete="off" spellCheck={false} maxLength={255} className="font-mono" data-testid={`calendar-push-${provider}-id`} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${base}-secret`}>{t("calendarPush.admin.clientSecret")}</Label>
            <Input
              id={`${base}-secret`}
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              autoComplete="new-password"
              spellCheck={false}
              maxLength={512}
              aria-describedby={`${base}-secret-hint`}
              data-testid={`calendar-push-${provider}-secret`}
            />
            <p id={`${base}-secret-hint`} className="type-footnote text-label-2" data-testid={`calendar-push-${provider}-secret-hint`}>
              {secretSet ? t("calendarPush.admin.secretSet", { masked: stored?.client_secret?.masked ?? "" }) : t("calendarPush.admin.secretUnset")}
            </p>
          </div>
          {provider === "microsoft" ? (
            <div className="grid gap-1.5 md:col-span-2">
              <Label htmlFor={`${base}-tenant`}>{t("calendarPush.admin.tenant")}</Label>
              <Input id={`${base}-tenant`} value={tenant} onChange={(e) => setTenant(e.target.value)} autoComplete="off" spellCheck={false} maxLength={64} aria-describedby={`${base}-tenant-hint`} className="font-mono md:max-w-sm" />
              <p id={`${base}-tenant-hint`} className="type-footnote text-label-2">{t("calendarPush.admin.tenantHint")}</p>
            </div>
          ) : null}
        </div>
        {error ? <p role="alert" className="type-footnote text-status-infeasible-fg">{error}</p> : null}
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" disabled={save.isPending} aria-busy={save.isPending || undefined} data-testid={`calendar-push-${provider}-save`}>
            <BusyLabel busy={save.isPending} label={t("busy.saving")}>{t("calendarPush.admin.save")}</BusyLabel>
          </Button>
          {stored?.client_id || secretSet ? (
            <Button type="button" variant="ghost" onClick={() => setRemoving(true)} disabled={save.isPending} data-testid={`calendar-push-${provider}-remove`}>
              {t("calendarPush.admin.remove")}
            </Button>
          ) : null}
        </div>
      </form>
      <ConfirmDialog
        open={removing}
        onOpenChange={(o) => !save.isPending && setRemoving(o)}
        title={t("calendarPush.admin.removeTitle", { provider: name })}
        description={t("calendarPush.admin.removeBody")}
        confirmLabel={t("calendarPush.admin.remove")}
        destructive
        busy={save.isPending}
        onConfirm={remove}
      />
    </section>
  );
}

function PublicUrl({ s }: { s: IntegrationSettings }) {
  const { t, locale } = useI18n();
  const save = useSaveIntegrationSettings();
  const [url, setUrl] = useState(s.public_url_source === "setting" ? (s.public_url ?? "") : "");
  const [error, setError] = useState<string | null>(null);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    save.mutate({ public_url: url.trim() }, { onSuccess: () => toast.success(t("calendarPush.admin.urlSaved")), onError: (er) => setError(t("calendarPush.admin.failed", { message: errorText(wave1Error(er), locale) })) });
  };
  return (
    <form className="grid gap-1.5" onSubmit={submit} noValidate>
      <Label htmlFor="cp-public-url">{t("calendarPush.admin.publicUrl")}</Label>
      <div className="flex flex-wrap items-center gap-2">
        <Input id="cp-public-url" type="url" inputMode="url" autoComplete="off" spellCheck={false} placeholder={s.public_url_source === "env" ? (s.public_url ?? "") : "https://"} value={url} onChange={(e) => setUrl(e.target.value)} className="min-w-0 flex-1 font-mono sm:max-w-md" aria-describedby="cp-public-url-hint" data-testid="calendar-push-public-url" />
        <Button type="submit" variant="outline" shape="rect" disabled={save.isPending} aria-busy={save.isPending || undefined}>
          <BusyLabel busy={save.isPending} label={t("busy.saving")}>{t("calendarPush.admin.saveUrl")}</BusyLabel>
        </Button>
      </div>
      <p id="cp-public-url-hint" className="type-footnote text-label-2" data-testid="calendar-push-url-source">
        {s.public_url_source === "env" ? t("calendarPush.admin.urlFromEnv", { url: s.public_url ?? "" }) : s.public_url ? t("calendarPush.admin.urlHint") : t("calendarPush.admin.urlMissing")}
      </p>
      {error ? <p role="alert" className="type-footnote text-status-infeasible-fg">{error}</p> : null}
    </form>
  );
}

export function CalendarPushAdmin() {
  const { t, locale } = useI18n();
  const q = useIntegrationSettings();
  const s = q.data;
  return (
    <Card data-testid="calendar-push-admin">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarCog className="size-4 text-label-3" aria-hidden />
          {t("calendarPush.admin.title")}
        </CardTitle>
        <CardDescription>{t("calendarPush.admin.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {q.isError ? (
          <p role="alert" className="type-footnote text-status-infeasible-fg">{errorText(wave1Error(q.error), locale)}</p>
        ) : null}
        {s ? (
          <>
            <div className="grid gap-2" data-testid="calendar-push-kvkk">
              <p className={s.calendar_sync_enabled ? "type-callout text-label-1" : "type-callout text-status-warning-fg"}>
                {t(s.calendar_sync_enabled ? "calendarPush.admin.kvkkOn" : "calendarPush.admin.kvkkOff")}
              </p>
              {s.calendar_sync_signoff ? <SignoffRecord signoff={s.calendar_sync_signoff} /> : null}
            </div>
            <PublicUrl key={`url-${s.public_url ?? ""}-${s.public_url_source ?? ""}`} s={s} />
            {PUSH_PROVIDERS.map((p) => (
              <ProviderClient key={`${p}-${s[p]?.client_id ?? ""}-${s[p]?.tenant ?? ""}`} provider={p} s={s} />
            ))}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
