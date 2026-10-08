"use client";
/** /admin/weeks (CRBS `Weeks`): timetable weeks (A/B rotation) with background colour; text colour is derived. */
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { crbs, crbsError, useCrbsMutation, useTimetableWeeks, type TimetableWeek } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, ConfirmDialog, Field, Loading, PageTitle, SectionTitle } from "./kit";
import { useErrorToast } from "./admin-gate";
import { EntityIcon, IconPicker } from "./icons";

const KEYS = [["crbs", "weeks"], ["crbs", "dates"], ["crbs", "session-dates"], ["crbs", "grid"]];

export function WeeksAdmin() {
  const { t } = useI18n();
  const weeks = useTimetableWeeks();
  const [editing, setEditing] = useState<TimetableWeek | null>(null);
  const [deleting, setDeleting] = useState<TimetableWeek | null>(null);
  const toastError = useErrorToast();
  const del = useCrbsMutation((w: TimetableWeek) => crbs.bookingAdmin.deleteWeek(w.id), KEYS);
  return (
    <div className="flex flex-col gap-5">
      <PageTitle title={t("crbs.admin.weeks.title")} subtitle={t("crbs.weeks.lead")} />
      <Card variant="glass" className="py-0">
        {weeks.isLoading ? (
          <Loading className="px-4" />
        ) : (weeks.data ?? []).length === 0 ? (
          <p className="px-4 py-5 type-callout text-label-2">{t("crbs.weeks.none")}</p>
        ) : (
          <ul>
            {(weeks.data ?? []).map((w) =>
              editing?.id === w.id ? (
                <li key={w.id} className="px-4 py-3 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
                  <WeekForm week={w} onDone={() => setEditing(null)} />
                </li>
              ) : (
                <li key={w.id} className="flex items-center gap-3 px-4 py-2.5 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
                  <span className="inline-flex h-6 min-w-16 items-center justify-center gap-1 rounded-md px-2 type-footnote font-semibold" style={{ background: w.bgcol, color: w.fgcol }}>
                    <EntityIcon name={w.icon} className="text-current" />
                    {w.name}
                  </span>
                  <span className="flex-1 font-mono type-footnote text-label-3">{w.bgcol}</span>
                  <Button variant="ghost" size="icon-sm" aria-label={t("crbs.rooms.editNamed", { name: w.name })} onClick={() => setEditing(w)}>
                    <Pencil />
                  </Button>
                  <Button variant="ghost" size="icon-sm" aria-label={t("crbs.rooms.deleteNamed", { name: w.name })} onClick={() => setDeleting(w)}>
                    <Trash2 />
                  </Button>
                </li>
              ),
            )}
          </ul>
        )}
      </Card>
      <section aria-labelledby="wk-add">
        <SectionTitle id="wk-add">{t("crbs.weeks.add")}</SectionTitle>
        <WeekForm week={null} onDone={() => undefined} />
      </section>
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("crbs.weeks.deleteTitle", { name: deleting?.name ?? "" })}
        description={t("crbs.weeks.deleteBody")}
        confirmLabel={t("crbs.common.delete")}
        destructive
        busy={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting, { onSuccess: () => setDeleting(null), onError: toastError })}
      />
    </div>
  );
}

function WeekForm({ week, onDone }: { week: TimetableWeek | null; onDone: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState(week?.name ?? "");
  const [col, setCol] = useState(week?.bgcol ?? "#71AAE3");
  const [icon, setIcon] = useState<string | null>(week?.icon ?? null);
  const [error, setError] = useState<string | null>(null);
  const save = useCrbsMutation(() => (week ? crbs.bookingAdmin.updateWeek(week.id, { name: name.trim(), bgcol: col, icon }) : crbs.bookingAdmin.createWeek({ name: name.trim(), bgcol: col, icon })), KEYS);
  return (
    <form
      className="grid items-end gap-3 sm:grid-cols-[2fr_auto_auto]"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        save.mutate(undefined, {
          onSuccess: () => {
            toast.success(t("crbs.common.saved"));
            if (!week) setName("");
            onDone();
          },
          onError: (err) => setError(bookingErrorMessage(crbsError(err), t)),
        });
      }}
    >
      <Field label={t("crbs.common.name")} htmlFor={`wk-name-${week?.id ?? "new"}`}>
        <Input id={`wk-name-${week?.id ?? "new"}`} required maxLength={20} placeholder={t("crbs.weeks.namePlaceholder")} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label={t("crbs.weeks.colour")} htmlFor={`wk-col-${week?.id ?? "new"}`}>
        <input id={`wk-col-${week?.id ?? "new"}`} type="color" value={col} onChange={(e) => setCol(e.target.value.toUpperCase())} className="h-8 w-16 cursor-pointer rounded-lg bg-fill-2 p-1 shadow-[inset_0_0_0_1px_var(--hairline)]" />
      </Field>
      <div className="flex gap-2">
        {week ? (
          <Button type="button" variant="ghost" onClick={onDone}>
            {t("crbs.common.cancel")}
          </Button>
        ) : null}
        <Button type="submit" disabled={!name.trim() || save.isPending}>
          {week ? null : <Plus aria-hidden />}
          {week ? t("crbs.common.save") : t("crbs.common.add")}
        </Button>
      </div>
      <Field label={t("crbs.icons.label")} htmlFor={`wk-icon-${week?.id ?? "new"}`} className="sm:col-span-3">
        <IconPicker id={`wk-icon-${week?.id ?? "new"}`} value={icon} onChange={setIcon} />
      </Field>
      {error ? <Alert tone="error" className="sm:col-span-3">{error}</Alert> : null}
    </form>
  );
}
