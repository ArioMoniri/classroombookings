"use client";
/**
 * /bookings — the CRBS booking grid on Liquid Glass. Chrome (toolbar, tray, sheets) is glass; the grid is
 * opaque. State lives in the URL (?display=day|room&date=&group=&room=&term=) so a view can be shared.
 */
import { ChevronLeft, ChevronRight, CircleSlash, Info, Layers, ListChecks, Printer, Wrench, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Toolbar, ToolbarButton, ToolbarLabel } from "@/components/ui/toolbar";
import { Skeleton } from "@/components/ui/skeleton";
import { crbs, crbsError, useBookingContext, useBookingDates, useBookingGrid, useCrbsMe, useOrgPublic, type Grid, type GridQuery, type GridSlot } from "@/lib/api/crbs";
import { bookingCapabilities, hasPermission } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import { Alert, PageTitle, SelectField } from "@/components/admin/kit";
import { BookSheet, type BookTarget } from "./book-sheet";
import { BookingDetailSheet } from "./booking-detail-sheet";
import { BookingGrid, reasonKey, TONE_CLASS, TONE_ICON } from "./booking-grid";
import { bookingErrorMessage } from "./booking-errors";
import { DatePicker } from "./date-picker";
import { isSelectable, slotKey, type SlotTone } from "./grid-model";
import { MultiBookDialog } from "./multi-book-dialog";
import { RoomInfoSheet } from "./room-info-sheet";
import { EntityIcon } from "@/components/admin/icons";
import { useBookingFormat, useProfileLanguage } from "./use-booking-format";
import { useIsPhone } from "./use-is-phone";

