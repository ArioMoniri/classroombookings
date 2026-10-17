"use client";
/**
 * CAL-09 admin settings (research doc §3.8; contract: CAL-B API.md `GET/PUT /calendar/admin/export-settings`),
 * rendered inside the two existing cards so W3-HUB's setup sheet embeds them unchanged:
 *
 * - `<ExportScopeSettings>` (in CalendarSyncAdmin): the three scopes on or off and the optional event fields (course
 *   title, department name, co-instructor names off by default, SmartSched link). Under "Gelişmiş" (the owner's
 *   simplicity principle, 2026-10-17): who may export a department (a fixed rule, shown as text), the time range
 *   (past days and the cancelled grace days of `/calendar/admin/settings`) and the status counts with the last
 *   nightly reconcile.
 * - `<PushRuleSettings>` (in CalendarPushAdmin): verified organisation accounts only + the allowed e-mail domains;
 *   under "Gelişmiş" the OAuth client source (own client / the sign-in provider's).
 *
 * Both render nothing while the backend has no export settings (404 on an older backend). Every switch saves at
 * once with just its own key.
 */
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useIntegrationSettings } from "@/lib/api/approval-first";
import { ADMIN_FIELDS, ADMIN_FIELD_KEYS, ADMIN_SCOPE_KEYS, SCOPE_KINDS, useExportAdminSettings, useSaveExportAdminSettings, useSaveFeedHorizon, type ExportAdminSettings, type ExportAdminSettingsIn } from "@/lib/api/calendar-export";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { relativeWhen } from "./model";
import { Advanced, providerName, scopeName } from "./steps";

/** defaults of the research doc §3.8 while a key is absent */
const DEFAULTS: Record<string, boolean> = {
  export_my_classes: true,
  export_department_classes: true,
  export_my_bookings: true,
  export_field_course_title: true,
  export_field_department: true,
  export_field_co_instructors: false,
  export_field_link: true,
};
const on = (s: ExportAdminSettings, key: string): boolean => {
  const v = (s as Record<string, unknown>)[key];
  return typeof v === "boolean" ? v : !!DEFAULTS[key];
};

export const HORIZON = {
  feed_past_days: { min: 0, max: 730 },
  feed_cancelled_grace_days: { min: 0, max: 90 },
} as const;
type HorizonKey = keyof typeof HORIZON;

/** Whole numbers inside the backend's bounds; the first failing key, else null. */
export function horizonError(values: Partial<Record<HorizonKey, string>>): HorizonKey | null {
  for (const k of Object.keys(values) as HorizonKey[]) {
    const raw = values[k];
    if (raw === undefined) continue;
    const n = Number(raw);
    if (raw.trim() === "" || !Number.isInteger(n) || n < HORIZON[k].min || n > HORIZON[k].max) return k;
  }
  return null;
}

/** "universite.edu.tr, @ogr.universite.edu.tr" → ["universite.edu.tr", "ogr.universite.edu.tr"] or the bad one. */
export function parseDomains(text: string): { ok: true; domains: string[] } | { ok: false; bad: string } {
  const parts = text
    .split(/[\s,;]+/)
    .map((d) => d.trim().replace(/^@/, "").toLocaleLowerCase("en-US"))
    .filter(Boolean);
  for (const d of parts) if (!/^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/.test(d)) return { ok: false, bad: d };
  return { ok: true, domains: [...new Set(parts)] };
}

function Row({ id, label, hint, checked, onChange, disabled, testId }: { id: string; label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; testId: string }) {
  return (
    <div className="flex min-h-11 items-center justify-between gap-4 py-2">
      <div className="min-w-0">
        <Label htmlFor={id} className="type-callout font-medium text-label-1">
          {label}
        </Label>
        {hint ? <p className="type-footnote text-label-2">{hint}</p> : null}
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} disabled={disabled} data-testid={testId} />
    </div>
  );
}

function Group({ title, hint, children, testId }: { title: string; hint?: string; children: ReactNode; testId: string }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="grid gap-1 rounded-xl bg-fill-3 px-3 py-3 sm:px-4" data-testid={testId}>
      <h3 id={id} className="type-headline text-label-1">
        {title}
      </h3>
      {hint ? <p className="type-footnote text-label-2">{hint}</p> : null}
      {children}
    </section>
  );
}

function useSaver() {
  const { t, locale } = useI18n();
  const save = useSaveExportAdminSettings();
  const [error, setError] = useState<string | null>(null);
  const put = (body: ExportAdminSettingsIn, after?: () => void) => {
    setError(null);
    save.mutate(body, {
      onSuccess: () => {
        toast.success(t("calendarExport.admin.saved"));
        after?.();
      },
      // the backend's own sentence (e.g. a personal mailbox domain is refused with a 422)
      onError: (e) => setError(t("calendarExport.admin.failed", { message: errorText(wave1Error(e), locale) })),
    });
  };
  return { put, pending: save.isPending, error };
}

