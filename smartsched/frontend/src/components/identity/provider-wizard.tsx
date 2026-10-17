"use client";
/**
 * The guided setup of one identity provider (wave 3b W3-IDP; design docs/design/v3/integrations.md §5): five steps
 * 1 Ön ayar (label, slug, domain), 2 Sağlayıcıda kaydet (values to paste into the provider's console, built from the
 * public URL, each with "Kopyala"), 3 Değerleri yapıştır (write-only secret), 4 Bağlantıyı dene (discovery / metadata
 * check rows + a real test login in a popup that reports the claims), 5 Etkinleştir (who may sign in, the sign-up role,
 * allowed domains, role mapping). Shared by every administrator: the header says "Son değişiklik: <ad>, <zaman>" and
 * each save sends the version it started from (409 ``conflict`` when another administrator saved in between).
 */
import { ArrowLeft, Check as CheckIcon, Circle, Lock, Plus, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { CopyField } from "@/components/admin/integrations/copy-field";
import { Field, FieldRow, Loading, SelectField } from "@/components/admin/kit";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { BusyButton } from "@/components/ui/busy-label";
import { Button, IconButton } from "@/components/ui/button";
import { StatusDot } from "@/components/ui/data-table/data-table";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useRoles } from "@/lib/api/crbs";
import { apiProblem } from "@/lib/api/identity";
import { problemText } from "@/lib/api/error-text";
import { useI18n } from "@/lib/i18n/provider";
import { roleLabel } from "@/lib/i18n/roles";
import { usePermissions } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import { idp, idpKeys, useIdpMutation, useProviderMappings, useSetup, type Check, type Provider, type ProviderIn, type Setup, type TestResult } from "./providers-api";
import { cleanPasted, copyAllText, firstOpenStep, looksLikeGuid, missingFields, parseDomains, signupRoleEligible, stepState, WIZARD_STEPS, type WizardStep } from "./providers-model";

export const POLL_MS = 1500;
const POLL_LIMIT = 120; // 3 minutes

type T = ReturnType<typeof useI18n>["t"];

function when(iso: string | null | undefined, locale: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Europe/Istanbul",
      });
}

export function changedLine(t: T, p: Pick<Provider, "changed_by" | "changed_at">, locale: string): string {
  return p.changed_by
    ? t("identity.changed", {
        who: p.changed_by,
        when: when(p.changed_at, locale),
      })
    : t("identity.changedNever");
}

function useSave(p: Provider) {
  const { t, locale } = useI18n();
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const m = useIdpMutation((body: ProviderIn) => idp.put(p.id, { version: p.version, ...body }));
  const save = (body: ProviderIn, ok?: string, after?: (out: Provider) => void) => {
    setError(null);
    m.mutate(body, {
      onSuccess: (out) => {
        if (ok) toast.success(ok);
        after?.(out);
      },
      onError: (e) => {
        const prob = apiProblem(e, locale);
        setConflict(prob.code === "conflict");
        setError(problemText(e, locale) ?? prob.text ?? t("identity.saveFailed"));
      },
    });
  };
  return { save, error, conflict, pending: m.isPending, setError };
}

interface Kept {
  step: WizardStep | null;
  setStep: (s: WizardStep) => void;
  test: TestResult | null;
  setTest: (r: TestResult) => void;
}

export function ProviderWizard({ providerId, onBack }: { providerId: number; onBack: () => void }) {
  const { t, locale } = useI18n();
  const q = useSetup(providerId);
  // the step and the last test survive the re-mount after each save (a new version)
  const [step, setStep] = useState<WizardStep | null>(null);
  const [test, setTest] = useState<TestResult | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => headingRef.current?.focus(), []);
  if (q.isLoading) return <Loading />;
  if (q.isError || !q.data) return <Alert tone="error">{problemText(q.error, locale) ?? t("identity.loadError")}</Alert>;
  return <Wizard key={q.data.provider.id} setup={q.data} onBack={onBack} headingRef={headingRef} keep={{ step, setStep, test, setTest }} />;
}

