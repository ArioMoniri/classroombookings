"use client";
/**
 * Add or edit a pool member: name, kind, which terms the rules apply to, caps (duties in total / per day), load
 * factor (100 % = a normal share, 50 % = half) and the unavailability list (a date or a weekday, the whole day or a
 * period range, with a note). A row linked to an instructor carries that instructor's rules into every plan; switching
 * "Görev alır" off takes the person out of the pool. Backend validation errors are shown verbatim.
 */
import { Plus, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { ResponsiveDialog } from "@/components/moderation/responsive-dialog";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { Button, IconButton } from "@/components/ui/button";
import { DateField } from "@/components/ui/date-field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { errorText } from "@/lib/api/analytics";
import { POOL_KINDS, useSaveMember, type PoolIn, type PoolKind, type PoolMember } from "@/lib/api/invigilation";
import { useI18n } from "@/lib/i18n/provider";
import { dayName, PERIODS } from "@/lib/time";
import { fromRows, newRow, rowProblem, toRows, type UnavailRow } from "./invigilation-model";

interface Form {
  full_name: string;
  kind: PoolKind;
  allTerms: boolean;
  max_duties: string;
  max_per_day: string;
  load_factor: string;
  active: boolean;
  notes: string;
  rows: UnavailRow[];
}

function initial(member: PoolMember | null, prefill?: Partial<PoolIn>): Form {
  return {
    full_name: member?.full_name ?? prefill?.full_name ?? "",
    kind: member?.kind ?? prefill?.kind ?? "STAFF",
    allTerms: member ? member.term_id === null : false,
    max_duties: member?.max_duties != null ? String(member.max_duties) : "",
    max_per_day: member?.max_per_day != null ? String(member.max_per_day) : "",
    load_factor: String(member?.load_factor ?? 100),
    active: member?.active ?? true,
    notes: member?.notes ?? "",
    rows: toRows(member?.unavailable),
  };
}

const intIn = (s: string, lo: number, hi: number) => s === "" || (/^\d+$/.test(s) && Number(s) >= lo && Number(s) <= hi);

export function PoolMemberDialog({ open, onOpenChange, termId, member, prefill }: { open: boolean; onOpenChange: (v: boolean) => void; termId: number | null; member: PoolMember | null; prefill?: Partial<PoolIn> }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const id = useId();
  const save = useSaveMember();
  const [f, setF] = useState<Form>(() => initial(member, prefill));
  const [tried, setTried] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sig = `${open}|${member?.id ?? "new"}|${prefill?.full_name ?? ""}`;
  const [seen, setSeen] = useState(sig);
  if (seen !== sig) {
    setSeen(sig);
    if (open) {
      setF(initial(member, prefill));
      setTried(false);
      setError(null);
    }
  }
  const bad = {
    full_name: !f.full_name.trim(),
    max_duties: !intIn(f.max_duties, 0, 200),
    max_per_day: !intIn(f.max_per_day, 0, 200),
    load_factor: !(f.load_factor !== "" && intIn(f.load_factor, 10, 500)),
    rows: f.rows.some((r) => rowProblem(r) !== null),
  };
  const invalid = Object.values(bad).some(Boolean);
  const setRow = (rid: string, patch: Partial<UnavailRow>) => setF((s) => ({ ...s, rows: s.rows.map((r) => (r.id === rid ? { ...r, ...patch } : r)) }));

  const submit = async () => {
    setTried(true);
    setError(null);
    if (invalid) return;
    const body: PoolIn = {
      full_name: f.full_name.trim(),
      kind: f.kind,
      term_id: f.allTerms ? null : termId,
      max_duties: f.max_duties === "" ? null : Number(f.max_duties),
      max_per_day: f.max_per_day === "" ? null : Number(f.max_per_day),
      load_factor: Number(f.load_factor),
      active: f.active,
      notes: f.notes.trim() || null,
      unavailable: fromRows(f.rows),
    };
    if (!member && prefill?.instructor_id) body.instructor_id = prefill.instructor_id;
    try {
      await save.mutateAsync({ id: member?.id, body });
      toast.success(t(member ? "invigilation.pool.saved" : "invigilation.pool.added", { name: body.full_name! }));
      onOpenChange(false);
    } catch (e) {
      setError(errorText(e, lang));
    }
  };

  const err = (k: keyof typeof bad) => tried && bad[k];
  const numField = (k: "max_duties" | "max_per_day" | "load_factor", label: string, hint: string, lo: number, hi: number) => (
    <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-${k}`}>
      <span className="type-footnote font-medium text-label-1">{label}</span>
      <Input id={`${id}-${k}`} type="number" inputMode="numeric" min={lo} max={hi} value={f[k]} aria-invalid={err(k) || undefined} aria-describedby={`${id}-${k}-h`} onChange={(e) => setF((s) => ({ ...s, [k]: e.target.value }))} data-testid={`pool-${k}`} />
      <span id={`${id}-${k}-h`} className={err(k) ? "type-caption text-status-infeasible-fg" : "type-caption text-label-2"}>{err(k) ? t("invigilation.form.range", { lo, hi }) : hint}</span>
    </label>
  );

  return (
    <ResponsiveDialog
      open={open}
      onOpenChange={onOpenChange}
      title={member ? t("invigilation.pool.editTitle", { name: member.full_name }) : prefill?.full_name ? t("invigilation.pool.rulesTitle", { name: prefill.full_name }) : t("invigilation.pool.addTitle")}
      description={t("invigilation.pool.formBody")}
      className="sm:max-w-2xl"
      testId="pool-form"
      footer={
        <>
          <Button variant="ghost" className="max-md:h-11" onClick={() => onOpenChange(false)}>{t("common.cancel")}</Button>
          <BusyButton busy={save.isPending} busyLabel={t("busy.saving")} className="max-md:h-11" onClick={() => void submit()} data-testid="pool-save">{t("common.save")}</BusyButton>
        </>
      }
    >
      <form className="flex flex-col gap-4" noValidate onSubmit={(e) => (e.preventDefault(), void submit())}>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-name`}>
            <span className="type-footnote font-medium text-label-1">{t("invigilation.pool.name")}</span>
            <Input id={`${id}-name`} maxLength={255} value={f.full_name} disabled={Boolean(!member && prefill?.instructor_id)} aria-invalid={err("full_name") || undefined} onChange={(e) => setF((s) => ({ ...s, full_name: e.target.value }))} data-testid="pool-name" />
            {err("full_name") ? <span className="type-caption text-status-infeasible-fg">{t("invigilation.pool.nameRequired")}</span> : null}
          </label>
          <label className="flex min-w-0 flex-col gap-1" htmlFor={`${id}-kind`}>
            <span className="type-footnote font-medium text-label-1">{t("invigilation.pool.kind")}</span>
            <NativeSelect id={`${id}-kind`} value={f.kind} onChange={(e) => setF((s) => ({ ...s, kind: e.target.value as PoolKind }))} data-testid="pool-kind">
              {POOL_KINDS.map((k) => <option key={k} value={k}>{t(`invigilation.kind.${k}`)}</option>)}
            </NativeSelect>
          </label>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="type-footnote font-medium text-label-1" id={`${id}-scope`}>{t("invigilation.pool.scope")}</span>
          <SegmentedControl
            semantics="radiogroup"
            aria-labelledby={`${id}-scope`}
            options={[
              { value: "term", label: t("invigilation.pool.thisTerm"), disabled: termId === null },
              { value: "all", label: t("invigilation.pool.allTerms") },
            ]}
            value={f.allTerms || termId === null ? "all" : "term"}
            onValueChange={(v) => setF((s) => ({ ...s, allTerms: v === "all" }))}
            fill
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {numField("max_duties", t("invigilation.pool.maxDuties"), t("invigilation.pool.maxDutiesHint"), 0, 200)}
          {numField("max_per_day", t("invigilation.pool.maxPerDay"), t("invigilation.pool.maxPerDayHint"), 0, 200)}
          {numField("load_factor", t("invigilation.pool.loadFactor"), t("invigilation.pool.loadFactorHint"), 10, 500)}
        </div>
        <label className="flex items-center justify-between gap-3 rounded-xl bg-fill-3 px-3 py-2 type-callout" htmlFor={`${id}-active`}>
          <span className="flex flex-col">
            <span className="font-medium">{t("invigilation.pool.active")}</span>
            <span className="type-caption text-label-2">{t("invigilation.pool.activeHint")}</span>
          </span>
          <Switch id={`${id}-active`} checked={f.active} onCheckedChange={(v) => setF((s) => ({ ...s, active: Boolean(v) }))} data-testid="pool-active" />
        </label>
        <fieldset className="flex flex-col gap-2" data-testid="pool-unavailable">
          <legend className="mb-1 type-footnote font-medium text-label-1">{t("invigilation.pool.unavailable")}</legend>
          {f.rows.length === 0 ? <p className="type-callout text-label-2">{t("invigilation.pool.noUnavailable")}</p> : null}
          <ul className="flex flex-col gap-2">
            {f.rows.map((r, i) => {
              const problem = tried ? rowProblem(r) : null;
              return (
                <li key={r.id} className="flex flex-col gap-2 rounded-xl bg-card p-2.5 edge-hairline" data-testid="pool-unavail-row">
                  <div className="flex flex-wrap items-end gap-2">
                    <SegmentedControl
                      size="sm"
                      semantics="radiogroup"
                      aria-label={t("invigilation.pool.rowMode", { n: i + 1 })}
                      options={[
                        { value: "date", label: t("invigilation.pool.onDate") },
                        { value: "day", label: t("invigilation.pool.everyDay") },
                      ]}
                      value={r.mode}
                      onValueChange={(v) => setRow(r.id, { mode: v as "date" | "day" })}
                    />
                    {r.mode === "date" ? (
                      <DateField size="sm" className="w-40" value={r.date} onChange={(v) => setRow(r.id, { date: v })} aria-label={t("invigilation.pool.date")} data-testid="pool-unavail-date" />
                    ) : (
                      <NativeSelect size="sm" className="w-36" aria-label={t("invigilation.pool.weekday")} value={r.day} onChange={(e) => setRow(r.id, { day: Number(e.target.value) })}>
                        {[1, 2, 3, 4, 5, 6, 7].map((d) => <option key={d} value={d}>{dayName(d, locale)}</option>)}
                      </NativeSelect>
                    )}
                    <IconButton type="button" size="sm" className="ml-auto" label={t("invigilation.pool.removeRow", { n: i + 1 })} onClick={() => setF((s) => ({ ...s, rows: s.rows.filter((x) => x.id !== r.id) }))}>
                      <Trash2 aria-hidden />
                    </IconButton>
                  </div>
                  <div className="flex flex-wrap items-end gap-2">
                    <SegmentedControl
                      size="sm"
                      semantics="radiogroup"
                      aria-label={t("invigilation.pool.rowSpan", { n: i + 1 })}
                      options={[
                        { value: "whole", label: t("invigilation.pool.wholeDay") },
                        { value: "range", label: t("invigilation.pool.hours") },
                      ]}
                      value={r.whole ? "whole" : "range"}
                      onValueChange={(v) => setRow(r.id, { whole: v === "whole" })}
                    />
                    {!r.whole ? (
                      <>
                        <NativeSelect size="sm" className="w-28" aria-label={t("invigilation.pool.from")} value={r.start} onChange={(e) => setRow(r.id, { start: Number(e.target.value) })}>
                          {PERIODS.map((p) => <option key={p.index} value={p.index}>{p.start}</option>)}
                        </NativeSelect>
                        <span aria-hidden className="pb-1.5 text-label-2">–</span>
                        <NativeSelect size="sm" className="w-28" aria-label={t("invigilation.pool.to")} value={r.end} onChange={(e) => setRow(r.id, { end: Number(e.target.value) })}>
                          {PERIODS.map((p) => <option key={p.index} value={p.index}>{p.end}</option>)}
                        </NativeSelect>
                      </>
                    ) : null}
                    <Input fieldSize="sm" className="min-w-40 flex-1" maxLength={200} placeholder={t("invigilation.pool.note")} aria-label={t("invigilation.pool.note")} value={r.note} onChange={(e) => setRow(r.id, { note: e.target.value })} />
                  </div>
                  {problem ? <span className="type-caption text-status-infeasible-fg">{t(problem === "date" ? "invigilation.pool.badDate" : "invigilation.pool.badRange")}</span> : null}
                </li>
              );
            })}
          </ul>
          <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => setF((s) => ({ ...s, rows: [...s.rows, newRow()] }))} data-testid="pool-unavail-add">
            <Plus aria-hidden />
            {t("invigilation.pool.addUnavailable")}
          </Button>
        </fieldset>
        <label className="flex flex-col gap-1" htmlFor={`${id}-notes`}>
          <span className="type-footnote font-medium text-label-1">{t("invigilation.pool.notes")}</span>
          <Textarea id={`${id}-notes`} rows={2} maxLength={2000} value={f.notes} onChange={(e) => setF((s) => ({ ...s, notes: e.target.value }))} />
        </label>
        {tried && invalid ? <Alert tone="error">{t("invigilation.form.fix")}</Alert> : null}
        {error ? <Alert tone="error" data-testid="pool-error">{error}</Alert> : null}
      </form>
    </ResponsiveDialog>
  );
}