/* ------------------------------------------------------------------------- calendar sync card */

export function ExportScopeSettings() {
  const q = useExportAdminSettings();
  if (!q.data) return null;
  return <ScopeBlocks s={q.data} />;
}

function ScopeBlocks({ s }: { s: ExportAdminSettings }) {
  const { t } = useI18n();
  const { put, pending, error } = useSaver();
  const base = useId();
  return (
    <div className="grid gap-3 pt-3" data-testid="cal-admin-export">
      <div className="grid gap-0.5">
        <h3 className="type-title-3 text-label-1">{t("calendarExport.admin.title")}</h3>
        <p className="type-footnote text-label-2">{t("calendarExport.admin.lead")}</p>
      </div>
      <Group title={t("calendarExport.admin.scopes")} testId="cal-admin-scopes">
        {SCOPE_KINDS.map((k) => (
          <Row
            key={k}
            id={`${base}-scope-${k}`}
            label={t(`calendarExport.admin.scope.${k}`)}
            hint={t(`calendarExport.admin.scope.${k}Hint`)}
            checked={on(s, ADMIN_SCOPE_KEYS[k])}
            disabled={pending}
            onChange={(v) => put({ [ADMIN_SCOPE_KEYS[k]]: v })}
            testId={`cal-admin-scope-${k}`}
          />
        ))}
      </Group>
      <Group title={t("calendarExport.admin.fields")} hint={t("calendarExport.admin.fieldsHint")} testId="cal-admin-fields">
        {ADMIN_FIELDS.map((f) => (
          <Row
            key={f}
            id={`${base}-field-${f}`}
            label={t(`calendarExport.admin.field.${f}`)}
            hint={f === "co_instructors" ? t("calendarExport.admin.field.co_instructorsHint") : undefined}
            checked={on(s, ADMIN_FIELD_KEYS[f])}
            disabled={pending}
            onChange={(v) => put({ [ADMIN_FIELD_KEYS[f]]: v })}
            testId={`cal-admin-field-${f}`}
          />
        ))}
      </Group>
      {error ? (
        <p role="alert" className="type-footnote text-status-infeasible-fg">
          {error}
        </p>
      ) : null}
      {/* the simplicity principle: who may export a department, the time range and the counts are for the few */}
      <Advanced testId="cal-admin-advanced">
        <p className="type-footnote text-label-2">{t("calendarExport.admin.advancedHint")}</p>
        <Group title={t("calendarExport.admin.who")} testId="cal-admin-who">
          <p className="type-footnote text-label-2">{t("calendarExport.admin.whoLead")}</p>
          <ul className="grid list-disc gap-0.5 pl-5 type-callout text-label-1" data-testid="cal-admin-rules">
            <li>{t("calendarExport.admin.rule.own")}</li>
            <li>{t("calendarExport.admin.rule.taught")}</li>
            <li>
              {t("calendarExport.admin.rule.permission")}
              <span className="block type-footnote text-label-2">{t("calendarExport.admin.rulePermissionHint")}</span>
            </li>
          </ul>
        </Group>
        <HorizonBlock />
        {s.status ? <StatusBlock s={s} /> : null}
      </Advanced>
    </div>
  );
}

/** Past days and the cancelled grace days live in `/calendar/admin/settings` (the KVKK card's endpoint). */
function HorizonBlock() {
  const q = useIntegrationSettings();
  if (!q.data) return null;
  return <HorizonForm key={`${q.data.feed_past_days}-${q.data.feed_cancelled_grace_days}`} past={q.data.feed_past_days ?? 30} grace={q.data.feed_cancelled_grace_days ?? 7} />;
}

