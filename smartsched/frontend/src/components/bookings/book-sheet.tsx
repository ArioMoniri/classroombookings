"use client";
/**
 * "Book a slot" sheet (CRBS `SingleAgent`): single or recurring (tabs by permission for this room), notes,
 * department and user (only with `set_department` / `set_user`), and for recurring the start/end choice
 * plus the preview with book / skip / replace per date.
 */
import { Loader2, Repeat, CalendarCheck } from "lucide-react";
import { useMemo, useReducer, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input, useShake } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { Textarea } from "@/components/ui/textarea";
import {
  BOOKING_KEYS,
  crbs,
  crbsError,
  useBookingDates,
  useCrbsMe,
  useCrbsMutation,
  useDepartments,
  useUserSearch,
  type Grid,
  type GridSlot,
  type RecurringIn,
} from "@/lib/api/crbs";
import { bookingCapabilities, hasPermission } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import { Alert, Field, SelectField } from "@/components/admin/kit";
import { bookingErrorMessage } from "./booking-errors";
import type { DateFormatter } from "./date-format";
import { holidaysOnWeekday, initialPreview, instancesPayload, previewReducer, summarise } from "./recurring-preview";
import { RecurringPreviewTable } from "./recurring-preview-table";
import { useIsPhone } from "./use-is-phone";

type Kind = "single" | "recurring";
type StartMode = "date" | "session" | "custom";
type EndMode = "session" | "custom";

export interface BookTarget {
  slot: GridSlot;
  grid: Grid;
}

