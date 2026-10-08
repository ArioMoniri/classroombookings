"use client";
/**
 * Create, edit and delete a session (CRBS `Sessions::add/edit/delete`, `V/sessions/add.php`) on top of
 * `POST/PUT/DELETE /terms`. A date change that leaves bookings outside the session cancels them (CRBS
 * `check_session_dates`); with the "confirm" setting the backend answers 409 first and the dialog asks.
 * Deleting a session deletes its bookings, as in CRBS: the confirm step names how many (`GET /terms/{id}/usage`).
 */
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { crbs, crbsAdmin, crbsError, useCrbsMutation, useSchedules, useTermUsage, weeksBetween, type Session } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, Field, Loading, SelectField } from "./kit";

export const SESSION_KEYS = [["crbs", "sessions"], ["crbs", "session-dates"], ["crbs", "term-schedules"], ["crbs", "context"], ["crbs", "grid"], ["crbs", "dates"], ["crbs", "holidays"], ["crbs", "term-usage"], ["crbs", "mine"], ["crbs", "dashboard"], ["terms"]];

/** `session` null = create. `onSaved` gets the term id (a new session becomes the selected one). */
export function SessionDialog({ open, session, onClose, onSaved }: { open: boolean; session: Session | null; onClose: () => void; onSaved: (termId: number) => void }) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-lg" data-testid="session-dialog">
        {open ? <SessionForm key={session?.term_id ?? "new"} session={session} onClose={onClose} onSaved={onSaved} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function SessionForm({ session, onClose, onSaved }: { session: Session | null; onClose: () => void; onSaved: (termId: number) => void }) {
  const { t } = useI18n();
  const schedules = useSchedules(!session);
  const [name, setName] = useState(session?.name ?? "");
  const [code, setCode] = useState(session?.code ?? "");
  const [start, setStart] = useState(session?.date_start ?? "");
  const [end, setEnd] = useState(session?.date_end ?? "");
  const [selectable, setSelectable] = useState(true);
  const [schedule, setSchedule] = useState("");
  const [error, setError] = useState<string | null>(null);
  /** bookings the new dates would cancel (409 `bookings_outside_term`), waiting for a confirm */
  const [outside, setOutside] = useState<number | null>(null);
  const save = useCrbsMutation(async (confirm: boolean) => {
    if (session) return crbsAdmin.terms.update(session.term_id, { name: name.trim(), start_date: start, end_date: end }, confirm);
    const created = await crbsAdmin.terms.create({ code: (code.trim() || name.trim()), name: name.trim() || null, start_date: start, end_date: end, week_count: weeksBetween(start, end) });
    await crbs.bookingAdmin.updateSession(created.id, { is_selectable: selectable, default_schedule_id: schedule ? Number(schedule) : null });
    return created;
  }, SESSION_KEYS);
  const badDates = !!start && !!end && end < start;
  const submit = (confirm: boolean) => {
    setError(null);
    save.mutate(confirm, {
      onSuccess: (out) => {
        toast.success(session ? t("crbs.common.saved") : t("admingaps.sessions.created", { name: out.name }));
        if (out.cancelled_booking_ids.length) toast.warning(t("admingaps.sessions.cancelled", { n: out.cancelled_booking_ids.length }));
        onSaved(out.id);
        onClose();
      },
      onError: (err) => {
        const e = crbsError(err);
        if (e.status === 409 && e.code === "bookings_outside_term") {
          setOutside(Array.isArray(e.data.bookings) ? e.data.bookings.length : 0);
          return;
        }
        setError(e.status === 409 && !e.code ? t("admingaps.sessions.codeTaken") : bookingErrorMessage(e, t));
      },
    });
  };
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit(false);
      }}
    >
      <DialogHeader>
        <DialogTitle>{session ? t("admingaps.sessions.editTitle", { name: session.name }) : t("admingaps.sessions.new")}</DialogTitle>
        <DialogDescription>{session ? t("admingaps.sessions.editHint") : t("admingaps.sessions.newHint")}</DialogDescription>
      </DialogHeader>
      <Field label={t("crbs.common.name")} htmlFor="ses-name">
        <Input id="ses-name" required maxLength={128} placeholder={t("admingaps.sessions.namePlaceholder")} value={name} onChange={(e) => setName(e.target.value)} data-testid="session-name" />
      </Field>
      {!session ? (
        <Field label={t("admingaps.sessions.code")} htmlFor="ses-code" hint={t("admingaps.sessions.codeHint")}>
          <Input id="ses-code" maxLength={32} placeholder={name.trim() || "2026-2027 GÜZ"} value={code} onChange={(e) => setCode(e.target.value)} data-testid="session-code" />
        </Field>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("admingaps.sessions.start")} htmlFor="ses-start">
          <Input id="ses-start" type="date" required value={start} onChange={(e) => (setStart(e.target.value), setOutside(null))} data-testid="session-start" />
        </Field>
        <Field label={t("admingaps.sessions.end")} htmlFor="ses-end" error={badDates ? t("admingaps.sessions.endBeforeStart") : null}>
          <Input id="ses-end" type="date" required min={start || undefined} value={end} onChange={(e) => (setEnd(e.target.value), setOutside(null))} data-testid="session-end" />
        </Field>
      </div>
      {!session ? (
        <>
          <label className="flex items-center justify-between gap-3 type-callout text-label-1">
            <span>
              {t("crbs.sessions.selectableLabel")}
              <span className="block type-footnote text-label-3">{t("crbs.sessions.selectableHint")}</span>
            </span>
            <Switch checked={selectable} onCheckedChange={setSelectable} aria-label={t("crbs.sessions.selectableLabel")} />
          </label>
          <Field label={t("crbs.sessions.defaultSchedule")} htmlFor="ses-sched" hint={t("crbs.sessions.defaultScheduleHint")}>
            <SelectField id="ses-sched" value={schedule} onChange={(e) => setSchedule(e.target.value)}>
              <option value="">{t("crbs.common.none")}</option>
              {(schedules.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </SelectField>
          </Field>
        </>
      ) : (
        <p className="type-footnote text-label-3">{t("admingaps.sessions.datesHint")}</p>
      )}
      {outside !== null ? (
        <Alert tone="warning" title={t("admingaps.sessions.outsideTitle", { n: outside })} testId="session-outside">
          {t("admingaps.sessions.outsideBody")}
        </Alert>
      ) : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("crbs.common.cancel")}
        </Button>
        {outside !== null ? (
          <Button type="button" variant="destructive" disabled={save.isPending} onClick={() => submit(true)} data-testid="session-confirm-dates">
            {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t("admingaps.sessions.outsideConfirm", { n: outside })}
          </Button>
        ) : (
          <Button type="submit" disabled={save.isPending || !name.trim() || !start || !end || badDates} data-testid="session-save">
            {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {session ? t("crbs.common.save") : t("crbs.common.create")}
          </Button>
        )}
      </DialogFooter>
    </form>
  );
}

/** CRBS `session.delete.warning`: the session's bookings are deleted with it; the counts come first. */
export function DeleteSessionDialog({ session, onClose, onDeleted }: { session: Session | null; onClose: () => void; onDeleted: () => void }) {
  const { t, n } = useI18n();
  const usage = useTermUsage(session?.term_id ?? null);
  const [ack, setAck] = useState(false);
  const del = useCrbsMutation((id: number) => crbsAdmin.terms.remove(id), SESSION_KEYS);
  const [error, setError] = useState<string | null>(null);
  const u = usage.data;
  const needsAck = !!u && u.bookings + u.runs + u.sections > 0;
  return (
    <Dialog open={!!session} onOpenChange={(o) => !o && (setAck(false), setError(null), onClose())}>
      <DialogContent className="sm:max-w-md" data-testid="session-delete-dialog">
        <DialogHeader>
          <DialogTitle>{t("admingaps.sessions.deleteTitle", { name: session?.name ?? "" })}</DialogTitle>
          <DialogDescription>{t("admingaps.sessions.deleteLead")}</DialogDescription>
        </DialogHeader>
        {usage.isLoading ? <Loading /> : null}
        {u ? (
          <ul className="flex flex-col rounded-xl bg-fill-3 px-3 py-1 type-callout text-label-1" data-testid="session-usage">
            <li className="flex justify-between gap-3 py-1.5" data-testid="session-usage-bookings">
              <span>{t("admingaps.sessions.usageBookings")}</span>
              <span className="tabular-nums">{t("admingaps.sessions.usageActive", { total: n(u.bookings), active: n(u.active_bookings) })}</span>
            </li>
            <li className="flex justify-between gap-3 py-1.5 hairline-t">
              <span>{t("admingaps.sessions.usageSeries")}</span>
              <span className="tabular-nums">{n(u.series)}</span>
            </li>
            <li className="flex justify-between gap-3 py-1.5 hairline-t">
              <span>{t("admingaps.sessions.usageHolidays")}</span>
              <span className="tabular-nums">{n(u.holidays)}</span>
            </li>
            <li className="flex justify-between gap-3 py-1.5 hairline-t">
              <span>{t("admingaps.sessions.usagePlanning")}</span>
              <span className="tabular-nums">{t("admingaps.sessions.usagePlanningValue", { sections: n(u.sections), runs: n(u.runs) })}</span>
            </li>
          </ul>
        ) : null}
        {needsAck ? (
          <label className="flex items-start gap-2 type-callout text-label-1">
            <Checkbox checked={ack} onCheckedChange={(v) => setAck(v === true)} data-testid="session-delete-ack" />
            <span>{t("admingaps.sessions.deleteAck", { n: u?.bookings ?? 0 })}</span>
          </label>
        ) : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t("crbs.common.cancel")}
          </Button>
          <Button
            variant="destructive"
            disabled={!u || del.isPending || (needsAck && !ack)}
            data-testid="session-delete-confirm"
            onClick={() =>
              session &&
              del.mutate(session.term_id, {
                onSuccess: () => {
                  toast.success(t("crbs.common.deleted"));
                  setAck(false);
                  onDeleted();
                },
                onError: (err) => setError(bookingErrorMessage(crbsError(err), t)),
              })
            }
          >
            {del.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t("admingaps.sessions.deleteConfirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
