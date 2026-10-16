"use client";
/**
 * One booking policy (P8): name, on/off, effect (refuse or turn into a request), scope (every room, a room, a room
 * group, a room type tag), the roles it binds (none = everyone), the term, every limit, quiet hours (weekday windows)
 * and blackout dates. Saved with `POST/PUT /booking-policies`; the backend's 422 lands next to the field it names.
 * Nothing is pre-filled: a new rule starts empty and the administrator writes every number.
 */
import { Plus, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { Field } from "@/components/admin/kit";
import { Button, IconButton } from "@/components/ui/button";
import { BusyLabel, busyProps } from "@/components/ui/busy-label";
import { Chip } from "@/components/ui/chip";
import { DateField } from "@/components/ui/date-field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Alert } from "@/components/ui/alert";
import { LIMITS, parseLimit, SCOPE_TYPES, toPayload, validatePolicy, type LimitKey, type PolicyFormError, type PolicyIn, type ScopeType } from "@/lib/api/booking-policies";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export interface PolicyFormContext {
  rooms: { id: number; name: string }[];
  groups: { id: number; name: string }[];
  terms: { id: number; name: string }[];
  /** role codes with a display name; null = the role list is not readable here (free text instead) */
  roles: { code: string; name: string }[] | null;
}

/** the backend's 422 `code` → the field it belongs to */
const FIELD_OF: Record<string, string> = {
  name: "name",
  scope_type: "scope",
  scope_id: "scope",
  tag: "scope",
  term_id: "term",
  effect: "effect",
  role_codes: "roles",
  quiet_hours: "quiet",
  time: "quiet",
  blackouts: "blackouts",
  empty: "limits",
  min_notice_workdays: "min_notice_workdays",
  max_advance_days: "max_advance_days",
  max_duration_minutes: "max_duration_minutes",
  max_active_bookings: "max_active_bookings",
  buffer_minutes: "buffer_minutes",
};

const LOCAL_FIELD: Record<PolicyFormError, string> = { name: "name", scope_id: "scope", tag: "scope", empty: "limits", quiet: "quiet", blackout: "blackouts" };

const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7] as const;

