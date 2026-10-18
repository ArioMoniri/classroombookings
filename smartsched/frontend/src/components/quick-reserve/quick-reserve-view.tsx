"use client";
/**
 * /reserve — Hızlı rezervasyon (docs/design/v3/quick-reserve.md). One screen, three steps, all visible:
 * 1 Ne zaman? (day chips, a slot in the administrator's unit, a length), 2 Nerede? (how many people, optional
 * features, the short ranked list of free rooms from POST /rooms/find), 3 Onayla (a sticky summary with one verb-honest
 * primary: "Rezerve et" or, under an approval rule, "Talep et"). Today's next free slot is preselected, so the common
 * case is two taps (room, Rezerve et) and any slot of the day is three. Success ends on a receipt with "Geri al"
 * (the real P7 undo, POST /audit/{id}/undo, from the create response's `audit_event_id`) or "Talebi geri çek".
 *
 * Reuses the existing APIs only: /bookings/context, /bookings/dates, /bookings/grid, /rooms/find, /rooms/facets,
 * POST /bookings (+ /bookings/multi for a span), /audit/{id}/undo, /approvals/mine + withdraw, /bookings/mine.
 * Motion: none on chips and lists (frequent actions); the receipt replaces the card in place.
 */
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Check, Hourglass, Loader2, RotateCcw, Stamp, Undo2, Zap } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { Alert, PageTitle } from "@/components/admin/kit";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { formatPattern } from "@/components/bookings/date-format";
import { focusAfter } from "@/components/bookings/focus-after";
import { timetableMissing } from "@/components/bookings/grid-model";
import { useNow } from "@/components/bookings/room-info-sheet";
import { periodVisible, slotLabel, type SlotDisplay } from "@/components/bookings/slot-display";
import { useBookingFormat, useProfileLanguage } from "@/components/bookings/use-booking-format";
import { useSlotDisplay } from "@/components/bookings/use-slot-display";
import { BareButton } from "@/components/shell/bare-button";
import { Button } from "@/components/ui/button";
import { BusyButton } from "@/components/ui/busy-label";
import { Chip } from "@/components/ui/chip";
import { DateField } from "@/components/ui/date-field";
import { EmptyState } from "@/components/ui/empty-state";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { request } from "@/lib/api/client";
import { BOOKING_KEYS, crbs, crbsError, useBookingContext, useBookingDates, useBookingGrid, useCrbsMe, useMyBookings, type GridPeriod } from "@/lib/api/crbs";
import { useFacets, wave1, type FindRow } from "@/lib/api/wave1";
import { bookingCapabilities } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";
import { ChipRadioGroup } from "./chip-radio-group";
import { addDay, dayChips, nextWeekday, schoolWeekdays, defaultSlot, findQuery, lengthChoices, rankRooms, roomAction, slotOptions, spanFor, type SlotOption } from "./quick-reserve-model";

const PEOPLE = [0, 10, 20, 40, 80] as const;
const SHOW_FIRST = 8;
/** one receipt toast at a time; "Geri al" on the receipt dismisses it */
const TOAST_ID = "quick-reserve-receipt";

const Created = z.object({ id: z.number(), status: z.string(), room_name: z.string().nullish(), audit_event_id: z.number().nullish() }).passthrough();
type Created = z.infer<typeof Created>;

interface Receipt {
  room: FindRow;
  span: GridPeriod[];
  date: string;
  created: Created[];
  pending: boolean;
}

