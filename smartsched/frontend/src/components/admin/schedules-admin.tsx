"use client";
/**
 * /admin/schedules (CRBS `Schedules` + `Periods`): schedules and their bookable periods. Every period is
 * mapped onto the university's 18-period grid (08:30–22:50), so bookings, the published timetable and the
 * solver share one clock; "Create the 18 university periods" fills an empty schedule in one step.
 */
import { Grid3x3, Loader2, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { crbs, crbsError, useCrbsMutation, useSchedules, type Period, type PeriodIn, type Schedule } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { addDays, formatPattern } from "@/components/bookings/date-format";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, ConfirmDialog, Field, Loading, PageTitle, SectionTitle } from "./kit";
import { useErrorToast } from "./admin-gate";

const KEYS = [["crbs", "schedules"], ["crbs", "grid"], ["crbs", "sessions"]];

function useWeekdays() {
  const { locale } = useI18n();
  return Array.from({ length: 7 }, (_, i) => ({ day: i + 1, label: formatPattern(addDays("2026-02-16", i), "EEE", locale) }));
}

function DaysPicker({ value, onChange, label }: { value: number[]; onChange: (v: number[]) => void; label: string }) {
  const days = useWeekdays();
  return (
    <div role="group" aria-label={label} className="flex gap-0.5">
      {days.map((d) => {
        const on = value.includes(d.day);
        return (
          <button
            key={d.day}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((x) => x !== d.day) : [...value, d.day].sort())}
            className={cn("h-7 min-w-9 rounded-md px-1.5 type-caption outline-none focus-visible:outline-2 focus-visible:outline-(--focus)", on ? "bg-tint-soft font-semibold text-tint-text" : "bg-fill-2 text-label-3")}
          >
            {d.label}
          </button>
        );
      })}
    </div>
  );
}

export function SchedulesAdmin() {
  const { t } = useI18n();
  const schedules = useSchedules();
  const [pick, setPick] = useState<number | null>(null);
  const [name, setName] = useState("");
  const toastError = useErrorToast();
  const create = useCrbsMutation(() => crbs.bookingAdmin.createSchedule({ name: name.trim() }), KEYS);
  const current = schedules.data?.find((s) => s.id === pick) ?? schedules.data?.[0];
  return (
    <div className="flex flex-col gap-5">
      <PageTitle title={t("crbs.admin.schedules.title")} subtitle={t("crbs.admin.schedules.lead")} />
      <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
        <div className="flex flex-col gap-3">
          <Card variant="glass" className="py-1">
            {schedules.isLoading ? <Loading className="px-4" /> : null}
            <ul>
              {(schedules.data ?? []).map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    aria-current={current?.id === s.id ? "true" : undefined}
                    onClick={() => setPick(s.id)}
                    className={cn("w-full px-4 py-2 text-left outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)", current?.id === s.id ? "bg-tint-soft" : "hover:bg-fill-3")}
                  >
                    <span className="block type-headline text-label-1">{s.name}</span>
                    <span className="block type-footnote text-label-3">{t("crbs.schedules.periodCount", { n: s.periods.length })}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate(undefined, { onSuccess: (s) => (setName(""), setPick(s.id)), onError: toastError });
            }}
          >
            <Input aria-label={t("crbs.schedules.newName")} placeholder={t("crbs.schedules.newName")} maxLength={32} value={name} onChange={(e) => setName(e.target.value)} />
            <Button type="submit" variant="outline" disabled={!name.trim()} aria-label={t("crbs.schedules.new")}>
              <Plus />
            </Button>
          </form>
        </div>
        {current ? <ScheduleEditor key={current.id} schedule={current} onDeleted={() => setPick(null)} /> : <p className="type-callout text-label-2">{t("crbs.schedules.none")}</p>}
      </div>
    </div>
  );
}