type Display = "day" | "room";

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
  const dates = useBookingDates({ term_id: g?.term.id }, !!g);
  const rooms = useQuery({ queryKey: ["crbs", "booking-rooms"], queryFn: () => crbs.bookings.rooms(), enabled: ctx.isSuccess, retry: false, staleTime: 60_000 });
  const roomIcons = useMemo(() => new Map((rooms.data ?? []).map((r) => [r.id, r.icon])), [rooms.data]);
  const highlight = num("highlight") ?? null;
  const [roomInfo, setRoomInfo] = useState<number | null>(null);

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
        if (!isSelectable(slot)) {
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

  const weekById = useMemo(() => new Map((dates.data?.weeks ?? []).map((w) => [w.id, w])), [dates.data]);

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
          max != null ? (
            <p className="type-callout text-label-2" data-testid="limits" aria-live="polite">
              {t("crbs.limits.pill", { remaining: remaining ?? 0, max })}
            </p>
          ) : null
        }
        className="mb-0 print:hidden"
      />

      {org.data?.maintenance_mode && caps.bypassMaintenance ? <Alert tone="warning" title={t("crbs.maintenance.bypassTitle")}>{org.data.maintenance_message || t("crbs.maintenance.bypass")}</Alert> : null}

      <Toolbar placement="inline" data-print-hide className="sticky top-2 z-30 h-auto w-full flex-wrap justify-start gap-2 rounded-3xl p-1.5 md:rounded-full" aria-label={t("crbs.toolbar.label")}>
        <SegmentedGlass<Display>
          aria-label={t("crbs.toolbar.display")}
          size="sm"
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
        <div className="flex items-center gap-1">
          <ToolbarButton size="icon-sm" aria-label={display === "day" ? t("crbs.toolbar.prevDay") : t("crbs.toolbar.prevWeek")} disabled={!g?.nav.prev} onClick={() => setParams({ date: g?.nav.prev })} data-testid="nav-prev">
            <ChevronLeft />
          </ToolbarButton>
          {g ? (
            <DatePicker
              value={display === "day" ? g.date : (g.dates[0]?.date ?? g.date)}
              onChange={(d) => setParams({ date: d })}
              dates={dates.data?.dates ?? []}
              weeks={dates.data?.weeks ?? []}
              termStart={g.term.start}
              termEnd={g.term.end}
              today={dates.data?.today}
              fmt={fmt}
            />
          ) : (
            <Skeleton className="h-8 w-48 rounded-full" />
          )}
          <ToolbarButton size="icon-sm" aria-label={display === "day" ? t("crbs.toolbar.nextDay") : t("crbs.toolbar.nextWeek")} disabled={!g?.nav.next} onClick={() => setParams({ date: g?.nav.next })} data-testid="nav-next">
            <ChevronRight />
          </ToolbarButton>
          <ToolbarButton onClick={() => setParams({ date: dates.data?.today ?? null })}>{t("crbs.toolbar.today")}</ToolbarButton>
        </div>
        <ToolbarButton size="icon-sm" aria-label={t("crbs.toolbar.print")} onClick={() => window.print()} data-testid="print">
          <Printer />
        </ToolbarButton>
        {display === "room" ? (
          <label className="flex min-w-40 items-center gap-2">
            <span className="sr-only">{t("crbs.toolbar.room")}</span>
            <SelectField value={String(g?.rooms[0]?.id ?? "")} onChange={(e) => setParams({ room: e.target.value })} aria-label={t("crbs.toolbar.room")} data-testid="room-select">
              {(rooms.data ?? g?.rooms ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </SelectField>
            {g?.rooms[0] ? (
              <ToolbarButton size="icon-sm" aria-label={t("crbs.roomInfo.open", { name: g.rooms[0].name })} onClick={() => setRoomInfo(g.rooms[0]?.id ?? null)}>
                <Info />
              </ToolbarButton>
            ) : null}
          </label>
        ) : null}
        {sessions.length > 1 ? (
          <label className="flex min-w-40 items-center gap-2">
            <span className="sr-only">{t("crbs.toolbar.session")}</span>
            <SelectField value={String(g?.term.id ?? "")} aria-label={t("crbs.toolbar.session")} onChange={(e) => setParams({ term: e.target.value, date: null })}>
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </SelectField>
          </label>
        ) : null}
        <div className="ml-auto flex items-center gap-1">
          {caps.single || caps.recurring ? (
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
          ) : null}
        </div>
      </Toolbar>

      {display === "day" && groups.length > 1 ? (
        <nav aria-label={t("crbs.toolbar.groups")} data-print-hide className="-mx-1 overflow-x-auto px-1 scrollbar-thin">
          <SegmentedGlass<string>
            aria-label={t("crbs.toolbar.groups")}
            size="sm"
            value={String(g?.room_group_id ?? groups[0]?.id ?? "")}
            onValueChange={(v) => {
              setSelected(new Set());
              setParams({ group: v });
            }}
            options={groups.map((gr) => ({ value: String(gr.id), label: gr.id === 0 ? t("crbs.grid.ungrouped") : gr.name, icon: <Layers aria-hidden /> }))}
          />
        </nav>
      ) : null}

      {g?.problems.includes("no_schedule") ? (
        <Alert tone="warning" title={t("crbs.problems.noScheduleTitle")}>
          {t("crbs.problems.noSchedule")}{" "}
          {hasPermission(me.data?.permissions, "setup.sessions") ? (
            <Link className="font-medium underline" href="/admin/sessions">
              {t("crbs.problems.fix")}
            </Link>
          ) : null}
        </Alert>
      ) : null}
      {g?.problems.includes("no_rooms") ? (
        <Alert tone="info" title={t("crbs.problems.noRoomsTitle")}>
          {t("crbs.problems.noRooms")}{" "}
          {hasPermission(me.data?.permissions, "setup.rooms") ? (
            <Link className="font-medium underline" href="/admin/rooms">
              {t("crbs.problems.fix")}
            </Link>
          ) : null}
        </Alert>
      ) : null}
      {grid.isError ? <Alert tone="error">{bookingErrorMessage(crbsError(grid.error), t, { formatDate: fmt.short })}</Alert> : null}

      <div aria-busy={grid.isFetching} className="relative">
        {g ? (
          <BookingGrid grid={g} columns={fitColumns} fmt={fmt} multi={multi} selected={selected} onActivate={onActivate} crosshair={!!ctx.data?.display.grid_highlight} highlightBookingId={highlight} roomIcons={roomIcons} onRoomInfo={setRoomInfo} />
        ) : grid.isLoading || ctx.isLoading ? (
          <Skeleton className="h-[420px] w-full rounded-xl" />
        ) : null}
      </div>

      <Legend />

      {multi && selected.size > 0 ? (
        <Toolbar placement="floating-bottom" aria-label={t("crbs.multi.tray")} data-testid="multi-tray" data-print-hide>
          <ToolbarLabel className="px-2 type-callout text-label-1" aria-live="polite">
            {t("crbs.multi.selected", { n: selected.size })}
          </ToolbarLabel>
          <ToolbarButton onClick={() => setSelected(new Set())}>
            <X aria-hidden />
            {t("crbs.multi.clear")}
          </ToolbarButton>
          <Button size="sm" onClick={() => setMultiOpen(true)} data-testid="multi-book">
            {t("crbs.multi.book")}
          </Button>
        </Toolbar>
      ) : null}

      <BookSheet target={book} onOpenChange={(o) => !o && setBook(null)} fmt={fmt} />
      <BookingDetailSheet bookingId={detail} onOpenChange={(o) => !o && setDetail(null)} fmt={fmt} />
      <SlotInfoSheet info={info} onOpenChange={(o) => !o && setInfo(null)} />
      <RoomInfoSheet roomId={roomInfo} onOpenChange={(o) => !o && setRoomInfo(null)} />
      <MultiBookDialog
        open={multiOpen}
        onOpenChange={setMultiOpen}
        slotKeys={[...selected]}
        termId={g?.term.id}
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

function SlotInfoSheet({ info, onOpenChange }: { info: { slot: GridSlot; grid: Grid } | null; onOpenChange: (o: boolean) => void }) {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  const phone = useIsPhone();
  const room = info?.grid.rooms.find((r) => r.id === info.slot.room_id);
  const period = info?.grid.periods.find((p) => p.id === info.slot.period_id);
  const s = info?.slot;
  const message = !s
    ? ""
    : s.status === "timetable"
      ? t("crbs.slot.timetableInfo", { label: s.label ?? "", room: room?.name ?? "", period: period?.name ?? "" })
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
  { tone: "timetable", key: "crbs.legend.timetable" },
  { tone: "holiday", key: "crbs.legend.holiday" },
  { tone: "unavailable", key: "crbs.legend.unavailable" },
];

function Legend() {
  const { t } = useI18n();
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-2 type-footnote text-label-2" aria-label={t("crbs.legend.label")}>
      {LEGEND.map(({ tone, key }) => {
        const Icon = TONE_ICON[tone];
        return (
          <li key={tone} className="flex items-center gap-1.5">
            <span aria-hidden className={`flex size-5 items-center justify-center rounded-[5px] shadow-[0_0_0_1px_var(--hairline)] ${TONE_CLASS[tone]}`}>
              <Icon className="size-3" />
            </span>
            {t(key)}
          </li>
        );
      })}
    </ul>
  );
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