export function QuickReserveView() {
  const { t, locale } = useI18n();
  useProfileLanguage();
  const hydrated = useHydrated();
  const params = useSearchParams();
  const qc = useQueryClient();
  const fmt = useBookingFormat();
  const me = useCrbsMe();
  const caps = bookingCapabilities(me.data?.permissions);
  const ctx = useBookingContext();
  const { display: sd } = useSlotDisplay();
  const termId = ctx.data?.current_term_id ?? undefined;
  const dates = useBookingDates({ term_id: termId }, ctx.isSuccess && termId != null);
  const today = dates.data?.today;
  const now = useNow();

  // ---- step 1: when
  const [pickedDay, setPickedDay] = useState<string | null>(params.get("date"));
  // the schedule's school days (a weekday grid lists every period with its `days`): Saturday is not offered when no
  // period runs on it, even though the term calendar keeps it open
  const probe = useBookingGrid({ display: "day", date: today ? nextWeekday(today) : undefined, term_id: termId }, !!today && termId != null);
  const school = useMemo(() => (probe.data ? schoolWeekdays(probe.data.periods) : null), [probe.data]);
  const chips = useMemo(() => (today && probe.data ? dayChips(dates.data?.dates ?? [], today, 7, school) : []), [dates.data?.dates, today, school, probe.data]);
  const allRooms = !ctx.data?.display.use_room_groups || (ctx.data?.room_groups.length ?? 0) <= 1;
  // smart default (quick-reserve.md §3): today, or the next open day once today's last slot has started
  const firstOpen = chips.find((c) => !c.closed)?.date ?? null;
  const firstGrid = useBookingGrid({ display: "day", date: firstOpen ?? undefined, term_id: termId }, !!firstOpen && termId != null && !pickedDay);
  const firstDone = !!firstGrid.data && firstGrid.data.date === firstOpen && slotOptions(firstGrid.data, sd, now, allRooms).length === 0;
  const nextOpen = firstOpen ? (chips.find((c) => !c.closed && c.date > firstOpen)?.date ?? null) : null;
  const autoDay = firstDone && nextOpen ? nextOpen : firstOpen;
  const day = pickedDay ?? autoDay ?? today ?? null;
  const movedFrom = !pickedDay && firstDone && nextOpen ? firstOpen : null;
  const grid = useBookingGrid({ display: "day", date: day ?? undefined, term_id: termId }, !!day && termId != null);
  const g = grid.data && grid.data.date === day ? grid.data : undefined;
  const options = useMemo(() => (g ? slotOptions(g, sd, now, allRooms) : []), [g, sd, now, allRooms]);
  const visible = useMemo(() => (g ? g.periods.filter((p) => periodVisible(p, sd)) : []), [g, sd]);
  const [pickedSlot, setPickedSlot] = useState<string | null>(null);
  const [dateOpen, setDateOpen] = useState(false);
  const slot: SlotOption | null = options.find((o) => o.key === pickedSlot) ?? defaultSlot(options);
  const lengths = useMemo(() => (slot ? lengthChoices(visible, slot, sd) : []), [visible, slot, sd]);
  const [pickedLength, setPickedLength] = useState<number | null>(null);
  const length = pickedLength && lengths.includes(pickedLength) ? pickedLength : (lengths[0] ?? null);
  const span = useMemo(() => (slot && length ? spanFor(visible, slot, length, sd) : null), [visible, slot, length, sd]);

  // ---- step 2: where
  const [people, setPeople] = useState(0);
  const [features, setFeatures] = useState<number[]>([]);
  const facets = useFacets();
  const booleanFacets = useMemo(() => (facets.data ?? []).filter((f) => f.kind === "BOOLEAN").slice(0, 6), [facets.data]);
  const query = useMemo(() => (day && span?.length ? findQuery({ date: day, termId, span, headcount: people, features }) : null), [day, termId, span, people, features]);
  const find = useQuery({ queryKey: ["quick-reserve", "find", query], queryFn: () => wave1.find.search(query!), enabled: !!query, placeholderData: keepPreviousData, staleTime: 15_000, retry: false });
  const mine = useMyBookings({ from: today ? addDay(today, -60) : undefined, status: "ALL" });
  const recent = useMemo(() => new Set((mine.data ?? []).map((b) => b.room_id)), [mine.data]);
  const [taken, setTaken] = useState<Set<string>>(new Set());
  const takenKey = (roomId: number) => `${day}|${span?.map((p) => p.id).join(",")}|${roomId}`;
  const rooms = useMemo(() => rankRooms(find.data?.results ?? [], recent), [find.data, recent]);
  const [showAll, setShowAll] = useState(false);
  const [roomId, setRoomId] = useState<number | null>(null);
  const room = rooms.find((r) => r.room_id === roomId && !taken.has(takenKey(r.room_id))) ?? null;
  const stale = find.isPlaceholderData || find.isFetching;

  // ---- step 3: confirm
  const [note, setNote] = useState("");
  const [noteOpen, setNoteOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ kind: "conflict" | "other"; text: string } | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [undoing, setUndoing] = useState(false);
  const [live, setLive] = useState("");
  const primaryRef = useRef<HTMLButtonElement>(null);
  const receiptRef = useRef<HTMLHeadingElement>(null);
  const action = room ? roomAction(room) : "book";
  const request_ = action === "request";
  const quotaNone = ctx.data?.remaining_bookings === 0;

  // a new slot / filter keeps the chosen room only while it is in the list (`room` above; quick-reserve.md §5).
  // The count is announced when results arrive, not while loading; receipts and undo take the region over.
  const liveText = live || (find.data && !find.isFetching && query ? t("quickReserve.rooms.count", { n: rooms.length }) : "");

  const labelFormat = useMemo(() => ({ time: fmt.time, ordinal: (n: number) => t("slotDisplay.ordinal", { n }) }), [fmt, t]);
  const dayWord = useCallback((iso: string) => (iso === today ? t("quickReserve.day.today") : today && iso === addDay(today, 1) ? t("quickReserve.day.tomorrow") : formatPattern(iso, "EEE d MMM", locale)), [today, t, locale]);
  const spanText = useCallback(
    (ps: readonly GridPeriod[], display: SlotDisplay = sd) => {
      if (!ps.length) return "";
      if (ps.length === 1) return slotLabel(ps[0]!, display, labelFormat).inline;
      const a = slotLabel(ps[0]!, { ...display, label: "period" }, labelFormat).primary;
      const b = slotLabel(ps[ps.length - 1]!, { ...display, label: "period" }, labelFormat).primary;
      const range = `${fmt.time(ps[0]!.time_start)}–${fmt.time(ps[ps.length - 1]!.time_end)}`;
      return display.label === "time" ? range : `${a}–${b} · ${range}`;
    },
    [sd, labelFormat, fmt],
  );

  const resetAfterChange = () => {
    setError(null);
    setLive("");
    setShowAll(false);
  };

  const submit = async () => {
    if (!room || !day || !span || busy || quotaNone || action === "mine") return;
    setBusy(true);
    setError(null);
    const periodIds = room.period_ids.length ? room.period_ids : span.map((p) => p.id);
    const extras = { notes: note.trim() || null, ...(timetableMissing(g) ? { confirm_unpublished: true } : {}) };
    try {
      let created: Created[];
      if (periodIds.length === 1) {
        created = [await request("/bookings", { method: "POST", silent: true, schema: Created, body: { room_id: room.room_id, date: day, period_id: periodIds[0], term_id: termId ?? null, ...extras } })];
      } else {
        const sel = await crbs.bookings.select(periodIds.map((pid) => ({ date: day, period_id: pid, room_id: room.room_id })), termId);
        try {
          const out = await crbs.bookings.multiCreate(sel.id, "single", sel.slots.map((s) => ({ mbs_id: s.mbs_id, notes: extras.notes })), !!extras.confirm_unpublished);
          created = z.array(Created).parse(out.created ?? []);
        } catch (e) {
          void crbs.bookings.dropSelection(sel.id).catch(() => undefined);
          throw e;
        }
      }
      const pending = created.some((c) => c.status === "PENDING");
      const r: Receipt = { room, span, date: day, created, pending };
      setReceipt(r);
      setNote("");
      setNoteOpen(false);
      // HX12B-F04: the pressed "Rezerve et" unmounts; the receipt title takes focus at once and keeps it while the
      // booking lists refetch (focus fell to <body> at 1440 while the refresh re-rendered the columns)
      focusAfter(["[data-testid=qr-receipt-title]"], 0, 4000);
      setLive(t(pending ? "quickReserve.receipt.liveRequested" : "quickReserve.receipt.live", { room: room.name }));
      toast.success(t(pending ? "quickReserve.toast.requested" : "quickReserve.toast.booked", { room: room.name }), {
        id: TOAST_ID,
        duration: 10_000,
        // MOBILE M-02: the action is a 44 px target on touch
        classNames: { actionButton: "pointer-coarse:min-h-11 pointer-coarse:px-4" },
        action: { label: t(pending ? "quickReserve.receipt.withdraw" : "quickReserve.receipt.undo"), onClick: () => void undo(r) },
      });
      await Promise.all(BOOKING_KEYS.map((k) => qc.invalidateQueries({ queryKey: k })));
      void qc.invalidateQueries({ queryKey: ["quick-reserve"] });
    } catch (e) {
      const err = crbsError(e);
      const conflict = err.status === 409 && ["conflict", "slots_unavailable", "slot_taken", "booked"].includes(err.code ?? "");
      if (conflict) {
        setTaken((prev) => new Set(prev).add(takenKey(room.room_id)));
        setRoomId(null);
        void find.refetch();
      }
      const text = err.status === 0 ? t("quickReserve.error.network") : conflict ? t("quickReserve.conflict.body") : bookingErrorMessage(err, t, { formatDate: fmt.short, locale });
      setError({ kind: conflict ? "conflict" : "other", text });
      window.requestAnimationFrame(() => document.getElementById("qr-error")?.focus());
    } finally {
      setBusy(false);
    }
  };

  const undo = async (r: Receipt) => {
    setUndoing(true);
    toast.dismiss(TOAST_ID);
    try {
      if (r.pending) {
        const reqs = await wave1.approvals.mine();
        const ids = new Set(r.created.map((c) => c.id));
        const open = [...new Set(reqs.filter((q) => q.status === "PENDING" && q.bookings.some((b) => ids.has(b.id))).map((q) => q.id))];
        for (const id of open) await wave1.approvals.withdraw(id);
        toast.success(t("quickReserve.toast.withdrawn"));
      } else {
        const events = r.created.map((c) => c.audit_event_id);
        if (events.every((e): e is number => typeof e === "number")) {
          for (const e of events) await request(`/audit/${e}/undo`, { method: "POST", silent: true });
        } else {
          await crbs.bookings.cancelMany(r.created.map((c) => c.id), "undo");
        }
        toast.success(t("quickReserve.toast.undone"));
      }
      setReceipt(null);
      setRoomId(r.room.room_id);
      // R6 / HX12B-F04: the user sees what came back: the same room selected, focus on its row. Watched through the
      // list refetch (the row is replaced while it loads), with the list's tab stop as the fallback, never <body>
      focusAfter([`[data-room-row="${r.room.room_id}"]`, "[data-testid=qr-rooms] [role=radio][tabindex='0']"], 50, 5000);
      await Promise.all(BOOKING_KEYS.map((k) => qc.invalidateQueries({ queryKey: k })));
      await qc.invalidateQueries({ queryKey: ["quick-reserve"] });
    } catch (e) {
      toast.error(bookingErrorMessage(crbsError(e), t, { formatDate: fmt.short, locale }));
    } finally {
      setUndoing(false);
    }
  };

  const newBooking = () => {
    setReceipt(null);
    setRoomId(null);
    focusAfter(["[data-testid=qr-rooms] [role=radio][tabindex='0']", "[data-testid=qr-slots] [role=radio][tabindex='0']"], 50);
  };

  // Ctrl/⌘ + Enter submits from anywhere on the page (quick-reserve.md §11)
  const onPageKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && room && !receipt) {
      e.preventDefault();
      void submit();
    }
  };

  // T-R1-19: render cache-fed markup after hydration only (no #418 mismatch)
  if (!hydrated || me.isLoading) return <Skeleton className="h-[420px] w-full rounded-xl" data-testid="qr-hydrating" />;
  if (me.data && !caps.single) {
    return <EmptyState title={t("quickReserve.noPermission.title")} description={t("quickReserve.noPermission.body")} data-testid="qr-no-permission" />;
  }
  if (ctx.isError) return <Alert tone="error">{bookingErrorMessage(crbsError(ctx.error), t)}</Alert>;

  const shownRooms = showAll ? rooms : rooms.slice(0, SHOW_FIRST);
  const summary = room && day && span ? t("quickReserve.summary.line", { room: room.name, day: dayWord(day), slot: spanText(span) }) : t("quickReserve.summary.none");
  const blocks = sd.unit === "blocks";
  const step = (n: number, key: "when" | "where" | "confirm") => t("quickReserve.step.n", { n, title: t(`quickReserve.step.${key}`) });

  return (
    <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-5 pb-[calc(15rem+env(safe-area-inset-bottom))] lg:pb-10" onKeyDown={onPageKeyDown} data-testid="quick-reserve">
      <PageTitle title={t("quickReserve.title")} subtitle={<span className="max-sm:sr-only">{t("quickReserve.lead")}</span>} className="mb-0" />
      <p className="sr-only" role="status" aria-live="polite" data-testid="qr-live">
        {liveText}
      </p>
      {ctx.isSuccess && termId == null ? <Alert tone="warning">{t("quickReserve.noTerm")}</Alert> : null}
      {timetableMissing(g) ? <Alert tone="warning" testId="qr-unpublished">{t("quickReserve.unpublished")}</Alert> : null}

      <div className="grid min-w-0 gap-6 lg:grid-cols-[320px_minmax(0,1fr)_340px] lg:items-start">
        {/* 1 · Ne zaman? */}
        <section aria-labelledby="qr-when" data-tour="reserve-when" className="flex min-w-0 flex-col gap-3">
          <h2 id="qr-when" className="type-title-3 text-label-1">
            {step(1, "when")}
          </h2>
          {chips.length ? (
            <ChipRadioGroup<string>
              label={t("quickReserve.day.label")}
              testId="qr-days"
              value={day}
              onChange={(d) => {
                setPickedDay(d);
                setPickedSlot(null);
                resetAfterChange();
              }}
              items={chips.map((c) => {
                const word = c.kind === "today" ? t("quickReserve.day.today") : c.kind === "tomorrow" ? t("quickReserve.day.tomorrow") : formatPattern(c.date, "EEE d", locale);
                const reason = c.holiday ? t("quickReserve.day.holiday", { name: c.holiday }) : c.closed ? t("quickReserve.day.closed") : null;
                return { value: c.date, label: word, sub: c.kind === "day" ? undefined : formatPattern(c.date, "d MMM", locale), name: reason ? t("quickReserve.day.closedName", { day: `${word} ${formatPattern(c.date, "d MMMM", locale)}`, reason }) : `${word}, ${formatPattern(c.date, "d MMMM EEEE", locale)}`, disabled: c.closed, testId: `qr-day-${c.date}` };
              })}
            />
          ) : (
            <Skeleton className="h-11 w-full rounded-full" />
          )}
          {movedFrom && day ? (
            <p className="type-footnote text-label-2" data-testid="qr-moved">
              {t("quickReserve.day.movedToNext", { from: dayWord(movedFrom), to: dayWord(day) })}
            </p>
          ) : null}
          {today && dates.data && !dateOpen ? (
            <Button variant="ghost" size="sm" className="self-start" onClick={() => setDateOpen(true)} aria-expanded={false} data-testid="qr-date-open">
              <CalendarDays aria-hidden />
              {t("quickReserve.day.pick")}
            </Button>
          ) : null}
          {today && dates.data && dateOpen ? (
            <label className="flex flex-col gap-1">
              <span className="type-footnote font-medium text-label-2">{t("quickReserve.day.pickLabel")}</span>
              <DateField
                value={day ?? today}
                min={today}
                max={g?.term.end}
                onChange={(d) => {
                  if (!d) return;
                  setPickedDay(d);
                  setPickedSlot(null);
                  resetAfterChange();
                }}
                aria-label={t("quickReserve.day.pick")}
                data-testid="qr-date"
              />
            </label>
          ) : null}

          <h3 id="qr-slot-label" className="mt-1 type-headline text-label-1">
            {t("quickReserve.slot.label")}
          </h3>
          {grid.isLoading && !g ? (
            <Skeleton className="h-11 w-full rounded-full" />
          ) : options.length ? (
            <ChipRadioGroup<string>
              label={t("quickReserve.slot.label")}
              testId="qr-slots"
              value={slot?.key ?? null}
              onChange={(k) => {
                setPickedSlot(k);
                resetAfterChange();
              }}
              items={options.map((o) => {
                const p = g!.periods.find((x) => x.id === o.periodId)!;
                const text = slotLabel(p, sd, labelFormat);
                const label = blocks ? fmt.time(o.time) : text.primary;
                const sub = blocks ? text.primary : text.secondary ?? undefined;
                const name = blocks ? `${fmt.time(o.time)}, ${text.a11y}` : text.a11y;
                return { value: o.key, label, sub: o.full ? t("quickReserve.slot.full") : sub, name: o.full ? t("quickReserve.slot.fullName", { slot: name }) : name, disabled: o.full, testId: `qr-slot-${o.key}` };
              })}
            />
          ) : g ? (
            <p className="type-callout text-label-2" data-testid="qr-no-slots">
              {t("quickReserve.slot.none")}
            </p>
          ) : null}
          {slot && lengths.length > 1 ? (
            <div className="flex flex-col gap-1">
              <span id="qr-length" className="type-footnote font-medium text-label-2">
                {t("quickReserve.length.label")}
              </span>
              <SegmentedControl<string>
                aria-labelledby="qr-length"
                semantics="radiogroup"
                fill
                value={String(length)}
                onValueChange={(v) => {
                  setPickedLength(Number(v));
                  resetAfterChange();
                }}
                options={lengths.map((n) => ({ value: String(n), label: blocks ? t("quickReserve.length.minutes", { n: n * sd.block_minutes }) : t("quickReserve.length.periods", { n }), testId: `qr-length-${n}` }))}
                data-testid="qr-lengths"
              />
            </div>
          ) : null}
          {slot && !lengths.length ? <p className="type-footnote text-label-2">{t("quickReserve.length.none", { n: blocks ? t("quickReserve.length.minutes", { n: sd.min_length * sd.block_minutes }) : t("quickReserve.length.periods", { n: sd.min_length }) })}</p> : null}
          {blocks && span ? (
            <p className="type-footnote text-label-2" data-testid="qr-mapped">
              {t("quickReserve.length.mapped", { range: spanText(span, { ...sd, label: "both", time_format: "range" }) })}
            </p>
          ) : null}
        </section>

        {/* 2 · Nerede? */}
        <section aria-labelledby="qr-where" data-tour="reserve-room-list" aria-busy={find.isFetching} className="flex min-w-0 flex-col gap-3">
          <h2 id="qr-where" className="type-title-3 text-label-1">
            {step(2, "where")}
          </h2>
          <ChipRadioGroup<string>
            label={t("quickReserve.people.label")}
            testId="qr-people"
            value={String(people)}
            onChange={(v) => {
              setPeople(Number(v));
              resetAfterChange();
            }}
            items={PEOPLE.map((n) => ({ value: String(n), label: n ? t("quickReserve.people.n", { n }) : t("quickReserve.people.any"), name: `${t("quickReserve.people.label")} ${n ? t("quickReserve.people.n", { n }) : t("quickReserve.people.any")}`, testId: `qr-people-${n}` }))}
          />
          {booleanFacets.length ? (
            <div role="group" aria-label={t("quickReserve.features.label")} className="-mx-1 flex gap-2 overflow-x-auto px-1 scrollbar-thin sm:flex-wrap sm:overflow-visible" data-testid="qr-features">
              {booleanFacets.map((f) => (
                <Chip key={f.id} selected={features.includes(f.id)} onSelectedChange={(on) => (setFeatures((prev) => (on ? [...prev, f.id] : prev.filter((x) => x !== f.id))), resetAfterChange())} data-testid={`qr-feature-${f.id}`}>
                  {f.name}
                </Chip>
              ))}
            </div>
          ) : null}
          <p className="type-callout font-medium text-label-2" data-testid="qr-count">
            {!query ? t("quickReserve.rooms.chooseFirst") : stale && !find.data ? t("quickReserve.rooms.searching") : t("quickReserve.rooms.count", { n: rooms.length })}
          </p>
          {find.isError ? (
            <Alert tone="error" title={t("quickReserve.error.network")}>
              <Button variant="outline" size="sm" onClick={() => void find.refetch()}>
                {t("quickReserve.error.retry")}
              </Button>
            </Alert>
          ) : null}
          {query && find.isLoading ? (
            <div className="flex flex-col gap-2">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-16 w-full rounded-xl" />
              ))}
            </div>
          ) : query && find.data && !rooms.length ? (
            <EmptyState
              size="sm"
              title={t("quickReserve.empty.title")}
              description={t("quickReserve.empty.otherDay")}
              actions={
                <Button variant="outline" size="sm" render={<Link href={`/find-room?date=${day ?? ""}${people ? `&headcount=${people}` : ""}`} />} nativeButton={false}>
                  {t("quickReserve.empty.advanced")}
                </Button>
              }
              data-testid="qr-empty"
            />
          ) : rooms.length ? (
            <div role="radiogroup" aria-label={t("quickReserve.rooms.label")} data-stale={stale ? "true" : undefined} className="flex flex-col overflow-hidden rounded-xl bg-(--mat-thick-solid) edge-hairline transition-opacity duration-(--dur-fast) data-[stale=true]:opacity-60" data-testid="qr-rooms">
              {shownRooms.map((r, i) => (
                <RoomRow
                  key={r.room_id}
                  row={r}
                  selected={r.room_id === room?.room_id}
                  tabStop={room ? r.room_id === room.room_id : i === 0}
                  recent={recent.has(r.room_id)}
                  taken={taken.has(takenKey(r.room_id))}
                  onSelect={() => {
                    setRoomId(r.room_id);
                    setError(null);
                  }}
                  onCommit={() => window.requestAnimationFrame(() => primaryRef.current?.focus())}
                />
              ))}
            </div>
          ) : null}
          {rooms.length > SHOW_FIRST && !showAll ? (
            <Button variant="ghost" className="self-start" onClick={() => setShowAll(true)} data-testid="qr-show-all">
              {t("quickReserve.rooms.showAll", { n: rooms.length })}
            </Button>
          ) : null}
        </section>

        {/* 3 · Onayla: the sticky action bar on phones and tablets, a card in the third column on desktop */}
        <section aria-labelledby="qr-confirm" className="max-lg:fixed max-lg:inset-x-0 max-lg:bottom-[calc(4.75rem+max(0.75rem,env(safe-area-inset-bottom)))] max-lg:[@media(max-height:500px)]:bottom-[calc(3.25rem+max(0.5rem,env(safe-area-inset-bottom)))] max-lg:z-30 max-lg:px-3 lg:sticky lg:top-20" data-testid="qr-confirm">
          {/* mobile-a fix 3: on a short landscape phone (≤ 500 px tall) the bar is one row, summary beside the button (the
              column took 160 of 390 px and left the list 32 % of the screen); it sits 8 px above the 44 px compact tab bar */}
          <div className="mx-auto flex max-h-[45dvh] w-full max-w-xl flex-col gap-2 overflow-y-auto rounded-3xl bg-(--mat-thick-solid) p-3 shadow-elev-3 edge-hairline lg:max-h-none lg:gap-3 lg:rounded-xl lg:p-4 lg:shadow-none [@media(max-height:500px)]:max-w-3xl [@media(max-height:500px)]:flex-row [@media(max-height:500px)]:items-center [@media(max-height:500px)]:gap-3 [@media(max-height:500px)]:py-2">
            {receipt ? (
              <ReceiptCard receipt={receipt} headingRef={receiptRef} undoing={undoing} onUndo={() => void undo(receipt)} onAgain={newBooking} line={t("quickReserve.summary.line", { room: receipt.room.name, day: dayWord(receipt.date), slot: spanText(receipt.span) })} />
            ) : (
              <>
                <h2 id="qr-confirm" className="sr-only">
                  {step(3, "confirm")}
                </h2>
                <p className={cn("type-headline [@media(max-height:500px)]:min-w-0 [@media(max-height:500px)]:flex-1", room ? "text-label-1" : "text-label-2")} data-testid="qr-summary">
                  {summary}
                </p>
                {error ? (
                  <div id="qr-error" tabIndex={-1} className="outline-hidden">
                    <Alert tone="error" title={error.kind === "conflict" ? t("quickReserve.conflict.title") : undefined} testId="qr-error">
                      <span>{error.text}</span>
                    </Alert>
                  </div>
                ) : null}
                {request_ ? <p className="flex items-start gap-1.5 type-footnote text-tint-text" data-testid="qr-approval"><Stamp className="mt-0.5 size-3.5 shrink-0" aria-hidden />{t("quickReserve.approval.body")}</p> : null}
                {quotaNone ? <p className="type-footnote text-status-warning-fg">{t("quickReserve.quota.none")}</p> : null}
                {!room ? null : noteOpen ? (
                  <label className="flex flex-col gap-1">
                    <span className="type-footnote font-medium text-label-2">{t("quickReserve.note.label")}</span>
                    <Textarea rows={1} maxLength={255} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("quickReserve.note.placeholder")} className="min-h-11 pointer-coarse:text-base" data-testid="qr-note" autoFocus />
                  </label>
                ) : (
                  <Button variant="ghost" size="sm" className="self-start" onClick={() => setNoteOpen(true)} data-testid="qr-note-add">
                    {t("quickReserve.note.add")}
                  </Button>
                )}
                <BusyButton
                  ref={primaryRef}
                  size="lg"
                  className="w-full [@media(max-height:500px)]:w-auto"
                  busy={busy}
                  busyLabel={t(request_ ? "quickReserve.submit.busyRequest" : "quickReserve.submit.busyBook")}
                  disabled={!room || quotaNone || action === "mine"}
                  focusableWhenDisabled
                  onClick={() => void submit()}
                  aria-label={room ? t(request_ ? "quickReserve.submit.requestFor" : "quickReserve.submit.bookFor", { room: room.name }) : undefined}
                  data-action={request_ ? "request" : "book"}
                  data-testid="qr-submit"
                  icon={request_ ? <Stamp aria-hidden /> : <Zap aria-hidden />}
                >
                  {t(request_ ? "quickReserve.submit.request" : "quickReserve.submit.book")}
                </BusyButton>
                {ctx.data?.remaining_bookings != null && ctx.data.remaining_bookings > 0 ? <p className="type-footnote text-label-2">{t("quickReserve.quota.left", { n: ctx.data.remaining_bookings })}</p> : null}
                <Link href={`/bookings?date=${day ?? ""}`} className="self-start type-footnote font-medium text-tint-text underline-offset-2 hover:underline max-lg:hidden" data-testid="qr-more">
                  {t("quickReserve.more")}
                </Link>
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function RoomRow({ row, selected, tabStop, recent, taken, onSelect, onCommit }: { row: FindRow; selected: boolean; tabStop: boolean; recent: boolean; taken: boolean; onSelect: () => void; onCommit: () => void }) {
  const { t } = useI18n();
  const act = roomAction(row);
  const title = row.code.replace(/\s/g, "") === row.name.replace(/\s/g, "") ? row.name : `${row.code} · ${row.name}`;
  const details = [row.building, row.capacity ? t("quickReserve.rooms.capacity", { n: row.capacity }) : null, ...row.tags.slice(0, 3)].filter(Boolean).join(" · ");
  const badge = act === "request" ? t("quickReserve.rooms.needsApproval") : act === "mine" ? t("quickReserve.rooms.mine") : taken ? t("quickReserve.conflict.taken") : null;
  const move = (el: HTMLElement, dir: 1 | -1 | "home" | "end") => {
    const list = [...(el.closest("[role=radiogroup]")?.querySelectorAll<HTMLElement>("[role=radio]") ?? [])];
    const i = list.indexOf(el);
    const next = dir === "home" ? list[0] : dir === "end" ? list[list.length - 1] : list[(i + dir + list.length) % list.length];
    next?.focus();
    next?.click();
  };
  return (
    <BareButton
      role="radio"
      aria-checked={selected}
      aria-disabled={taken || undefined}
      aria-label={[title, details, badge, recent ? t("quickReserve.rooms.recent") : null].filter(Boolean).join(", ")}
      tabIndex={tabStop ? 0 : -1}
      data-room-row={row.room_id}
      data-testid={`qr-room-${row.code}`}
      data-action={act}
      onClick={() => !taken && onSelect()}
      onKeyDown={(e) => {
        const k = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1, Home: "home", End: "end" } as const;
        const dir = k[e.key as keyof typeof k];
        if (dir !== undefined) {
          e.preventDefault();
          move(e.currentTarget, dir);
        } else if (e.key === "Enter" && !taken) {
          e.preventDefault();
          onSelect();
          onCommit();
        }
      }}
      className={cn(
        "flex min-h-14 w-full items-center gap-3 rounded-none px-3 py-2 text-left font-normal not-last:edge-hairline-b focus-visible:z-10 focus-visible:-outline-offset-2",
        selected ? "bg-tint-soft inset-ring-2 inset-ring-(--accent)" : "hover:bg-fill-3",
        taken && "cursor-not-allowed text-label-3",
      )}
    >
      <span aria-hidden className={cn("flex size-6 shrink-0 items-center justify-center rounded-full", selected ? "bg-tint text-white" : "inset-ring-2 inset-ring-(--border-control)")}>
        {selected ? <Check className="size-3.5 stroke-[3]" /> : null}
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate type-headline text-label-1">{title}</span>
        {details ? <span className="truncate type-footnote text-label-2">{details}</span> : null}
        {recent ? <span className="type-caption text-label-3">{t("quickReserve.rooms.recent")}</span> : null}
      </span>
      {badge ? (
        <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 type-caption font-semibold", act === "request" || act === "mine" ? "bg-tint-soft text-tint-text" : "bg-fill-2 text-label-2")}>
          {act === "request" || act === "mine" ? <Hourglass className="size-3" aria-hidden /> : null}
          {badge}
        </span>
      ) : null}
    </BareButton>
  );
}

