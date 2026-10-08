"use client";
/**
 * "Book a slot" sheet (CRBS `SingleAgent`): single or recurring (tabs by permission for this room), the
 * period (CRBS single_form: change it in the form), notes, department and user (only with
 * `set_department` / `set_user`), and for recurring the start/end choice plus the preview with book / skip /
 * replace per date.
 *
 * Reservation panel: the sheet can hold a span of consecutive free periods (drag / Shift-click in the grid,
 * or the period chips here). One period books as before; a span books every period in one transaction
 * through the multi-booking selection (all or nothing), recurring spans become one weekly series per period.
 */
import { CalendarCheck, DoorOpen, Loader2, Repeat } from "lucide-react";
import { useMemo, useReducer, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input, useShake } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { Textarea } from "@/components/ui/textarea";
import { BOOKING_KEYS, crbs, crbsError, useBookingDates, useBookingUsers, useCrbsMe, useCrbsMutation, useDepartments, type Grid, type GridSlot, type MultiSlotChoice, type RecurringIn } from "@/lib/api/crbs";
import { bookingCapabilities } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import { Alert, Field, SelectField } from "@/components/admin/kit";
import { bookingErrorMessage } from "./booking-errors";
import type { DateFormatter } from "./date-format";
import { isSelectable, slotKey } from "./grid-model";
import { holidaysOnWeekday, initialPreview, instancesPayload, previewReducer, summarise } from "./recurring-preview";
import { RecurringPreviewTable } from "./recurring-preview-table";
import { freeRun, roomDay, toggleRange } from "./reserve-model";
import { useIsPhone } from "./use-is-phone";

type Kind = "single" | "recurring";
type StartMode = "date" | "session" | "custom";
type EndMode = "session" | "custom";

export interface BookTarget {
  slot: GridSlot;
  grid: Grid;
  /** consecutive reservable periods of the same room and date (includes `slot`) */
  span?: GridSlot[];
}

