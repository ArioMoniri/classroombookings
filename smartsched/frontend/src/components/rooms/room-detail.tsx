"use client";
/**
 * /rooms/[id] (Liquid Glass v2): the room's week (7 × 18, opaque marks: faculty fill for classes, hatch for
 * pre-occupied, booking style for bookings), the free-slot finder ("at least n periods", evening optional)
 * with "Book this room" through /api/v1/bookings when the room has booking periods, the term occupancy
 * heat (server aggregate for this room) whose rows pick the week, and a link to the same week in the
 * calendar. Data: the calendar index of the term's working run (shared with /timetable).
 */
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { spanText } from "@/components/timetable/model/check";
import { dateOf } from "@/components/timetable/model/dates";
import { heatStep } from "@/components/timetable/model/heat";
import { chipVars } from "@/components/timetable/event-chip";
import { useCalendarData } from "@/components/timetable/use-calendar-data";
import "@/components/timetable/calendar.css";
import { calendarApi, calKeys, useHeat } from "@/lib/api/calendar";
import { HttpError } from "@/lib/api/client";
import { useRoom } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS, PERIODS_PER_DAY, dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { RoomVisual, floorText, nowLine, tagWords } from "./room-card";
import { freeRuns, heldAt, roomWeek, weekClasses, weekShare, type FreeRun, type RoomCell } from "./room-occupancy";
import { defaultWeek, useRunNow } from "./use-room-week";

const EVENING_FROM = 12; // P12 starts the evening programme (17:30)

