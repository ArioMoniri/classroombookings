"use client";
/** /admin/holidays (CRBS `Holidays`): named date ranges inside a session; no bookings, series skip them. */
import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { crbs, crbsError, useCrbsMutation, useHolidays, useSessions, type Holiday, type Session } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, ConfirmDialog, Field, Loading, PageTitle, SectionTitle, SelectField } from "./kit";
import { useErrorToast } from "./admin-gate";

/** CRBS `holiday.field.duration`: inclusive day count (`1 + diff(start, end)`). */
export function holidayDays(h: Pick<Holiday, "date_start" | "date_end">): number {
  const ms = Date.parse(`${h.date_end}T00:00:00Z`) - Date.parse(`${h.date_start}T00:00:00Z`);
  return Number.isFinite(ms) ? Math.max(1, Math.round(ms / 86_400_000) + 1) : 1;
}

const KEYS = [["crbs", "holidays"], ["crbs", "grid"], ["crbs", "dates"], ["crbs", "sessions"], ["crbs", "session-dates"]];

export function HolidaysAdmin() {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  const sessions = useSessions();
  const [termPick, setTermPick] = useState<number | null>(null);
  const termId = termPick ?? sessions.data?.find((s) => s.is_selectable)?.term_id ?? sessions.data?.[0]?.term_id ?? null;
  const term = sessions.data?.find((s) => s.term_id === termId);
  const list = useHolidays(termId ?? undefined);
  const [name, setName] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Holiday | null>(null);
  const [editing, setEditing] = useState<Holiday | null>(null);
  const toastError = useErrorToast();
  const keys = KEYS;
  const add = useCrbsMutation(() => crbs.holidays.create({ term_id: termId ?? 0, name: name.trim(), date_start: start, date_end: end || start }), keys);
  const del = useCrbsMutation((h: Holiday) => crbs.holidays.remove(h.id), keys);
  return (
    <div className="flex flex-col gap-5">
      <PageTitle title={t("crbs.admin.holidays.title")} subtitle={t("crbs.admin.holidays.lead")} />
      <div className="max-w-xs">
        <Field label={t("crbs.export.session")} htmlFor="hol-term">
          <SelectField id="hol-term" value={termId ?? ""} onChange={(e) => setTermPick(Number(e.target.value))}>
            {(sessions.data ?? []).map((s) => (
              <option key={s.term_id} value={s.term_id}>
                {s.name}
              </option>
            ))}
          </SelectField>
        </Field>
      </div>
      <Card variant="glass" className="py-0">
        {list.isLoading ? (
          <Loading className="px-4" />
        ) : (list.data ?? []).length === 0 ? (
          <p className="px-4 py-5 type-callout text-label-2">{t("crbs.holidays.none")}</p>
        ) : (
          <ul data-testid="holiday-list">
            {(list.data ?? []).map((h) => (
              <li key={h.id} className="flex items-center gap-3 px-4 py-2.5 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
                <span className="min-w-0 flex-1">
                  <span className="block type-headline text-label-1">{h.name}</span>
                  <span className="block type-footnote text-label-2">{h.date_start === h.date_end ? fmt.long(h.date_start) : `${fmt.long(h.date_start)} – ${fmt.long(h.date_end)}`}</span>
                </span>
                <span className="shrink-0 type-callout text-label-2 tabular-nums" data-testid="holiday-duration">
                  {t("admingaps.holidays.days", { n: holidayDays(h) })}
                </span>
                <span className="flex shrink-0">
                  <Button variant="ghost" size="icon-sm" aria-label={t("admingaps.holidays.editNamed", { name: h.name })} onClick={() => setEditing(h)} data-testid="holiday-edit">
                    <Pencil />
                  </Button>
                  <Button variant="ghost" size="icon-sm" aria-label={t("crbs.holidays.deleteNamed", { name: h.name })} onClick={() => setDeleting(h)}>
                    <Trash2 />
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <section aria-labelledby="hol-add">
        <SectionTitle id="hol-add">{t("crbs.holidays.add")}</SectionTitle>
        <form
          className="grid items-end gap-3 sm:grid-cols-[2fr_1fr_1fr_auto]"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            add.mutate(undefined, {
              onSuccess: () => {
                toast.success(t("crbs.common.saved"));
                setName("");
                setStart("");
                setEnd("");
              },
              onError: (err) => setError(bookingErrorMessage(crbsError(err), t)),
            });
          }}
        >
          <Field label={t("crbs.common.name")} htmlFor="hol-name">
            <Input id="hol-name" required maxLength={50} placeholder={t("crbs.holidays.namePlaceholder")} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label={t("crbs.holidays.start")} htmlFor="hol-start">
            <Input id="hol-start" type="date" required min={term?.date_start ?? undefined} max={term?.date_end ?? undefined} value={start} onChange={(e) => setStart(e.target.value)} />
          </Field>
          <Field label={t("crbs.holidays.end")} htmlFor="hol-end">
            <Input id="hol-end" type="date" min={start || term?.date_start || undefined} max={term?.date_end ?? undefined} value={end} onChange={(e) => setEnd(e.target.value)} />
          </Field>
          <Button type="submit" disabled={!termId || !name.trim() || !start || add.isPending}>
            <Plus aria-hidden />
            {t("crbs.common.add")}
          </Button>
        </form>
        {error ? <Alert tone="error" className="mt-3">{error}</Alert> : null}
      </section>
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="sm:max-w-md" data-testid="holiday-dialog">
          {editing ? <HolidayForm key={editing.id} holiday={editing} term={term} onClose={() => setEditing(null)} /> : null}
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("crbs.holidays.deleteTitle", { name: deleting?.name ?? "" })}
        confirmLabel={t("crbs.common.delete")}
        destructive
        busy={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting, { onSuccess: () => setDeleting(null), onError: toastError })}
      />
    </div>
  );
}

/** CRBS `Holidays::edit`: name and dates of one holiday (`PUT /holidays/{id}`). */
function HolidayForm({ holiday, term, onClose }: { holiday: Holiday; term: Session | undefined; onClose: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState(holiday.name);
  const [start, setStart] = useState(holiday.date_start);
  const [end, setEnd] = useState(holiday.date_end);
  const [error, setError] = useState<string | null>(null);
  const save = useCrbsMutation(() => crbs.holidays.update(holiday.id, { name: name.trim(), date_start: start, date_end: end || start }), KEYS);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        save.mutate(undefined, { onSuccess: () => (toast.success(t("crbs.common.saved")), onClose()), onError: (err) => setError(bookingErrorMessage(crbsError(err), t)) });
      }}
    >
      <DialogHeader>
        <DialogTitle>{t("admingaps.holidays.editTitle", { name: holiday.name })}</DialogTitle>
        <DialogDescription>{t("admingaps.holidays.editHint")}</DialogDescription>
      </DialogHeader>
      <Field label={t("crbs.common.name")} htmlFor="hol-edit-name">
        <Input id="hol-edit-name" required maxLength={50} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("crbs.holidays.start")} htmlFor="hol-edit-start">
          <Input id="hol-edit-start" type="date" required min={term?.date_start ?? undefined} max={term?.date_end ?? undefined} value={start} onChange={(e) => setStart(e.target.value)} />
        </Field>
        <Field label={t("crbs.holidays.end")} htmlFor="hol-edit-end">
          <Input id="hol-edit-end" type="date" min={start || term?.date_start || undefined} max={term?.date_end ?? undefined} value={end} onChange={(e) => setEnd(e.target.value)} data-testid="holiday-edit-end" />
        </Field>
      </div>
      <p className="type-footnote text-label-3">{t("admingaps.holidays.days", { n: holidayDays({ date_start: start, date_end: end || start }) })}</p>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("crbs.common.cancel")}
        </Button>
        <Button type="submit" disabled={!name.trim() || !start || save.isPending || (!!end && end < start)} data-testid="holiday-save">
          {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {t("crbs.common.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}