function HorizonForm({ past, grace }: { past: number; grace: number }) {
  const { t, locale } = useI18n();
  const save = useSaveFeedHorizon();
  const base = useId();
  const [v, setV] = useState<Record<HorizonKey, string>>({ feed_past_days: String(past), feed_cancelled_grace_days: String(grace) });
  const [bad, setBad] = useState<HorizonKey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const labels: Record<HorizonKey, string> = { feed_past_days: t("calendarExport.admin.past"), feed_cancelled_grace_days: t("calendarExport.admin.grace") };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const k = horizonError(v);
    setBad(k);
    setError(null);
    if (k) return;
    save.mutate(
      { feed_past_days: Number(v.feed_past_days), feed_cancelled_grace_days: Number(v.feed_cancelled_grace_days) },
      { onSuccess: () => toast.success(t("calendarExport.admin.saved")), onError: (er) => setError(t("calendarExport.admin.failed", { message: errorText(wave1Error(er), locale) })) },
    );
  };
  return (
    <Group title={t("calendarExport.admin.horizon")} hint={t("calendarExport.admin.horizonHint")} testId="cal-admin-horizon">
      <form className="grid gap-3 pt-1" onSubmit={submit} noValidate>
        <div className="grid gap-3 sm:grid-cols-2">
          {(Object.keys(HORIZON) as HorizonKey[]).map((k) => (
            <div key={k} className="grid content-start gap-1.5">
              <Label htmlFor={`${base}-${k}`}>{labels[k]}</Label>
              <Input
                id={`${base}-${k}`}
                type="number"
                inputMode="numeric"
                min={HORIZON[k].min}
                max={HORIZON[k].max}
                value={v[k]}
                onChange={(e) => setV((p) => ({ ...p, [k]: e.target.value }))}
                aria-invalid={bad === k || undefined}
                className="tnum"
                data-testid={`cal-admin-${k}`}
              />
            </div>
          ))}
        </div>
        {bad ? (
          <p role="alert" className="type-footnote text-status-infeasible-fg" data-testid="cal-admin-horizon-error">
            {t("calendarExport.admin.range", { label: labels[bad], min: HORIZON[bad].min, max: HORIZON[bad].max })}
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="type-footnote text-status-infeasible-fg">
            {error}
          </p>
        ) : null}
        <div>
          <Button type="submit" variant="outline" shape="rect" disabled={save.isPending} aria-busy={save.isPending || undefined} data-testid="cal-admin-horizon-save">
            <BusyLabel busy={save.isPending} label={t("busy.saving")}>
              {t("calendarExport.admin.saveHorizon")}
            </BusyLabel>
          </Button>
        </div>
      </form>
    </Group>
  );
}

function StatusBlock({ s }: { s: ExportAdminSettings }) {
  const { t, locale } = useI18n();
  const st = s.status!;
  const links = Object.entries(st.links).reduce((n, [, v]) => n + v, 0);
  const night = st.nightly_reconcile;
  const when = relativeWhen(night?.at, locale, { today: t("calendarExport.manage.today"), yesterday: t("calendarExport.manage.yesterday") });
  const byScope = (m: Record<string, number>) =>
    Object.entries(m)
      .filter(([, n]) => n > 0)
      .map(([k, n]) => t("calendarExport.admin.byScope", { scope: k === "legacy" ? t("calendarExport.admin.legacyLinks") : scopeName(k, t), n }))
      .join(" · ");
  return (
    <Group title={t("calendarExport.admin.status")} testId="cal-admin-status">
      <dl className="grid gap-2 pt-1 sm:grid-cols-2">
        <div>
          <dt className="type-footnote text-label-2">{t("calendarExport.admin.links")}</dt>
          <dd className="type-headline text-label-1 tnum" data-testid="cal-admin-links">
            {links}
          </dd>
          {byScope(st.links) ? <dd className="type-footnote text-label-3">{byScope(st.links)}</dd> : null}
        </div>
        {Object.entries(st.connections).map(([provider, n]) => (
          <div key={provider}>
            <dt className="type-footnote text-label-2">{t("calendarExport.admin.connections", { provider: providerName(provider, t) })}</dt>
            <dd className="type-headline text-label-1 tnum" data-testid={`cal-admin-connections-${provider}`}>
              {n}
            </dd>
          </div>
        ))}
        {st.needs_attention ? (
          <div>
            <dt className="type-footnote text-label-2">{t("calendarExport.admin.attention")}</dt>
            <dd className="type-headline text-status-warning-fg tnum" data-testid="cal-admin-attention">
              {st.needs_attention}
            </dd>
          </div>
        ) : null}
        {st.least_privilege_flagged ? (
          <div>
            <dt className="type-footnote text-label-2">{t("calendarExport.admin.broadGrant")}</dt>
            <dd className="type-headline text-label-1 tnum">{st.least_privilege_flagged}</dd>
          </div>
        ) : null}
        <div>
          <dt className="type-footnote text-label-2">{t("calendarExport.admin.failedJobs")}</dt>
          <dd className={st.failed_jobs ? "type-headline text-status-warning-fg tnum" : "type-headline text-label-1 tnum"} data-testid="cal-admin-failed">
            {st.failed_jobs}
          </dd>
        </div>
        <div>
          <dt className="type-footnote text-label-2">{t("calendarExport.admin.reconcile")}</dt>
          <dd className="type-callout text-label-1" data-testid="cal-admin-reconcile">
            {when ? t("calendarExport.admin.reconcileAt", { when: when.label, n: night?.queued ?? 0 }) : t("calendarExport.admin.reconcileNever")}
          </dd>
        </div>
      </dl>
    </Group>
  );
}

