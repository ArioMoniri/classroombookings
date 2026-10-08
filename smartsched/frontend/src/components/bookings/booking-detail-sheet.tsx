"use client";
/**
 * Booking details (CRBS `Bookings::view`, `UpdateAgent`, `cancel_*`): room, period, user and notes as far
 * as the viewer may see them, the series, and the edit / cancel actions the backend allows. Edit fields
 * follow `edit_features[scope]`; future/all scopes only change notes, department and user (CRBS rule).
 */
import { CalendarClock, Loader2, Pencil, Repeat, Trash2, User } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input, useShake } from "@/components/ui/input";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import {
  BOOKING_KEYS,
  crbs,
  crbsError,
  useBooking,
  useBookingGrid,
  useCrbsMe,
  useCrbsMutation,
  useDepartments,
  useSeries,
  useUserSearch,
  type BookingDetail,
  type Scope,
} from "@/lib/api/crbs";
import { useQuery } from "@tanstack/react-query";
import { hasPermission } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import { Alert, ConfirmDialog, Field, Loading, SelectField } from "@/components/admin/kit";
import { bookingErrorMessage } from "./booking-errors";
import type { DateFormatter } from "./date-format";
import { useIsPhone } from "./use-is-phone";

export function BookingDetailSheet({ bookingId, onOpenChange, fmt }: { bookingId: number | null; onOpenChange: (open: boolean) => void; fmt: DateFormatter }) {
  const phone = useIsPhone();
  return (
    <Sheet open={bookingId !== null} onOpenChange={onOpenChange}>
      <SheetContent side={phone ? "bottom" : "right"} className="gap-0 sm:max-w-lg data-[side=right]:sm:max-w-lg" data-testid="booking-sheet">
        {bookingId !== null ? <Detail key={bookingId} id={bookingId} fmt={fmt} onClose={() => onOpenChange(false)} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function Detail({ id, fmt, onClose }: { id: number; fmt: DateFormatter; onClose: () => void }) {
  const { t } = useI18n();
  const q = useBooking(id);
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [cancelOpen, setCancelOpen] = useState(false);
  const [showSeries, setShowSeries] = useState(false);
  const b = q.data;
  const series = useSeries(b?.series_id ? id : null, showSeries);

  if (q.isLoading) return <Loading className="px-5" />;
  if (!b) {
    return (
      <div className="p-5">
        <SheetTitle className="type-title-3">{t("crbs.detail.title")}</SheetTitle>
        <Alert tone="error" className="mt-3">
          {bookingErrorMessage(crbsError(q.error), t)}
        </Alert>
      </div>
    );
  }
  const cancelled = b.status !== "BOOKED";
  const who = b.is_owner ? t("crbs.slot.mine") : b.user_name || (b.user_hidden ? t("crbs.detail.userHidden") : t("crbs.detail.noUser"));

  return (
    <>
      <SheetHeader className="px-5 pt-5 pb-3">
        <SheetTitle className="type-title-3">
          {b.room_name} · {b.period_name}
        </SheetTitle>
        <SheetDescription className="type-callout text-label-2">
          {fmt.long(b.date)}
          {b.time_start ? ` · ${fmt.time(b.time_start)}–${fmt.time(b.time_end ?? "")}` : ""}
        </SheetDescription>
      </SheetHeader>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 pb-4">
        {cancelled ? (
          <Alert tone="warning" title={t("crbs.detail.cancelled")}>
            {b.cancel_reason ? t("crbs.detail.reason", { reason: b.cancel_reason }) : null}
          </Alert>
        ) : null}
        {mode === "view" ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 type-callout">
            <dt className="text-label-3">{t("crbs.detail.type")}</dt>
            <dd className="flex items-center gap-1.5 text-label-1">
              {b.type === "recurring" ? <Repeat className="size-3.5" aria-hidden /> : <CalendarClock className="size-3.5" aria-hidden />}
              {b.type === "recurring" ? t("crbs.legend.recurring") : t("crbs.legend.single")}
            </dd>
            <dt className="text-label-3">{t("crbs.detail.user")}</dt>
            <dd className="flex items-center gap-1.5 text-label-1">
              <User className="size-3.5" aria-hidden />
              {who}
            </dd>
            {b.department_name ? (
              <>
                <dt className="text-label-3">{t("crbs.book.department")}</dt>
                <dd className="text-label-1">{b.department_name}</dd>
              </>
            ) : null}
            <dt className="text-label-3">{t("crbs.book.notes")}</dt>
            <dd className="whitespace-pre-wrap text-label-1">{b.notes || (b.notes_hidden ? t("crbs.detail.notesHidden") : "—")}</dd>
            {b.room ? (
              <>
                <dt className="text-label-3">{t("crbs.detail.room")}</dt>
                <dd className="text-label-1">
                  {[b.room.group, b.room.location, b.room.capacity ? t("crbs.grid.seats", { n: b.room.capacity }) : null, b.room.owner ? t("crbs.detail.owner", { name: b.room.owner }) : null].filter(Boolean).join(" · ")}
                </dd>
                {b.room.fields
                  .filter((f) => f.value !== null && f.value !== "" && f.value !== false)
                  .map((f) => (
                    <div key={f.field_id} className="contents">
                      <dt className="text-label-3">{f.name}</dt>
                      <dd className="text-label-1">{f.value === true ? t("crbs.common.yes") : String(f.value)}</dd>
                    </div>
                  ))}
              </>
            ) : null}
          </dl>
        ) : (
          <EditForm booking={b} fmt={fmt} onDone={() => setMode("view")} />
        )}
        {mode === "view" ? (
          <Link
            href={`/bookings?display=day&date=${b.date}${b.room?.room_group_id ? `&group=${b.room.room_group_id}` : ""}&highlight=${b.id}`}
            className="self-start type-callout font-medium text-tint-text underline-offset-4 hover:underline"
            onClick={onClose}
          >
            {t("crbs.detail.showInGrid")}
          </Link>
        ) : null}
        {b.series_id && mode === "view" ? (
          <section aria-label={t("crbs.detail.series")}>
            <Button variant="ghost" size="sm" onClick={() => setShowSeries((v) => !v)} aria-expanded={showSeries}>
              <Repeat aria-hidden />
              {showSeries ? t("crbs.detail.hideSeries") : t("crbs.detail.showSeries")}
            </Button>
            {showSeries ? (
              series.isLoading ? (
                <Loading />
              ) : (
                <ol className="mt-2 flex flex-col rounded-xl bg-(--mat-thick-solid) shadow-[0_0_0_1px_var(--hairline)]">
                  {(series.data ?? []).map((x) => (
                    <li key={x.id} className="flex items-center justify-between px-3 py-1.5 type-callout shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
                      <span className={x.status !== "BOOKED" ? "text-label-3 line-through" : x.id === b.id ? "font-semibold text-label-1" : "text-label-1"}>{fmt.weekday(x.date)}</span>
                      <span className="type-footnote text-label-3">{x.status === "BOOKED" ? t("crbs.status.booked") : t("crbs.status.cancelled")}</span>
                    </li>
                  ))}
                </ol>
              )
            ) : null}
          </section>
        ) : null}
      </div>
      {mode === "view" && !cancelled && (b.can_edit || b.can_cancel) ? (
        <SheetFooter className="hairline-t flex-row justify-end gap-2 px-5 py-3">
          {b.can_cancel ? (
            <Button variant="ghost" className="text-status-infeasible-fg" onClick={() => setCancelOpen(true)} data-testid="booking-cancel">
              <Trash2 aria-hidden />
              {t("crbs.detail.cancel")}
            </Button>
          ) : null}
          {b.can_edit ? (
            <Button variant="outline" onClick={() => setMode("edit")} data-testid="booking-edit">
              <Pencil aria-hidden />
              {t("crbs.detail.edit")}
            </Button>
          ) : null}
        </SheetFooter>
      ) : null}
      <CancelDialog booking={b} open={cancelOpen} onOpenChange={setCancelOpen} onCancelled={onClose} fmt={fmt} />
    </>
  );
}

function ScopePicker({ value, onChange, booking }: { value: Scope; onChange: (s: Scope) => void; booking: BookingDetail }) {
  const { t } = useI18n();
  if (!booking.series_id) return null;
  return (
    <Field label={t("crbs.scope.label")}>
      <SegmentedGlass<Scope>
        aria-label={t("crbs.scope.label")}
        value={value}
        onValueChange={onChange}
        fill
        size="sm"
        options={[
          { value: "one", label: t("crbs.scope.one") },
          { value: "future", label: t("crbs.scope.future") },
          { value: "all", label: t("crbs.scope.all") },
        ]}
      />
    </Field>
  );
}

function EditForm({ booking: b, fmt, onDone }: { booking: BookingDetail; fmt: DateFormatter; onDone: () => void }) {
  const { t } = useI18n();
  const me = useCrbsMe();
  const [scope, setScope] = useState<Scope>("one");
  const f = b.edit_features[scope];
  const [date, setDate] = useState(b.date);
  const [periodId, setPeriodId] = useState(String(b.period_id));
  const [roomId, setRoomId] = useState(String(b.room_id));
  const [notes, setNotes] = useState(b.notes ?? "");
  const [dept, setDept] = useState(b.department_id ? String(b.department_id) : "none");
  const [user, setUser] = useState(b.user_id ? String(b.user_id) : "none");
  const [error, setError] = useState<string | null>(null);
  const { ref: shakeRef, shake } = useShake<HTMLDivElement>();
  const canPickUser = f.edit_user && hasPermission(me.data?.permissions, "setup.users");
  const departments = useDepartments(f.department);
  const users = useUserSearch({ limit: 500, enabled: true, sort: "displayname" }, canPickUser);
  const rooms = useQuery({ queryKey: ["crbs", "booking-rooms"], queryFn: () => crbs.bookings.rooms(), enabled: f.room, retry: false });
  const periodsGrid = useBookingGrid({ display: "room", date, room_id: Number(roomId) }, f.period);
  const periods = periodsGrid.data?.periods ?? [];

  const body = () => {
    const out: Parameters<typeof crbs.bookings.update>[2] = {};
    if (f.date && date !== b.date) out.date = date;
    if (f.period && Number(periodId) !== b.period_id) out.period_id = Number(periodId);
    if (f.room && Number(roomId) !== b.room_id) out.room_id = Number(roomId);
    if (f.edit_notes && notes !== (b.notes ?? "")) out.notes = notes.trim() || null;
    if (f.department && (dept === "none" ? null : Number(dept)) !== (b.department_id ?? null)) out.department_id = dept === "none" ? null : Number(dept);
    if (canPickUser && (user === "none" ? null : Number(user)) !== (b.user_id ?? null)) out.user_id = user === "none" ? null : Number(user);
    return out;
  };
  const save = useCrbsMutation(() => crbs.bookings.update(b.id, scope, body()), BOOKING_KEYS);

  const submit = () => {
    setError(null);
    const changes = body();
    if (!Object.keys(changes).length) {
      onDone();
      return;
    }
    save.mutate(undefined, {
      onSuccess: (rows) => {
        toast.success(t("crbs.detail.saved", { n: rows.length }));
        onDone();
      },
      onError: (e) => {
        setError(bookingErrorMessage(crbsError(e), t, { roomName: (id) => rooms.data?.find((r) => r.id === id)?.name ?? (id === b.room_id ? b.room_name : undefined), formatDate: fmt.short }));
        shake();
      },
    });
  };

  return (
    <div ref={shakeRef} className="t-input flex flex-col gap-3" data-testid="booking-edit-form">
      <ScopePicker value={scope} onChange={setScope} booking={b} />
      {f.date ? (
        <Field label={t("crbs.edit.date")} htmlFor="edit-date">
          <Input id="edit-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
      ) : null}
      {f.period ? (
        <Field label={t("crbs.edit.period")} htmlFor="edit-period">
          <SelectField id="edit-period" value={periodId} onChange={(e) => setPeriodId(e.target.value)}>
            {periods.length === 0 ? <option value={b.period_id}>{b.period_name}</option> : null}
            {periods.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {fmt.time(p.time_start)}–{fmt.time(p.time_end)}
              </option>
            ))}
          </SelectField>
        </Field>
      ) : null}
      {f.room ? (
        <Field label={t("crbs.edit.room")} htmlFor="edit-room">
          <SelectField id="edit-room" value={roomId} onChange={(e) => setRoomId(e.target.value)}>
            {!rooms.data ? <option value={b.room_id}>{b.room_name}</option> : null}
            {(rooms.data ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </SelectField>
        </Field>
      ) : null}
      {f.edit_notes ? (
        <Field label={t("crbs.book.notes")} htmlFor="edit-notes">
          <Textarea id="edit-notes" maxLength={255} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      ) : null}
      {f.department ? (
        <Field label={t("crbs.book.department")} htmlFor="edit-dept">
          <SelectField id="edit-dept" value={dept} onChange={(e) => setDept(e.target.value)}>
            <option value="none">{t("crbs.book.departmentNone")}</option>
            {(departments.data ?? []).map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </SelectField>
        </Field>
      ) : null}
      {canPickUser ? (
        <Field label={t("crbs.book.user")} htmlFor="edit-user">
          <SelectField id="edit-user" value={user} onChange={(e) => setUser(e.target.value)}>
            <option value="none">{t("crbs.book.userNone")}</option>
            {(users.data?.items ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.displayname || u.username || u.email}
              </option>
            ))}
          </SelectField>
        </Field>
      ) : null}
      {scope !== "one" ? <p className="type-footnote text-label-3">{t("crbs.edit.scopeHint")}</p> : null}
      {error ? (
        <Alert tone="error" testId="edit-error">
          {error}
        </Alert>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onDone}>
          {t("crbs.common.cancel")}
        </Button>
        <Button onClick={submit} disabled={save.isPending} data-testid="edit-save">
          {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {t("crbs.common.save")}
        </Button>
      </div>
    </div>
  );
}

function CancelDialog({ booking: b, open, onOpenChange, onCancelled, fmt }: { booking: BookingDetail; open: boolean; onOpenChange: (o: boolean) => void; onCancelled: () => void; fmt: DateFormatter }) {
  const { t } = useI18n();
  const [scope, setScope] = useState<Scope>("one");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const cancel = useCrbsMutation(() => crbs.bookings.cancel(b.id, scope, reason.trim() || null), BOOKING_KEYS);
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("crbs.cancel.title")}
      description={t("crbs.cancel.body", { room: b.room_name, date: fmt.weekday(b.date), period: b.period_name ?? "" })}
      confirmLabel={t("crbs.cancel.confirm")}
      destructive
      busy={cancel.isPending}
      onConfirm={() => {
        setError(null);
        cancel.mutate(undefined, {
          onSuccess: (res) => {
            toast.success(t("crbs.cancel.done", { n: res.cancelled.length }));
            onOpenChange(false);
            onCancelled();
          },
          onError: (e) => setError(bookingErrorMessage(crbsError(e), t)),
        });
      }}
    >
      <div className="flex flex-col gap-3">
        <ScopePicker value={scope} onChange={setScope} booking={b} />
        <Field label={t("crbs.cancel.reason")} htmlFor="cancel-reason" hint={t("crbs.cancel.reasonHint")}>
          <Textarea id="cancel-reason" maxLength={1000} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        {error ? <Alert tone="error">{error}</Alert> : null}
      </div>
    </ConfirmDialog>
  );
}