export function PolicyForm({
  initial,
  ctx,
  busy,
  serverError,
  onSave,
  onCancel,
}: {
  initial: PolicyIn;
  ctx: PolicyFormContext;
  busy: boolean;
  /** the backend's refusal: `code` (FIELD_OF) and its text */
  serverError: { code: string | null; text: string } | null;
  onSave: (body: PolicyIn) => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const [p, setP] = useState<PolicyIn>(initial);
  const [tried, setTried] = useState(false);
  const [roleText, setRoleText] = useState(initial.role_codes.join(", "));
  const set = <K extends keyof PolicyIn>(k: K, v: PolicyIn[K]) => setP((x) => ({ ...x, [k]: v }));
  const local = tried ? validatePolicy(p) : [];
  const errorFor = (field: string): string | null => {
    const hit = local.find((e) => LOCAL_FIELD[e] === field);
    if (hit) return t(`policies.form.err.${hit}` as MessageKey);
    if (serverError && serverError.code && FIELD_OF[serverError.code] === field) return serverError.text;
    return null;
  };
  const generalError = serverError && !(serverError.code && FIELD_OF[serverError.code]) ? serverError.text : null;
  const ids = { name: useId(), enabled: useId(), scope: useId(), target: useId(), term: useId(), note: useId(), roles: useId() };

  const submit = () => {
    setTried(true);
    const body = toPayload(ctx.roles ? p : { ...p, role_codes: roleText.split(/[,\s]+/) });
    if (validatePolicy(body).length) return;
    onSave(body);
  };

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      noValidate
      data-testid="policy-form"
    >
      <Field label={t("policies.form.name")} htmlFor={ids.name} error={errorFor("name")} hint={t("policies.form.nameHint")}>
        <Input id={ids.name} value={p.name} maxLength={120} onChange={(e) => set("name", e.target.value)} aria-invalid={!!errorFor("name") || undefined} data-testid="policy-name" />
      </Field>

      <div className="flex min-h-11 items-center justify-between gap-4">
        <Label htmlFor={ids.enabled} className="type-callout font-medium text-label-1">
          {t("policies.form.enabled")}
        </Label>
        <Switch id={ids.enabled} checked={p.enabled} onCheckedChange={(v) => set("enabled", v)} data-testid="policy-enabled" />
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="type-footnote font-medium text-label-2" id={`${ids.scope}-effect`}>
          {t("policies.form.effect")}
        </span>
        <SegmentedControl
          aria-labelledby={`${ids.scope}-effect`}
          value={p.effect}
          onValueChange={(v) => set("effect", v as PolicyIn["effect"])}
          options={[
            { value: "refuse", label: t("policies.effect.refuse"), testId: "policy-effect-refuse" },
            { value: "request", label: t("policies.effect.request"), testId: "policy-effect-request" },
          ]}
        />
        <p className="type-footnote text-label-3">{p.effect === "refuse" ? t("policies.effect.refuseHint") : t("policies.effect.requestHint")}</p>
      </div>

      <fieldset className="min-w-0 flex flex-col gap-2">
        <legend className="mb-1 type-footnote font-medium text-label-2">{t("policies.form.scope")}</legend>
        <SegmentedControl
          aria-label={t("policies.form.scope")}
          value={p.scope_type}
          onValueChange={(v) => setP((x) => ({ ...x, scope_type: v as ScopeType, scope_id: null }))}
          options={SCOPE_TYPES.map((s) => ({ value: s, label: t(`policies.scope.${s}` as MessageKey), testId: `policy-scope-${s}` }))}
        />
        {p.scope_type === "room" || p.scope_type === "room_group" ? (
          <NativeSelect id={ids.target} aria-label={p.scope_type === "room" ? t("policies.form.pickRoom") : t("policies.form.pickGroup")} value={p.scope_id ?? ""} onChange={(e) => set("scope_id", e.target.value ? Number(e.target.value) : null)} data-testid="policy-scope-target">
            <option value="">{p.scope_type === "room" ? t("policies.form.pickRoom") : t("policies.form.pickGroup")}</option>
            {(p.scope_type === "room" ? ctx.rooms : ctx.groups).map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
          </NativeSelect>
        ) : null}
        {p.scope_type === "tag" ? <Input aria-label={t("policies.form.tag")} placeholder={t("policies.form.tagPlaceholder")} value={p.tag ?? ""} maxLength={32} onChange={(e) => set("tag", e.target.value)} data-testid="policy-scope-tag" /> : null}
        {errorFor("scope") ? <p className="type-footnote text-status-infeasible-fg" role="alert">{errorFor("scope")}</p> : null}
      </fieldset>

      <fieldset className="min-w-0 flex flex-col gap-2">
        <legend className="mb-1 type-footnote font-medium text-label-2">{t("policies.form.roles")}</legend>
        {ctx.roles ? (
          ctx.roles.length ? (
            <div className="flex flex-wrap gap-2">
              {ctx.roles.map((r) => {
                const on = p.role_codes.includes(r.code);
                return (
                  <Chip key={r.code} selected={on} onSelectedChange={(v) => set("role_codes", v ? [...p.role_codes, r.code] : p.role_codes.filter((x) => x !== r.code))} data-testid={`policy-role-${r.code}`}>
                    {r.name}
                  </Chip>
                );
              })}
            </div>
          ) : (
            <p className="type-footnote text-label-3">{t("policies.form.noRoles")}</p>
          )
        ) : (
          <Input id={ids.roles} aria-label={t("policies.form.roleCodes")} placeholder="TEACHER, VIEWER" value={roleText} onChange={(e) => setRoleText(e.target.value)} />
        )}
        <p className="type-footnote text-label-3">{t("policies.form.rolesHint")}</p>
        {errorFor("roles") ? <p className="type-footnote text-status-infeasible-fg" role="alert">{errorFor("roles")}</p> : null}
      </fieldset>

      <Field label={t("policies.form.term")} htmlFor={ids.term} error={errorFor("term")}>
        <NativeSelect id={ids.term} value={p.term_id ?? ""} onChange={(e) => set("term_id", e.target.value ? Number(e.target.value) : null)}>
          <option value="">{t("policies.form.allTerms")}</option>
          {ctx.terms.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
            </option>
          ))}
        </NativeSelect>
      </Field>

      <fieldset className="min-w-0 flex flex-col gap-3">
        <legend className="mb-1 type-headline text-label-1">{t("policies.form.limits")}</legend>
        <p className="-mt-2 type-footnote text-label-3">{t("policies.form.limitsHint")}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          {LIMITS.map((l) => (
            <LimitField key={l.key} k={l.key} min={l.min} max={l.max} value={p[l.key]} error={errorFor(l.key)} onChange={(v) => set(l.key, v)} />
          ))}
        </div>
        {errorFor("limits") ? <p className="type-footnote text-status-infeasible-fg" role="alert">{errorFor("limits")}</p> : null}
      </fieldset>

      <QuietHours value={p.quiet_hours} onChange={(v) => set("quiet_hours", v)} error={errorFor("quiet")} />
      <Blackouts value={p.blackouts} onChange={(v) => set("blackouts", v)} error={errorFor("blackouts")} />

      <Field label={t("policies.form.note")} htmlFor={ids.note} hint={t("policies.form.noteHint")}>
        <Textarea id={ids.note} rows={2} value={p.note ?? ""} onChange={(e) => set("note", e.target.value)} />
      </Field>

      {generalError ? (
        <Alert tone="error" data-testid="policy-error">
          {generalError}
        </Alert>
      ) : null}

      <div className="sticky bottom-0 -mx-5 flex flex-col-reverse gap-2 bg-(--mat-thick-solid) px-5 pt-3 pb-[max(1rem,env(safe-area-inset-bottom))] edge-hairline-t sm:flex-row sm:justify-end">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          {t("crbs.common.cancel")}
        </Button>
        <Button type="submit" {...busyProps(busy)} data-testid="policy-save">
          <BusyLabel busy={busy} label={t("busy.saving")}>
            {t("crbs.common.save")}
          </BusyLabel>
        </Button>
      </div>
    </form>
  );
}

