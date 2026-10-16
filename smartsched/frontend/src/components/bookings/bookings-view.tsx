"use client";
/**
 * /bookings — the CRBS booking grid on Liquid Glass, and the reservation panel around it. Chrome (toolbar,
 * tray, sheets) is glass; the grid and the free-slot list are opaque. State lives in the URL
 * (?display=day|room&date=&group=&room=&term=&lens=grid|free&scope=day|week) so a view can be shared; the
 * department lens is remembered per user.
 *
 * Reserve: a free cell (or a period in the "Free slots" lens) opens the booking sheet with room, date and
 * period; drag / Shift-click selects a span. Room names open the room details with "Other available rooms".
 */
import { CalendarSync, ChevronLeft, ChevronRight, CircleSlash, DoorOpen, Info, LayoutGrid, Layers, List, ListChecks, Printer, Search, SlidersHorizontal, Trash2, Wrench, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useState, type ReactNode } from "react";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useBusyDelay } from "@/components/ui/busy-label";
import { Chip } from "@/components/ui/chip";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Toolbar, ToolbarButton, ToolbarLabel } from "@/components/ui/toolbar";
import { Skeleton } from "@/components/ui/skeleton";
import { crbs, crbsError, crbsKeys, useBookingContext, useBookingDates, useBookingGrid, useCrbsMe, useOrgPublic, type Grid, type GridQuery, type GridSlot } from "@/lib/api/crbs";
import { bookingCapabilities, hasPermission } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import { Alert, PageTitle, SelectField } from "@/components/admin/kit";
import { BookSheet, type BookTarget } from "./book-sheet";
import { ConflictBanner } from "@/components/conflicts/conflict-banner";
import { PolicyWhy } from "@/components/policies/policy-why";
import { useApprovalFirst, violationText } from "@/lib/api/booking-policies";
import { useMyRequests } from "@/lib/api/wave1";
import { BookingDetailSheet } from "./booking-detail-sheet";
import { BookingGrid, pickKind, reasonKey, TONE_CLASS, TONE_ICON } from "./booking-grid";
import { bookingErrorMessage } from "./booking-errors";
import { DatePicker } from "./date-picker";
import { isSelectable, slotKey, timetableMissing, type SlotTone } from "./grid-model";
import { MultiBookDialog } from "./multi-book-dialog";
import { RoomInfoSheet, useNow, type RoomContext } from "./room-info-sheet";
import { CalendarSyncPanel } from "./calendar-sync";
import { CancelManyDialog } from "./cancel-many-dialog";
import { DepartmentBar, useDepartmentLens } from "./department-lens";
import { FreeSlotsList } from "./free-slots-list";
import { addDays } from "./date-format";
import { freeSlotsByRoom } from "./reserve-model";
import { EntityIcon } from "@/components/admin/icons";
import { useBookingFormat, useProfileLanguage } from "./use-booking-format";
import { useIsCompact, useIsPhone } from "./use-is-phone";

type Display = "day" | "room";
type Lens = "grid" | "free";
type Scope = "day" | "week";

