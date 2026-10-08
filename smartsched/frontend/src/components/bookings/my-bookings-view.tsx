"use client";
/**
 * /my-bookings (CRBS `Dashboard` + `Bookings_model::ByUser/ByRoomOwner` + `Export`): my upcoming and past
 * bookings with multi-cancel, bookings by others in rooms I own, a calendar subscription link and, with
 * `system.export_bookings`, the CSV export.
 */
import { CalendarSync, Download, Repeat, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
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
import { useI18n } from "@/lib/i18n/provider";
import { Field, Loading, PageTitle, SectionTitle, SelectField } from "@/components/admin/kit";
import { addDays } from "./date-format";
import { BookingDetailSheet } from "./booking-detail-sheet";
import { CalendarSyncPanel } from "./calendar-sync";
import { CancelManyDialog } from "./cancel-many-dialog";
import { RoomInfoSheet } from "./room-info-sheet";
import { useBookingFormat, useProfileLanguage } from "./use-booking-format";

type Tab = "upcoming" | "past" | "cancelled";

export function MyBookingsView() {
  const { t } = useI18n();
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
    <div className="flex flex-col gap-8 pb-16">
      <PageTitle
        title={t("crbs.mine.title")}
        subtitle={
          dash.data ? (
            <span data-testid="mine-totals">
              {t("crbs.mine.totals", { active: dash.data.totals.active, session: dash.data.totals.session, all: dash.data.totals.all })}
              {dash.data.limits.max_active_bookings != null ? ` · ${t("crbs.mine.limit", { n: dash.data.limits.max_active_bookings })}` : ""}
              {dash.data.limits.max_active_bookings != null ? (
                <span data-testid="mine-can-create">{` · ${t("reserve.mine.canCreate", { n: Math.max(0, dash.data.limits.max_active_bookings - dash.data.totals.active) })}`}</span>
              ) : null}
            </span>
          ) : null
        }
      />

      <section aria-labelledby="mine-list">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 id="mine-list" className="sr-only">
            {t("crbs.mine.title")}
          </h2>
          <SegmentedGlass<Tab>
            aria-label={t("crbs.mine.filter")}
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
          {tab === "upcoming" && selected.size > 0 ? (
            <Button variant="outline" className="text-status-infeasible-fg" onClick={() => setCancelOpen(true)} data-testid="cancel-selected">
              <Trash2 aria-hidden />
              {t("crbs.mine.cancelSelected", { n: selected.size })}
            </Button>
          ) : null}
        </div>
        <Card variant="glass" className="py-0">
          {list.isLoading ? (
            <Loading className="px-4" />
          ) : rows.length === 0 ? (
            <p className="px-4 py-6 type-callout text-label-2">{tab === "upcoming" ? t("crbs.mine.emptyUpcoming") : t("crbs.mine.empty")}</p>
          ) : (
            <BookingList rows={rows} fmt={fmt} selectable={tab === "upcoming"} selected={selected} onToggle={toggle} onOpen={setDetail} onRoom={(id, date) => setRoomInfo({ id, date })} />
          )}
        </Card>
      </section>

      {owned.data && owned.data.length > 0 ? (
        <section aria-labelledby="owned">
          <SectionTitle id="owned">{t("crbs.mine.ownedRooms")}</SectionTitle>
          <div className="flex flex-col gap-3">
            {owned.data.map((room) => (
              <Card key={room.id} variant="glass" className="py-0">
                <div className="flex items-baseline justify-between px-4 pt-3">
                  <h3 className="type-headline text-label-1">{room.name}</h3>
                  <span className="type-footnote text-label-3">{t("crbs.mine.upcomingCount", { n: room.upcoming.length })}</span>
                </div>
                {room.upcoming.length ? <BookingList rows={room.upcoming} fmt={fmt} showUser onOpen={setDetail} onRoom={(id, date) => setRoomInfo({ id, date })} /> : <p className="px-4 pb-3 type-callout text-label-2">{t("crbs.mine.ownedEmpty")}</p>}
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
          <Card variant="glass" className="gap-3 px-4">
            <CalendarSyncPanel departmentId={me.data?.department_id ?? null} />
          </Card>
        </section>
        {caps.exportBookings ? <ExportCard /> : null}
      </div>

      <BookingDetailSheet bookingId={detail} onOpenChange={(o) => !o && setDetail(null)} fmt={fmt} />
      <RoomInfoSheet roomId={roomInfo?.id ?? null} context={roomInfo ? { date: roomInfo.date } : undefined} fmt={fmt} onOpenChange={(o) => !o && setRoomInfo(null)} />
      <CancelManyDialog
        ids={[...selected]}
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        onDone={() => {
          setSelected(new Set());
          setCancelOpen(false);
        }}
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
}: {
  rows: BookingOut[];
  fmt: ReturnType<typeof useBookingFormat>;
  selectable?: boolean;
  selected?: ReadonlySet<number>;
  onToggle?: (id: number, on: boolean) => void;
  onOpen: (id: number) => void;
  onRoom?: (roomId: number, date: string) => void;
  showUser?: boolean;
}) {
  const { t } = useI18n();
  return (
    <ul className="flex flex-col" data-testid="booking-list">
      {rows.map((b) => (
        <li key={b.id} className="flex items-center gap-3 px-4 py-2.5 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none" data-booking-id={b.id}>
          {selectable ? <Checkbox checked={selected?.has(b.id) ?? false} onCheckedChange={(v) => onToggle?.(b.id, v === true)} aria-label={t("crbs.mine.select", { room: b.room_name, date: fmt.short(b.date) })} /> : null}
          <div className="flex min-w-0 flex-1 items-center justify-between gap-3">
            <span className="min-w-0">
              <span className="block type-headline text-label-1">
                {/* CRBS user_bookings.php: the room name opens the room-info drawer */}
                <button type="button" onClick={() => onRoom?.(b.room_id, b.date)} disabled={!onRoom} className="rounded-sm outline-none hover:text-tint-text focus-visible:outline-2 focus-visible:outline-(--focus) disabled:hover:text-label-1" aria-label={t("crbs.roomInfo.open", { name: b.room_name })} data-testid={`mine-room-${b.id}`}>
                  {b.room_name}
                </button>
                <span> · {b.period_name}</span>
                {b.time_start ? <span className="ml-1.5 font-normal text-label-3 tabular-nums">{fmt.time(b.time_start)}</span> : null}
              </span>
              <button type="button" onClick={() => onOpen(b.id)} className="flex w-full items-center gap-1 truncate rounded-sm text-left type-footnote text-label-2 outline-none hover:text-label-1 focus-visible:outline-2 focus-visible:outline-(--focus)">
                {b.type === "recurring" ? <Repeat className="size-3 shrink-0" aria-label={t("crbs.legend.recurring")} /> : null}
                {fmt.long(b.date)}
                {showUser && b.user_name ? ` · ${b.user_name}` : ""}
                {b.notes ? ` · ${b.notes}` : ""}
              </button>
            </span>
            {b.status !== "BOOKED" ? <span className="shrink-0 type-footnote font-medium text-label-3">{t("crbs.status.cancelled")}</span> : null}
          </div>
        </li>
      ))}
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
      <Card variant="glass" className="gap-3 px-4">
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