function LimitField({ k, min, max, value, error, onChange }: { k: LimitKey; min: number; max: number; value: number | null; error: string | null; onChange: (v: number | null) => void }) {
  const { t } = useI18n();
  const id = useId();
  const [text, setText] = useState(value == null ? "" : String(value));
  return (
    <Field label={t(`policies.limit.${k}` as MessageKey)} htmlFor={id} error={error} hint={t(`policies.limit.${k}Hint` as MessageKey, { min, max })}>
      <Input
        id={id}
        inputMode="numeric"
        type="number"
        min={min}
        max={max}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          onChange(parseLimit(e.target.value));
        }}
        aria-invalid={!!error || undefined}
        data-testid={`policy-${k}`}
      />
    </Field>
  );
}

function QuietHours({ value, onChange, error }: { value: PolicyIn["quiet_hours"]; onChange: (v: PolicyIn["quiet_hours"]) => void; error: string | null }) {
  const { t } = useI18n();
  const update = (i: number, patch: Partial<PolicyIn["quiet_hours"][number]>) => onChange(value.map((w, j) => (j === i ? { ...w, ...patch } : w)));
  return (
    <fieldset className="min-w-0 flex flex-col gap-2" data-testid="policy-quiet">
      <legend className="mb-1 type-headline text-label-1">{t("policies.quiet.title")}</legend>
      <p className="-mt-1 type-footnote text-label-3">{t("policies.quiet.lead")}</p>
      {value.length === 0 ? <p className="type-footnote text-label-2">{t("policies.quiet.none")}</p> : null}
      <ul className="flex flex-col gap-2">
        {value.map((w, i) => (
          <li key={i} className="flex flex-col gap-2 rounded-lg bg-fill-3 p-2.5">
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("policies.quiet.days", { n: i + 1 })}>
              {WEEKDAYS.map((d) => (
                <Chip key={d} size="sm" selected={w.weekdays.includes(d)} onSelectedChange={(on) => update(i, { weekdays: on ? [...w.weekdays, d].sort() : w.weekdays.filter((x) => x !== d) })}>
                  {t(`policies.day.${d}` as MessageKey)}
                </Chip>
              ))}
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <Field label={t("policies.quiet.start")} htmlFor={`qs-${i}`} className="min-w-28 flex-1">
                <Input id={`qs-${i}`} type="time" value={w.start} onChange={(e) => update(i, { start: e.target.value })} data-testid={`policy-quiet-start-${i}`} />
              </Field>
              <Field label={t("policies.quiet.end")} htmlFor={`qe-${i}`} className="min-w-28 flex-1">
                <Input id={`qe-${i}`} type="time" value={w.end} onChange={(e) => update(i, { end: e.target.value })} data-testid={`policy-quiet-end-${i}`} />
              </Field>
              <IconButton label={t("policies.quiet.remove", { n: i + 1 })} onClick={() => onChange(value.filter((_, j) => j !== i))}>
                <Trash2 aria-hidden />
              </IconButton>
            </div>
          </li>
        ))}
      </ul>
      {error ? <p className="type-footnote text-status-infeasible-fg" role="alert">{error}</p> : null}
      <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => onChange([...value, { weekdays: [1, 2, 3, 4, 5], start: "", end: "" }])} data-testid="policy-quiet-add">
        <Plus aria-hidden />
        {t("policies.quiet.add")}
      </Button>
    </fieldset>
  );
}

