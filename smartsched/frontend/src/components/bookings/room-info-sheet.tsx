"use client";
/**
 * Room details (CRBS `Rooms::info` / `room_info` plus the reservation panel): photo (enlarges on click),
 * capacity and exam capacity, building, floor, group, location, owner, tags and typed features, notes; the
 * room's bookings and classes on the chosen day, its next free slot; and "Other available rooms" for the
 * same date and period(s), each with one-click Reserve.
 *
 * Alternatives: T1 `POST /rooms/find` ranks them when the backend has it; the day grids of every room group
 * (the same `GET /bookings/grid` the panel shows) decide what is reservable, so a Reserve button is only
 * offered where the grid itself would let the user book. Phones get a bottom sheet (liquid-glass.md §15).
 */
import { useQueries, useQuery } from "@tanstack/react-query";
import { CalendarClock, DoorOpen, GraduationCap, Repeat, User } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { crbs, crbsError, crbsKeys, useBookingContext, useBookingDates, useBookingGrid, type FindOut, type Grid, type GridPeriod, type GridQuery, type RoomInfo } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { Alert, Loading, SelectField } from "@/components/admin/kit";
import { EntityIcon } from "@/components/admin/icons";
import { bookingErrorMessage } from "./booking-errors";
import type { BookTarget } from "./book-sheet";
import type { DateFormatter } from "./date-format";
import { slotText } from "./grid-model";
import { alternativesFromGrids, nextFreeSlot, roomDay, type Alternative, type Now } from "./reserve-model";
import { useIsPhone } from "./use-is-phone";

export interface RoomContext {
  /** the date the user is looking at (default: the booking clock's today) */
  date?: string;
  /** the period(s) asked for; alternatives are computed for them */
  periods?: Pick<GridPeriod, "id" | "start_period" | "end_period" | "time_start" | "time_end" | "name">[];
  termId?: number;
}

/** HH:MM now, only when the browser's date is the backend's booking date (the clock may be pinned) */
export function useNow(): Now | undefined {
  const today = useBookingDates({}).data?.today;
  return useMemo(() => {
    if (!today) return undefined;
    const d = new Date();
    const local = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return { date: today, time: local === today ? `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}` : "00:00" };
  }, [today]);
}

