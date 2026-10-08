"use client";
/** /admin/holidays (CRBS `Holidays`): named date ranges inside a session; no bookings, series skip them. */
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { crbs, crbsError, useCrbsMutation, useHolidays, useSessions, type Holiday } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, ConfirmDialog, Field, Loading, PageTitle, SectionTitle, SelectField } from "./kit";
import { useErrorToast } from "./admin-gate";

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
  const toastError = useErrorToast();
  const keys = [["crbs", "holidays"], ["crbs", "grid"], ["crbs", "dates"], ["crbs", "sessions"]];
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
                <Button variant="ghost" size="icon-sm" aria-label={t("crbs.holidays.deleteNamed", { name: h.name })} onClick={() => setDeleting(h)}>
                  <Trash2 />
                </Button>
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
