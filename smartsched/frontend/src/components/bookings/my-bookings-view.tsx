"use client";
/**
 * /my-bookings (CRBS `Dashboard` + `Bookings_model::ByUser/ByRoomOwner` + `Export`): my upcoming and past
 * bookings with multi-cancel, bookings by others in rooms I own, a calendar subscription link and, with
 * `system.export_bookings`, the CSV export. Wave 1 (P1): my approval requests with their timeline come first
 * (`?request=<id>` from the in-app notification opens one).
 */
import { CalendarSync, Download, Repeat, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useIsPhone } from "./use-is-phone";
import {
  exportCsvUrl,
  useBookingContext,
  useBookingDashboard,
  useBookingDates,
  useCrbsMe,
  useMyBookings,
  useOwnedRooms,
  type BookingOut,
} from "@/lib/api/crbs";
import { bookingCapabilities } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/provider";
import { Field, Loading, PageTitle, SectionTitle, SelectField } from "@/components/admin/kit";
import { MyRequests } from "@/components/approvals/my-requests";
import { useMyRequests } from "@/lib/api/wave1";
import { StatusPill } from "@/components/approvals/request-parts";
import { addDays } from "./date-format";
import { BookingDetailSheet } from "./booking-detail-sheet";
import { CalendarSyncPanel } from "./calendar-sync";
import { CancelManyDialog } from "./cancel-many-dialog";
import { RoomInfoSheet } from "./room-info-sheet";
import { useBookingFormat, useProfileLanguage } from "./use-booking-format";
import { focusRowAfterRemoval, groupBookings, openRequestCount, rowIndexOf, rowSelectorsAfterRemoval } from "./my-bookings-model";
import { focusAfter } from "./focus-after";
import { cancelReasonText } from "./cancel-reason";
import { BareButton } from "@/components/shell/bare-button";

type Tab = "upcoming" | "past" | "cancelled";

/** MOBILE.md M-02 (loop-r1-laneB2, lane-A2 ask): a row stacks a 16 px checkbox, the room chip and the date line; on
 *  coarse pointers the row keeps 20 px between the checkbox (its 44 px zone reaches 14 px past the box) and the
 *  text, and each text control is at least 44 × 44, so no tap zone is cut by its neighbour. */
export const BOOKING_ROW_CLASS = "flex items-center gap-3 px-4 py-2.5 not-last:edge-hairline-b pointer-coarse:gap-5";
export const BOOKING_ROW_CONTROL_CLASS = "pointer-coarse:min-h-11 pointer-coarse:min-w-11 pointer-coarse:py-1";