function Wizard({ setup, onBack, headingRef, keep }: { setup: Setup; onBack: () => void; headingRef: React.RefObject<HTMLHeadingElement | null>; keep: Kept }) {
  const { t, locale } = useI18n();
  const p = setup.provider;
  const states = stepState(p, { publicUrl: setup.public_url });
  const step: WizardStep = keep.step ?? (!p.configured && !p.client_id && !p.issuer && !p.saml?.idp_entity_id ? "preset" : firstOpenStep(states));
  const setStep = keep.setStep;
  const test = keep.test;
  const setTest = keep.setTest;
  const tested = test?.ok === true || p.test_ok === true;
  const name = locale === "en" ? p.label_en : p.label;
  return (
    <div className="flex flex-col gap-5" data-testid="idp-wizard" data-provider={p.name}>
      <div className="flex flex-wrap items-start gap-3">
        <Button variant="ghost" size="md" onClick={onBack} className="-ml-2 pointer-coarse:min-h-11" data-testid="idp-wizard-back">
          <ArrowLeft aria-hidden />
          {t("identity.back")}
        </Button>
        <div className="min-w-0 flex-1">
          <h2 ref={headingRef} tabIndex={-1} className="flex items-center gap-2 type-title-3 text-label-1 outline-hidden">
            <Monogram text={p.badge} />
            {t("identity.wizard.title", { name })}
          </h2>
          <p className="type-footnote text-label-2" data-testid="idp-changed">
            {changedLine(t, p, locale)} · {t("identity.wizard.shared")}
          </p>
        </div>
        <StatusWord status={p.status} />
      </div>
      <nav aria-label={t("identity.wizard.steps")}>
        <ol className="flex flex-wrap gap-2" data-testid="idp-steps">
          {WIZARD_STEPS.map((s, i) => {
            const st = s === "enable" && tested && p.configured ? (p.enabled ? "done" : "open") : states[s];
            return (
              <li key={s}>
                <Button
                  variant={step === s ? "secondary" : "ghost"}
                  size="sm"
                  aria-current={step === s ? "step" : undefined}
                  disabled={st === "locked"}
                  onClick={() => setStep(s)}
                  className="min-h-11 gap-1.5 sm:min-h-9"
                  data-testid={`idp-step-${s}`}
                  data-state={st}
                >
                  {st === "done" ? <CheckIcon aria-hidden className="size-4" /> : st === "locked" ? <Lock aria-hidden className="size-4" /> : <Circle aria-hidden className="size-3" />}
                  <span>
                    {i + 1}. {t(`identity.step.${s}`)}
                  </span>
                </Button>
              </li>
            );
          })}
        </ol>
      </nav>
      {step === "preset" ? <PresetStep p={p} onNext={() => setStep("console")} /> : null}
      {step === "console" ? <ConsoleStep setup={setup} onNext={() => setStep("values")} /> : null}
      {step === "values" ? <ValuesStep p={p} setup={setup} onNext={() => setStep("test")} /> : null}
      {step === "test" ? <TestStep p={p} result={test} onResult={setTest} onGoto={(s) => setStep(s)} onNext={() => setStep("enable")} /> : null}
      {step === "enable" ? <EnableStep p={p} tested={tested} onDone={onBack} /> : null}
    </div>
  );
}

export function Monogram({ text }: { text: string }) {
  return (
    <span aria-hidden className="grid h-10 min-w-10 place-items-center rounded-xl bg-fill-2 px-1.5 type-caption font-bold text-label-1 shadow-(--edge-control)">
      {text}
    </span>
  );
}

export function StatusWord({ status }: { status: Provider["status"] }) {
  const { t } = useI18n();
  const tone = status === "connected" ? "feasible" : status === "error" ? "infeasible" : status === "disabled" ? "locked" : "neutral";
  return (
    <StatusDot tone={tone}>
      <span data-testid="idp-status">{t(`identity.status.${status}`)}</span>
    </StatusDot>
  );
}

function StepFrame({ title, lead, children, footer }: { title: string; lead?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <section className="flex flex-col gap-4 rounded-2xl bg-(--mat) p-4 shadow-(--edge-control) sm:p-5">
      <div>
        <h3 className="type-headline text-label-1">{title}</h3>
        {lead ? <p className="mt-1 type-footnote text-label-2">{lead}</p> : null}
      </div>
      {children}
      {footer ? <div className="sticky bottom-0 -mx-4 flex flex-wrap gap-2 bg-(--mat) px-4 pt-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] sm:static sm:mx-0 sm:px-0 sm:pb-0">{footer}</div> : null}
    </section>
  );
}

function ErrorLine({ error, conflict }: { error: string | null; conflict?: boolean }) {
  const { t } = useI18n();
  if (!error) return null;
  return (
    <Alert tone={conflict ? "warning" : "error"} data-testid="idp-error">
      {error}
      {conflict ? (
        <Button size="sm" variant="outline" className="mt-2 min-h-11 sm:min-h-9" onClick={() => window.location.reload()}>
          {t("identity.reload")}
        </Button>
      ) : null}
    </Alert>
  );
}

/* ---------------------------------------------------------------------------------------- step 1 */