export function RoomInfoSheet({
  roomId,
  onOpenChange,
  context,
  fmt,
  onReserve,
}: {
  roomId: number | null;
  onOpenChange: (o: boolean) => void;
  context?: RoomContext;
  fmt?: DateFormatter;
  onReserve?: (target: BookTarget) => void;
}) {
  const { t } = useI18n();
  const phone = useIsPhone();
  const q = useQuery({ queryKey: ["crbs", "room-info", roomId], queryFn: () => crbs.bookings.room(roomId ?? 0), enabled: roomId !== null, retry: false });
  const r = q.data;
  return (
    <Sheet open={roomId !== null} onOpenChange={onOpenChange}>
      <SheetContent side={phone ? "bottom" : "right"} className="gap-0 data-[side=bottom]:max-h-[92dvh] data-[side=right]:sm:max-w-md" data-testid="room-info">
        {q.isLoading ? <Loading className="px-5" /> : null}
        {q.isError ? (
          <div className="p-5">
            <SheetTitle className="sr-only">{t("crbs.detail.room")}</SheetTitle>
            <Alert tone="error">{bookingErrorMessage(crbsError(q.error), t)}</Alert>
          </div>
        ) : null}
        {r ? <RoomBody key={`${r.id}|${context?.date ?? ""}|${(context?.periods ?? []).map((p) => p.id).join(",")}`} r={r} context={context} fmt={fmt} onReserve={onReserve ? (x) => (onOpenChange(false), onReserve(x)) : undefined} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function RoomBody({ r, context, fmt, onReserve }: { r: RoomInfo; context?: RoomContext; fmt?: DateFormatter; onReserve?: (target: BookTarget) => void }) {
  const { t } = useI18n();
  const [photo, setPhoto] = useState(false);
  const today = useBookingDates({}).data?.today;
  const date = context?.date ?? today;
  const typed = r.fields.filter((f) => f.value !== null && f.value !== "" && f.value !== undefined && f.value !== false);
  const facts: [string, string][] = [
    [t("reserve.room.capacity"), r.capacity ? t("crbs.grid.seats", { n: r.capacity }) : ""],
    [t("reserve.room.examCapacity"), r.exam_capacity ? t("crbs.grid.seats", { n: r.exam_capacity }) : ""],
    [t("reserve.room.building"), r.building ?? ""],
    [t("reserve.room.floor"), r.floor ?? ""],
    [t("reserve.room.group"), r.group ?? ""],
    [t("crbs.rooms.location"), r.location ?? ""],
    [t("crbs.rooms.owner"), r.owner ?? ""],
  ];
  return (
    <>
      <SheetHeader className="px-5 pt-5">
        <SheetTitle className="flex items-center gap-2 type-title-3">
          <EntityIcon name={r.icon} className="size-5" />
          {r.name}
        </SheetTitle>
        <SheetDescription>{[r.group, r.capacity ? t("crbs.grid.seats", { n: r.capacity }) : null].filter(Boolean).join(" · ")}</SheetDescription>
      </SheetHeader>
      <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-5 pb-5">
        {r.photo_url ? (
          <button type="button" onClick={() => setPhoto(true)} aria-label={t("reserve.room.photoOpen")} className="block overflow-hidden rounded-xl outline-none focus-visible:outline-2 focus-visible:outline-(--focus)">
            {/* eslint-disable-next-line @next/next/no-img-element -- uploaded by an administrator, served by the backend */}
            <img src={r.photo_url} alt={t("crbs.rooms.photoAlt", { name: r.name })} className="max-h-60 w-full object-cover" />
          </button>
        ) : null}
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 type-callout" data-testid="room-facts">
          {facts
            .filter(([, v]) => v)
            .map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-label-3">{k}</dt>
                <dd className="text-label-1">{v}</dd>
              </div>
            ))}
          {r.tags.length ? (
            <>
              <dt className="text-label-3">{t("crbs.roomInfo.tags")}</dt>
              <dd className="flex flex-wrap gap-1">
                {r.tags.map((tag) => (
                  <span key={tag} className="rounded-xs bg-fill-2 px-1.5 py-0.5 type-footnote font-medium text-label-1">
                    {tag}
                  </span>
                ))}
              </dd>
            </>
          ) : null}
          {typed.map((f) => (
            <div key={f.field_id} className="contents">
              <dt className="text-label-3">{f.name}</dt>
              <dd className="text-label-1">
                {f.value === true ? t("crbs.common.yes") : Array.isArray(f.value) ? f.value.join(", ") : String(f.value)}
                {f.unit && f.value !== true ? ` ${f.unit}` : ""}
              </dd>
            </div>
          ))}
        </dl>
        {r.notes ? <p className="whitespace-pre-wrap type-callout text-label-2">{r.notes}</p> : null}
        {date && fmt ? <RoomDay room={r} date={date} termId={context?.termId} fmt={fmt} onReserve={onReserve} /> : null}
        {date && fmt ? <OtherRooms room={r} date={date} context={context} fmt={fmt} onReserve={onReserve} /> : null}
      </div>
      <Dialog open={photo} onOpenChange={setPhoto}>
        <DialogContent className="sm:max-w-3xl">
          <DialogTitle className="sr-only">{t("crbs.rooms.photoAlt", { name: r.name })}</DialogTitle>
          {/* eslint-disable-next-line @next/next/no-img-element -- uploaded by an administrator */}
          {r.photo_url ? <img src={r.photo_url} alt={t("crbs.rooms.photoAlt", { name: r.name })} className="max-h-[80dvh] w-full rounded-xl object-contain" /> : null}
        </DialogContent>
      </Dialog>
    </>
  );
}

/** The room's day (bookings and classes) and its next free slot this week, from the room-view grid. */
function RoomDay({ room, date, termId, fmt, onReserve }: { room: RoomInfo; date: string; termId?: number; fmt: DateFormatter; onReserve?: (target: BookTarget) => void }) {
  const { t } = useI18n();
  const now = useNow();
  const week = useBookingGrid({ display: "room", room_id: room.id, date, term_id: termId });
  const g = week.data;
  const periods = useMemo(() => new Map((g?.periods ?? []).map((p) => [p.id, p])), [g?.periods]);
  if (week.isLoading) return <Loading />;
  if (!g || g.rooms[0]?.id !== room.id) return null;
  const held = roomDay(g, room.id, date).filter((s) => s.status === "booked" || s.status === "timetable" || (s.status === "unavailable" && s.reason === "holiday"));
  const describe = (x: (typeof held)[number]) => {
    const text = slotText(x, { booked: t("crbs.slot.booked"), mine: t("crbs.slot.mine"), class: t("reserve.cell.class") });
    return [text.primary, x.booking?.notes, x.booking?.department_name].filter(Boolean).join(" · ");
  };
  // consecutive periods held by the same class or booking series are one row
  const order = new Map(g.periods.map((p, i) => [p.id, i]));
  const runs: (typeof held)[] = [];
  for (const x of held) {
    const last = runs[runs.length - 1];
    const prev = last?.[last.length - 1];
    const same = prev && (order.get(x.period_id) ?? 0) === (order.get(prev.period_id) ?? 0) + 1 && prev.status === x.status && describe(prev) === describe(x) && (prev.booking?.series_id ?? prev.booking?.id ?? null) === (x.booking?.series_id ?? x.booking?.id ?? null);
    if (same) last!.push(x);
    else runs.push([x]);
  }
  const next = nextFreeSlot(g, room.id, now);
  const np = next ? periods.get(next.period_id) : undefined;
  return (
    <>
      <section aria-labelledby="room-day" className="flex flex-col gap-2" data-testid="room-day">
        <h3 id="room-day" className="type-headline text-label-1">
          {t("reserve.room.day", { date: fmt.long(date) })}
        </h3>
        {held.length === 0 ? (
          <p className="type-callout text-label-2">{t("reserve.room.dayEmpty")}</p>
        ) : (
          <ul className="flex flex-col overflow-hidden rounded-xl bg-fill-2">
            {runs.map((run) => {
              const s = run[0]!;
              const a = periods.get(s.period_id);
              const b = periods.get(run[run.length - 1]!.period_id);
              const Icon = s.status === "timetable" ? GraduationCap : s.reason === "recurring" ? Repeat : User;
              return (
                <li key={s.period_id} className="flex items-center gap-3 px-3 py-2 type-callout shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none">
                  <span className="w-28 shrink-0 text-label-3 tabular-nums">
                    {run.length > 1 ? `${a?.name}–${b?.name}` : a?.name} · {a ? fmt.time(a.time_start) : ""}
                  </span>
                  <Icon className="size-3.5 shrink-0 text-label-2" aria-label={s.status === "timetable" ? t("reserve.room.class") : t("reserve.room.booking")} />
                  <span className="min-w-0 truncate text-label-1">{describe(s)}</span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
      <section aria-labelledby="room-next" className="flex items-center justify-between gap-3 rounded-xl bg-fill-2 px-3 py-2.5" data-testid="room-next-free">
        <div className="min-w-0">
          <h3 id="room-next" className="type-footnote font-medium text-label-3">
            {t("reserve.room.next")}
          </h3>
          <p className="flex items-center gap-1.5 type-callout text-label-1">
            <CalendarClock className="size-3.5 shrink-0 text-label-2" aria-hidden />
            {next && np ? `${fmt.weekday(next.date)} · ${np.name} ${fmt.time(np.time_start)}–${fmt.time(np.time_end)}` : t("reserve.room.nextNone")}
          </p>
        </div>
        {next && np && onReserve ? (
          <Button size="sm" className="min-h-11 sm:min-h-0" onClick={() => onReserve({ slot: next, grid: g })} aria-label={t("reserve.room.reserveNext", { time: `${fmt.weekday(next.date)} ${np.name}` })} data-testid="room-next-reserve">
            {t("reserve.room.reserve")}
          </Button>
        ) : null}
      </section>
    </>
  );
}

/** Day grids of every room group for the date (shared cache with the panel's own grid query). */
export function useDayGrids(date: string | undefined, termId?: number, enabled = true): { grids: Grid[]; loading: boolean } {
  const ctx = useBookingContext();
  const groups = ctx.data?.display.use_room_groups ? (ctx.data.room_groups ?? []).map((g) => g.id) : [undefined];
  const queries = useQueries({
    queries: groups.map((gid) => {
      const q: GridQuery = { display: "day", date, term_id: termId, room_group_id: gid };
      return { queryKey: crbsKeys.grid(q), queryFn: () => crbs.bookings.grid(q), enabled: enabled && !!date && ctx.isSuccess, staleTime: 10_000, retry: false };
    }),
  });
  const grids = queries.map((x) => x.data).filter((x): x is Grid => !!x && x.date === date);
  return { grids, loading: !ctx.isSuccess || queries.some((x) => x.isLoading) };
}

function OtherRooms({ room, date, context, fmt, onReserve }: { room: RoomInfo; date: string; context?: RoomContext; fmt: DateFormatter; onReserve?: (target: BookTarget) => void }) {
  const { t, locale } = useI18n();
  const now = useNow();
  const { grids, loading } = useDayGrids(date, context?.termId);
  const infos = useQuery({ queryKey: ["crbs", "booking-rooms"], queryFn: () => crbs.bookings.rooms(), retry: false, staleTime: 60_000 });
  const infoMap = useMemo(() => new Map((infos.data ?? []).map((x) => [x.id, x])), [infos.data]);
  // the asked period(s): from the context, else the first period of the day that is not over
  const dayPeriods = useMemo(() => {
    const g = grids.find((x) => x.rooms.some((rr) => rr.id === room.id)) ?? grids[0];
    return g?.periods ?? [];
  }, [grids, room.id]);
  const fallback = dayPeriods.find((p) => !now || date > now.date || (date === now.date && p.time_end > now.time)) ?? dayPeriods[0];
  const [picked, setPicked] = useState<number | null>(null);
  const asked = context?.periods?.length && picked === null ? context.periods : dayPeriods.filter((p) => p.id === (picked ?? fallback?.id));
  const [minSeats, setMinSeats] = useState<number>(room.capacity ?? 0);
  const [tags, setTags] = useState<string[]>(room.tags);

  const first = asked[0];
  const last = asked[asked.length - 1];
  // T1 when the backend has it: it ranks; the grids decide what may be reserved
  const finder = useQuery({
    queryKey: ["crbs", "find", date, first?.start_period, last?.end_period, minSeats, tags, context?.termId],
    queryFn: () => crbs.rooms.find({ date, start: first!.start_period, end: last!.end_period, headcount: minSeats, tags, term_id: context?.termId, include_busy: false, include_requestable: false, flex: { periods: 0 }, limit: 50 }),
    enabled: !!first && !!last,
    retry: false,
    staleTime: 30_000,
  });
  const alts = useMemo(() => {
    const local = first ? alternativesFromGrids(grids, { date, periods: asked, excludeRoomId: room.id, minSeats, tags }, infoMap) : [];
    const ranked: FindOut | undefined = finder.data;
    if (!ranked?.results?.length) return { list: local, ranked: false };
    const rank = new Map(ranked.results.filter((x) => x.status === "free" && x.action === "book").map((x, i) => [x.room_id, i]));
    const list = local.filter((a) => rank.has(a.room.id)).sort((a, b) => (rank.get(a.room.id) ?? 0) - (rank.get(b.room.id) ?? 0));
    return { list: list.length ? list : local, ranked: list.length > 0 };
  }, [asked, date, finder.data, first, grids, infoMap, minSeats, room.id, tags]);

  const time = first && last ? `${fmt.time(first.time_start)}–${fmt.time(last.time_end)}` : "";
  const allTags = useMemo(() => [...new Set([...room.tags, ...(infos.data ?? []).flatMap((x) => x.tags)])].sort((a, b) => a.localeCompare(b, locale)).slice(0, 8), [infos.data, locale, room.tags]);

  return (
    <section aria-labelledby="room-alts" className="flex flex-col gap-3" data-testid="room-alternatives">
      <div className="flex flex-col gap-0.5">
        <h3 id="room-alts" className="flex items-center gap-1.5 type-headline text-label-1">
          <DoorOpen className="size-4 text-label-2" aria-hidden />
          {t("reserve.alt.title")}
        </h3>
        <p className="type-footnote text-label-2">{t("reserve.alt.lead", { date: fmt.weekday(date), time })}</p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        {!context?.periods?.length || picked !== null ? (
          <label className="flex flex-col gap-1 type-footnote text-label-3">
            {t("reserve.alt.time")}
            <SelectField value={String(first?.id ?? "")} onChange={(e) => setPicked(Number(e.target.value))} data-testid="alt-period">
              {dayPeriods.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({fmt.time(p.time_start)}–{fmt.time(p.time_end)})
                </option>
              ))}
            </SelectField>
          </label>
        ) : null}
        <label className="flex flex-col gap-1 type-footnote text-label-3">
          {t("reserve.alt.minSeats")}
          <span className="flex items-center gap-1.5">
            <Input type="number" min={0} max={2000} inputMode="numeric" value={minSeats} onChange={(e) => setMinSeats(Math.max(0, Number(e.target.value) || 0))} className="w-20" data-testid="alt-min-seats" />
            <span className="text-label-2">{t("reserve.alt.seatsUnit")}</span>
          </span>
        </label>
      </div>
      {allTags.length ? (
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={t("reserve.alt.tags")}>
          <span className="type-footnote text-label-3">{t("reserve.alt.tags")}</span>
          {allTags.map((tag) => (
            <Chip key={tag} size="sm" selected={tags.includes(tag)} onSelectedChange={(on) => setTags((cur) => (on ? [...cur, tag] : cur.filter((x) => x !== tag)))}>
              {tag}
            </Chip>
          ))}
        </div>
      ) : null}
      {loading || (finder.isLoading && !!first) ? (
        // wait for the finder's ranking too, so the list does not reorder under the pointer
        <Loading label={t("reserve.alt.loading")} />
      ) : alts.list.length === 0 ? (
        <p className="type-callout text-label-2" data-testid="alt-empty">
          {t("reserve.alt.empty")}
        </p>
      ) : (
        <ul className="flex flex-col overflow-hidden rounded-xl bg-fill-2">
          {alts.list.slice(0, 12).map((a) => (
            <AltRow key={a.room.id} a={a} time={time} onReserve={onReserve} />
          ))}
        </ul>
      )}
      {alts.ranked ? <p className="type-caption text-label-3">{t("reserve.alt.finder")}</p> : null}
    </section>
  );
}

function AltRow({ a, time, onReserve }: { a: Alternative; time: string; onReserve?: (target: BookTarget) => void }) {
  const { t } = useI18n();
  const seats = a.room.capacity ?? a.info?.capacity;
  const fit = a.spare === null ? t("reserve.alt.unknownSize") : a.spare === 0 ? t("reserve.alt.exact") : t("reserve.alt.spare", { n: a.spare });
  return (
    <li className="flex items-center gap-3 px-3 py-2 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none" data-testid={`alt-room-${a.room.code}`}>
      <div className="min-w-0 flex-1">
        <p className="type-callout font-medium text-label-1">{a.room.name}</p>
        <p className="truncate type-footnote text-label-2">{[seats ? t("crbs.grid.seats", { n: seats }) : null, a.info?.building ?? a.info?.group, ...(a.info?.tags ?? []), fit].filter(Boolean).join(" · ")}</p>
      </div>
      {onReserve ? (
        <Button size="sm" variant="outline" className="min-h-11 sm:min-h-0" onClick={() => onReserve({ slot: a.slots[0]!, grid: a.grid, span: a.slots })} aria-label={t("reserve.alt.reserveRoom", { room: a.room.name, time })} data-testid={`alt-reserve-${a.room.code}`}>
          {t("reserve.alt.reserve")}
        </Button>
      ) : null}
    </li>
  );
}
