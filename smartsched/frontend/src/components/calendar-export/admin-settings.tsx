"use client";
/**
 * CAL-09 admin settings (research doc §3.8), rendered inside the two existing cards so W3-HUB's setup sheet embeds
 * them unchanged:
 *
 * - `<ExportScopeSettings>` (in CalendarSyncAdmin, Ayarlar › Takvim): the scopes on or off, who may export the
 *   department scope (own department, taught departments, the `calendar.department_feed` permission), the field
 *   allow-list (course title, department name, co-instructors off, SmartSched link), the horizon (past days, days
 *   ahead ≤ 200, cancelled grace days) and the status counts with the last nightly reconcile.
 * - `<PushRuleSettings>` (in CalendarPushAdmin): `push_verified_only` + the allowed e-mail domains, the OAuth client
 *   source (identity / own) and the Google scope mode (`app_created` default, `events` legacy).
 *
 * Each block renders only the settings the backend answers with (an older backend shows none of them), and every
 * switch saves at once through `PUT /calendar/admin/settings` with just its own key.
 */
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  ADMIN_FIELDS,
  DEPARTMENT_RULES,
  SCOPE_KINDS,
  useExportAdminSettings,
  useExportAdminStatus,
  useSaveExportAdminSettings,
  type ExportAdminSettings,
  type ExportAdminSettingsIn,
} from "@/lib/api/calendar-export";
import { errorText, wave1Error } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import { relativeWhen } from "./model";
import { Advanced, providerName, scopeName } from "./steps";

/** defaults of the research doc §3.8, used while the backend sends a partial map */
const SCOPE_DEFAULTS: Record<string, boolean> = { my_classes: true, department_classes: true, my_bookings: true };
const RULE_DEFAULTS: Record<string, boolean> = { own: true, taught: true, permission: true };
const FIELD_DEFAULTS: Record<string, boolean> = { title: true, department: true, co_instructors: false, link: true };

export const HORIZON = {
  feed_past_days: { min: 0, max: 730 },
  feed_future_days: { min: 1, max: 200 },
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
      onError: (e) => setError(t("calendarExport.admin.failed", { message: errorText(wave1Error(e), locale) })),
    });
  };
  return { put, pending: save.isPending, error };
}

/* ------------------------------------------------------------------------- Ayarlar › Takvim (sync card) */

export function ExportScopeSettings() {
  const q = useExportAdminSettings();
  const s = q.data;
  if (!s || (s.export_scopes == null && s.export_fields == null && s.department_rule == null && s.feed_future_days == null)) return null;
  return <ScopeBlocks s={s} />;
}