/* ------------------------------------------------------------------------- push card */

export function PushRuleSettings() {
  const q = useExportAdminSettings();
  if (!q.data) return null;
  return <PushBlocks s={q.data} />;
}

function Radio<V extends string>({ name, value, current, label, hint, onPick, disabled, testId }: { name: string; value: V; current: V | null | undefined; label: string; hint?: string; onPick: (v: V) => void; disabled: boolean; testId: string }) {
  const id = useId();
  return (
    <label htmlFor={id} className="flex min-h-11 cursor-pointer items-start gap-3 py-1.5 type-callout text-label-1">
      <input id={id} type="radio" name={name} value={value} checked={current === value} onChange={() => onPick(value)} disabled={disabled} className="mt-0.5 size-5 shrink-0 accent-(--accent)" data-testid={testId} />
      <span className="grid gap-0.5">
        <span>{label}</span>
        {hint ? <span className="type-footnote text-label-2">{hint}</span> : null}
      </span>
    </label>
  );
}

function PushBlocks({ s }: { s: ExportAdminSettings }) {
  const { t } = useI18n();
  const { put, pending, error } = useSaver();
  const base = useId();
  const [domains, setDomains] = useState((s.push_allowed_domains ?? []).join(", "));
  const [bad, setBad] = useState<string | null>(null);
  const identityAny = Object.values(s.identity_clients).some(Boolean);
  const saveDomains = (e: FormEvent) => {
    e.preventDefault();
    const r = parseDomains(domains);
    if (!r.ok) return setBad(r.bad);
    setBad(null);
    put({ push_allowed_domains: r.domains }, () => setDomains(r.domains.join(", ")));
  };
  return (
    <Group title={t("calendarExport.admin.push")} testId="cal-admin-push">
      <Row id={`${base}-verified`} label={t("calendarExport.admin.verifiedOnly")} hint={t("calendarExport.admin.verifiedOnlyHint")} checked={s.push_verified_only !== false} disabled={pending} onChange={(v) => put({ push_verified_only: v })} testId="cal-admin-verified" />
      <form className="grid gap-1.5 pb-2" onSubmit={saveDomains} noValidate>
        <Label htmlFor={`${base}-domains`}>{t("calendarExport.admin.domains")}</Label>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            id={`${base}-domains`}
            value={domains}
            onChange={(e) => setDomains(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            inputMode="url"
            className="min-w-0 flex-1 font-mono sm:max-w-md"
            aria-describedby={`${base}-domains-hint`}
            aria-invalid={bad ? true : undefined}
            data-testid="cal-admin-domains"
          />
          <Button type="submit" variant="outline" shape="rect" disabled={pending} aria-busy={pending || undefined} data-testid="cal-admin-domains-save">
            <BusyLabel busy={pending} label={t("busy.saving")}>
              {t("calendarExport.admin.saveDomains")}
            </BusyLabel>
          </Button>
        </div>
        <p id={`${base}-domains-hint`} className="type-footnote text-label-2">
          {t("calendarExport.admin.domainsHint")}
        </p>
        {bad ? (
          <p role="alert" className="type-footnote text-status-infeasible-fg" data-testid="cal-admin-domains-error">
            {t("calendarExport.admin.domainInvalid", { domain: bad })}
          </p>
        ) : null}
      </form>
      {error ? (
        <p role="alert" className="type-footnote text-status-infeasible-fg" data-testid="cal-admin-push-error">
          {error}
        </p>
      ) : null}
      <Advanced testId="cal-admin-push-advanced" className="bg-fill-2">
        <fieldset className="grid" disabled={pending}>
          <legend className="type-callout font-semibold text-label-1">{t("calendarExport.admin.source")}</legend>
          <Radio name={`${base}-source`} value="own" current={s.calendar_client_source ?? "own"} label={t("calendarExport.admin.sourceOwn")} onPick={(v) => put({ calendar_client_source: v })} disabled={pending} testId="cal-admin-source-own" />
          <Radio
            name={`${base}-source`}
            value="identity"
            current={s.calendar_client_source ?? "own"}
            label={t("calendarExport.admin.sourceIdentity")}
            hint={identityAny ? undefined : t("calendarExport.admin.sourceIdentityMissing")}
            onPick={(v) => put({ calendar_client_source: v })}
            disabled={pending || (!identityAny && s.calendar_client_source !== "identity")}
            testId="cal-admin-source-identity"
          />
        </fieldset>
      </Advanced>
    </Group>
  );
}