export function BookingsView() {
  const { t } = useI18n();
  usePrintInLight();
  useProfileLanguage();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const qc = useQueryClient();
  const fmt = useBookingFormat();
  const ctx = useBookingContext();
  const me = useCrbsMe();
  const org = useOrgPublic();
  const caps = bookingCapabilities(me.data?.permissions);

  const display = (params.get("display") as Display | null) ?? ctx.data?.display.type ?? "day";
  const num = (k: string) => (params.get(k) ? Number(params.get(k)) : undefined);
  const query: GridQuery = { display, date: params.get("date") ?? undefined, term_id: num("term"), room_group_id: num("group"), room_id: num("room") };
  const grid = useBookingGrid(query, ctx.isSuccess);
  const g = grid.data;
  // T-R1-10: approval-first on for this viewer -> every free slot says "Talep et · Onay gerekir"
  const approvalFirst = useApprovalFirst(g?.rooms[0]?.id, g?.term.id);
  // T-R1-14: the own open requests of the free-slot list link to the request (booking id -> request id)
  const myRequests = useMyRequests(!!g && g.slots.some((s) => s.reason === "pending" && s.booking?.is_owner));
  const requestFor = useCallback((bookingId: number) => myRequests.data?.find((r) => r.bookings.some((b) => b.id === bookingId))?.id ?? null, [myRequests.data]);
  // motion audit T2: the previous grid stays while the next one loads (keepPreviousData). The date control shows
  // the requested day in the input frame, and after 120 ms the stale grid dims (opacity only, no travel)
  const pendingDate = grid.isPlaceholderData ? (query.date ?? null) : null;
  const stale = useBusyDelay(!!g && grid.isPlaceholderData, 120);
  const dates = useBookingDates({ term_id: g?.term.id }, !!g);
  const rooms = useQuery({ queryKey: ["crbs", "booking-rooms"], queryFn: () => crbs.bookings.rooms(), enabled: ctx.isSuccess, retry: false, staleTime: 60_000 });
  const roomIcons = useMemo(() => new Map((rooms.data ?? []).map((r) => [r.id, r.icon])), [rooms.data]);
  const highlight = num("highlight") ?? null;
  const [roomInfo, setRoomInfo] = useState<{ id: number; context: RoomContext } | null>(null);
  const phone = useIsPhone();
  const compact = useIsCompact();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const lens: Lens = (params.get("lens") as Lens | null) ?? (phone ? "free" : "grid");
  const scope: Scope = params.get("scope") === "week" ? "week" : "day";
  const [department, setDepartment, myDepartment] = useDepartmentLens();
  const [syncOpen, setSyncOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const now = useNow();

  const [multi, setMulti] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [book, setBook] = useState<BookTarget | null>(null);
  const [detail, setDetail] = useState<number | null>(null);
  const [info, setInfo] = useState<{ slot: GridSlot; grid: Grid } | null>(null);
  const [multiOpen, setMultiOpen] = useState(false);

  const setParams = useCallback(
    (patch: Record<string, string | number | null | undefined>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === null || v === undefined || v === "") next.delete(k);
        else next.set(k, String(v));
      }
      router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    },
    [params, pathname, router],
  );

  const onActivate = useCallback(
    (slot: GridSlot) => {
      if (!g) return;
      if (multi) {
        if (!pickKind(slot)) {
          if (slot.status === "booked" && slot.booking) setDetail(slot.booking.id);
          return;
        }
        setSelected((prev) => {
          const next = new Set(prev);
          const k = slotKey(slot);
          if (next.has(k)) next.delete(k);
          else next.add(k);
          return next;
        });
        return;
      }
      if (slot.status === "booked" && slot.booking) setDetail(slot.booking.id);
      else if (isSelectable(slot)) setBook({ slot, grid: g });
      else setInfo({ slot, grid: g });
    },
    [g, multi],
  );

  const onSpan = useCallback((slots: GridSlot[]) => g && slots[0] && setBook({ slot: slots[0], grid: g, span: slots }), [g]);
  const openRoom = useCallback((id: number, context: RoomContext = {}) => setRoomInfo({ id, context: { termId: g?.term.id, date: g?.display === "day" ? g.date : undefined, ...context } }), [g]);
  // stable, so the memoised grid does not re-render when a sheet opens (motion audit T3)
  const onGridRoomInfo = useCallback((id: number) => openRoom(id), [openRoom]);
  const otherRooms = useCallback(
    (target: BookTarget) => {
      const span = target.span?.length ? target.span : [target.slot];
      const periods = span.map((s) => target.grid.periods.find((p) => p.id === s.period_id)).filter((p): p is NonNullable<typeof p> => !!p);
      setBook(null);
      openRoom(target.slot.room_id, { date: target.slot.date, periods, termId: target.grid.term.id });
    },
    [openRoom],
  );

  const weekById = useMemo(() => new Map((dates.data?.weeks ?? []).map((w) => [w.id, w])), [dates.data]);
  const slotByKey = useMemo(() => new Map((g?.slots ?? []).map((x) => [slotKey(x), x])), [g?.slots]);
  const bookKeys = [...selected].filter((k) => isSelectable(slotByKey.get(k)));
  const cancelIds = [...selected].map((k) => slotByKey.get(k)).filter((x) => x?.status === "booked" && x.booking?.can_cancel).map((x) => x!.booking!.id);

  // Free slots lens: the day grid, or the open days of its week (same group) for "Week"
  const weekDates = useMemo(() => {
    if (!g || g.display !== "day" || lens !== "free" || scope !== "week") return [];
    const monday = addDays(g.date, -(((new Date(`${g.date}T12:00:00`).getDay() + 6) % 7)));
    const open = new Map((dates.data?.dates ?? []).map((d) => [d.date, d]));
    return Array.from({ length: 7 }, (_, i) => addDays(monday, i)).filter((d) => open.get(d)?.open && !open.get(d)?.holiday);
  }, [dates.data?.dates, g, lens, scope]);
  const weekGrids = useQueries({
    queries: weekDates.map((d) => {
      const q: GridQuery = { display: "day", date: d, term_id: g?.term.id, room_group_id: g?.room_group_id ?? undefined };
      return { queryKey: crbsKeys.grid(q), queryFn: () => crbs.bookings.grid(q), staleTime: 10_000, retry: false };
    }),
  });
  const deptRooms = useQuery({
    queryKey: ["crbs", "department-rooms", department === "all" ? null : department, g?.term.id],
    queryFn: () => crbs.bookings.departmentRooms(department === "all" ? 0 : department, g?.term.id, 8),
    enabled: department !== "all" && !!g,
    retry: false,
    staleTime: 60_000,
  });
  const weekData = weekGrids.map((x) => x.data);
  const weekKey = weekData.map((x) => x?.date ?? "").join(",") + weekGrids.map((x) => x.dataUpdatedAt).join(",");
  const firstRooms = useMemo(() => new Set((deptRooms.data?.rooms ?? []).map((r) => r.room_id)), [deptRooms.data]);
  const freeRooms = useMemo(
    () => {
      const grids = scope === "week" && g?.display === "day" ? weekData.filter((x): x is Grid => !!x) : g ? [g] : [];
      return freeSlotsByRoom(grids, { now, firstRooms });
    },
    // weekKey stands for the week grids (a new array every render)
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [scope, g, weekKey, now, firstRooms],
  );

  if (ctx.isError) {
    const err = crbsError(ctx.error);
    if (err.status === 503) {
      return (
        <section className="max-w-xl py-10" aria-labelledby="maint-title">
          <Wrench className="mb-3 size-6 text-label-2" aria-hidden />
          <h1 id="maint-title" className="type-title-2 text-label-1">
            {t("crbs.maintenance.title")}
          </h1>
          <p className="mt-2 type-body text-label-2" data-testid="maintenance-message">
            {err.message || t("crbs.maintenance.default")}
          </p>
        </section>
      );
    }
    return <Alert tone="error">{bookingErrorMessage(err, t)}</Alert>;
  }

  const day = g?.date ?? params.get("date") ?? "";
  const dayInfo = g?.dates.find((d) => d.date === day) ?? g?.dates[0];
  const week = dayInfo?.timetable_week_id != null ? weekById.get(dayInfo.timetable_week_id) : undefined;
  const groups = ctx.data?.display.use_room_groups ? (ctx.data?.room_groups ?? []) : [];
  const sessions = ctx.data?.sessions ?? [];
  const remaining = g?.remaining_bookings ?? ctx.data?.remaining_bookings;
  const max = g?.limits.max_active_bookings ?? ctx.data?.limits.max_active_bookings;
  const columns = ctx.data?.display.columns ?? "periods";
  const fitColumns = display === "day" ? (columns === "days" ? "periods" : columns) : columns === "rooms" ? "periods" : columns;

  const goToday = () => setParams({ date: dates.data?.today ?? null });
  const datePickerProps = (gr: Grid) => ({
    value: pendingDate ?? (display === "day" ? gr.date : (gr.dates[0]?.date ?? gr.date)),
    onChange: (d: string) => setParams({ date: d }),
    dates: dates.data?.dates ?? [],
    weeks: dates.data?.weeks ?? [],
    termStart: gr.term.start,
    termEnd: gr.term.end,
    today: dates.data?.today,
    fmt,
  });
  // the filters the sheet changes away from the defaults (the compact trigger says "Filters · n")
  const activeFilters = [display === "room", lens === "free" && display === "day" && scope === "week", display === "day" && groups.length > 1 && params.has("group"), params.has("term"), department !== "all"].filter(Boolean).length;
  const resetFilters = () => {
    setSelected(new Set());
    setDepartment("all");
    setParams({ display: null, scope: null, group: null, term: null, room: null });
  };
  const navPrev = (
    <ToolbarButton size={compact ? "icon" : "icon-sm"} className="shrink-0" aria-label={display === "day" ? t("crbs.toolbar.prevDay") : t("crbs.toolbar.prevWeek")} disabled={!g?.nav.prev} onClick={() => setParams({ date: g?.nav.prev })} data-testid="nav-prev">
      <ChevronLeft />
    </ToolbarButton>
  );
  const navNext = (
    <ToolbarButton size={compact ? "icon" : "icon-sm"} className="shrink-0" aria-label={display === "day" ? t("crbs.toolbar.nextDay") : t("crbs.toolbar.nextWeek")} disabled={!g?.nav.next} onClick={() => setParams({ date: g?.nav.next })} data-testid="nav-next">
      <ChevronRight />
    </ToolbarButton>
  );
  const printButton = (
    <ToolbarButton size="icon-sm" aria-label={t("crbs.toolbar.print")} onClick={() => window.print()} data-testid="print">
      <Printer />
    </ToolbarButton>
  );
  const lensControl = (labelledBy?: string) => (
    <SegmentedControl<Lens>
      aria-label={labelledBy ? undefined : t("reserve.lens.label")}
      aria-labelledby={labelledBy}
      size="sm"
      fill={!!labelledBy}
      value={lens}
      onValueChange={(v) => {
        setSelected(new Set());
        setMulti(false);
        setParams({ lens: v });
      }}
      options={[
        { value: "grid", label: t("reserve.lens.grid"), icon: <LayoutGrid aria-hidden /> },
        { value: "free", label: t("reserve.lens.free"), icon: <List aria-hidden /> },
      ]}
      data-testid="lens"
    />
  );
  const displayControl = () => (
    <SegmentedControl<Display>
      aria-label={t("crbs.toolbar.display")}
      size="sm"
      fill={compact}
      value={display}
      onValueChange={(v) => {
        setSelected(new Set());
        setParams({ display: v, group: null });
      }}
      options={[
        { value: "day", label: t("crbs.toolbar.byDay") },
        { value: "room", label: t("crbs.toolbar.byRoom") },
      ]}
    />
  );
  const scopeControl = () => (
    <SegmentedControl<Scope>
      aria-label={t("reserve.free.scope")}
      size="sm"
      fill={compact}
      value={scope}
      onValueChange={(v) => setParams({ scope: v === "day" ? null : v })}
      options={[
        { value: "day", label: t("reserve.free.day") },
        { value: "week", label: t("reserve.free.week") },
      ]}
    />
  );
  const groupControl = (labelledBy?: string) => (
    <SegmentedControl<string>
      aria-label={labelledBy ? undefined : t("crbs.toolbar.groups")}
      aria-labelledby={labelledBy}
      size="sm"
      fill={!!labelledBy}
      value={String(g?.room_group_id ?? groups[0]?.id ?? "")}
      onValueChange={(v) => {
        setSelected(new Set());
        setParams({ group: v });
      }}
      options={groups.map((gr) => {
        const name = gr.id === 0 ? t("crbs.grid.ungrouped") : gr.name;
        return { value: String(gr.id), label: gr.room_count != null ? t("reserve.toolbar.groupCount", { name, n: gr.room_count }) : name, icon: <Layers aria-hidden /> };
      })}
    />
  );
  const roomPicker = (wide = false) => (
    <>
      <span className="sr-only">{t("crbs.toolbar.room")}</span>
      <SelectField value={String(g?.rooms[0]?.id ?? "")} onChange={(e) => setParams({ room: e.target.value })} aria-label={t("crbs.toolbar.room")} className={wide ? "min-w-0 flex-1" : undefined} data-testid="room-select">
        {/* CRBS filter/room.php: rooms under their room group */}
        {roomOptions(rooms.data ?? [], g?.rooms ?? [], t("reserve.toolbar.ungrouped")).map((grp) =>
          grp.label === null ? (
            grp.rooms.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))
          ) : (
            <optgroup key={grp.label} label={grp.label}>
              {grp.rooms.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </optgroup>
          ),
        )}
      </SelectField>
      {g?.rooms[0] ? (
        <ToolbarButton size="icon-sm" aria-label={t("crbs.roomInfo.open", { name: g.rooms[0].name })} onClick={() => g.rooms[0] && (setFiltersOpen(false), openRoom(g.rooms[0].id, { date: g.date }))}>
          <Info />
        </ToolbarButton>
      ) : null}
    </>
  );
  const sessionPicker = (wide = false) => (
    <>
      <span className="sr-only">{t("crbs.toolbar.session")}</span>
      <SelectField value={String(g?.term.id ?? "")} aria-label={t("crbs.toolbar.session")} onChange={(e) => setParams({ term: e.target.value, date: null })} className={wide ? "w-full" : undefined} data-testid="session-select">
        {/* CRBS grid/Controls.php: "Current and future" and "Past" */}
        {[
          { label: t("reserve.toolbar.current"), items: sessions.filter((s) => s.is_current || !dates.data?.today || s.end >= dates.data.today) },
          { label: t("reserve.toolbar.past"), items: sessions.filter((s) => !s.is_current && !!dates.data?.today && s.end < dates.data.today) },
        ]
          .filter((x) => x.items.length)
          .map((x) => (
            <optgroup key={x.label} label={x.label}>
              {x.items.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </optgroup>
          ))}
      </SelectField>
    </>
  );
  const multiChip =
    (caps.single || caps.recurring) && lens === "grid" ? (
      <Chip
        selected={multi}
        onSelectedChange={(v) => {
          setMulti(v);
          if (!v) setSelected(new Set());
        }}
        icon={<ListChecks aria-hidden />}
        data-testid="multi-toggle"
      >
        {t("crbs.toolbar.multi")}
      </Chip>
    ) : null;

  const subtitle = g ? (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <span>{g.term.name}</span>
      {dayInfo?.term_week ? <span>· {t("crbs.grid.termWeek", { n: dayInfo.term_week })}</span> : null}
      {week ? (
        <span className="inline-flex items-center gap-1.5">
          · <span aria-hidden className="inline-block size-2.5 rounded-full" style={{ background: week.bgcol }} />
          <EntityIcon name={week.icon} />
          {week.name}
        </span>
      ) : null}
      {dayInfo?.holiday ? <span className="font-medium text-label-1">· {dayInfo.holiday}</span> : null}
    </span>
  ) : null;

  return (
    <div className="flex flex-col gap-4 pb-24 print:gap-2 print:pb-0" data-print-area>
      <style>{PRINT_CSS}</style>
      <div className="hidden print:block">
        <p className="type-headline">{org.data?.name ?? ""}</p>
        <p className="type-callout">
          {g ? (display === "day" ? fmt.long(g.date) : `${fmt.long(g.dates[0]?.date ?? g.date)} – ${fmt.long(g.dates[g.dates.length - 1]?.date ?? g.date)}`) : ""}
          {display === "day" && groups.length > 1 ? ` · ${groups.find((x) => x.id === g?.room_group_id)?.name ?? ""}` : ""}
          {display === "room" && g?.rooms[0] ? ` · ${g.rooms[0].name}` : ""}
        </p>
      </div>
      <PageTitle
        title={t("crbs.bookings.title")}
        subtitle={subtitle}
        actions={
          <>
            {max != null ? (
              <p className="type-callout text-label-2" data-testid="limits" aria-live="polite">
                {t("crbs.limits.pill", { remaining: remaining ?? 0, max })}
              </p>
            ) : null}
            {/* T1: the same day in "Find a room" (wave 1) */}
            <Button variant="outline" size="sm" render={<Link href={g ? `/find-room?date=${display === "day" ? g.date : (g.dates[0]?.date ?? g.date)}` : "/find-room"} />} nativeButton={false} data-testid="bookings-find-room">
              <Search aria-hidden />
              {t("wave1.find.title")}
            </Button>
          </>
        }
        className="mb-0 print:hidden"
      />

      {org.data?.maintenance_mode && caps.bypassMaintenance ? <Alert tone="warning" title={t("crbs.maintenance.bypassTitle")}>{org.data.maintenance_message || t("crbs.maintenance.bypass")}</Alert> : null}
      {/* P2: planners see the open clashes of a newly published timetable, with a link to the resolver */}
      <ConflictBanner />

      {compact ? (
        <Toolbar placement="inline" data-print-hide className="sticky top-2 z-30 h-auto w-full flex-nowrap gap-1 p-1" aria-label={t("crbs.toolbar.label")} data-testid="bookings-toolbar">
          {navPrev}
          {g ? (
            <DatePicker {...datePickerProps(g)} compact onToday={goToday} className="flex-1" />
          ) : (
            <Skeleton className="h-(--control-h-md) min-w-0 flex-1 rounded-full" />
          )}
          {navNext}
          <ToolbarButton size="md" onClick={() => setFiltersOpen(true)} aria-haspopup="dialog" className="shrink-0" data-testid="filters-open">
            <SlidersHorizontal aria-hidden />
            {activeFilters ? t("reserve.filters.openCount", { n: activeFilters }) : t("reserve.filters.open")}
          </ToolbarButton>
        </Toolbar>
      ) : (
        <Toolbar placement="inline" data-print-hide className="sticky top-2 z-30 h-auto w-full flex-wrap justify-start gap-2 rounded-3xl p-1.5 md:rounded-full" aria-label={t("crbs.toolbar.label")} data-testid="bookings-toolbar">
          {lensControl()}
          {displayControl()}
          <div className="flex items-center gap-1">
            {navPrev}
            {g ? <DatePicker {...datePickerProps(g)} /> : <Skeleton className="h-8 w-48 rounded-full" />}
            {navNext}
            <ToolbarButton onClick={goToday}>{t("crbs.toolbar.today")}</ToolbarButton>
          </div>
          {printButton}
          {display === "room" ? <label className="flex min-w-40 items-center gap-2">{roomPicker()}</label> : null}
          {sessions.length > 1 ? <label className="flex min-w-40 items-center gap-2">{sessionPicker()}</label> : null}
          <div className="ml-auto flex items-center gap-1">
            {lens === "free" && display === "day" ? scopeControl() : null}
            <ToolbarButton onClick={() => setSyncOpen(true)} aria-label={t("reserve.sync.title")} data-testid="sync-open">
              <CalendarSync aria-hidden />
              <span className="hidden lg:inline">{t("reserve.sync.open")}</span>
            </ToolbarButton>
            {multiChip}
          </div>
        </Toolbar>
      )}

      {!compact && display === "day" && groups.length > 1 ? (
        <nav aria-label={t("crbs.toolbar.groups")} data-print-hide className="-mx-1 overflow-x-auto px-1 scrollbar-thin" data-testid="group-tabs">
          {groupControl()}
        </nav>
      ) : null}

      <DepartmentBar grid={g} value={department} onChange={setDepartment} mine={myDepartment} termId={g?.term.id} onRoomInfo={(id) => openRoom(id)} part={compact ? "strip" : "all"} />

      <Sheet open={compact && filtersOpen} onOpenChange={setFiltersOpen}>
        <SheetContent side={phone ? "bottom" : "right"} className="gap-0 data-[side=bottom]:max-h-[92dvh] data-[side=right]:sm:max-w-md" data-testid="filters-sheet">
          <SheetHeader className="px-5 pt-5">
            <SheetTitle className="type-title-3">{t("reserve.filters.title")}</SheetTitle>
            <SheetDescription>{t("reserve.filters.lead")}</SheetDescription>
          </SheetHeader>
          <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto overscroll-contain px-5 pt-4 pb-5">
            <FilterGroup label={t("reserve.filters.view")}>
              {(id) => (
                <>
                  {lensControl(id)}
                  {displayControl()}
                  {lens === "free" && display === "day" ? scopeControl() : null}
                </>
              )}
            </FilterGroup>
            {display === "room" ? <FilterGroup label={t("crbs.toolbar.room")}>{() => <div className="flex items-center gap-2">{roomPicker(true)}</div>}</FilterGroup> : null}
            {display === "day" && groups.length > 1 ? <FilterGroup label={t("crbs.toolbar.groups")}>{(id) => groupControl(id)}</FilterGroup> : null}
            {sessions.length > 1 ? <FilterGroup label={t("crbs.toolbar.session")}>{() => sessionPicker(true)}</FilterGroup> : null}
            <DepartmentBar grid={g} value={department} onChange={setDepartment} mine={myDepartment} termId={g?.term.id} onRoomInfo={(id) => (setFiltersOpen(false), openRoom(id))} part="picker" />
            <FilterGroup label={t("reserve.filters.more")}>
              {() => (
                <div className="flex flex-wrap items-center gap-2">
                  {multiChip}
                  <Button variant="outline" size="sm" onClick={() => (setFiltersOpen(false), setSyncOpen(true))} data-testid="sync-open">
                    <CalendarSync aria-hidden />
                    {t("reserve.sync.open")}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => (setFiltersOpen(false), window.setTimeout(() => window.print(), 300))} data-testid="print">
                    <Printer aria-hidden />
                    {t("crbs.toolbar.print")}
                  </Button>
                </div>
              )}
            </FilterGroup>
          </div>
          <div className="flex items-center gap-2 border-t border-hairline px-5 pt-3 pb-[max(1rem,env(safe-area-inset-bottom))] max-sm:pb-4">
            {activeFilters ? (
              <Button variant="ghost" onClick={resetFilters} data-testid="filters-reset">
                {t("reserve.filters.reset")}
              </Button>
            ) : null}
            <Button className="ml-auto min-w-32" onClick={() => setFiltersOpen(false)} data-testid="filters-apply">
              {t("reserve.filters.apply")}
            </Button>
          </div>
        </SheetContent>
      </Sheet>

      {timetableMissing(g) ? (
        <Alert tone="warning" testId="grid-no-timetable">
          {t("wave1.grid.noTimetable")}
        </Alert>
      ) : null}
      {g?.problems.includes("no_schedule") ? (
        <Alert tone="warning" title={t("crbs.problems.noScheduleTitle")}>
          {/* one run of text: the link reads (and is hit-tested, M-02) as part of the sentence */}
          <span>
            {t("crbs.problems.noSchedule")}{" "}
            {hasPermission(me.data?.permissions, "setup.sessions") ? (
              <Link className="font-medium underline" href="/admin/sessions">
                {t("crbs.problems.fix")}
              </Link>
            ) : null}
          </span>
        </Alert>
      ) : null}
      {g?.problems.includes("no_rooms") ? (
        <Alert tone="info" title={t("crbs.problems.noRoomsTitle")}>
          {/* one run of text: the link reads (and is hit-tested, M-02) as part of the sentence */}
          <span>
            {t("crbs.problems.noRooms")}{" "}
            {hasPermission(me.data?.permissions, "setup.rooms") ? (
              <Link className="font-medium underline" href="/admin/rooms">
                {t("crbs.problems.fix")}
              </Link>
            ) : null}
          </span>
        </Alert>
      ) : null}
      {grid.isError ? <Alert tone="error">{bookingErrorMessage(crbsError(grid.error), t, { formatDate: fmt.short })}</Alert> : null}

      <div aria-busy={grid.isFetching} data-stale={stale ? "true" : undefined} className="relative transition-opacity duration-(--dur-fast) data-[stale=true]:opacity-60" data-testid="booking-grid-wrap">
        {g && lens === "free" ? (
          <FreeSlotsList
            rooms={freeRooms}
            loading={grid.isFetching || weekGrids.some((x) => x.isLoading)}
            week={display === "room" || scope === "week"}
            fmt={fmt}
            deptFirst={firstRooms.size > 0 && freeRooms.some((r) => firstRooms.has(r.room.id))}
            onReserve={setBook}
            onRoomInfo={(id, date) => openRoom(id, { date })}
            approvalFirst={approvalFirst}
            requestFor={requestFor}
          />
        ) : g ? (
          <BookingGrid
            grid={g}
            columns={fitColumns}
            fmt={fmt}
            multi={multi}
            selected={selected}
            onActivate={onActivate}
            onSpan={caps.single || caps.recurring ? onSpan : undefined}
            crosshair={!!ctx.data?.display.grid_highlight}
            highlightBookingId={highlight}
            roomIcons={roomIcons}
            onRoomInfo={onGridRoomInfo}
            department={department}
            approvalFirst={approvalFirst}
          />
        ) : grid.isLoading || ctx.isLoading ? (
          <Skeleton className="h-[420px] w-full rounded-xl" />
        ) : null}
      </div>

      {lens === "grid" ? <Legend /> : null}

      {multi && selected.size > 0 ? (
        <Toolbar placement="floating-bottom" aria-label={t("crbs.multi.tray")} data-testid="multi-tray" data-print-hide>
          <ToolbarLabel className="px-2 type-callout text-label-1" aria-live="polite">
            {t("crbs.multi.selected", { n: selected.size })}
          </ToolbarLabel>
          <ToolbarButton onClick={() => setSelected(new Set())}>
            <X aria-hidden />
            {t("crbs.multi.clear")}
          </ToolbarButton>
          {cancelIds.length ? (
            <ToolbarButton onClick={() => setCancelOpen(true)} className="text-status-infeasible-fg" data-testid="multi-cancel">
              <Trash2 aria-hidden />
              {t("reserve.multi.cancelN", { n: cancelIds.length })}
            </ToolbarButton>
          ) : null}
          {bookKeys.length ? (
            <Button size="sm" onClick={() => setMultiOpen(true)} data-testid="multi-book">
              {t("crbs.multi.book")}
            </Button>
          ) : null}
        </Toolbar>
      ) : null}

      <BookSheet target={book} onOpenChange={(o) => !o && setBook(null)} fmt={fmt} onOtherRooms={otherRooms} />
      <BookingDetailSheet bookingId={detail} onOpenChange={(o) => !o && setDetail(null)} fmt={fmt} onRoomInfo={(id, date) => (setDetail(null), openRoom(id, { date }))} />
      <SlotInfoSheet
        info={info}
        onOpenChange={(o) => !o && setInfo(null)}
        onAlternatives={(slot, gr) => {
          const p = gr.periods.find((x) => x.id === slot.period_id);
          setInfo(null);
          openRoom(slot.room_id, { date: slot.date, periods: p ? [p] : undefined, termId: gr.term.id });
        }}
      />
      <RoomInfoSheet roomId={roomInfo?.id ?? null} context={roomInfo?.context} fmt={fmt} onOpenChange={(o) => !o && setRoomInfo(null)} onReserve={setBook} />
      <Sheet open={syncOpen} onOpenChange={setSyncOpen}>
        <SheetContent side={phone ? "bottom" : "right"} className="gap-0 data-[side=bottom]:max-h-[92dvh] data-[side=right]:sm:max-w-lg" data-testid="sync-sheet">
          <SheetHeader className="px-5 pt-5">
            <SheetTitle className="type-title-3">{t("reserve.sync.title")}</SheetTitle>
            <SheetDescription className="sr-only">{t("reserve.sync.lead")}</SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5">
            {syncOpen ? <CalendarSyncPanel roomId={display === "room" ? (g?.rooms[0]?.id ?? null) : null} departmentId={department === "all" ? null : department} /> : null}
          </div>
        </SheetContent>
      </Sheet>
      <CancelManyDialog
        ids={cancelIds}
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        description={t("reserve.multi.cancelBody")}
        onDone={() => {
          setSelected(new Set());
          setCancelOpen(false);
          setMulti(false);
        }}
      />
      <MultiBookDialog
        open={multiOpen}
        onOpenChange={setMultiOpen}
        slotKeys={bookKeys}
        termId={g?.term.id}
        termEnd={g?.term.end}
        fmt={fmt}
        onBooked={() => {
          setSelected(new Set());
          setMulti(false);
          void qc.invalidateQueries({ queryKey: ["crbs", "grid"] });
        }}
      />
    </div>
  );
}