/**
 * The receipt's check (quick-reserve.md §8 "✓ draws", pattern 10): adapted from the transitions.dev free recipe
 * "success-check" (fade + rotate + Y-bob + stroke draw) to motion.md limits: 240 ms one-shot (≤ 300 ms), a 6 px bob
 * on the bouncySubtle curve, no blur filter (the card may sit on chrome; backdrop-root rule), static under
 * prefers-reduced-motion. The path length (≈ 20.6) is measured once, rounded up.
 */
const SUCCESS_CHECK_CSS = `.qr-success-check{display:inline-flex;transform-origin:center;opacity:0}
.qr-success-check svg path{stroke-dasharray:21;stroke-dashoffset:21}
.qr-success-check[data-state="in"]{animation:qr-check-fade 240ms var(--ease-out,cubic-bezier(.22,1,.36,1)) forwards,qr-check-rotate 240ms cubic-bezier(.22,1,.36,1) forwards,qr-check-bob 240ms var(--spring-bouncy-subtle,cubic-bezier(.34,1.35,.64,1)) forwards}
.qr-success-check[data-state="in"] svg path{animation:qr-check-draw 220ms cubic-bezier(.22,1,.36,1) 40ms forwards}
@keyframes qr-check-fade{from{opacity:0}to{opacity:1}}
@keyframes qr-check-rotate{from{transform:rotate(40deg)}to{transform:rotate(0)}}
@keyframes qr-check-bob{from{translate:0 6px}to{translate:0 0}}
@keyframes qr-check-draw{to{stroke-dashoffset:0}}
@media (prefers-reduced-motion: reduce){.qr-success-check{animation:none!important;opacity:1}.qr-success-check svg path{animation:none!important;stroke-dashoffset:0!important}}`;