function Blackouts({ value, onChange, error }: { value: PolicyIn["blackouts"]; onChange: (v: PolicyIn["blackouts"]) => void; error: string | null }) {
  const { t } = useI18n();
  const update = (i: number, patch: Partial<PolicyIn["blackouts"][number]>) => onChange(value.map((b, j) => (j === i ? { ...b, ...patch } : b)));
  return (
    <fieldset className="min-w-0 flex flex-col gap-2" data-testid="policy-blackouts">
      <legend className="mb-1 type-headline text-label-1">{t("policies.blackout.title")}</legend>
      <p className="-mt-1 type-footnote text-label-3">{t("policies.blackout.lead")}</p>
      {value.length === 0 ? <p className="type-footnote text-label-2">{t("policies.blackout.none")}</p> : null}
      <ul className="flex flex-col gap-2">
        {value.map((b, i) => (
          <li key={i} className={cn("grid gap-2 rounded-lg bg-fill-3 p-2.5 sm:grid-cols-[1fr_1fr_1.4fr_auto] sm:items-end")}>
            <Field label={t("policies.blackout.from")} htmlFor={`bf-${i}`}>
              <DateField id={`bf-${i}`} value={b.from} onChange={(v) => update(i, { from: v })} data-testid={`policy-blackout-from-${i}`} />
            </Field>
            <Field label={t("policies.blackout.to")} htmlFor={`bt-${i}`}>
              <DateField id={`bt-${i}`} value={b.to ?? ""} min={b.from || undefined} onChange={(v) => update(i, { to: v })} data-testid={`policy-blackout-to-${i}`} />
            </Field>
            <Field label={t("policies.blackout.label")} htmlFor={`bl-${i}`}>
              <Input id={`bl-${i}`} value={b.label ?? ""} maxLength={120} onChange={(e) => update(i, { label: e.target.value })} />
            </Field>
            <IconButton label={t("policies.blackout.remove", { n: i + 1 })} onClick={() => onChange(value.filter((_, j) => j !== i))} className="justify-self-start">
              <Trash2 aria-hidden />
            </IconButton>
          </li>
        ))}
      </ul>
      {error ? <p className="type-footnote text-status-infeasible-fg" role="alert">{error}</p> : null}
      <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => onChange([...value, { from: "", to: "", label: "" }])} data-testid="policy-blackout-add">
        <Plus aria-hidden />
        {t("policies.blackout.add")}
      </Button>
    </fieldset>
  );
}
