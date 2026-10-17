"use client";
/**
 * The guided SMTP setup (W3-MAIL; docs/design/v3/integrations.md §7): 1 Sağlayıcı · 2 Bağlantı · 3 Gönderen ·
 * 4 Alan adı · 5 Deneme · 6 Etkinleştir. Settings are organisation rows shared by every administrator ("Son
 * değişiklik: <ad>, <zaman>"); secrets are write-only (saved → "•••••••• kayıtlı" + Değiştir). Presets fill and lock
 * host / port / security; providers abroad need the KVKK md. 9 acknowledgement. Phones: "Adım n / 6" + a bar, the
 * Geri / İleri footer sticks above the tab bar, every control 44 px, inputs 16 px.
 */
import { CheckCircle2, ExternalLink, Send } from "lucide-react";
import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { CopyField } from "@/components/admin/integrations/copy-field";
import { Alert, Field, Loading, SelectField } from "@/components/admin/kit";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { Badge } from "@/components/ui/badge";
import { BusyLabel } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { mailApi, mailError, secretSet, useMailSettings, usePresets, useSaveMail, type DnsOut, type MailSettings, type MailSettingsIn, type Preset, type Secret, type TestOut } from "./api";
import { STEPS, changes, cleanSecret, dnsTone, domainOf, leavesPreset, presetFill, stepDone, stepsText, type Step } from "./email-model";

const STEP_KEY = {
  provider: "email.steps.provider",
  connection: "email.steps.connection",
  sender: "email.steps.sender",
  domain: "email.steps.domain",
  test: "email.steps.test",
  enable: "email.steps.enable",
} as const;

export function StatusLine({ data }: { data: MailSettings }) {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  const tone = data.status === "connected" ? "feasible" : data.status === "error" ? "infeasible" : "warning";
  const change = data.last_change;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1" data-testid="mail-status">
      <Badge variant="secondary" tone={tone}>
        {t(`email.status.${data.status}`)}
      </Badge>
      <span className="type-footnote text-label-2">
        {change?.at ? t("email.status.lastChange", { by: change.by ?? "-", at: fmt.dateTime(change.at) }) : t("email.status.never")}
      </span>
      {data.last_check?.at ? <span className="type-footnote text-label-3">{t("email.status.lastCheck", { at: fmt.dateTime(data.last_check.at) })}</span> : null}
    </div>
  );
}

export function SmtpWizard() {
  const q = useMailSettings();
  const presets = usePresets();
  const { t, locale } = useI18n();
  if (q.isLoading || presets.isLoading) return <Loading />;
  if (!q.data) return <Alert tone="error">{mailError(q.error, locale)}</Alert>;
  return (
    <div className="flex flex-col gap-4">
      <StatusLine data={q.data} />
      <p className="type-footnote text-label-3">{t("email.status.shared")}</p>
      <Wizard data={q.data} presets={presets.data ?? []} />
    </div>
  );
}