export function BookSheet({ target, onOpenChange, fmt }: { target: BookTarget | null; onOpenChange: (open: boolean) => void; fmt: DateFormatter }) {
  const phone = useIsPhone();
  return (
    <Sheet open={!!target} onOpenChange={onOpenChange}>
      <SheetContent side={phone ? "bottom" : "right"} className="gap-0 sm:max-w-lg data-[side=right]:sm:max-w-lg" data-testid="book-sheet">
        {target ? <BookForm key={`${target.slot.date}|${target.slot.period_id}|${target.slot.room_id}`} target={target} fmt={fmt} onDone={() => onOpenChange(false)} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function BookForm({ target, fmt, onDone }: { target: BookTarget; fmt: DateFormatter; onDone: () => void }) {
  const { t } = useI18n();
  const { slot, grid } = target;
  const me = useCrbsMe();
  const perms = me.data?.permissions;
  const caps = bookingCapabilities(perms);
  const room = grid.rooms.find((r) => r.id === slot.room_id);
  const period = grid.periods.find((p) => p.id === slot.period_id);
  const kinds: Kind[] = [...(slot.allow_single ? (["single"] as const) : []), ...(slot.allow_recur ? (["recurring"] as const) : [])];
  const [kind, setKind] = useState<Kind>(kinds[0] ?? "single");
  const [notes, setNotes] = useState("");
  const canDept = kind === "single" ? caps.setDepartment.single : caps.setDepartment.recurring;
  const canUser = (kind === "single" ? caps.setUser.single : caps.setUser.recurring) && hasPermission(perms, "setup.users");
  const [dept, setDept] = useState<string>("");
  const [user, setUser] = useState<string>("");
  const departments = useDepartments(canDept);
  const users = useUserSearch({ limit: 500, enabled: true, sort: "displayname" }, canUser);
  const [error, setError] = useState<string | null>(null);
  const { ref: shakeRef, shake } = useShake<HTMLDivElement>();

  const [startMode, setStartMode] = useState<StartMode>("date");
  const [endMode, setEndMode] = useState<EndMode>("session");
  const [startDate, setStartDate] = useState(slot.date);
  const [endDate, setEndDate] = useState(grid.term.end);
  const [preview, dispatch] = useReducer(previewReducer, initialPreview);
  const summary = useMemo(() => summarise(preview), [preview]);
  const termDates = useBookingDates({ term_id: grid.term.id }, kind === "recurring");

  const roomName = (id: number) => grid.rooms.find((r) => r.id === id)?.name;
  const explain = (e: unknown) => {
    setError(bookingErrorMessage(crbsError(e), t, { roomName, formatDate: fmt.short }));
    shake();
  };

  const extras = () => ({
    notes: notes.trim() || null,
    ...(canDept && dept !== "" ? { department_id: dept === "none" ? null : Number(dept) } : {}),
    ...(canUser && user !== "" ? { user_id: user === "none" ? null : Number(user) } : {}),
  });

  const single = useCrbsMutation(() => crbs.bookings.create({ room_id: slot.room_id, date: slot.date, period_id: slot.period_id, term_id: grid.term.id, ...extras() }), BOOKING_KEYS);

  const recurBody = (): RecurringIn => ({
    room_id: slot.room_id,
    period_id: slot.period_id,
    date: slot.date,
    term_id: grid.term.id,
    start: startMode === "session" ? "session" : startMode === "custom" ? startDate : slot.date,
    end: endMode === "session" ? "session" : endDate,
  });
  const previewM = useCrbsMutation(() => crbs.bookings.previewRecurring(recurBody()));
  const recur = useCrbsMutation(() => crbs.bookings.createRecurring({ ...recurBody(), ...extras(), instances: instancesPayload(preview) }), BOOKING_KEYS);

  const runPreview = () => {
    setError(null);
    previewM.mutate(undefined, {
      onSuccess: (plan) => {
        const first = plan.instances[0]?.date ?? slot.date;
        const last = plan.instances[plan.instances.length - 1]?.date ?? grid.term.end;
        dispatch({ type: "load", plan, holidays: holidaysOnWeekday(termDates.data?.dates ?? [], plan.weekday, first, last) });
      },
      onError: explain,
    });
  };

  const submit = () => {
    setError(null);
    if (kind === "single") {
      single.mutate(undefined, {
        onSuccess: (b) => {
          toast.success(t("crbs.book.done", { room: b.room_name, date: fmt.weekday(b.date), period: b.period_name ?? "" }));
          onDone();
        },
        onError: explain,
      });
      return;
    }
    recur.mutate(undefined, {
      onSuccess: (res) => {
        toast.success(t("crbs.recur.done", { created: res.created.length, skipped: res.skipped.length }));
        onDone();
      },
      onError: explain,
    });
  };

  const busy = single.isPending || recur.isPending;
  const title = `${room?.name ?? ""} · ${period?.name ?? ""}`;

  return (
    <>
      <SheetHeader className="px-5 pt-5 pb-3">
        <SheetTitle className="type-title-3">{title}</SheetTitle>
        <SheetDescription className="type-callout text-label-2">
          {fmt.long(slot.date)}
          {period ? ` · ${fmt.time(period.time_start)}–${fmt.time(period.time_end)}` : ""}
          {room?.capacity ? ` · ${t("crbs.grid.seats", { n: room.capacity })}` : ""}
        </SheetDescription>
      </SheetHeader>
      <div ref={shakeRef} className="t-input flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 pb-4">
        {kinds.length > 1 ? (
          <SegmentedGlass<Kind>
            aria-label={t("crbs.book.kind")}
            value={kind}
            onValueChange={(v) => {
              setKind(v);
              setError(null);
            }}
            options={[
              { value: "single", label: t("crbs.book.single"), icon: <CalendarCheck aria-hidden /> },
              { value: "recurring", label: t("crbs.book.recurring"), icon: <Repeat aria-hidden /> },
            ]}
          />
        ) : null}
        <Field label={t("crbs.book.notes")} htmlFor="book-notes" hint={t("crbs.book.notesHint", { n: 255 - notes.length })}>
          <Textarea id="book-notes" maxLength={255} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder={t("crbs.book.notesPlaceholder")} />
        </Field>
        {canDept ? (
          <Field label={t("crbs.book.department")} htmlFor="book-dept">
            <SelectField id="book-dept" value={dept} onChange={(e) => setDept(e.target.value)}>
              <option value="">{t("crbs.book.departmentMine")}</option>
              <option value="none">{t("crbs.book.departmentNone")}</option>
              {(departments.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </SelectField>
          </Field>
        ) : null}
        {canUser ? (
          <Field label={t("crbs.book.user")} htmlFor="book-user" hint={t("crbs.book.userHint")}>
            <SelectField id="book-user" value={user} onChange={(e) => setUser(e.target.value)}>
              <option value="">{t("crbs.book.userMe")}</option>
              <option value="none">{t("crbs.book.userNone")}</option>
              {(users.data?.items ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.displayname || u.username || u.email}
                </option>
              ))}
            </SelectField>
          </Field>
        ) : null}
        {kind === "recurring" ? (
          <fieldset className="flex flex-col gap-3">
            <legend className="mb-2 type-headline text-label-1">{t("crbs.recur.range")}</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("crbs.recur.start")} htmlFor="recur-start">
                <SelectField id="recur-start" value={startMode} onChange={(e) => { setStartMode(e.target.value as StartMode); dispatch({ type: "reset" }); }}>
                  <option value="date">{t("crbs.recur.startThis", { date: fmt.short(slot.date) })}</option>
                  <option value="session">{t("crbs.recur.startSession")}</option>
                  <option value="custom">{t("crbs.recur.custom")}</option>
                </SelectField>
                {startMode === "custom" ? <Input type="date" aria-label={t("crbs.recur.startDate")} min={grid.term.start} max={grid.term.end} value={startDate} onChange={(e) => { setStartDate(e.target.value); dispatch({ type: "reset" }); }} /> : null}
              </Field>
              <Field label={t("crbs.recur.end")} htmlFor="recur-end">
                <SelectField id="recur-end" value={endMode} onChange={(e) => { setEndMode(e.target.value as EndMode); dispatch({ type: "reset" }); }}>
                  <option value="session">{t("crbs.recur.endSession", { date: fmt.short(grid.term.end) })}</option>
                  <option value="custom">{t("crbs.recur.custom")}</option>
                </SelectField>
                {endMode === "custom" ? <Input type="date" aria-label={t("crbs.recur.endDate")} min={grid.term.start} max={grid.term.end} value={endDate} onChange={(e) => { setEndDate(e.target.value); dispatch({ type: "reset" }); }} /> : null}
              </Field>
            </div>
            <Button variant="outline" onClick={runPreview} disabled={previewM.isPending} className="self-start" data-testid="recur-preview-btn">
              {previewM.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {preview.plan ? t("crbs.recur.refresh") : t("crbs.recur.preview")}
            </Button>
            {preview.plan ? <RecurringPreviewTable summary={summary} dispatch={dispatch} fmt={fmt} /> : null}
          </fieldset>
        ) : null}
        {error ? (
          <Alert tone="error" testId="book-error">
            {error}
          </Alert>
        ) : null}
      </div>
      <SheetFooter className="hairline-t flex-row justify-end gap-2 px-5 py-3">
        <Button variant="ghost" onClick={onDone}>
          {t("crbs.common.cancel")}
        </Button>
        <Button onClick={submit} disabled={busy || (kind === "recurring" && (!preview.plan || summary.willCreate === 0))} data-testid="book-submit">
          {busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {kind === "single" ? t("crbs.book.submit") : t("crbs.recur.submit", { n: summary.willCreate })}
        </Button>
      </SheetFooter>
    </>
  );
}