export function MyBookingsView() {
  const { t } = useI18n();
  const phone = useIsPhone();
  useProfileLanguage();
  const fmt = useBookingFormat();
  const me = useCrbsMe();
  const caps = bookingCapabilities(me.data?.permissions);
  const today = useBookingDates({}).data?.today;
  const [tab, setTab] = useState<Tab>("upcoming");
  const q = tab === "upcoming" ? { from: today, status: "BOOKED" as const } : tab === "past" ? { to: today ? addDays(today, -1) : undefined, status: "ALL" as const } : { status: "CANCELLED" as const };
  const list = useMyBookings(q);
  const dash = useBookingDashboard();
  const owned = useOwnedRooms();
  const [detail, setDetail] = useState<number | null>(null);
  const [roomInfo, setRoomInfo] = useState<{ id: number; date: string } | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [cancelOpen, setCancelOpen] = useState(false);

  // T-R1-17 (R1-A-22): an approved request's note ("Onaylandı, iyi dersler.") on the booking it made
  const requests = useMyRequests();
  const approverNote = useCallback(
    (bookingId: number) => requests.data?.find((r) => r.status === "APPROVED" && r.note && r.bookings.some((x) => x.id === bookingId))?.note ?? null,
    [requests.data],
  );
  // R3-S-05: after a cancel, focus the row that takes the cancelled row's place (or the heading), never <body>
  // the row index is taken when the row (or the bulk cancel) is opened: by the time the cancel's onSuccess runs, the
  // invalidated list may already have refetched without the row
  const pendingFocus = useRef<{ index: number; ids: number[] } | null>(null);
  const openedIndex = useRef(0);
  const noteRows = (ids: number[]) => {
    openedIndex.current = ids.map(rowIndexOf).filter((i) => i >= 0).sort((a, b) => a - b)[0] ?? 0;
  };
  const placeFocus = (index: number) => {
    focusRowAfterRemoval(index);
    focusAfter(rowSelectorsAfterRemoval(index), 50);
  };
  // a tick, not the list: the cancel's callback closes over an older render, so the effect below decides with the
  // current list (it may already have refetched without the row)
  const [focusTick, setFocusTick] = useState(0);
  const rememberRow = (ids: number[]) => {
    pendingFocus.current = { index: openedIndex.current, ids };
    setFocusTick((n) => n + 1);
  };
  useEffect(() => {
    const p = pendingFocus.current;
    if (!p || !list.data || list.isFetching) return;
    if (list.data.some((b) => p.ids.includes(b.id) && b.status !== "CANCELLED")) return; // not refetched yet
    pendingFocus.current = null;
    // after the sheet / dialog has closed (their exit returns focus to a trigger that is gone)
    placeFocus(p.index);
  }, [list.data, list.isFetching, focusTick]);
  const rows = useMemo(() => {
    const items = [...(list.data ?? [])];
    if (tab === "past") items.reverse();
    return items;
  }, [list.data, tab]);

  const toggle = (id: number, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  return (
    <div className={cn("flex flex-col gap-8 pb-16", phone && selected.size > 0 && "pb-36")}>
      <PageTitle
        title={t("crbs.mine.title")}
        actions={
          <Button variant="outline" render={<Link href="/find-room" />} nativeButton={false} data-testid="mine-find-room">
            <Search aria-hidden />
            {t("wave1.find.title")}
          </Button>
        }
        subtitle={
          dash.data ? (
            <span data-testid="mine-totals">
              {t("crbs.mine.totals", { active: dash.data.totals.active, session: dash.data.totals.session, all: dash.data.totals.all })}
              {/* W3-SLOT: the totals are live bookings; open requests are named apart */}
              {openRequestCount(requests.data) ? <span data-testid="mine-pending">{` · ${t("quickReserve.pendingApart", { n: openRequestCount(requests.data) })}`}</span> : null}
              {dash.data.limits.max_active_bookings != null ? ` · ${t("crbs.mine.limit", { n: dash.data.limits.max_active_bookings })}` : ""}
              {dash.data.limits.max_active_bookings != null ? (
                <span data-testid="mine-can-create">{` · ${t("reserve.mine.canCreate", { n: Math.max(0, dash.data.limits.max_active_bookings - (dash.data.totals.active_periods ?? dash.data.totals.active)) })}`}</span>
              ) : null}
            </span>
          ) : null
        }
      />

      <MyRequests fmt={fmt} />

      <section aria-labelledby="mine-list">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 id="mine-list" className="sr-only" tabIndex={-1} data-focus-fallback>
            {t("crbs.mine.title")}
          </h2>
          <SegmentedControl<Tab>
            aria-label={t("crbs.mine.filter")}
            fill={phone}
            className={phone ? "w-full" : undefined}
            value={tab}
            onValueChange={(v) => {
              setTab(v);
              setSelected(new Set());
            }}
            options={[
              { value: "upcoming", label: t("crbs.mine.upcoming") },
              { value: "past", label: t("crbs.mine.past") },
              { value: "cancelled", label: t("crbs.mine.cancelled") },
            ]}
          />
          {tab === "upcoming" && selected.size > 0 && !phone ? (
            <Button variant="outline" className="text-status-infeasible-fg" onClick={() => (noteRows([...selected]), setCancelOpen(true))} data-testid="cancel-selected">
              <Trash2 aria-hidden />
              {t("crbs.mine.cancelSelected", { n: selected.size })}
            </Button>
          ) : null}
        </div>
        <Card className="py-0">
          {list.isLoading ? (
            <Loading className="px-4" />
          ) : rows.length === 0 ? (
            <p className="px-4 py-6 type-callout text-label-2">{tab === "upcoming" ? t("crbs.mine.emptyUpcoming") : t("crbs.mine.empty")}</p>
          ) : (
            <BookingList rows={rows} fmt={fmt} selectable={tab === "upcoming"} selected={selected} onToggle={toggle} onOpen={(id) => (noteRows([id]), setDetail(id))} onRoom={(id, date) => setRoomInfo({ id, date })} approverNote={approverNote} />
          )}
        </Card>
      </section>

      {owned.data && owned.data.length > 0 ? (
        <section aria-labelledby="owned">
          <SectionTitle id="owned">{t("crbs.mine.ownedRooms")}</SectionTitle>
          <div className="flex flex-col gap-3">
            {owned.data.map((room) => (
              <Card key={room.id} className="py-0">
                <div className="flex items-baseline justify-between px-4 pt-3">
                  <h3 className="type-headline text-label-1">{room.name}</h3>
                  <span className="type-footnote text-label-3">{t("crbs.mine.upcomingCount", { n: room.upcoming.length })}</span>
                </div>
                {room.upcoming.length ? <BookingList rows={room.upcoming} fmt={fmt} showUser onOpen={(id) => (noteRows([id]), setDetail(id))} onRoom={(id, date) => setRoomInfo({ id, date })} /> : <p className="px-4 pb-3 type-callout text-label-2">{t("crbs.mine.ownedEmpty")}</p>}
              </Card>
            ))}
          </div>
        </section>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="feed-title">
          <SectionTitle id="feed-title">
            <span className="inline-flex items-center gap-2">
              <CalendarSync className="size-5 text-label-2" aria-hidden />
              {t("reserve.sync.title")}
            </span>
          </SectionTitle>
          <Card className="gap-3 px-4">
            <CalendarSyncPanel departmentId={me.data?.department_id ?? null} />
          </Card>
        </section>
        {caps.exportBookings ? <ExportCard /> : null}
      </div>

      {/* T-R2-11 (R2-S-04, MOBILE M-05): on a phone the bulk action is a capsule fixed above the tab bar, not a button at
          the top of the page that scrolls away */}
      {tab === "upcoming" && selected.size > 0 && phone ? (
        <div className="fixed inset-x-4 bottom-[calc(var(--shell-bottom-h)+0.75rem)] z-20 flex items-center justify-between gap-3 rounded-2xl glass-chrome px-4 py-2 shadow-elev-2" data-testid="cancel-selected-capsule">
          <span className="type-callout text-label-1">{t("crbs.mine.selectedN", { n: selected.size })}</span>
          <Button variant="outline" className="text-status-infeasible-fg" onClick={() => (noteRows([...selected]), setCancelOpen(true))} data-testid="cancel-selected">
            <Trash2 aria-hidden />
            {t("crbs.mine.cancelSelected", { n: selected.size })}
          </Button>
        </div>
      ) : null}
      <BookingDetailSheet bookingId={detail} onOpenChange={(o) => !o && setDetail(null)} fmt={fmt} onCancelled={(id) => rememberRow([id])} />
      <RoomInfoSheet roomId={roomInfo?.id ?? null} context={roomInfo ? { date: roomInfo.date } : undefined} fmt={fmt} onOpenChange={(o) => !o && setRoomInfo(null)} />
      <CancelManyDialog
        ids={[...selected]}
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        onDone={() => {
          rememberRow([...selected]);
          setSelected(new Set());
          setCancelOpen(false);
        }}
        placeFocus={false}
        ownOnly
      />
    </div>
  );
}

function BookingList({
  rows,
  fmt,
  selectable,
  selected,
  onToggle,
  onOpen,
  onRoom,
  showUser,
  approverNote,
}: {
  rows: BookingOut[];
  fmt: ReturnType<typeof useBookingFormat>;
  selectable?: boolean;
  selected?: ReadonlySet<number>;
  onToggle?: (id: number, on: boolean) => void;
  onOpen: (id: number) => void;
  onRoom?: (roomId: number, date: string) => void;
  showUser?: boolean;
  approverNote?: (bookingId: number) => string | null;
}) {
  const { t } = useI18n();
  // T-R2-13 (A-12): the periods of one submission on one day are one row ("C 303 · P7–P8 (13:30–15:00)")
  const groups = useMemo(() => groupBookings(rows), [rows]);
  return (
    <ul className="flex flex-col" data-testid="booking-list">
      {groups.map((g) => {
        const b = g.first;
        const note = g.ids.map((id) => approverNote?.(id) ?? null).find((n) => n) ?? null;
        const time = b.time_start ? (g.bookings.length > 1 && g.last.time_end ? `${fmt.time(b.time_start)}–${fmt.time(g.last.time_end)}` : fmt.time(b.time_start)) : null;
        const allSelected = g.ids.every((id) => selected?.has(id));
        return (
        <li key={g.id} className={BOOKING_ROW_CLASS} data-booking-id={g.id} data-booking-ids={g.ids.join(",")} data-periods={g.bookings.length}>
          {selectable ? (
            /* T-R2-11: the row's left column is a 44 px label for the checkbox, so the tap never lands on the neighbouring chip */
            <label className="flex min-h-11 min-w-11 shrink-0 items-center justify-center self-stretch">
              <Checkbox checked={allSelected} onCheckedChange={(v) => g.ids.forEach((id) => onToggle?.(id, v === true))} aria-label={t("crbs.mine.select", { room: `${b.room_name} ${g.periodLabel}`, date: fmt.short(b.date) })} />
            </label>
          ) : null}
          <div className="flex min-w-0 flex-1 items-center justify-between gap-3">
            <span className="min-w-0">
              <span className="block type-headline text-label-1">
                {/* CRBS user_bookings.php: the room name opens the room-info drawer */}
                <BareButton onClick={() => onRoom?.(b.room_id, b.date)} disabled={!onRoom} className={cn("rounded-sm hover:text-tint-text disabled:hover:text-label-1", BOOKING_ROW_CONTROL_CLASS)} aria-label={t("crbs.roomInfo.open", { name: b.room_name })} data-testid={`mine-room-${b.id}`}>
                  {b.room_name}
                </BareButton>
                <span> · {g.periodLabel}</span>
                {time ? <span className="ml-1.5 font-normal text-label-3 tabular-nums">{g.bookings.length > 1 ? `(${time})` : time}</span> : null}
              </span>
              <BareButton onClick={() => onOpen(b.id)} data-row-open className={cn("flex w-full items-center gap-1 truncate rounded-sm text-left type-footnote text-label-2 hover:text-label-1", BOOKING_ROW_CONTROL_CLASS)}>
                {b.type === "recurring" ? <Repeat className="size-3 shrink-0" aria-label={t("crbs.legend.recurring")} /> : null}
                {fmt.long(b.date)}
                {showUser && b.user_name ? ` · ${b.user_name}` : ""}
                {b.notes ? ` · ${b.notes}` : ""}
              </BareButton>
              {/* a span: each period opens its own detail (per-period edit / cancel inside) */}
              {g.bookings.length > 1 ? (
                <span className="flex flex-wrap items-center gap-x-2 type-footnote text-label-3" data-testid={`mine-periods-${g.id}`}>
                  {g.bookings.map((x) => (
                    <BareButton key={x.id} onClick={() => onOpen(x.id)} className={cn("rounded-sm tabular-nums hover:text-label-1", BOOKING_ROW_CONTROL_CLASS)} aria-label={t("crbs.mine.openPeriod", { period: x.period_name ?? `P${x.start_period}` })} data-testid={`mine-period-${x.id}`}>
                      {x.period_name ?? `P${x.start_period}`}
                    </BareButton>
                  ))}
                </span>
              ) : null}
              {/* T-R1-17 (R1-A-22): why it was cancelled, and what the approver wrote (once per submission) */}
              {b.status === "CANCELLED" && b.cancel_reason ? (
                <span className="block type-footnote text-label-2" data-testid={`mine-cancel-reason-${b.id}`}>
                  {t("crbs.mine.cancelReason", { reason: cancelReasonText(b.cancel_reason, t)! })}
                </span>
              ) : null}
              {b.status !== "CANCELLED" && note ? (
                <span className="block type-footnote text-label-2" data-testid={`mine-approver-note-${b.id}`}>
                  {t("crbs.mine.approverNote", { note })}
                </span>
              ) : null}
            </span>
            {b.status === "CANCELLED" ? <span className="shrink-0 type-footnote font-medium text-label-3">{t("crbs.status.cancelled")}</span> : b.status !== "BOOKED" ? <StatusPill status={b.status} /> : null}
          </div>
        </li>
        );
      })}
    </ul>
  );
}

function ExportCard() {
  const { t } = useI18n();
  const ctx = useBookingContext();
  const [term, setTerm] = useState<string>("");
  const [group, setGroup] = useState<string>("");
  const [cancelled, setCancelled] = useState(false);
  const termId = term ? Number(term) : (ctx.data?.current_term_id ?? undefined);
  const href = exportCsvUrl({ term_id: termId, room_group_id: group === "" ? undefined : Number(group), include_cancelled: cancelled });
  return (
    <section aria-labelledby="export-title">
      <SectionTitle id="export-title">{t("crbs.export.title")}</SectionTitle>
      <Card className="gap-3 px-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("crbs.export.session")} htmlFor="export-term">
            <SelectField id="export-term" value={term || String(termId ?? "")} onChange={(e) => setTerm(e.target.value)}>
              {(ctx.data?.sessions ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </SelectField>
          </Field>
          <Field label={t("crbs.export.group")} htmlFor="export-group">
            <SelectField id="export-group" value={group} onChange={(e) => setGroup(e.target.value)}>
              <option value="">{t("crbs.export.allGroups")}</option>
              {(ctx.data?.room_groups ?? [])
                .filter((g) => g.id !== 0)
                .map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
            </SelectField>
          </Field>
        </div>
        <label className="flex items-center gap-2 type-callout text-label-1">
          <Checkbox checked={cancelled} onCheckedChange={(v) => setCancelled(v === true)} />
          {t("crbs.export.includeCancelled")}
        </label>
        <div>
          <Button render={<a href={href} download data-testid="export-csv" />} nativeButton={false}>
            <Download aria-hidden />
            {t("crbs.export.download")}
          </Button>
        </div>
        <p className="type-footnote text-label-3">{t("crbs.export.hint")}</p>
      </Card>
    </section>
  );
}