function ScopeBlocks({ s }: { s: ExportAdminSettings }) {
  const { t } = useI18n();
  const { put, pending, error } = useSaver();
  const base = useId();
  const scopes = { ...SCOPE_DEFAULTS, ...(s.export_scopes ?? {}) };
  const rules = { ...RULE_DEFAULTS, ...(s.department_rule ?? {}) };
  const fields = { ...FIELD_DEFAULTS, ...(s.export_fields ?? {}) };
  return (
    <div className="grid gap-3 pt-3" data-testid="cal-admin-export">
      <div className="grid gap-0.5">
        <h3 className="type-title-3 text-label-1">{t("calendarExport.admin.title")}</h3>
        <p className="type-footnote text-label-2">{t("calendarExport.admin.lead")}</p>
      </div>
      {s.export_scopes != null ? (
        <Group title={t("calendarExport.admin.scopes")} testId="cal-admin-scopes">
          {SCOPE_KINDS.map((k) => (
            <Row
              key={k}
              id={`${base}-scope-${k}`}
              label={t(`calendarExport.admin.scope.${k}`)}
              hint={t(`calendarExport.admin.scope.${k}Hint`)}
              checked={!!scopes[k]}
              disabled={pending}
              onChange={(v) => put({ export_scopes: { ...scopes, [k]: v } })}
              testId={`cal-admin-scope-${k}`}
            />
          ))}
        </Group>
      ) : null}
      {s.export_fields != null ? (
        <Group title={t("calendarExport.admin.fields")} hint={t("calendarExport.admin.fieldsHint")} testId="cal-admin-fields">
          {ADMIN_FIELDS.map((f) => (
            <Row
              key={f}
              id={`${base}-field-${f}`}
              label={t(`calendarExport.admin.field.${f}`)}
              hint={f === "co_instructors" ? t("calendarExport.admin.field.co_instructorsHint") : undefined}
              checked={!!fields[f]}
              disabled={pending}
              onChange={(v) => put({ export_fields: { ...fields, [f]: v } })}
              testId={`cal-admin-field-${f}`}
            />
          ))}
        </Group>
      ) : null}
      {error ? (
        <p role="alert" className="type-footnote text-status-infeasible-fg">
          {error}
        </p>
      ) : null}
      {/* the simplicity principle: who may export a department, the time range and the counts are for the few */}
      <Advanced testId="cal-admin-advanced">
        <p className="type-footnote text-label-2">{t("calendarExport.admin.advancedHint")}</p>
        {s.department_rule != null ? (
          <Group title={t("calendarExport.admin.who")} testId="cal-admin-who">
            <fieldset className="grid gap-0.5" disabled={pending || !scopes.department_classes} data-testid="cal-admin-rules">
              <legend className="sr-only">{t("calendarExport.admin.who")}</legend>
              {DEPARTMENT_RULES.map((r) => (
                <Row
                  key={r}
                  id={`${base}-rule-${r}`}
                  label={t(`calendarExport.admin.rule.${r}`)}
                  hint={r === "permission" ? t("calendarExport.admin.rulePermissionHint") : undefined}
                  checked={!!rules[r]}
                  disabled={pending || !scopes.department_classes}
                  onChange={(v) => put({ department_rule: { ...rules, [r]: v } })}
                  testId={`cal-admin-rule-${r}`}
                />
              ))}
            </fieldset>
          </Group>
        ) : null}
        {s.feed_future_days != null ? <HorizonForm key={`${s.feed_past_days}-${s.feed_future_days}-${s.feed_cancelled_grace_days}`} s={s} /> : null}
        <StatusBlock />
      </Advanced>
    </div>
  );
}

function HorizonForm({ s }: { s: ExportAdminSettings }) {
  const { t } = useI18n();
  const { put, pending, error } = useSaver();
  const base = useId();
  const [v, setV] = useState<Record<HorizonKey, string>>({
    feed_past_days: String(s.feed_past_days ?? 30),
    feed_future_days: String(s.feed_future_days ?? 200),
    feed_cancelled_grace_days: String(s.feed_cancelled_grace_days ?? 7),
  });
  const [bad, setBad] = useState<HorizonKey | null>(null);
  const labels: Record<HorizonKey, string> = { feed_past_days: t("calendarExport.admin.past"), feed_future_days: t("calendarExport.admin.future"), feed_cancelled_grace_days: t("calendarExport.admin.grace") };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const k = horizonError(v);
    setBad(k);
    if (k) return;
    put({ feed_past_days: Number(v.feed_past_days), feed_future_days: Number(v.feed_future_days), feed_cancelled_grace_days: Number(v.feed_cancelled_grace_days) });
  };
  return (
    <Group title={t("calendarExport.admin.horizon")} testId="cal-admin-horizon">
      <form className="grid gap-3 pt-1" onSubmit={submit} noValidate>
        <div className="grid gap-3 sm:grid-cols-3">
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
          <Button type="submit" variant="outline" shape="rect" disabled={pending} aria-busy={pending || undefined} data-testid="cal-admin-horizon-save">
            <BusyLabel busy={pending} label={t("busy.saving")}>
              {t("calendarExport.admin.saveHorizon")}
            </BusyLabel>
          </Button>
        </div>
      </form>
    </Group>
  );
}