/** A labelled group in the filters sheet; the render prop gets the heading id for aria-labelledby. */
function FilterGroup({ label, children }: { label: string; children: (labelId: string) => ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-2">
      <h3 id={id} className="type-footnote font-medium text-label-2">
        {label}
      </h3>
      {children(id)}
    </section>
  );
}

function SlotInfoSheet({ info, onOpenChange, onAlternatives }: { info: { slot: GridSlot; grid: Grid } | null; onOpenChange: (o: boolean) => void; onAlternatives: (slot: GridSlot, grid: Grid) => void }) {
  const { t, locale } = useI18n();
  const fmt = useBookingFormat();
  const phone = useIsPhone();
  const room = info?.grid.rooms.find((r) => r.id === info.slot.room_id);
  const period = info?.grid.periods.find((p) => p.id === info.slot.period_id);
  const s = info?.slot;
  const message = !s
    ? ""
    : s.status === "timetable"
      ? t("crbs.slot.timetableInfo", { label: s.label || t("reserve.cell.class"), room: room?.name ?? "", period: period?.name ?? "" })
      : s.reason === "policy" && s.policy
        ? violationText(s.policy, locale)
        : t(reasonKey(s.reason), { name: s.label ?? "" });
  return (
    <Sheet open={!!info} onOpenChange={onOpenChange}>
      <SheetContent side={phone ? "bottom" : "right"} className="sm:max-w-md" data-testid="slot-info">
        {s ? (
          <>
            <SheetHeader className="px-5 pt-5">
              <SheetTitle className="type-title-3">
                {room?.name} · {period?.name}
              </SheetTitle>
              <SheetDescription>
                {fmt.long(s.date)}
                {period ? ` · ${fmt.time(period.time_start)}–${fmt.time(period.time_end)}` : ""}
              </SheetDescription>
            </SheetHeader>
            <div className="px-5 pb-5">
              <Alert tone={s.status === "timetable" ? "info" : "warning"} title={s.status === "timetable" ? t("crbs.legend.timetable") : t("crbs.slot.notBookable")} testId="slot-info-message">
                <span className="inline-flex items-center gap-1.5">
                  <CircleSlash className="size-3.5 shrink-0" aria-hidden />
                  {message}
                </span>
              </Alert>
              {/* P8 "Neden?": the rules behind a policy refusal, from GET /booking-policies/effective */}
              {s.reason === "policy" ? <PolicyWhy className="mt-2" query={{ room_id: s.room_id, date: s.date, period_id: s.period_id, term_id: info.grid.term.id }} violation={s.policy} /> : null}
              <Button variant="outline" className="mt-3 min-h-11 sm:min-h-0" onClick={() => onAlternatives(s, info.grid)} data-testid="slot-info-alternatives">
                <DoorOpen aria-hidden />
                {t("reserve.slotInfo.alternatives")}
              </Button>
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

const LEGEND: { tone: SlotTone; key: Parameters<ReturnType<typeof useI18n>["t"]>[0] }[] = [
  { tone: "available", key: "crbs.legend.available" },
  { tone: "booked-mine", key: "crbs.legend.mine" },
  { tone: "booked-single", key: "crbs.legend.single" },
  { tone: "booked-recurring", key: "crbs.legend.recurring" },
  { tone: "booked-pending", key: "wave1.grid.pendingLegend" },
  { tone: "timetable", key: "crbs.legend.timetable" },
  { tone: "holiday", key: "crbs.legend.holiday" },
  { tone: "unavailable", key: "crbs.legend.unavailable" },
];

function Legend() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-2">
    <p className="hidden type-footnote text-label-3 sm:block print:hidden">{t("reserve.grid.hint")}</p>
    <p className="type-footnote text-label-3 sm:hidden print:hidden">{t("reserve.grid.longPress")}</p>
    <ul className="flex flex-wrap gap-x-4 gap-y-2 type-footnote text-label-2" aria-label={t("crbs.legend.label")}>
      {LEGEND.map(({ tone, key }) => {
        const Icon = TONE_ICON[tone];
        return (
          <li key={tone} className="flex items-center gap-1.5">
            <span aria-hidden className={`flex size-5 items-center justify-center rounded-[5px] edge-hairline ${TONE_CLASS[tone]}`}>
              <Icon className="size-3" />
            </span>
            {t(key)}
          </li>
        );
      })}
    </ul>
    </div>
  );
}

/** Room picker options under their room group (CRBS filter/room.php), in the grid's order. */
function roomOptions(infos: { id: number; name: string; group?: string | null }[], fallback: { id: number; name: string }[], ungrouped: string): { label: string | null; rooms: { id: number; name: string }[] }[] {
  if (!infos.length) return [{ label: null, rooms: fallback }];
  const out: { label: string | null; rooms: { id: number; name: string }[] }[] = [];
  for (const r of infos) {
    const label = r.group ?? ungrouped;
    const last = out[out.length - 1];
    if (last && last.label === label) last.rooms.push(r);
    else out.push({ label, rooms: [r] });
  }
  return out.length === 1 ? [{ label: null, rooms: out[0]!.rooms }] : out;
}

/* CRBS print.css: only the grid (with its title and legend) on white paper, landscape, every column on the
   page, colours kept. The shell is not ours, so everything outside the print area is hidden by visibility
   rather than by selectors; the light palette for dark-mode users comes from usePrintInLight(). */
const PRINT_CSS = `@media print {
  @page { size: A4 landscape; margin: 8mm; }
  html, body { background: #fff !important; background-image: none !important; color-scheme: light; }
  body * { visibility: hidden !important; }
  [data-print-area], [data-print-area] * { visibility: visible !important; }
  [data-print-area] { position: absolute; left: 0; top: 0; width: 100%; }
  [data-print-hide], [data-print-hide] * { display: none !important; }
  [data-print-area] * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  [data-testid="booking-grid"] { max-height: none !important; overflow: visible !important; border-radius: 0 !important; }
  [data-testid="booking-grid"] table { width: 100% !important; min-width: 0 !important; table-layout: fixed !important; font-size: 7pt; line-height: 1.15; }
  [data-testid="booking-grid"] col { width: auto !important; }
  [data-testid="booking-grid"] col:first-child { width: 20mm !important; }
  [data-testid="booking-grid"] th { position: static !important; padding: 1mm !important; }
  [data-testid="booking-grid"] thead { display: table-header-group; }
  [data-testid="booking-grid"] tr { break-inside: avoid; }
  [data-testid="booking-grid"] [data-cell] { height: auto !important; min-height: 8mm; padding: 0.6mm 0.8mm !important; outline: none !important; }
  [data-testid="booking-grid"] [data-tone="available"] svg { display: none !important; }
  [data-testid="booking-grid"] button { color: inherit; }
}`;

/** Dark-mode users still print on white: drop the theme class for the print only (CRBS prints light). */
function usePrintInLight() {
  useEffect(() => {
    const root = document.documentElement;
    let restore = false;
    const before = () => {
      restore = root.classList.contains("dark");
      if (restore) root.classList.remove("dark");
    };
    const after = () => {
      if (restore) root.classList.add("dark");
      restore = false;
    };
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
      after();
    };
  }, []);
}