function ScheduleEditor({ schedule, onDeleted }: { schedule: Schedule; onDeleted: () => void }) {
  const { t, locale } = useI18n();
  const [name, setName] = useState(schedule.name);
  const [days, setDays] = useState<number[]>([1, 2, 3, 4, 5]);
  const [del, setDel] = useState(false);
  const toastError = useErrorToast();
  const rename = useCrbsMutation(() => crbs.bookingAdmin.updateSchedule(schedule.id, { name: name.trim() }), KEYS);
  const fromGrid = useCrbsMutation(() => crbs.bookingAdmin.periodsFromGrid(schedule.id, days), KEYS);
  const remove = useCrbsMutation(() => crbs.bookingAdmin.deleteSchedule(schedule.id), KEYS);
  const fmtDays = (ds: number[]) => (ds.length === 7 ? t("crbs.schedules.everyDay") : ds.map((d) => formatPattern(addDays("2026-02-16", d - 1), "EEE", locale)).join(" "));
  return (
    <Card variant="glass" className="gap-5 px-5">
      <div className="flex flex-wrap items-end gap-2">
        <Field label={t("crbs.common.name")} htmlFor="sch-name" className="min-w-56 flex-1">
          <Input id="sch-name" maxLength={32} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Button variant="outline" disabled={name.trim() === schedule.name || !name.trim()} onClick={() => rename.mutate(undefined, { onSuccess: () => toast.success(t("crbs.common.saved")), onError: toastError })}>
          {t("crbs.common.save")}
        </Button>
        <Button variant="ghost" className="text-status-infeasible-fg" onClick={() => setDel(true)}>
          <Trash2 aria-hidden />
          {t("crbs.common.delete")}
        </Button>
      </div>
      {schedule.periods.length === 0 ? (
        <section aria-labelledby="from-grid" className="flex flex-col gap-2 rounded-xl bg-fill-3 p-4">
          <h3 id="from-grid" className="type-headline text-label-1">
            {t("crbs.schedules.fromGridTitle")}
          </h3>
          <p className="type-callout text-label-2">{t("crbs.schedules.fromGridLead")}</p>
          <DaysPicker value={days} onChange={setDays} label={t("crbs.schedules.days")} />
          <div>
            <Button disabled={!days.length || fromGrid.isPending} onClick={() => fromGrid.mutate(undefined, { onSuccess: () => toast.success(t("crbs.schedules.fromGridDone")), onError: toastError })} data-testid="periods-from-grid">
              {fromGrid.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Grid3x3 aria-hidden />}
              {t("crbs.schedules.fromGrid")}
            </Button>
          </div>
        </section>
      ) : (
        <div className="overflow-x-auto rounded-xl bg-(--mat-thick-solid) shadow-[0_0_0_1px_var(--hairline)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-3">{t("crbs.common.name")}</TableHead>
                <TableHead>{t("crbs.schedules.time")}</TableHead>
                <TableHead className="hidden sm:table-cell">{t("crbs.schedules.grid")}</TableHead>
                <TableHead>{t("crbs.schedules.days")}</TableHead>
                <TableHead>{t("crbs.schedules.bookable")}</TableHead>
                <TableHead className="w-10 pr-3">
                  <span className="sr-only">{t("crbs.common.actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {schedule.periods.map((p) => (
                <PeriodRow key={p.id} period={p} fmtDays={fmtDays} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <PeriodAdd scheduleId={schedule.id} />
      <ConfirmDialog
        open={del}
        onOpenChange={setDel}
        title={t("crbs.schedules.deleteTitle", { name: schedule.name })}
        description={t("crbs.schedules.deleteBody")}
        confirmLabel={t("crbs.common.delete")}
        destructive
        busy={remove.isPending}
        onConfirm={() => remove.mutate(undefined, { onSuccess: () => (setDel(false), onDeleted()), onError: (e) => (toastError(e), setDel(false)) })}
      />
    </Card>
  );
}

function PeriodRow({ period: p, fmtDays }: { period: Period; fmtDays: (d: number[]) => string }) {
  const { t } = useI18n();
  const toastError = useErrorToast();
  const update = useCrbsMutation((body: PeriodIn) => crbs.bookingAdmin.updatePeriod(p.id, body), KEYS);
  const remove = useCrbsMutation(() => crbs.bookingAdmin.deletePeriod(p.id), KEYS);
  return (
    <TableRow>
      <TableCell className="pl-3 font-medium text-label-1">{p.name}</TableCell>
      <TableCell className="tabular-nums text-label-1">
        {p.time_start}–{p.time_end}
      </TableCell>
      <TableCell className="hidden text-label-2 sm:table-cell">{p.start_period === p.end_period ? `P${p.start_period}` : `P${p.start_period}–P${p.end_period}`}</TableCell>
      <TableCell className="text-label-2">{fmtDays(p.days)}</TableCell>
      <TableCell>
        <Switch size="sm" checked={p.bookable} aria-label={t("crbs.schedules.bookableNamed", { name: p.name })} onCheckedChange={(v) => update.mutate({ bookable: v }, { onError: toastError })} />
      </TableCell>
      <TableCell className="pr-3">
        <Button variant="ghost" size="icon-sm" aria-label={t("crbs.rooms.deleteNamed", { name: p.name })} onClick={() => remove.mutate(undefined, { onError: toastError })}>
          <Trash2 />
        </Button>
      </TableCell>
    </TableRow>
  );
}

function PeriodAdd({ scheduleId }: { scheduleId: number }) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [days, setDays] = useState<number[]>([1, 2, 3, 4, 5]);
  const [error, setError] = useState<string | null>(null);
  const add = useCrbsMutation(() => crbs.bookingAdmin.createPeriod(scheduleId, { name: name.trim(), time_start: start, time_end: end, days, bookable: true }), KEYS);
  return (
    <section aria-labelledby="per-add" className="flex flex-col gap-3">
      <SectionTitle id="per-add">{t("crbs.schedules.addPeriod")}</SectionTitle>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          add.mutate(undefined, { onSuccess: () => (setName(""), setStart(""), setEnd("")), onError: (err) => setError(bookingErrorMessage(crbsError(err), t)) });
        }}
      >
        <Field label={t("crbs.common.name")} htmlFor="per-name">
          <Input id="per-name" className="w-32" maxLength={30} required value={name} onChange={(e) => setName(e.target.value)} placeholder="P19" />
        </Field>
        <Field label={t("crbs.schedules.start")} htmlFor="per-start">
          <Input id="per-start" className="w-28" required placeholder="18.00" value={start} onChange={(e) => setStart(e.target.value)} />
        </Field>
        <Field label={t("crbs.schedules.end")} htmlFor="per-end">
          <Input id="per-end" className="w-28" required placeholder="18.40" value={end} onChange={(e) => setEnd(e.target.value)} />
        </Field>
        <Field label={t("crbs.schedules.days")}>
          <DaysPicker value={days} onChange={setDays} label={t("crbs.schedules.days")} />
        </Field>
        <Button type="submit" variant="outline" disabled={add.isPending || !name.trim() || !start || !end || !days.length}>
          <Plus aria-hidden />
          {t("crbs.common.add")}
        </Button>
      </form>
      <p className="type-footnote text-label-3">{t("crbs.schedules.timeHint")}</p>
      {error ? <Alert tone="error">{error}</Alert> : null}
    </section>
  );
}