function StatusBlock() {
  const { t, locale } = useI18n();
  const q = useExportAdminStatus();
  const st = q.data;
  if (!st) return null;
  const when = relativeWhen(st.last_reconcile_at, locale, { today: t("calendarExport.manage.today"), yesterday: t("calendarExport.manage.yesterday") });
  const scopes = (m: Record<string, number>) =>
    Object.entries(m)
      .filter(([, n]) => n > 0)
      .map(([k, n]) => t("calendarExport.admin.byScope", { scope: scopeName(k, t), n }))
      .join(" · ");
  return (
    <Group title={t("calendarExport.admin.status")} testId="cal-admin-status">
      <dl className="grid gap-2 pt-1 sm:grid-cols-2">
        <div>
          <dt className="type-footnote text-label-2">{t("calendarExport.admin.links")}</dt>
          <dd className="type-headline text-label-1 tnum" data-testid="cal-admin-links">
            {st.active_links}
          </dd>
          {scopes(st.links_by_scope) ? <dd className="type-footnote text-label-3">{scopes(st.links_by_scope)}</dd> : null}
        </div>
        {st.connections.map((c) => (
          <div key={c.provider}>
            <dt className="type-footnote text-label-2">{t("calendarExport.admin.connections", { provider: providerName(c.provider, t) })}</dt>
            <dd className="type-headline text-label-1 tnum" data-testid={`cal-admin-connections-${c.provider}`}>
              {c.count}
            </dd>
            {scopes(c.by_scope) ? <dd className="type-footnote text-label-3">{scopes(c.by_scope)}</dd> : null}
          </div>
        ))}
        <div>
          <dt className="type-footnote text-label-2">{t("calendarExport.admin.failedJobs")}</dt>
          <dd className={st.failed_jobs ? "type-headline text-status-warning-fg tnum" : "type-headline text-label-1 tnum"} data-testid="cal-admin-failed">
            {st.failed_jobs}
          </dd>
        </div>
        <div>
          <dt className="type-footnote text-label-2">{t("calendarExport.admin.reconcile")}</dt>
          <dd className="type-callout text-label-1" data-testid="cal-admin-reconcile">
            {when ? when.label : t("calendarExport.admin.reconcileNever")}
          </dd>
        </div>
      </dl>
    </Group>
  );
}

/* ------------------------------------------------------------------------- push card */

export function PushRuleSettings() {
  const q = useExportAdminSettings();
  const s = q.data;
  if (!s || (s.push_verified_only == null && s.calendar_client_source == null && s.google_scope_mode == null)) return null;
  return <PushBlocks s={s} />;
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
  const saveDomains = (e: FormEvent) => {
    e.preventDefault();
    const r = parseDomains(domains);
    if (!r.ok) return setBad(r.bad);
    setBad(null);
    put({ push_allowed_domains: r.domains }, () => setDomains(r.domains.join(", ")));
  };
  return (
    <Group title={t("calendarExport.admin.push")} testId="cal-admin-push">
      {s.push_verified_only != null ? (
        <>
          <Row id={`${base}-verified`} label={t("calendarExport.admin.verifiedOnly")} hint={t("calendarExport.admin.verifiedOnlyHint")} checked={!!s.push_verified_only} disabled={pending} onChange={(v) => put({ push_verified_only: v })} testId="cal-admin-verified" />
          {s.push_allowed_domains !== undefined ? (
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
          ) : null}
        </>
      ) : null}
      {s.calendar_client_source != null || s.google_scope_mode != null ? (
        <Advanced testId="cal-admin-push-advanced">
      {s.calendar_client_source != null ? (
        <fieldset className="grid pt-1" disabled={pending}>
          <legend className="type-callout font-semibold text-label-1">{t("calendarExport.admin.source")}</legend>
          <Radio name={`${base}-source`} value="identity" current={s.calendar_client_source} label={t("calendarExport.admin.sourceIdentity")} onPick={(v) => put({ calendar_client_source: v })} disabled={pending} testId="cal-admin-source-identity" />
          <Radio name={`${base}-source`} value="own" current={s.calendar_client_source} label={t("calendarExport.admin.sourceOwn")} onPick={(v) => put({ calendar_client_source: v })} disabled={pending} testId="cal-admin-source-own" />
        </fieldset>
      ) : null}
      {s.google_scope_mode != null ? (
        <fieldset className="grid pt-1" disabled={pending}>
          <legend className="type-callout font-semibold text-label-1">{t("calendarExport.admin.googleScope")}</legend>
          <Radio name={`${base}-gscope`} value="app_created" current={s.google_scope_mode} label={t("calendarExport.admin.googleAppCreated")} onPick={(v) => put({ google_scope_mode: v })} disabled={pending} testId="cal-admin-gscope-app_created" />
          <Radio name={`${base}-gscope`} value="events" current={s.google_scope_mode} label={t("calendarExport.admin.googleEvents")} hint={t("calendarExport.admin.googleEventsHint")} onPick={(v) => put({ google_scope_mode: v })} disabled={pending} testId="cal-admin-gscope-events" />
        </fieldset>
      ) : null}
        </Advanced>
      ) : null}
      {error ? (
        <p role="alert" className="type-footnote text-status-infeasible-fg">
          {error}
        </p>
      ) : null}
    </Group>
  );
}