function PresetStep({ p, onNext }: { p: Provider; onNext: () => void }) {
  const { t } = useI18n();
  const { save, error, conflict, pending } = useSave(p);
  const [label, setLabel] = useState(p.display_name ?? "");
  const [slug, setSlug] = useState(p.name);
  const [domain, setDomain] = useState(p.kind === "google_workspace" ? p.hosted_domains.join(", ") : (p.domain_hint ?? ""));
  const body: ProviderIn = {};
  if (cleanPasted(label).value !== (p.display_name ?? "")) body.display_name = cleanPasted(label).value;
  if (slug !== p.name && !p.identities && p.kind !== "entra") body.name = cleanPasted(slug).value;
  if (p.kind === "google_workspace" && parseDomains(domain).join(",") !== p.hosted_domains.join(",")) body.hosted_domains = parseDomains(domain);
  if (p.kind === "entra" && cleanPasted(domain).value !== (p.domain_hint ?? "")) body.domain_hint = cleanPasted(domain).value;
  return (
    <StepFrame
      title={t("identity.step.preset")}
      lead={t("identity.preset.lead")}
      footer={
        <BusyButton
          busy={pending}
          busyLabel={t("busy.saving")}
          className="min-h-11"
          data-testid="idp-preset-next"
          onClick={() => (Object.keys(body).length ? save(body, t("identity.saved"), onNext) : onNext())}
        >
          {t("identity.next")}
        </BusyButton>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label={t("identity.field.display_name")}
          htmlFor="idp-label"
          hint={t("identity.preset.labelHint", {
            label: label || p.label,
          })}
        >
          <Input id="idp-label" value={label} placeholder={p.label} onChange={(e) => setLabel(e.target.value)} className="text-base sm:text-sm" data-testid="idp-label" />
        </Field>
        <Field label={t("identity.field.slug")} htmlFor="idp-slug" hint={p.identities || p.kind === "entra" ? t("identity.preset.slugLocked") : t("identity.preset.slugHint")}>
          <Input
            id="idp-slug"
            value={slug}
            disabled={!!p.identities || p.kind === "entra"}
            onChange={(e) => setSlug(e.target.value.toLowerCase())}
            className="font-mono text-base sm:text-sm"
            spellCheck={false}
            data-testid="idp-slug"
          />
        </Field>
        {p.kind === "google_workspace" || p.kind === "entra" ? (
          <Field label={t(p.kind === "google_workspace" ? "identity.field.hosted_domains" : "identity.field.domain_hint")} htmlFor="idp-domain" hint={t("identity.hint.domains")}>
            <Input id="idp-domain" value={domain} placeholder="uni.edu.tr" onChange={(e) => setDomain(e.target.value)} className="text-base sm:text-sm" spellCheck={false} data-testid="idp-domain" />
          </Field>
        ) : null}
      </div>
      <ErrorLine error={error} conflict={conflict} />
    </StepFrame>
  );
}

/* ---------------------------------------------------------------------------------------- step 2 */

function ConsoleStep({ setup, onNext }: { setup: Setup; onNext: () => void }) {
  const { t, locale } = useI18n();
  const steps = locale === "en" ? setup.steps.en : setup.steps.tr;
  if (!setup.public_url) {
    return (
      <StepFrame title={t("identity.step.console")}>
        <Alert tone="error" data-testid="idp-no-public-url">
          {t("identity.console.noPublicUrl")}
        </Alert>
      </StepFrame>
    );
  }
  const all = copyAllText(setup.console, locale === "en" ? "en" : "tr");
  const mail = `mailto:?subject=${encodeURIComponent(t("identity.console.mailSubject", { name: setup.provider.label }))}&body=${encodeURIComponent(`${steps.join("\n")}\n\n${all}`)}`;
  return (
    <StepFrame
      title={t("identity.step.console")}
      lead={t("identity.console.lead")}
      footer={
        <Button className="min-h-11" onClick={onNext} data-testid="idp-console-next">
          {t("identity.next")}
        </Button>
      }
    >
      {!setup.public_url_secure ? <Alert tone="warning">{t("identity.console.httpWarning")}</Alert> : null}
      <ol className="list-decimal space-y-1 pl-5 type-callout text-label-1" data-testid="idp-console-steps">
        {steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      <div className="flex flex-col gap-4" data-testid="idp-console-values">
        {setup.console.map((v) =>
          v.value ? <CopyField key={v.key} label={locale === "en" ? v.label_en : v.label_tr} value={v.value} multiline={v.value.length > 60} testId={`idp-copy-${v.key}`} /> : null,
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          className="min-h-11 sm:min-h-9"
          onClick={() => void navigator.clipboard?.writeText(all).then(() => toast.success(t("identity.console.copiedAll")))}
          data-testid="idp-copy-all"
        >
          {t("identity.console.copyAll")}
        </Button>
        <a href={mail} className="inline-flex min-h-11 items-center rounded-lg px-3 type-callout text-(--accent) underline sm:min-h-9">
          {t("identity.console.sendIt")}
        </a>
        {setup.provider.kind === "saml" ? (
          <a
            href={`/api/v1/auth/sso/${setup.provider.name}/metadata`}
            download={`${setup.provider.name}-sp-metadata.xml`}
            className="inline-flex min-h-11 items-center rounded-lg px-3 type-callout text-(--accent) underline sm:min-h-9"
            data-testid="idp-sp-metadata"
          >
            {t("identity.console.downloadMetadata")}
          </a>
        ) : null}
      </div>
    </StepFrame>
  );
}

/* ---------------------------------------------------------------------------------------- step 3 */

function SecretField({ p, value, onChange }: { p: Provider; value: string; onChange: (v: string) => void }) {
  const { t } = useI18n();
  const [replacing, setReplacing] = useState(!p.client_secret_set);
  const [note, setNote] = useState<string | null>(null);
  if (p.client_secret_set && !replacing) {
    return (
      <Field label={t("identity.field.client_secret")} htmlFor="idp-secret-replace" hint={t("identity.hint.secret")}>
        <span className="flex flex-wrap items-center gap-2">
          <StatusDot tone="feasible">
            <span data-testid="idp-secret-set">{t("identity.secretSet")}</span>
          </StatusDot>
          <Button id="idp-secret-replace" size="sm" variant="outline" className="min-h-11 sm:min-h-9" onClick={() => setReplacing(true)} data-testid="idp-secret-replace">
            {t("identity.replace")}
          </Button>
        </span>
      </Field>
    );
  }
  return (
    <Field label={t("identity.field.client_secret")} htmlFor="idp-secret" hint={note ?? t("identity.hint.secret")}>
      <Input
        id="idp-secret"
        type="password"
        autoComplete="new-password"
        spellCheck={false}
        value={value}
        onChange={(e) => {
          const c = cleanPasted(e.target.value);
          onChange(c.value);
          setNote(looksLikeGuid(c.value) ? t("identity.hint.secretLooksLikeId") : c.trimmed && c.value ? t("identity.hint.trimmed") : null);
        }}
        className="text-base sm:text-sm"
        data-testid="idp-secret"
      />
    </Field>
  );
}

function TextField({
  id,
  label,
  hint,
  value,
  onChange,
  placeholder,
  mono = true,
}: {
  id: string;
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  mono?: boolean;
}) {
  return (
    <Field label={label} htmlFor={id} hint={hint}>
      <Input
        id={id}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        autoComplete="off"
        className={cn("text-base sm:text-sm", mono && "font-mono")}
        data-testid={id}
      />
    </Field>
  );
}

function ValuesStep({ p, setup, onNext }: { p: Provider; setup: Setup; onNext: () => void }) {
  const { t } = useI18n();
  const { save, error, conflict, pending } = useSave(p);
  const [v, setV] = useState({
    tenant_id: p.tenant_id ?? "",
    client_id: p.client_id ?? "",
    client_secret: "",
    issuer: p.issuer ?? "",
    hosted_domains: p.hosted_domains.join(", "),
    groups_claim: p.groups_claim,
    roles_claim: p.roles_claim,
    metadata_url: p.saml?.metadata_url ?? "",
    metadata_xml: "",
    idp_entity_id: p.saml?.idp_entity_id ?? "",
    email_attribute: p.saml?.email_attribute ?? "",
    groups_attribute: p.saml?.groups_attribute ?? "",
    secret_expires: p.secret_expires ?? "",
  });
  const set = (k: keyof typeof v) => (x: string) => setV((o) => ({ ...o, [k]: x }));
  const body: ProviderIn = {};
  const c = (x: string) => cleanPasted(x).value;
  if (p.kind === "entra" && c(v.tenant_id) !== (p.tenant_id ?? "")) body.tenant_id = c(v.tenant_id);
  if (p.kind !== "saml" && c(v.client_id) !== (p.client_id ?? "")) body.client_id = c(v.client_id);
  if (p.kind !== "saml" && v.client_secret) body.client_secret = v.client_secret;
  if (p.kind !== "saml" && v.secret_expires !== (p.secret_expires ?? "")) body.secret_expires = v.secret_expires;
  if (p.kind === "oidc") {
    if (c(v.issuer) !== (p.issuer ?? "")) body.issuer = c(v.issuer);
    if (c(v.groups_claim) !== p.groups_claim) body.groups_claim = c(v.groups_claim);
    if (c(v.roles_claim) !== p.roles_claim) body.roles_claim = c(v.roles_claim);
  }
  if (p.kind === "google_workspace" && parseDomains(v.hosted_domains).join(",") !== p.hosted_domains.join(",")) body.hosted_domains = parseDomains(v.hosted_domains);
  if (p.kind === "saml") {
    if (c(v.metadata_url) !== (p.saml?.metadata_url ?? "")) body.metadata_url = c(v.metadata_url);
    if (v.metadata_xml.trim()) body.metadata_xml = v.metadata_xml;
    if (c(v.idp_entity_id) !== (p.saml?.idp_entity_id ?? "")) body.idp_entity_id = c(v.idp_entity_id);
    if (c(v.email_attribute) !== (p.saml?.email_attribute ?? "")) body.email_attribute = c(v.email_attribute);
    if (c(v.groups_attribute) !== (p.saml?.groups_attribute ?? "")) body.groups_attribute = c(v.groups_attribute);
  }
  const missing = missingFields(p);
  return (
    <StepFrame
      title={t("identity.step.values")}
      lead={
        missing.length
          ? t("identity.values.missing", {
              fields: missing.map((m) => t(`identity.field.${m}` as "identity.field.issuer")).join(", "),
            })
          : t("identity.values.complete")
      }
      footer={
        <>
          <BusyButton
            busy={pending}
            busyLabel={t("busy.saving")}
            disabled={!Object.keys(body).length}
            className="min-h-11"
            onClick={() => save(body, t("identity.saved"))}
            data-testid="idp-values-save"
          >
            {t("identity.save")}
          </BusyButton>
          <Button variant="outline" className="min-h-11" disabled={!p.configured} onClick={onNext} data-testid="idp-values-next">
            {t("identity.next")}
          </Button>
        </>
      }
    >
      {p.library_required ? (
        <Alert tone="warning" data-testid="idp-library-required">
          {t("identity.libraryRequired")}
        </Alert>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        {p.kind === "entra" ? <TextField id="idp-tenant" label={t("identity.field.tenant_id")} hint={t("identity.hint.tenant")} value={v.tenant_id} onChange={set("tenant_id")} /> : null}
        {p.kind === "oidc" ? (
          <TextField
            id="idp-issuer"
            label={t("identity.field.issuer")}
            hint={t("identity.hint.issuer", {
              example: setup.issuer_hint ?? "https://idp.uni.edu.tr",
            })}
            value={v.issuer}
            placeholder={setup.issuer_hint ?? ""}
            onChange={set("issuer")}
          />
        ) : null}
        {p.kind !== "saml" ? <TextField id="idp-client" label={t("identity.field.client_id")} value={v.client_id} onChange={set("client_id")} /> : null}
        {p.kind === "google_workspace" ? (
          <TextField id="idp-hd" label={t("identity.field.hosted_domains")} hint={t("identity.hint.domains")} value={v.hosted_domains} onChange={set("hosted_domains")} mono={false} />
        ) : null}
      </div>
      {p.kind !== "saml" ? <SecretField p={p} value={v.client_secret} onChange={set("client_secret")} /> : null}
      {p.kind !== "saml" ? (
        <Field label={t("identity.field.secret_expires")} htmlFor="idp-secret-expires" hint={t("identity.hint.secretExpires")}>
          <Input id="idp-secret-expires" type="date" value={v.secret_expires} onChange={(e) => set("secret_expires")(e.target.value)} className="max-w-48 text-base sm:text-sm" data-testid="idp-secret-expires" />
        </Field>
      ) : null}
      {p.kind === "oidc" ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField id="idp-groups-claim" label={t("identity.field.groups_claim")} hint={t("identity.hint.claims")} value={v.groups_claim} onChange={set("groups_claim")} />
          <TextField id="idp-roles-claim" label={t("identity.field.roles_claim")} value={v.roles_claim} onChange={set("roles_claim")} />
          <FieldRow label={t("identity.field.trust_email")} hint={t("identity.hint.trustEmail")} htmlFor="idp-trust-email">
            <Switch id="idp-trust-email" checked={p.trust_email} disabled={pending} onCheckedChange={(x) => save({ trust_email: x })} />
          </FieldRow>
        </div>
      ) : null}
      {p.kind === "saml" ? (
        <div className="grid gap-4">
          <TextField
            id="idp-metadata-url"
            label={t("identity.field.metadata_url")}
            hint={t("identity.hint.metadata")}
            value={v.metadata_url}
            placeholder={setup.issuer_hint ?? ""}
            onChange={set("metadata_url")}
          />
          <Field label={t("identity.field.metadata_xml")} htmlFor="idp-metadata-xml">
            <Textarea
              id="idp-metadata-xml"
              rows={4}
              value={v.metadata_xml}
              onChange={(e) => set("metadata_xml")(e.target.value)}
              className="font-mono text-base sm:text-sm"
              data-testid="idp-metadata-xml"
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField id="idp-entity" label={t("identity.field.idp_entity_id")} value={v.idp_entity_id} onChange={set("idp_entity_id")} />
            <TextField id="idp-mail-attr" label={t("identity.field.email_attribute")} value={v.email_attribute} onChange={set("email_attribute")} />
            <TextField id="idp-groups-attr" label={t("identity.field.groups_attribute")} value={v.groups_attribute} onChange={set("groups_attribute")} />
          </div>
        </div>
      ) : null}
      <Checks checks={p.discovery.checks} />
      <ErrorLine error={error} conflict={conflict} />
    </StepFrame>
  );
}

function Checks({ checks }: { checks: Check[] }) {
  const { locale } = useI18n();
  if (!checks.length) return null;
  return (
    <ul className="flex flex-col gap-1.5" data-testid="idp-checks" aria-live="polite">
      {checks.map((c) => (
        <li key={c.key} className="flex items-start gap-2 type-callout" data-testid={`idp-check-${c.key}`} data-ok={c.ok}>
          {c.ok ? <CheckIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-status-feasible-fg" /> : <X aria-hidden className="mt-0.5 size-4 shrink-0 text-status-infeasible-fg" />}
          <span className="text-label-1">{locale === "en" ? c.en : c.tr}</span>
        </li>
      ))}
    </ul>
  );
}

/* ---------------------------------------------------------------------------------------- step 4 */

function TestStep({ p, result, onResult, onGoto, onNext }: { p: Provider; result: TestResult | null; onResult: (r: TestResult) => void; onGoto: (s: WizardStep) => void; onNext: () => void }) {
  const { t, locale } = useI18n();
  const discover = useIdpMutation(() => idp.discover(p.id));
  const [polling, setPolling] = useState(false);
  const [popupBlocked, setPopupBlocked] = useState(false);
  const timer = useRef<number | null>(null);
  useEffect(() => () => (timer.current ? window.clearTimeout(timer.current) : undefined), []);
  const runTest = async () => {
    setPopupBlocked(false);
    const popup = window.open("about:blank", "smartsched-idp-test", "popup,width=520,height=680");
    let start;
    try {
      start = await idp.startTest(p.id);
    } catch (e) {
      popup?.close();
      toast.error(problemText(e, locale) ?? t("identity.saveFailed"));
      return;
    }
    if (popup) popup.location.href = start.authorize_url;
    else {
      setPopupBlocked(true);
      window.location.assign(start.authorize_url); // phones / blocked popups: same tab (the result stays on the server)
      return;
    }
    setPolling(true);
    let n = 0;
    const tick = async () => {
      n += 1;
      try {
        const r = await idp.testResult(p.id, start.test_id);
        if (r.status === "done") {
          setPolling(false);
          onResult(r);
          return;
        }
      } catch {
        /* keep polling */
      }
      if (n < POLL_LIMIT) timer.current = window.setTimeout(tick, POLL_MS);
      else setPolling(false);
    };
    timer.current = window.setTimeout(tick, POLL_MS);
  };
  const checks = discover.data?.checks ?? p.discovery.checks;
  return (
    <StepFrame
      title={t("identity.step.test")}
      lead={t("identity.test.lead")}
      footer={
        <>
          <BusyButton variant="outline" busy={discover.isPending} busyLabel={t("identity.test.checking")} className="min-h-11" onClick={() => discover.mutate(undefined)} data-testid="idp-discover">
            {t("identity.test.check")}
          </BusyButton>
          <BusyButton busy={polling} busyLabel={t("identity.test.waiting")} className="min-h-11" onClick={() => void runTest()} data-testid="idp-test-login">
            {t("identity.test.login")}
          </BusyButton>
          <Button variant="ghost" className="min-h-11" disabled={!(result?.ok || p.test_ok)} onClick={onNext} data-testid="idp-test-next">
            {t("identity.next")}
          </Button>
        </>
      }
    >
      <Checks checks={checks} />
      {popupBlocked ? <Alert tone="warning">{t("identity.test.popupBlocked")}</Alert> : null}
      {result ? <TestReport r={result} onGoto={onGoto} /> : p.test_ok ? <Alert tone="success">{t("identity.test.passedBefore", { when: p.test_at ?? "" })}</Alert> : null}
    </StepFrame>
  );
}

const STEP_OF: Record<number, WizardStep> = {
  1: "preset",
  2: "console",
  3: "values",
  4: "test",
};

export function TestReport({ r, onGoto }: { r: TestResult; onGoto?: (s: WizardStep) => void }) {
  const { t, locale } = useI18n();
  if (!r.ok) {
    const hint = r.hint ? (locale === "en" ? r.hint.en : r.hint.tr) : t("identity.test.failedGeneric");
    const back = r.hint?.step ? STEP_OF[r.hint.step] : null;
    return (
      <div data-testid="idp-test-result" data-ok="false">
        <Alert tone="error" title={t("identity.test.failed")}>
          <span className="block">{hint}</span>
          {r.detail ? (
            <details className="mt-1 type-footnote">
              <summary>{t("identity.test.detail")}</summary>
              <code className="break-all">{r.hint?.raw ?? r.detail}</code>
            </details>
          ) : null}
          {back && onGoto ? (
            <Button size="sm" variant="outline" className="mt-2 min-h-11 sm:min-h-9" onClick={() => onGoto(back)}>
              {t("identity.test.goto", { n: r.hint?.step ?? 0 })}
            </Button>
          ) : null}
        </Alert>
      </div>
    );
  }
  const claims = Object.entries(r.claims ?? {}).filter(([k]) => !["iss", "aud", "exp", "iat", "nbf"].includes(k));
  return (
    <div className="flex flex-col gap-3" data-testid="idp-test-result" data-ok="true">
      <Alert
        tone="success"
        title={t("identity.test.passed", {
          email: r.verified_email ?? "—",
        })}
      >
        {t("identity.test.groups", { n: r.groups.length })}
        {r.mapped_role ? ` · ${t("identity.test.mapped", { role: r.mapped_role.name })}` : ""}
        {r.domain_ok === false ? ` · ${t("identity.test.domainBlocked")}` : ""}
      </Alert>
      <details>
        <summary className="cursor-pointer type-callout text-label-1">{t("identity.test.claims", { n: claims.length })}</summary>
        <dl className="mt-2 grid grid-cols-[minmax(6rem,auto)_1fr] gap-x-3 gap-y-1 type-footnote">
          {claims.map(([k, val]) => (
            <div key={k} className="contents">
              <dt className="font-mono text-label-2">{k}</dt>
              <dd className="break-all font-mono text-label-1">{Array.isArray(val) ? val.join(", ") : String(val)}</dd>
            </div>
          ))}
        </dl>
      </details>
    </div>
  );
}

/* ---------------------------------------------------------------------------------------- step 5 */

function EnableStep({ p, tested, onDone }: { p: Provider; tested: boolean; onDone: () => void }) {
  const { t, locale } = useI18n();
  const { can } = usePermissions();
  const roles = useRoles(can("setup.roles"));
  const { save, error, conflict, pending } = useSave(p);
  const [inviteOnly, setInviteOnly] = useState(p.invite_only || !p.self_signup);
  const [roleId, setRoleId] = useState(String(p.default_role?.id ?? ""));
  const [domains, setDomains] = useState(p.allowed_domains.join(", "));
  const name = locale === "en" ? p.label_en : p.label;
  const role = roles.data?.find((r) => String(r.id) === roleId) ?? p.default_role ?? null;
  const body = (enabled: boolean): ProviderIn => ({
    invite_only: inviteOnly,
    self_signup: !inviteOnly,
    allowed_domains: parseDomains(domains),
    ...(roleId && Number(roleId) !== p.default_role?.id ? { default_role_id: Number(roleId) } : {}),
    enabled,
  });
  return (
    <StepFrame
      title={t("identity.step.enable")}
      lead={t(inviteOnly ? "identity.enable.summaryInvite" : "identity.enable.summaryOpen", { name, role: role ? roleLabel(t, role) : "—" })}
      footer={
        <>
          <BusyButton
            busy={pending}
            busyLabel={t("busy.saving")}
            disabled={!tested || !p.configured}
            className="min-h-11"
            onClick={() => save(body(true), t("identity.enable.enabled", { name }), onDone)}
            data-testid="idp-enable"
          >
            {t("identity.enable.enable")}
          </BusyButton>
          <Button variant="outline" className="min-h-11" disabled={pending} onClick={() => save(body(false), t("identity.saved"), onDone)} data-testid="idp-save-off">
            {t("identity.enable.saveOff")}
          </Button>
        </>
      }
    >
      {!tested ? <Alert tone="info">{t("identity.enable.needsTest")}</Alert> : null}
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 type-callout font-semibold text-label-1">{t("identity.enable.who")}</legend>
        {[true, false].map((only) => (
          <label key={String(only)} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-2 hover:bg-fill-3">
            <input type="radio" name="idp-who" checked={inviteOnly === only} onChange={() => setInviteOnly(only)} className="size-4" data-testid={only ? "idp-invite-only" : "idp-open-signup"} />
            <span className="type-callout text-label-1">{t(only ? "identity.enable.inviteOnly" : "identity.enable.open")}</span>
          </label>
        ))}
      </fieldset>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("identity.field.default_role")} htmlFor="idp-role" hint={t("identity.hint.defaultRole")}>
          <SelectField id="idp-role" value={roleId} onChange={(e) => setRoleId(e.target.value)} data-testid="idp-role">
            {!roleId ? <option value="">—</option> : null}
            {(
              roles.data ??
              (p.default_role
                ? [
                    {
                      ...p.default_role,
                      permissions: [] as string[],
                    },
                  ]
                : [])
            )
              .filter((r) => signupRoleEligible(r) || r.id === p.default_role?.id)
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {roleLabel(t, r)}
                </option>
              ))}
          </SelectField>
        </Field>
        <TextField id="idp-allowed" label={t("identity.field.allowed_domains")} hint={t("identity.hint.allowedDomains")} value={domains} onChange={setDomains} mono={false} />
      </div>
      <FieldRow label={t("identity.field.role_mapping")} hint={t("identity.hint.roleMapping")} htmlFor="idp-mapping">
        <Switch id="idp-mapping" checked={p.role_mapping_enabled} disabled={pending} onCheckedChange={(x) => save({ role_mapping_enabled: x })} data-testid="idp-mapping" />
      </FieldRow>
      {p.role_mapping_enabled ? <Mappings p={p} /> : null}
      <ErrorLine error={error} conflict={conflict} />
    </StepFrame>
  );
}

function Mappings({ p }: { p: Provider }) {
  const { t, locale } = useI18n();
  const { can } = usePermissions();
  const roles = useRoles(can("setup.roles"));
  const q = useProviderMappings(p.id);
  const [claim, setClaim] = useState<"role" | "group">("group");
  const [value, setValue] = useState("");
  const [role, setRole] = useState("");
  const [error, setError] = useState<string | null>(null);
  const add = useIdpMutation((b: { claim: "role" | "group"; value: string; role_id: number }) => idp.addMapping(p.id, b), [idpKeys.mappings(p.id)]);
  const del = useIdpMutation((id: number) => idp.deleteMapping(p.id, id), [idpKeys.mappings(p.id)]);
  return (
    <div className="flex flex-col gap-2" data-testid="idp-mappings">
      {(q.data ?? []).map((m) => (
        <div key={m.id} className="flex flex-wrap items-center gap-2 py-1.5 hairline-b">
          <Badge variant="secondary">{t(m.claim === "group" ? "identity.mapping.group" : "identity.mapping.role")}</Badge>
          <span className="min-w-0 flex-1 truncate font-mono type-footnote">{m.value}</span>
          <span className="type-callout">→ {roleLabel(t, m.role)}</span>
          <IconButton label={t("identity.mapping.delete")} size="sm" onClick={() => del.mutate(m.id)}>
            <Trash2 />
          </IconButton>
        </div>
      ))}
      <form
        className="grid gap-2 sm:grid-cols-[auto_1fr_auto_auto] sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          const clean = cleanPasted(value).value;
          if (!clean || !role) return setError(t("identity.mapping.incomplete"));
          add.mutate(
            { claim, value: clean, role_id: Number(role) },
            {
              onSuccess: () => setValue(""),
              onError: (err) => setError(problemText(err, locale) ?? apiProblem(err, locale).text ?? t("identity.saveFailed")),
            },
          );
        }}
      >
        <SelectField aria-label={t("identity.mapping.claim")} value={claim} onChange={(e) => setClaim(e.target.value === "role" ? "role" : "group")}>
          <option value="group">{t("identity.mapping.group")}</option>
          <option value="role">{t("identity.mapping.role")}</option>
        </SelectField>
        <Input
          aria-label={t("identity.mapping.value")}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={p.kind === "saml" ? "urn:mace:uni.edu.tr:planlama" : "/personel/planlama"}
          className="font-mono text-base sm:text-sm"
          data-testid="idp-map-value"
        />
        <SelectField aria-label={t("identity.mapping.to")} value={role} onChange={(e) => setRole(e.target.value)} data-testid="idp-map-role">
          <option value="">—</option>
          {(roles.data ?? []).map((r) => (
            <option key={r.id} value={r.id}>
              {roleLabel(t, r)}
            </option>
          ))}
        </SelectField>
        <BusyButton type="submit" variant="outline" busy={add.isPending} busyLabel={t("busy.saving")} className="min-h-11 sm:min-h-9" data-testid="idp-map-add">
          <Plus aria-hidden />
          {t("identity.mapping.add")}
        </BusyButton>
      </form>
      {error ? <Alert tone="error">{error}</Alert> : null}
    </div>
  );
}