function ReceiptCard({ receipt, headingRef, undoing, onUndo, onAgain, line }: { receipt: Receipt; headingRef: React.RefObject<HTMLHeadingElement | null>; undoing: boolean; onUndo: () => void; onAgain: () => void; line: string }) {
  const { t } = useI18n();
  const pending = receipt.pending;
  return (
    <div className="flex flex-col gap-3" data-testid="qr-receipt" data-state={pending ? "requested" : "booked"}>
      <style>{SUCCESS_CHECK_CSS}</style>
      <div className="flex items-center gap-2">
        <span aria-hidden className={cn("flex size-8 shrink-0 items-center justify-center rounded-full", pending ? "bg-tint-soft text-tint-text" : "bg-status-feasible text-status-feasible-fg")}>
          {pending ? (
            <Hourglass className="size-4" />
          ) : (
            <span className="qr-success-check" data-state="in">
              <svg viewBox="0 0 24 24" fill="none" className="size-4" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12.5l4.5 4.5L19 7.5" />
              </svg>
            </span>
          )}
        </span>
        <h2 ref={headingRef} tabIndex={-1} className="type-title-3 text-label-1 outline-hidden" data-testid="qr-receipt-title">
          {t(pending ? "quickReserve.receipt.requested" : "quickReserve.receipt.booked")}
        </h2>
      </div>
      <p className="type-callout text-label-1">{line}</p>
      {pending ? <p className="type-footnote text-label-2">{t("quickReserve.receipt.requestedBody")}</p> : null}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={onUndo} disabled={undoing} aria-label={pending ? t("quickReserve.receipt.withdraw") : t("quickReserve.receipt.undoFor", { room: receipt.room.name })} data-testid="qr-undo">
          {undoing ? <Loader2 className="animate-spin" aria-hidden /> : <Undo2 aria-hidden />}
          {t(pending ? "quickReserve.receipt.withdraw" : "quickReserve.receipt.undo")}
        </Button>
        <Button variant="ghost" render={<Link href="/my-bookings" />} nativeButton={false} data-testid="qr-mine">
          {t("quickReserve.receipt.mine")}
        </Button>
        <Button variant="ghost" onClick={onAgain} data-testid="qr-again">
          <RotateCcw aria-hidden />
          {t("quickReserve.receipt.again")}
        </Button>
      </div>
    </div>
  );
}