export function RoomDetail({ id }: { id: number }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const room = useRoom(id);
  const cal = useCalendarData(Number(params.get("run") ?? "") || null);
  const now = useRunNow(cal.model);
  const week = defaultWeek(cal.model, now, Number(params.get("week") ?? "") || null);
  const weekList = cal.model?.weeks ?? [];
  const weekIdx = week !== null ? weekList.indexOf(week) : -1;
  const heat = useHeat(cal.runId, { scale: "term", roomId: id });
  const [minLen, setMinLen] = useState(2);
  const [evening, setEvening] = useState(false);
  const [picked, setPicked] = useState<FreeRun | null>(null);

  const setWeek = (w: number) => {
    const next = new URLSearchParams(params.toString());
    next.set("week", String(w));
    setPicked(null);
    router.replace(`/rooms/${id}?${next.toString()}`, { scroll: false });
  };

  const grid = useMemo(() => (cal.model && week !== null ? roomWeek(cal.model, id, week) : null), [cal.model, week, id]);
  const classes = useMemo(() => (cal.model && week !== null ? weekClasses(cal.model, id, week) : []), [cal.model, week, id]);
  const runs = useMemo(() => (grid ? freeRuns(grid, minLen, [1, 2, 3, 4, 5, 6], evening ? PERIODS_PER_DAY : EVENING_FROM - 1) : []), [grid, minLen, evening]);
  const showSunday = !!grid && grid[6].some((c) => c.kind !== "free");
  const days = showSunday ? [1, 2, 3, 4, 5, 6, 7] : [1, 2, 3, 4, 5, 6];

  const r = room.data;
  if (room.isError) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-[15px]">{t("roomsV2.notFound")}</p>
        <Button variant="outline" size="sm" render={<Link href="/rooms" />} nativeButton={false}>{t("roomsV2.back")}</Button>
      </div>
    );
  }
  if (!r) return <Skeleton className="h-64 rounded-2xl" />;

  const floor = floorText(r.floor, t);
  const tags = tagWords(r, t);
  const pct = grid ? Math.round(weekShare(grid) * 100) : null;
  const calHref = `/timetable?lens=week&subject=room:${id}${week !== null ? `&week=${week}` : ""}${cal.runId ? `&run=${cal.runId}` : ""}`;
  const bookingsOn = cal.model?.index.bookings_enabled !== false && r.is_bookable;
  const nowCell = now && grid && week === now.week ? heldAt(grid, now.day, now.period) : undefined;

  return (
    <div className="flex flex-col gap-4" data-testid="room-detail">
      <Link href="/rooms" className="inline-flex w-fit items-center gap-1 text-[13px] text-label-2 hover:text-label-1">
        <ArrowLeft className="size-4" aria-hidden /> {t("roomsV2.back")}
      </Link>

      <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
        {!r.photo_url ? <RoomVisual room={r} variant="tile" /> : null}
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h1 className="type-title-1 flex items-center gap-2">
            {r.display_name}
            {!r.is_bookable ? <Badge variant="secondary" tone="preoccupied">{t("roomsV2.notBookable")}</Badge> : null}
          </h1>
          <p className="text-[13px] text-label-2 tabular-nums">
            {[t("roomsV2.building", { b: r.building_code }), floor, t("roomsV2.seats", { n: r.capacity }), t("roomsV2.examSeats", { n: r.exam_capacity }), ...tags].filter(Boolean).join(" · ")}
          </p>
          {nowCell !== undefined ? <p className={cn("text-[13px]", nowCell ? "text-label-1" : "text-status-feasible-fg")}>{nowLine(nowCell, t)}</p> : null}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" render={<Link href={calHref} />} nativeButton={false} data-testid="room-open-calendar">
            <CalendarDays aria-hidden />{t("roomsV2.openWeek")}
          </Button>
          {bookingsOn ? (
            <Button size="sm" onClick={() => document.getElementById("free-finder")?.focus()} data-testid="room-book">{t("roomsV2.book")}</Button>
          ) : null}
        </div>
      </div>

      {cal.noRun ? <p className="text-[13px] text-label-2">{t("roomsV2.noRun")}</p> : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-4">
          {r.photo_url ? <RoomVisual room={r} variant="hero" className="max-h-[360px]" /> : null}

          <Card className="gap-3 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="type-headline">{t("roomsV2.weekly")}</h2>
              {pct !== null ? <span className="text-[13px] text-label-2 tabular-nums">{t("roomsV2.occupancy", { p: pct, w: week ?? "" })}</span> : null}
              {week !== null && weekList.length ? (
                <span className="ml-auto flex items-center gap-1" role="group" aria-label={t("roomsV2.week")}>
                  <Button variant="ghost" size="icon-sm" aria-label={t("roomsV2.prevWeek")} disabled={weekIdx <= 0} onClick={() => setWeek(weekList[weekIdx - 1])}><ChevronLeft /></Button>
                  <span className="min-w-20 text-center text-[13px] font-semibold tabular-nums" aria-live="polite" data-testid="room-week">{t("roomsV2.weekLabel", { w: week })}</span>
                  <Button variant="ghost" size="icon-sm" aria-label={t("roomsV2.nextWeek")} disabled={weekIdx < 0 || weekIdx >= weekList.length - 1} onClick={() => setWeek(weekList[weekIdx + 1])}><ChevronRight /></Button>
                </span>
              ) : null}
            </div>
            {grid ? <WeekGrid grid={grid} days={days} picked={picked} onPick={bookingsOn ? setPicked : undefined} now={now && now.week === week ? now : null} /> : cal.loading ? <Skeleton className="h-48 rounded-xl" /> : null}
            <Legend />
          </Card>

          <Card variant="plain" className="gap-0 p-0">
            <h2 className="type-headline px-4 pt-3 pb-2">{week !== null ? t("roomsV2.classesThisWeek", { w: week }) : t("roomsV2.weekly")}</h2>
            {classes.length === 0 ? (
              <p className="px-4 pb-4 text-[13px] text-label-2">{week !== null ? t("roomsV2.noClasses", { w: week }) : "—"}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-[13px]" data-testid="room-classes">
                  <thead>
                    <tr className="hairline-b text-left text-[12px] text-label-2">
                      <th scope="col" className="py-1.5 pr-2 pl-4 font-semibold">{t("roomsV2.dayCol")}</th>
                      <th scope="col" className="px-2 font-semibold">{t("roomsV2.timeCol")}</th>
                      <th scope="col" className="px-2 font-semibold">{t("roomsV2.courseCol")}</th>
                      <th scope="col" className="px-2 font-semibold">{t("roomsV2.programCol")}</th>
                      <th scope="col" className="py-1.5 pr-4 pl-2 text-right font-semibold">{t("roomsV2.sizeCol")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {classes.map((e) => (
                      <tr key={e.key} className="hairline-b hover:bg-fill-3">
                        <td className="py-1.5 pr-2 pl-4">{dayName(e.day, locale, "short")}</td>
                        <td className="px-2 tabular-nums">{spanText(e.sp, e.ep)}</td>
                        <td className="px-2">
                          <Link href={`/timetable?lens=week&subject=room:${id}&week=${week}&day=${e.day}&sel=${e.a.id}${cal.runId ? `&run=${cal.runId}` : ""}`} className="flex items-center gap-2 font-semibold hover:underline">
                            <span aria-hidden className="h-3.5 w-[3px] rounded-full" style={{ background: `var(--fac-${e.a.slot}-bar)` }} />
                            {e.a.label}
                          </Link>
                        </td>
                        <td className="max-w-[240px] truncate px-2 text-label-2">{e.a.prog ?? "—"}</td>
                        <td className={cn("py-1.5 pr-4 pl-2 text-right tabular-nums", e.a.size > r.capacity && "text-status-warning-fg")}>{t("roomsV2.people", { size: e.a.size, cap: r.capacity })}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <Card className="gap-3 p-4">
            <h2 id="free-finder" tabIndex={-1} className="type-headline outline-none">{t("roomsV2.freeFinder")}</h2>
            <SegmentedGlass
              size="sm"
              aria-label={t("roomsV2.minLen", { n: minLen })}
              value={String(minLen)}
              onValueChange={(v) => {
                setMinLen(Number(v));
                setPicked(null);
              }}
              options={[1, 2, 3, 4, 6].map((n) => ({ value: String(n), label: `≥ ${n}` }))}
            />
            <label className="flex items-center justify-between gap-2 text-[13px]">
              {t("roomsV2.includeEvening")}
              <Switch checked={evening} onCheckedChange={(v) => setEvening(!!v)} />
            </label>
            {grid ? (
              runs.length ? (
                <ul className="flex max-h-[280px] flex-col gap-1 overflow-y-auto" data-testid="free-slots">
                  {runs.map((f) => {
                    const on = picked?.day === f.day && picked.sp === f.sp;
                    return (
                      <li key={`${f.day}:${f.sp}`}>
                        <button
                          type="button"
                          aria-pressed={on}
                          disabled={!bookingsOn}
                          onClick={() => setPicked(on ? null : f)}
                          className={cn("flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] tabular-nums transition-colors duration-(--dur-fast) disabled:cursor-default", on ? "bg-tint-soft text-tint-text" : "bg-fill-3 hover:bg-fill-2")}
                        >
                          <span>{dayName(f.day, locale, "short")} {spanText(f.sp, f.ep)}</span>
                          <span className="text-[12px] text-label-2">P{f.sp}–P{f.ep}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-[13px] text-label-2">{t("roomsV2.noFree", { w: week ?? "" })}</p>
              )
            ) : null}
            {!bookingsOn ? <p className="text-[12px] text-label-2">{t("roomsV2.bookingsOff")}</p> : picked ? null : <p className="text-[12px] text-label-2">{t("roomsV2.pickSlot")}</p>}
            {picked && cal.model && week !== null ? (
              <BookingForm
                roomId={id}
                roomName={r.display_name}
                termId={cal.model.index.run.term_id}
                date={dateOf(cal.model.index.weeks, week, picked.day)}
                run={picked}
                onDone={() => {
                  setPicked(null);
                  if (cal.runId) void qc.invalidateQueries({ queryKey: calKeys.index(cal.runId) });
                }}
                lang={lang}
              />
            ) : null}
          </Card>

          <Card className="gap-3 p-4">
            <h2 className="type-headline">{t("roomsV2.termHeat")}</h2>
            <TermStrip cells={heat.data?.cells ?? []} week={week} onWeek={setWeek} />
          </Card>

          <Card variant="plain" className="gap-2 p-4">
            <h2 className="type-headline">{t("roomsV2.facts")}</h2>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]">
              <dt className="text-label-2">{t("roomsV2.code")}</dt><dd className="tabular-nums">{r.code}</dd>
              <dt className="text-label-2">{t("roomsV2.capacity")}</dt><dd className="tabular-nums">{r.capacity}</dd>
              <dt className="text-label-2">{t("roomsV2.examCapacity")}</dt><dd className="tabular-nums">{r.exam_capacity}</dd>
              <dt className="text-label-2">{t("roomsV2.bookable")}</dt><dd>{r.is_bookable ? t("common.yes") : t("common.no")}</dd>
              {r.notes ? <><dt className="text-label-2">{t("roomsV2.notes")}</dt><dd>{r.notes}</dd></> : null}
            </dl>
          </Card>
        </div>
      </div>
    </div>
  );
}

function cellClass(c: RoomCell): string {
  if (c.kind === "class") return "cal-chip";
  if (c.kind === "block") return "cal-block";
  if (c.kind === "booking") return "cal-booking";
  return "";
}

/** 7 × 18 occupancy grid: one merged mark per class/block/booking span, free cells pickable for booking. */
function WeekGrid({ grid, days, picked, onPick, now }: { grid: RoomCell[][]; days: number[]; picked: FreeRun | null; onPick?: (f: FreeRun) => void; now: { day: number; period: number | null } | null }) {
  const { t, locale } = useI18n();
  return (
    <div className="overflow-x-auto" data-testid="room-week-grid">
      <div role="grid" aria-label={t("roomsV2.weekly")} className="grid min-w-[720px] gap-[2px] text-[11px]" style={{ gridTemplateColumns: `44px repeat(${PERIODS_PER_DAY}, minmax(30px, 1fr))` }}>
        <div role="row" className="contents">
          <span role="columnheader" />
          {PERIODS.map((p) => (
            <span key={p.index} role="columnheader" className="pb-0.5 text-center leading-tight text-label-2 tabular-nums" title={`${p.start}–${p.end}`}>
              P{p.index}
              <span className="block text-[9px] text-label-3">{p.start}</span>
            </span>
          ))}
        </div>
        {days.map((day) => {
          const row = grid[day - 1];
          const cells: React.ReactNode[] = [];
          for (let p = 1; p <= PERIODS_PER_DAY; ) {
            const c = row[p - 1];
            if (c.kind === "free") {
              const isPicked = !!picked && picked.day === day && p >= picked.sp && p <= picked.ep;
              const isNow = !!now && now.day === day && now.period === p;
              const label = t("roomsV2.cellFree", { day: dayName(day, locale), p });
              cells.push(
                onPick ? (
                  <button
                    key={p}
                    type="button"
                    role="gridcell"
                    aria-label={label}
                    aria-selected={isPicked}
                    onClick={() => {
                      // two periods from here (one when the next period is taken)
                      const ep = p < PERIODS_PER_DAY && row[p].kind === "free" ? p + 1 : p;
                      onPick({ day, sp: p, ep, length: ep - p + 1 });
                    }}
                    className={cn("h-7 rounded-[4px] bg-fill-3 hover:bg-fill-2 focus-visible:outline-2 focus-visible:outline-(--focus)", isPicked && "bg-tint-soft shadow-[inset_0_0_0_1.5px_var(--accent)]", isNow && "shadow-[inset_0_-2px_0_var(--now)]")}
                  />
                ) : (
                  <span key={p} role="gridcell" aria-label={label} className={cn("h-7 rounded-[4px] bg-fill-3", isNow && "shadow-[inset_0_-2px_0_var(--now)]")} />
                ),
              );
              p++;
              continue;
            }
            const end = Math.min(PERIODS_PER_DAY, "ep" in c ? c.ep : p);
            // span only as far as the same item continues in this row
            let ep = p;
            while (ep < end && row[ep].kind === c.kind && (row[ep] as { label: string }).label === c.label) ep++;
            const label = t("roomsV2.cellHeld", { day: dayName(day, locale), p: `${p}${ep > p ? `–${ep}` : ""}`, label: c.label });
            cells.push(
              <span
                key={p}
                role="gridcell"
                aria-label={label}
                title={label}
                data-conflict={c.kind === "class" && c.conflict ? "true" : undefined}
                className={cn("h-7 min-w-0 overflow-hidden rounded-[4px] font-semibold whitespace-nowrap", cellClass(c), c.kind === "class" ? "!relative justify-center" : "flex items-center px-1.5")}
                style={{ gridColumn: `${p + 1} / ${ep + 2}`, ...(c.kind === "class" ? chipVars(c.fac) : {}) }}
              >
                <span className="truncate">{c.label}</span>
              </span>,
            );
            p = ep + 1;
          }
          return (
            <div key={day} role="row" className="contents">
              <span role="rowheader" className="flex items-center text-[12px] font-semibold text-label-2">{dayName(day, locale, "short")}</span>
              {cells}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Legend() {
  const { t } = useI18n();
  return (
    <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-label-2">
      <span className="flex items-center gap-1.5"><span aria-hidden className="size-3 rounded-[3px]" style={{ background: "var(--fac-1-fill)", boxShadow: "inset 2px 0 0 var(--fac-1-bar)" }} />{t("roomsV2.legendClass")}</span>
      <span className="flex items-center gap-1.5"><span aria-hidden className="cal-block size-3 rounded-[3px]" />{t("roomsV2.legendBlock")}</span>
      <span className="flex items-center gap-1.5"><span aria-hidden className="size-3 rounded-[3px] bg-fill-3 shadow-[inset_0_0_0_1px_var(--hairline)]" />{t("roomsV2.legendFree")}</span>
    </p>
  );
}

/** Term occupancy for this room: one row per week (7 day cells), the row picks the week. */
function TermStrip({ cells, week, onWeek }: { cells: { week: number | null; day: number; occupancy: number; in_term: boolean }[]; week: number | null; onWeek: (w: number) => void }) {
  const { t, locale } = useI18n();
  const weeks = [...new Set(cells.map((c) => c.week).filter((w): w is number => w !== null))].sort((a, b) => a - b);
  if (!weeks.length) return <Skeleton className="h-40 rounded-xl" />;
  const at = new Map(cells.map((c) => [`${c.week}:${c.day}`, c]));
  return (
    <div className="flex flex-col gap-[3px]" data-testid="room-term-heat">
      <div className="grid grid-cols-[32px_repeat(7,1fr)] gap-[3px] text-center text-[10px] text-label-3" aria-hidden>
        <span />
        {[1, 2, 3, 4, 5, 6, 7].map((d) => <span key={d}>{dayName(d, locale, "short").slice(0, 2)}</span>)}
      </div>
      {weeks.map((w) => {
        const row = [1, 2, 3, 4, 5, 6, 7].map((d) => at.get(`${w}:${d}`));
        const mean = row.slice(0, 5).reduce((s, c) => s + (c?.occupancy ?? 0), 0) / 5;
        return (
          <button
            key={w}
            type="button"
            onClick={() => onWeek(w)}
            aria-label={`${t("roomsV2.heatWeek", { w })} · ${t("roomsV2.occupancyShort", { p: Math.round(mean * 100) })}`}
            aria-current={w === week ? "true" : undefined}
            className={cn("grid grid-cols-[32px_repeat(7,1fr)] items-center gap-[3px] rounded-md p-0.5 text-left focus-visible:outline-2 focus-visible:outline-(--focus)", w === week ? "bg-tint-soft" : "hover:bg-fill-3")}
          >
            <span className="text-[11px] font-semibold text-label-2 tabular-nums">H{w}</span>
            {row.map((c, i) => (
              <span key={i} title={c ? t("roomsV2.heatCell", { w, day: dayName(i + 1, locale), p: Math.round(c.occupancy * 100) }) : undefined} className="cal-heat h-3.5 rounded-[3px]" data-step={c ? heatStep(c.occupancy) : 0} data-out={c && !c.in_term ? "true" : undefined} />
            ))}
          </button>
        );
      })}
    </div>
  );
}

/** Book the picked free run: one booking per booking period inside it (same flow as calendar quick-create). */
function BookingForm({ roomId, roomName, termId, date, run, onDone, lang }: { roomId: number; roomName: string; termId: number; date: string | null; run: FreeRun; onDone: () => void; lang: "tr" | "en" }) {
  const { t, locale } = useI18n();
  const [periods, setPeriods] = useState<{ id: number; start_period: number; end_period: number }[] | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!date) return;
    let alive = true;
    calendarApi
      .bookingPeriods(roomId, date)
      .then((ps) => alive && setPeriods(ps))
      .catch(() => alive && setPeriods([]));
    return () => {
      alive = false;
    };
  }, [roomId, date]);
  if (!date) return <p className="text-[12px] text-label-2">{t("roomsV2.noDate")}</p>;
  const inRange = (periods ?? []).filter((p) => p.start_period >= run.sp && p.end_period <= run.ep);
  const when = t("roomsV2.bookingFor", { day: dayName(run.day, locale), date: new Date(`${date}T12:00:00`).toLocaleDateString(lang === "tr" ? "tr-TR" : "en-GB", { day: "numeric", month: "long" }), range: spanText(run.sp, run.ep) });
  const book = async () => {
    setBusy(true);
    try {
      for (const p of inRange) await calendarApi.createBooking({ room_id: roomId, date, period_id: p.id, notes: note || undefined, term_id: termId });
      toast.success(t("roomsV2.bookedOk", { when: `${roomName} · ${when}` }));
      onDone();
    } catch (e) {
      toast.error(t("roomsV2.bookFailed", { reason: e instanceof HttpError ? e.message : String(e) }));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex flex-col gap-2 rounded-xl bg-fill-3 p-3" data-testid="room-booking-form">
      <p className="text-[13px] font-semibold">{when}</p>
      {periods === null ? (
        <p className="text-[12px] text-label-2" role="status">{t("roomsV2.loadingPeriods")}</p>
      ) : inRange.length === 0 ? (
        <p className="text-[12px] text-label-2">{t("roomsV2.bookingsOff")}</p>
      ) : (
        <>
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("roomsV2.bookingNote")} aria-label={t("roomsV2.bookingNote")} />
          <Button size="sm" className="w-fit" disabled={busy} onClick={() => void book()} data-testid="room-book-confirm">
            {busy ? t("roomsV2.booking") : t("roomsV2.bookConfirm")}
          </Button>
        </>
      )}
    </div>
  );
}