export function BookSheet({ target, onOpenChange, fmt, onOtherRooms }: { target: BookTarget | null; onOpenChange: (open: boolean) => void; fmt: DateFormatter; onOtherRooms?: (target: BookTarget) => void }) {
  const phone = useIsPhone();
  const key = target ? `${slotKey(target.slot)}|${(target.span ?? []).map(slotKey).join(",")}` : "";
  return (
    <Sheet open={!!target} onOpenChange={onOpenChange}>
      <SheetContent side={phone ? "bottom" : "right"} className="gap-0 sm:max-w-lg data-[side=right]:sm:max-w-lg" data-testid="book-sheet">
        {target ? <BookForm key={key} target={target} fmt={fmt} onDone={() => onOpenChange(false)} onOtherRooms={onOtherRooms} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function initialRange(run: GridSlot[], target: BookTarget): { lo: number; hi: number } {
  const idx = (s: GridSlot) => run.findIndex((x) => x.period_id === s.period_id);
  const span = target.span && target.span.length > 1 ? target.span : [target.slot];
  const lo = Math.max(0, idx(span[0]!));
  const hi = Math.max(lo, idx(span[span.length - 1]!));
  return { lo, hi };
}

function BookForm({ target, fmt, onDone, onOtherRooms }: { target: BookTarget; fmt: DateFormatter; onDone: () => void; onOtherRooms?: (target: BookTarget) => void }) {
  const { t } = useI18n();
  const { grid } = target;
  const me = useCrbsMe();
  const caps = bookingCapabilities(me.data?.permissions);
  const room = grid.rooms.find((r) => r.id === target.slot.room_id);

  // the anchor period can be changed in the form (CRBS single_form.php:24-38); the chips extend it
  const [anchor, setAnchor] = useState<GridSlot>(target.span?.[0] ?? target.slot);
  const run = useMemo(() => freeRun(grid, anchor), [grid, anchor]);
  const [range, setRange] = useState(() => initialRange(run, target));
  const chosen = run.slice(range.lo, range.hi + 1);
  const first = chosen[0] ?? anchor;
  const last = chosen[chosen.length - 1] ?? anchor;
  const isSpan = chosen.length > 1;
  const periods = useMemo(() => new Map(grid.periods.map((p) => [p.id, p])), [grid.periods]);
  const p0 = periods.get(first.period_id);
  const p1 = periods.get(last.period_id);
  const dayChoices = useMemo(() => roomDay(grid, anchor.room_id, anchor.date).filter(isSelectable), [grid, anchor.room_id, anchor.date]);

  const kinds: Kind[] = [...(chosen.every((s) => s.allow_single) ? (["single"] as const) : []), ...(chosen.every((s) => s.allow_recur) ? (["recurring"] as const) : [])];
  const [kindState, setKind] = useState<Kind>(kinds[0] ?? "single");
  const kind = kinds.includes(kindState) ? kindState : (kinds[0] ?? "single");
  const [notes, setNotes] = useState("");
  const canDept = kind === "single" ? caps.setDepartment.single : caps.setDepartment.recurring;
  const canUser = kind === "single" ? caps.setUser.single : caps.setUser.recurring;
  const [dept, setDept] = useState<string>("");
  const [user, setUser] = useState<string>("");
  const departments = useDepartments(canDept);
  const users = useBookingUsers(canUser);
  const [error, setError] = useState<string | null>(null);
  const { ref: shakeRef, shake } = useShake<HTMLDivElement>();

  const [startMode, setStartMode] = useState<StartMode>("date");
  const [endMode, setEndMode] = useState<EndMode>("session");
  const [startDate, setStartDate] = useState(anchor.date);
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

  const single = useCrbsMutation(() => crbs.bookings.create({ room_id: first.room_id, date: first.date, period_id: first.period_id, term_id: grid.term.id, ...extras() }), BOOKING_KEYS);

  const recurBody = (): RecurringIn => ({
    room_id: first.room_id,
    period_id: first.period_id,
    date: first.date,
    term_id: grid.term.id,
    start: startMode === "session" ? "session" : startMode === "custom" ? startDate : first.date,
    end: endMode === "session" ? "session" : endDate,
  });
  const previewM = useCrbsMutation(() => crbs.bookings.previewRecurring(recurBody()));
  const recur = useCrbsMutation(() => crbs.bookings.createRecurring({ ...recurBody(), ...extras(), instances: instancesPayload(preview) }), BOOKING_KEYS);

  // a span: one server-side selection, then every period in one transaction (or one series each)
  const spanM = useCrbsMutation(async () => {
    const sel = await crbs.bookings.select(
      chosen.map((s) => ({ date: s.date, period_id: s.period_id, room_id: s.room_id })),
      grid.term.id,
    );
    const x = extras();
    const choices: MultiSlotChoice[] = sel.slots.map((s) => ({
      mbs_id: s.mbs_id,
      ...x,
      ...(kind === "recurring"
        ? { recurring_start: startMode === "custom" ? startDate : startMode === "date" ? first.date : null, recurring_end: endMode === "custom" ? endDate : null }
        : {}),
    }));
    try {
      return await crbs.bookings.multiCreate(sel.id, kind, choices);
    } catch (e) {
      void crbs.bookings.dropSelection(sel.id).catch(() => undefined);
      throw e;
    }
  }, BOOKING_KEYS);

  const runPreview = () => {
    setError(null);
    previewM.mutate(undefined, {
      onSuccess: (plan) => {
        const a = plan.instances[0]?.date ?? first.date;
        const b = plan.instances[plan.instances.length - 1]?.date ?? grid.term.end;
        dispatch({ type: "load", plan, holidays: holidaysOnWeekday(termDates.data?.dates ?? [], plan.weekday, a, b) });
      },
      onError: explain,
    });
  };

  const submit = () => {
    setError(null);
    if (isSpan) {
      spanM.mutate(undefined, {
        onSuccess: () => {
          toast.success(t("reserve.book.doneN", { room: room?.name ?? "", date: fmt.weekday(first.date), n: chosen.length }));
          onDone();
        },
        onError: explain,
      });
      return;
    }
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

  const pickPeriod = (periodId: number) => {
    const next = dayChoices.find((s) => s.period_id === periodId);
    if (!next) return;
    const nextRun = freeRun(grid, next);
    const i = nextRun.findIndex((s) => s.period_id === next.period_id);
    setAnchor(next);
    setRange({ lo: i, hi: i });
    dispatch({ type: "reset" });
    setError(null);
  };

  const busy = single.isPending || recur.isPending || spanM.isPending;
  const periodName = isSpan ? `${p0?.name ?? ""}–${p1?.name ?? ""}` : (p0?.name ?? "");
  const title = `${room?.name ?? ""} · ${periodName}`;

  return (
    <>
      <SheetHeader className="px-5 pt-5 pb-3">
        <SheetTitle className="type-title-3">{title}</SheetTitle>
        <SheetDescription className="type-callout text-label-2">
          {fmt.long(first.date)}
          {p0 && p1 ? ` · ${fmt.time(p0.time_start)}–${fmt.time(p1.time_end)}` : ""}
          {room?.capacity ? ` · ${t("crbs.grid.seats", { n: room.capacity })}` : ""}
        </SheetDescription>
      </SheetHeader>
      <div ref={shakeRef} className="t-input flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 pb-4">
        {dayChoices.length > 1 ? (
          <Field label={t("reserve.book.period")} htmlFor="book-period">
            <SelectField id="book-period" value={String(first.period_id)} onChange={(e) => pickPeriod(Number(e.target.value))} data-testid="book-period">
              {dayChoices.map((s) => {
                const p = periods.get(s.period_id);
                return (
                  <option key={s.period_id} value={s.period_id}>
                    {p ? `${p.name} (${fmt.time(p.time_start)}–${fmt.time(p.time_end)})` : s.period_id}
                  </option>
                );
              })}
            </SelectField>
          </Field>
        ) : null}
        {run.length > 1 ? (
          <fieldset className="flex flex-col gap-2" data-testid="book-periods">
            <legend className="mb-1 type-subheadline font-medium text-label-1">{t("reserve.book.periods")}</legend>
            <div className="flex flex-wrap gap-1.5">
              {run.map((s, i) => {
                const p = periods.get(s.period_id);
                return (
                  <Chip key={s.period_id} size="md" selected={i >= range.lo && i <= range.hi} onSelectedChange={() => setRange((r) => toggleRange(r, i))} className="min-h-11 sm:min-h-0" data-period-id={s.period_id}>
                    {p?.name}
                    <span className="font-normal text-label-3 tabular-nums">{p ? fmt.time(p.time_start) : ""}</span>
                  </Chip>
                );
              })}
            </div>
            <p className="type-footnote text-label-3">{t("reserve.book.periodsHint")}</p>
          </fieldset>
        ) : null}
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
            <SelectField id="book-user" value={user} onChange={(e) => setUser(e.target.value)} data-testid="book-user">
              <option value="">{t("crbs.book.userMe")}</option>
              <option value="none">{t("crbs.book.userNone")}</option>
              {(users.data ?? []).map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
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
                <SelectField
                  id="recur-start"
                  value={startMode}
                  onChange={(e) => {
                    setStartMode(e.target.value as StartMode);
                    dispatch({ type: "reset" });
                  }}
                >
                  <option value="date">{t("crbs.recur.startThis", { date: fmt.short(first.date) })}</option>
                  <option value="session">{t("crbs.recur.startSession")}</option>
                  <option value="custom">{t("crbs.recur.custom")}</option>
                </SelectField>
                {startMode === "custom" ? (
                  <Input
                    type="date"
                    aria-label={t("crbs.recur.startDate")}
                    min={grid.term.start}
                    max={grid.term.end}
                    value={startDate}
                    onChange={(e) => {
                      setStartDate(e.target.value);
                      dispatch({ type: "reset" });
                    }}
                  />
                ) : null}
              </Field>
              <Field label={t("crbs.recur.end")} htmlFor="recur-end">
                <SelectField
                  id="recur-end"
                  value={endMode}
                  onChange={(e) => {
                    setEndMode(e.target.value as EndMode);
                    dispatch({ type: "reset" });
                  }}
                >
                  <option value="session">{t("crbs.recur.endSession", { date: fmt.short(grid.term.end) })}</option>
                  <option value="custom">{t("crbs.recur.custom")}</option>
                </SelectField>
                {endMode === "custom" ? (
                  <Input
                    type="date"
                    aria-label={t("crbs.recur.endDate")}
                    min={grid.term.start}
                    max={grid.term.end}
                    value={endDate}
                    onChange={(e) => {
                      setEndDate(e.target.value);
                      dispatch({ type: "reset" });
                    }}
                  />
                ) : null}
              </Field>
            </div>
            {isSpan ? (
              <p className="type-footnote text-label-2">{t("reserve.book.spanRecurring", { date: fmt.short(endMode === "custom" ? endDate : grid.term.end) })}</p>
            ) : (
              <>
                <Button variant="outline" onClick={runPreview} disabled={previewM.isPending} className="self-start" data-testid="recur-preview-btn">
                  {previewM.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                  {preview.plan ? t("crbs.recur.refresh") : t("crbs.recur.preview")}
                </Button>
                {preview.plan ? <RecurringPreviewTable summary={summary} dispatch={dispatch} fmt={fmt} /> : null}
              </>
            )}
          </fieldset>
        ) : null}
        {error ? (
          <Alert tone="error" testId="book-error">
            {error}
          </Alert>
        ) : null}
      </div>
      <SheetFooter className="hairline-t flex-row flex-wrap items-center justify-end gap-2 px-5 py-3">
        {onOtherRooms ? (
          <Button variant="ghost" className="mr-auto" onClick={() => onOtherRooms({ slot: first, grid, span: chosen })} data-testid="book-other-rooms">
            <DoorOpen aria-hidden />
            {t("reserve.book.otherRooms")}
          </Button>
        ) : null}
        <Button variant="ghost" onClick={onDone}>
          {t("crbs.common.cancel")}
        </Button>
        <Button onClick={submit} disabled={busy || !kinds.length || (kind === "recurring" && !isSpan && (!preview.plan || summary.willCreate === 0))} data-testid="book-submit">
          {busy ? <Loader2 className="animate-spin" aria-hidden /> : null}
          {isSpan ? t("reserve.book.submitN", { n: chosen.length }) : kind === "single" ? t("crbs.book.submit") : t("crbs.recur.submit", { n: summary.willCreate })}
        </Button>
      </SheetFooter>
    </>
  );
}