function Wizard({ data, presets }: { data: MailSettings; presets: Preset[] }) {
  const { t, locale } = useI18n();
  const [step, setStep] = useState<Step>(data.configured ? "test" : "provider");
  const [d, setD] = useState<MailSettingsIn>({});
  const [error, setError] = useState<string | null>(null);
  const [dns, setDns] = useState<DnsOut | null>(null);
  const [test, setTest] = useState<TestOut | null>(null);
  const save = useSaveMail();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const v = { ...data, ...d } as MailSettings & MailSettingsIn;
  const preset = presets.find((p) => p.id === v.provider);
  const set = <K extends keyof MailSettingsIn>(k: K, val: MailSettingsIn[K]) => setD((p) => ({ ...p, [k]: val }));
  const idx = STEPS.indexOf(step);
  const pending = changes(data, d);
  const dirty = Object.keys(pending).length > 0;

  const go = (next: Step) => {
    setStep(next);
    // focus never falls to <body>: the new step's heading takes it
    requestAnimationFrame(() => headingRef.current?.focus());
  };
  const persist = async (): Promise<boolean> => {
    if (!dirty) return true;
    try {
      await save.mutateAsync(pending);
      setD({});
      setError(null);
      toast.success(t("email.steps.saved"));
      return true;
    } catch (e) {
      setError(mailError(e, locale));
      return false;
    }
  };
  const next = async () => {
    if (await persist()) go(STEPS[Math.min(idx + 1, STEPS.length - 1)]!);
  };

  return (
    <Card className="gap-0 p-0">
      <nav aria-label={t("email.steps.label")} className="hairline-b px-4 py-3">
        <p className="mb-2 type-footnote text-label-2 sm:hidden">{t("email.steps.progress", { n: idx + 1, total: STEPS.length })}</p>
        <Progress value={((idx + 1) / STEPS.length) * 100} className="mb-2 sm:hidden" aria-hidden />
        <ol className="flex gap-1 overflow-x-auto max-sm:hidden">
          {STEPS.map((s, i) => {
            const done = stepDone(s, data, { dnsChecked: !!dns, testOk: test?.ok });
            return (
              <li key={s}>
                <Button
                  variant={s === step ? "secondary" : "ghost"}
                  size="sm"
                  aria-current={s === step ? "step" : undefined}
                  onClick={() => go(s)}
                  data-testid={`mail-step-${s}`}
                  className="pointer-coarse:min-h-11"
                >
                  {done ? <CheckCircle2 aria-hidden className="text-status-feasible-fg" /> : <span aria-hidden>{i + 1}.</span>}
                  {t(STEP_KEY[s])}
                </Button>
              </li>
            );
          })}
        </ol>
      </nav>
      <section className="flex flex-col gap-4 px-4 py-4" aria-labelledby="mail-step-heading">
        <h3 id="mail-step-heading" ref={headingRef} tabIndex={-1} className="type-title-3 text-label-1 outline-none">
          {t(STEP_KEY[step])}
        </h3>
        {step === "provider" ? <ProviderStep presets={presets} value={v.provider ?? ""} onPick={(p) => setD((prev) => ({ ...prev, ...presetFill(p) }))} /> : null}
        {step === "connection" ? <ConnectionStep v={v} data={data} preset={preset} set={set} /> : null}
        {step === "sender" ? <SenderStep v={v} stored={data.abroad_ack} ticked={d.abroad_ack === true} preset={preset} set={set} /> : null}
        {step === "domain" ? <DomainStep v={v} result={dns} onResult={setDns} set={set} /> : null}
        {step === "test" ? <TestStep result={test} onResult={setTest} configured={data.configured} /> : null}
        {step === "enable" ? <EnableStep data={data} /> : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
      </section>
      <div className="hairline-t flex items-center justify-between gap-2 px-4 py-3 max-lg:sticky max-lg:bottom-[calc(var(--shell-bottom-h,0px)+0.5rem)] max-lg:glass-chrome max-lg:rounded-2xl">
        <Button variant="outline" disabled={idx === 0} onClick={() => go(STEPS[Math.max(idx - 1, 0)]!)} className="pointer-coarse:min-h-11">
          {t("email.steps.back")}
        </Button>
        <div className="flex gap-2">
          {dirty ? (
            <Button variant="outline" onClick={() => void persist()} disabled={save.isPending} className="pointer-coarse:min-h-11" data-testid="mail-save">
              <BusyLabel busy={save.isPending} label={t("busy.saving")}>
                {t("email.steps.save")}
              </BusyLabel>
            </Button>
          ) : null}
          {idx < STEPS.length - 1 ? (
            <Button onClick={() => void next()} disabled={save.isPending} className="pointer-coarse:min-h-11" data-testid="mail-next">
              {t("email.steps.next")}
            </Button>
          ) : null}
        </div>
      </div>
    </Card>
  );
}

function ProviderStep({ presets, value, onPick }: { presets: Preset[]; value: string; onPick: (p: Preset) => void }) {
  const { t } = useI18n();
  return (
    <fieldset>
      <legend className="mb-3 type-callout text-label-2">{t("email.preset.title")}</legend>
      <div role="radiogroup" className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {presets.map((p) => (
          <button
            key={p.id}
            type="button"
            role="radio"
            aria-checked={value === p.id}
            onClick={() => onPick(p)}
            data-testid={`mail-preset-${p.id}`}
            className={cn("flex min-h-14 flex-col items-start gap-1 rounded-xl border px-3 py-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-tint", value === p.id ? "border-tint bg-tint-soft" : "border-hairline-strong hover:bg-fill-2")}
          >
            <span className="flex w-full items-center justify-between gap-2 type-headline text-label-1">
              {p.label}
              {p.abroad ? <Badge variant="outline">{t("email.preset.abroad")}</Badge> : null}
            </span>
            <span className="type-footnote text-label-3">{p.host ? `${p.host} · ${p.port}` : "—"}</span>
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function SecretInput({ id, label, hint, stored, value, onChange }: { id: string; label: string; hint?: string; stored: Secret; value: string | null | undefined; onChange: (v: string | null) => void }) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(!secretSet(stored));
  const [trimmed, setTrimmed] = useState(false);
  if (!editing)
    return (
      <Field label={label} htmlFor={id} hint={hint}>
        <div className="flex items-center gap-2">
          <span className="type-callout text-label-2" id={id}>
            {t("email.field.secretSaved")}
          </span>
          <Button size="sm" variant="outline" onClick={() => setEditing(true)} className="pointer-coarse:min-h-11">
            {t("email.field.secretChange")}
          </Button>
        </div>
      </Field>
    );
  return (
    <Field label={label} htmlFor={id} hint={trimmed ? t("email.field.trimmed") : hint}>
      <div className="flex items-center gap-2">
        <Input
          id={id}
          type="password"
          autoComplete="new-password"
          className="w-full max-sm:text-base"
          value={value ?? ""}
          onChange={(e) => {
            const c = cleanSecret(e.target.value);
            setTrimmed(c.trimmed && e.target.value.length > 0);
            onChange(c.value);
          }}
        />
        {secretSet(stored) ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setEditing(false);
              onChange(null);
            }}
            className="pointer-coarse:min-h-11"
          >
            {t("email.field.secretKeep")}
          </Button>
        ) : null}
      </div>
    </Field>
  );
}

type Setter = <K extends keyof MailSettingsIn>(k: K, val: MailSettingsIn[K]) => void;

function ConnectionStep({ v, data, preset, set }: { v: MailSettings & MailSettingsIn; data: MailSettings; preset: Preset | undefined; set: Setter }) {
  const { t, locale } = useI18n();
  const [unlocked, setUnlocked] = useState(false);
  const locked = !!preset && preset.id !== "custom" && !unlocked;
  const ids = useId();
  return (
    <div className="flex flex-col gap-4">
      {preset ? (
        <div className="flex flex-col gap-3">
          <p className="type-headline text-label-1">{t("email.preset.whatToCreate")}</p>
          <ol className="flex list-decimal flex-col gap-2 ps-5 type-callout text-label-1">
            {preset.steps.map((s, i) => (
              <li key={i} className="flex flex-col gap-2">
                <span>{locale === "tr" ? s.tr : s.en}</span>
                {s.copy ? <CopyField label={t("email.preset.copy")} value={s.copy} /> : null}
              </li>
            ))}
          </ol>
          <div className="flex flex-wrap gap-2">
            {preset.console_url ? (
              <a href={preset.console_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 type-callout text-tint-text underline-offset-2 hover:underline pointer-coarse:min-h-11">
                {t("email.preset.console", { name: preset.label })}
                <ExternalLink aria-hidden className="size-4" />
              </a>
            ) : null}
          </div>
          <CopyField label={t("email.preset.whatToCreate")} value={stepsText(preset, locale === "tr" ? "tr" : "en")} multiline mono={false} />
          {(locale === "tr" ? preset.notes_tr : preset.notes_en) ? <Alert tone="warning">{locale === "tr" ? preset.notes_tr : preset.notes_en}</Alert> : null}
        </div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
        <Field label={t("email.field.host")} htmlFor={`${ids}-host`}>
          {preset && preset.hosts.length > 1 && locked ? (
            <SelectField id={`${ids}-host`} value={v.host ?? ""} onChange={(e) => set("host", e.target.value)}>
              {preset.hosts.map((h) => (
                <option key={h} value={h}>
                  {h}
                </option>
              ))}
            </SelectField>
          ) : (
            <Input id={`${ids}-host`} className="max-sm:text-base" readOnly={locked} value={v.host ?? ""} onChange={(e) => set("host", e.target.value)} placeholder="smtp.uni.edu.tr" />
          )}
        </Field>
        <Field label={t("email.field.port")} htmlFor={`${ids}-port`}>
          <Input id={`${ids}-port`} type="number" inputMode="numeric" className="max-sm:text-base" readOnly={locked} value={v.port ?? ""} onChange={(e) => set("port", Number(e.target.value) || 0)} />
        </Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("email.field.security")} htmlFor={`${ids}-sec`}>
          <SelectField id={`${ids}-sec`} disabled={locked} value={v.security ?? "starttls"} onChange={(e) => set("security", e.target.value as "starttls" | "ssl" | "none")}>
            <option value="starttls">STARTTLS</option>
            <option value="ssl">SSL/TLS</option>
            <option value="none">{t("email.field.securityNone")}</option>
          </SelectField>
        </Field>
        <Field label={t("email.field.auth")} htmlFor={`${ids}-auth`}>
          <SelectField id={`${ids}-auth`} value={v.auth_mode ?? "password"} onChange={(e) => set("auth_mode", e.target.value as "password" | "xoauth2" | "none")}>
            <option value="password">{t("email.field.authPassword")}</option>
            <option value="xoauth2">{t("email.field.authOauth")}</option>
            <option value="none">{t("email.field.authNone")}</option>
          </SelectField>
        </Field>
      </div>
      {locked ? (
        <Button variant="ghost" size="sm" className="self-start pointer-coarse:min-h-11" onClick={() => setUnlocked(true)}>
          {t("email.preset.unlock")}
        </Button>
      ) : leavesPreset(preset, v) ? (
        <p className="type-footnote text-label-3">{t("email.preset.unlocked")}</p>
      ) : null}
      {v.security === "none" ? <Alert tone="warning">{t("email.field.securityNoneWarn")}</Alert> : null}
      {v.auth_mode !== "none" ? (
        <Field label={t("email.field.username")} htmlFor={`${ids}-user`} hint={preset ? (locale === "tr" ? preset.username_hint_tr : preset.username_hint_en) : undefined}>
          <Input id={`${ids}-user`} autoComplete="off" className="max-sm:text-base" value={v.username ?? ""} onChange={(e) => set("username", e.target.value)} />
        </Field>
      ) : null}
      {v.auth_mode === "password" ? (
        <SecretInput id={`${ids}-pw`} label={preset ? (locale === "tr" ? preset.password_label_tr : preset.password_label_en) : t("email.field.password")} stored={data.password} value={typeof v.password === "string" ? v.password : null} onChange={(x) => set("password", x)} />
      ) : null}
      {v.auth_mode === "xoauth2" ? (
        <div className="grid gap-3">
          <Field label={t("email.field.oauthProvider")} htmlFor={`${ids}-op`}>
            <SelectField id={`${ids}-op`} value={v.oauth_provider ?? ""} onChange={(e) => set("oauth_provider", e.target.value as "" | "google" | "microsoft")}>
              <option value="">—</option>
              <option value="microsoft">Microsoft 365</option>
              <option value="google">Google</option>
            </SelectField>
          </Field>
          {v.oauth_provider === "microsoft" ? (
            <Field label={t("email.field.tenant")} htmlFor={`${ids}-tenant`}>
              <Input id={`${ids}-tenant`} className="font-mono max-sm:text-base" value={v.oauth_tenant ?? ""} onChange={(e) => set("oauth_tenant", e.target.value.trim())} />
            </Field>
          ) : null}
          <Field label={t("email.field.clientId")} htmlFor={`${ids}-cid`}>
            <Input id={`${ids}-cid`} className="font-mono max-sm:text-base" value={v.oauth_client_id ?? ""} onChange={(e) => set("oauth_client_id", e.target.value.trim())} />
          </Field>
          <SecretInput id={`${ids}-cs`} label={t("email.field.clientSecret")} stored={data.oauth_client_secret} value={typeof v.oauth_client_secret === "string" ? v.oauth_client_secret : null} onChange={(x) => set("oauth_client_secret", x)} />
          <SecretInput id={`${ids}-rt`} label={t("email.field.refreshToken")} hint={t("email.field.refreshHint")} stored={data.oauth_refresh_token} value={typeof v.oauth_refresh_token === "string" ? v.oauth_refresh_token : null} onChange={(x) => set("oauth_refresh_token", x)} />
        </div>
      ) : null}
    </div>
  );
}

function SenderStep({ v, stored, ticked, preset, set }: { v: MailSettings & MailSettingsIn; stored: MailSettings["abroad_ack"]; ticked: boolean; preset: Preset | undefined; set: Setter }) {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  const ids = useId();
  const acked = stored && stored.provider === preset?.id ? stored : null;
  return (
    <div className="flex flex-col gap-3">
      <Field label={t("email.field.from")} htmlFor={`${ids}-from`} hint={t("email.field.fromHint")}>
        <Input id={`${ids}-from`} type="email" inputMode="email" className="max-sm:text-base" value={v.from_address ?? ""} onChange={(e) => set("from_address", e.target.value)} />
      </Field>
      <Field label={t("email.field.fromName")} htmlFor={`${ids}-fname`}>
        <Input id={`${ids}-fname`} className="max-sm:text-base" value={v.from_name ?? ""} onChange={(e) => set("from_name", e.target.value)} />
      </Field>
      <Field label={t("email.field.replyTo")} htmlFor={`${ids}-reply`} hint={t("email.field.replyHint")}>
        <Input id={`${ids}-reply`} type="email" inputMode="email" className="max-sm:text-base" value={v.reply_to ?? ""} onChange={(e) => set("reply_to", e.target.value)} />
      </Field>
      {preset?.abroad ? (
        <Alert tone="warning" testId="mail-abroad">
          <p className="type-headline">{t("email.abroad.title")}</p>
          <p>{t("email.abroad.body", { provider: preset.label })}</p>
          {acked ? (
            <p className="type-footnote">{t("email.abroad.recorded", { by: acked.by ?? "-", at: acked.at ? fmt.dateTime(acked.at) : "-" })}</p>
          ) : (
            <label className="mt-2 flex min-h-11 items-center gap-2">
              <Checkbox checked={ticked} onCheckedChange={(c) => set("abroad_ack", c === true)} />
              <span>{t("email.abroad.check")}</span>
            </label>
          )}
        </Alert>
      ) : null}
    </div>
  );
}

function DomainStep({ v, result, onResult, set }: { v: MailSettings & MailSettingsIn; result: DnsOut | null; onResult: (r: DnsOut) => void; set: Setter }) {
  const { t, locale } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ids = useId();
  const domain = domainOf(v.from_address);
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      onResult(await mailApi.dns({ domain, selector: v.dkim_selector || undefined }));
    } catch (e) {
      setError(mailError(e, locale));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex flex-col gap-3">
      <p className="type-callout text-label-2">{t("email.dns.title", { domain: domain || "—" })}</p>
      <p className="type-footnote text-label-3">{t("email.dns.lead")}</p>
      <Field label={t("email.field.selector")} htmlFor={`${ids}-sel`} hint={t("email.field.selectorHint")}>
        <Input id={`${ids}-sel`} className="font-mono max-sm:text-base" value={v.dkim_selector ?? ""} onChange={(e) => set("dkim_selector", e.target.value.trim())} />
      </Field>
      <Button variant="outline" className="self-start pointer-coarse:min-h-11" disabled={!domain || busy} onClick={() => void run()} data-testid="mail-dns-run">
        <BusyLabel busy={busy} label={t("busy.checking")}>
          {result ? t("email.dns.rerun") : t("email.dns.run")}
        </BusyLabel>
      </Button>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {result ? (
        <ul className="flex flex-col gap-2" aria-live="polite" data-testid="mail-dns">
          {result.checks.map((c) => (
            <li key={c.check}>
              <Alert tone={dnsTone(c.status) === "neutral" ? "neutral" : dnsTone(c.status)}>
                <p className="type-headline">
                  {c.check.toUpperCase()} · {t(`email.dns.${c.status}`)}
                </p>
                <p>{locale === "tr" ? c.message_tr : c.message_en}</p>
                {c.record ? <p className="mt-1 font-mono type-caption break-all">{c.record}</p> : null}
                {(locale === "tr" ? c.fix_tr : c.fix_en) ? <CopyField label={t("email.dns.fix")} value={(locale === "tr" ? c.fix_tr : c.fix_en) ?? ""} mono={false} /> : null}
              </Alert>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function TestStep({ result, onResult, configured }: { result: TestOut | null; onResult: (r: TestOut) => void; configured: boolean }) {
  const { t, locale } = useI18n();
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [arrived, setArrived] = useState<boolean | null>(null);
  const ids = useId();
  const send = async () => {
    setBusy(true);
    setError(null);
    setArrived(null);
    try {
      onResult(await mailApi.test(to, locale === "tr" ? "tr" : "en"));
    } catch (e) {
      setError(mailError(e, locale));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex flex-col gap-3">
      {!configured ? <Alert tone="info">{t("email.test.unsent")}</Alert> : null}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <Field label={t("email.test.to")} htmlFor={`${ids}-to`} className="min-w-0 max-sm:w-full">
          <Input id={`${ids}-to`} type="email" inputMode="email" className="w-full sm:w-72 max-sm:text-base" value={to} onChange={(e) => setTo(e.target.value)} />
        </Field>
        <Button type="submit" disabled={!to || busy} className="pointer-coarse:min-h-11 max-sm:w-full" data-testid="mail-test-send">
          <BusyLabel busy={busy} label={t("busy.sending")} icon={<Send aria-hidden />}>
            {t("email.test.send")}
          </BusyLabel>
        </Button>
      </form>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {result ? (
        <div className="flex flex-col gap-2" aria-live="polite" data-testid="mail-test-result">
          {result.ok ? (
            <Alert tone="success">{t("email.test.sent", { ms: result.duration_ms })}</Alert>
          ) : (
            <Alert tone={result.status === "UNSENT" ? "info" : "error"}>
              <p className="type-headline">{t("email.test.failed")}</p>
              <p>{(locale === "tr" ? result.hint_tr : result.hint_en) ?? result.error}</p>
              {result.error ? <p className="mt-1 font-mono type-caption break-all">{result.error}</p> : null}
            </Alert>
          )}
          {result.transcript.length ? (
            <details className="rounded-xl bg-fill-2 p-3">
              <summary className="min-h-11 cursor-pointer content-center type-callout text-label-1">{t("email.test.transcript")}</summary>
              <pre className="mt-2 max-h-72 overflow-auto font-mono type-caption whitespace-pre-wrap break-all text-label-2" data-testid="mail-transcript">
                {result.transcript.join("\n")}
              </pre>
            </details>
          ) : null}
          {result.ok ? (
            <div className="flex flex-col gap-2">
              <p className="type-callout text-label-1">{t("email.test.arrived")}</p>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" className="pointer-coarse:min-h-11" onClick={() => setArrived(true)}>
                  {t("email.test.yes")}
                </Button>
                <Button variant="outline" className="pointer-coarse:min-h-11" onClick={() => setArrived(false)}>
                  {t("email.test.no")}
                </Button>
              </div>
              {arrived === true ? <Alert tone="success">{t("email.test.thanks")}</Alert> : null}
              {arrived === false ? <Alert tone="info">{t("email.test.tips")}</Alert> : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function EnableStep({ data }: { data: MailSettings }) {
  const { t, locale } = useI18n();
  const [busy, setBusy] = useState(false);
  const [left, setLeft] = useState(data.unsent);
  return (
    <div className="flex flex-col gap-3">
      {data.configured ? (
        <Alert tone="success">
          <p className="type-headline">{t("email.enable.ready")}</p>
          <p>{t("email.enable.summary", { host: data.host ?? "-", from: data.from_address ?? "-" })}</p>
        </Alert>
      ) : (
        <Alert tone="warning">{t("email.enable.notReady")}</Alert>
      )}
      {data.configured && left > 0 ? (
        <div className="flex flex-col gap-2" data-testid="mail-unsent">
          <p className="type-callout text-label-1">{t("email.enable.unsent", { n: left })}</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" className="pointer-coarse:min-h-11" onClick={() => setLeft(0)}>
              {t("email.enable.onlyNew")}
            </Button>
            <Button
              className="pointer-coarse:min-h-11"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  const r = await mailApi.requeue();
                  setLeft(r.unsent);
                  toast.success(t("email.enable.queued", { n: r.queued }));
                } catch (e) {
                  toast.error(mailError(e, locale));
                } finally {
                  setBusy(false);
                }
              }}
            >
              {t("email.enable.sendWaiting")}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
