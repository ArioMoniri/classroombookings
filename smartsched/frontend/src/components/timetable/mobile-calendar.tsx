"use client";
/**
 * Phone calendar, 360–430 px (calendar.md §14, wireframe calendar-mobile-day.svg): a large-title day list,
 * a horizontal 7-day strip (swipe to change week, heat dot per day), "Liste · Zaman çizelgesi", subject chips,
 * and the inspector as a bottom sheet. Moving uses "Taşı…" (the Move dialog with the free-room finder); no drag.
 */
import { CalendarDays, Search } from "lucide-react";
import { useMemo, useRef, useState, type PointerEvent } from "react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { ClassInspector } from "@/components/classes/class-inspector";
import { useI18n } from "@/lib/i18n/provider";
import { dayName, formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";
import { AgendaLens } from "./agenda-lens";
import { SubjectPicker } from "./capsule-toolbar";
import { MonthHeat, TermHeat } from "./heat-lenses";
import { MoveDialog } from "./move-dialog";
import { TimeGrid, type GridColumn } from "./time-grid";
import { eventsOf, blocksOf, roomCap, type CalEvent, type CalendarModel } from "./model/index-model";
import type { HeatMetric, HeatValue } from "./model/heat";
import { rowHeightFor } from "./model/geometry";
import type { Lens, Subject } from "./model/view-state";
import type { useCalendarActions } from "./use-calendar-actions";

export interface MobileCalendarProps {
  model: CalendarModel;
  week: number;
  day: number;
  dates: (string | null)[];
  onDay: (d: number) => void;
  onWeek: (w: number) => void;
  heat: Map<string, HeatValue>;
  now: { minutes: number; iso: string };
  selection: ReadonlySet<number>;
  onSelect: (aid: number | null, mode: "replace" | "toggle" | "range") => void;
  subject: Subject | null;
  onSubject: (s: Subject | null) => void;
  runId: number | null;
  termId: number | null;
  actions: ReturnType<typeof useCalendarActions>;
  readOnly: boolean;
  lens: Lens;
  onLens: (l: Lens) => void;
}

export function MobileCalendar(p: MobileCalendarProps) {
  const { t, locale } = useI18n();
  const [mode, setMode] = useState<"list" | "timeline">("list");
  const [open, setOpen] = useState<CalEvent | null>(null);
  const [moving, setMoving] = useState<CalEvent | null>(null);
  const [metric, setMetric] = useState<HeatMetric>("occupancy");
  const swipe = useRef<{ x: number; y: number } | null>(null);
  const subjectKeep = (e: CalEvent) => {
    const s = p.subject;
    if (!s) return true;
    if (s.kind === "room") return e.room === Number(s.id);
    if (s.kind === "instructor") return e.a.instr_ids.includes(Number(s.id));
    if (s.kind === "cohort") return e.cohort === s.id;
    return String(e.a.mr) === s.id;
  };
  const dayEvents = useMemo(() => eventsOf(p.model, p.week, p.day).filter(subjectKeep), [p.model, p.week, p.day, p.subject]); // eslint-disable-line react-hooks/exhaustive-deps
  const date = p.dates[p.day - 1];
  const big = date ? dayName(p.day, locale) : "";
  const sub = date ? `${formatDate(date, locale, { day: "numeric", month: "long" })} · ${t("calendar.nav.weekShort", { n: p.week })}` : "";

  const onStripDown = (e: PointerEvent<HTMLDivElement>) => {
    swipe.current = { x: e.clientX, y: e.clientY };
  };
  const onStripUp = (e: PointerEvent<HTMLDivElement>) => {
    const s = swipe.current;
    swipe.current = null;
    if (!s) return;
    const dx = e.clientX - s.x;
    if (Math.abs(dx) > 56 && Math.abs(dx) > Math.abs(e.clientY - s.y)) p.onWeek(p.week + (dx < 0 ? 1 : -1));
  };

  const room = p.subject?.kind === "room" ? Number(p.subject.id) : null;
  const columns: GridColumn[] = [{ key: `d${p.day}`, room, day: p.day, label: dayName(p.day, locale, "short"), ariaLabel: dayName(p.day, locale) }];

  return (
    <div className="cal-canvas -mx-4 -mt-4 flex min-h-[calc(100dvh-7rem)] flex-col" data-testid="calendar-mobile">
      <header className="flex items-start justify-between gap-2 px-4 pt-4">
        <div>
          <h1 className="type-title-1 capitalize" data-testid="calendar-title">{big}</h1>
          <p className="text-[13px] text-label-2">{sub}</p>
        </div>
        <div className="flex gap-2 pt-1">
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="outline" size="icon-lg" aria-label={t("calendar.lens.label")} />}><CalendarDays /></DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuRadioGroup value={p.lens === "month" || p.lens === "term" ? p.lens : "agenda"} onValueChange={(v) => p.onLens(v as Lens)}>
                <DropdownMenuRadioItem value="agenda">{t("calendar.lens.day")}</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="month">{t("calendar.lens.month")}</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="term">{t("calendar.lens.term")}</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
          <span className="glass-chrome flex size-10 items-center justify-center rounded-full" data-glass="chrome">
            <SubjectPicker model={p.model} subject={p.subject} onSubject={p.onSubject} condensed />
          </span>
        </div>
      </header>

      {p.lens === "month" ? (
        <div className="min-h-[70dvh]"><MonthHeat model={p.model} heat={p.heat} metric={metric} onMetric={setMetric} unplacedByDay={new Map()} todayIso={p.now.iso} onPick={(w, d) => { p.onWeek(w); p.onDay(d); p.onLens("agenda"); }} compareOn={false} month={(date ?? p.now.iso).slice(0, 7)} onMonth={() => undefined} /></div>
      ) : p.lens === "term" ? (
        <div className="min-h-[70dvh]"><TermHeat model={p.model} heat={p.heat} metric={metric} onMetric={setMetric} unplacedByDay={new Map()} todayIso={p.now.iso} onPick={(w, d) => { p.onWeek(w); p.onDay(d); p.onLens("agenda"); }} compareOn={false} brush={null} onBrush={() => undefined} currentWeek={p.week} /></div>
      ) : (
        <>
          <div className="mt-3 grid grid-cols-7 px-2" role="tablist" aria-label={t("calendar.mobile.days")} onPointerDown={onStripDown} onPointerUp={onStripUp} style={{ touchAction: "pan-y" }}>
            {[1, 2, 3, 4, 5, 6, 7].map((d) => {
              const iso = p.dates[d - 1];
              const occ = p.heat.get(`${p.week}:${d}`)?.occupancy ?? 0;
              const selected = d === p.day;
              const today = iso === p.now.iso;
              return (
                <button key={d} type="button" role="tab" aria-selected={selected} onClick={() => p.onDay(d)} className="flex min-h-11 flex-col items-center gap-0.5 py-1" aria-label={`${dayName(d, locale)} ${iso ?? ""}`}>
                  <span className="text-[11px] font-semibold text-label-3">{dayName(d, locale, "short").slice(0, 1)}</span>
                  <span className={cn("flex size-9 items-center justify-center rounded-full text-[15px] tabular-nums", selected && "bg-label-1 font-semibold text-(--cal-canvas)", !selected && today && "font-semibold text-[var(--now-strong)]")}>{iso ? Number(iso.slice(8)) : ""}</span>
                  <span aria-hidden className={cn("size-1 rounded-full", occ > 0.75 ? "bg-label-1" : occ > 0.4 ? "bg-label-2" : occ > 0 ? "bg-label-4" : "bg-transparent")} />
                </button>
              );
            })}
          </div>
          <div className="px-4 pt-2">
            <SegmentedGlass fill size="md" aria-label={t("calendar.mobile.list")} options={[{ value: "list", label: t("calendar.mobile.list") }, { value: "timeline", label: t("calendar.mobile.timeline") }]} value={mode} onValueChange={setMode} />
          </div>
          <div className="flex gap-2 overflow-x-auto px-4 py-3 [scrollbar-width:none]">
            <Button size="sm" variant={p.subject ? "secondary" : "default"} onClick={() => p.onSubject(null)}>{t("calendar.subject.all")}</Button>
            {p.subject ? <Button size="sm">{p.subject.kind === "room" ? (p.model.roomById.get(Number(p.subject.id))?.name ?? "") : p.subject.id}</Button> : null}
            <Button size="sm" variant="secondary" onClick={() => (document.querySelector("[data-testid=subject-picker]") as HTMLElement | null)?.click()}><Search aria-hidden />{t("calendar.subject.label")}</Button>
          </div>
          <div className="relative min-h-[60dvh] flex-1">
            {mode === "list" ? (
              <AgendaLens model={p.model} events={dayEvents} days={[p.day]} dates={p.dates} todayIso={p.now.iso} nowMin={p.now.minutes} selection={p.selection} onSelect={p.onSelect} onOpen={(ev) => setOpen(ev)} compact emptyLabel={t("calendar.agenda.empty")} />
            ) : p.subject ? (
              <div className="absolute inset-0">
                <TimeGrid model={p.model} mask={1 << (p.week - 1)} columns={columns} colW={Math.max(240, typeof window !== "undefined" ? window.innerWidth - 72 : 300)} rowH={rowHeightFor(3)} events={dayEvents} colOf={() => 0} blocks={room !== null ? blocksOf(p.model, p.week, p.day).filter((b) => b.room === room) : []} blockCol={() => 0} bookings={[]} bookingCol={() => 0} selection={p.selection} onSelect={p.onSelect} onSelectMany={() => undefined} onOpen={(ev) => setOpen(ev)} onMove={() => undefined} onCreate={() => undefined} onResize={() => undefined} onAnnounce={() => undefined} readOnly nowMin={p.dates[p.day - 1] === p.now.iso ? p.now.minutes : null} nowCols={p.dates[p.day - 1] === p.now.iso ? [0] : []} gridLabel={t("calendar.timelineLabel", { day: dayName(p.day, locale) })} headerH={48} line2={(e) => `${p.model.roomById.get(e.room)?.name ?? ""} · ${e.a.size}/${roomCap(p.model, p.model.roomById.get(e.room))}`} ariaFor={(e) => e.a.label} />
              </div>
            ) : (
              <p className="px-4 text-[13px] text-label-2">{t("calendar.empty.pickSubject")}</p>
            )}
          </div>
        </>
      )}

      <Sheet open={open !== null} onOpenChange={(o) => !o && setOpen(null)}>
        <SheetContent side="bottom" className="max-h-[92dvh] p-0" showCloseButton={false}>
          <SheetTitle className="sr-only">{open?.a.label ?? ""}</SheetTitle>
          {open ? (
            <ClassInspector
              surface="calendar"
              className="max-h-[88dvh] rounded-none bg-transparent shadow-none [backdrop-filter:none]"
              termId={p.termId}
              runId={p.runId}
              kind={p.model.exam ? "exams" : "meetings"}
              assignment={open.a}
              roomName={(id) => p.model.roomById.get(id)?.name ?? `#${id}`}
              roomCap={(ids) => ids.reduce((s, id) => s + roomCap(p.model, p.model.roomById.get(id)), 0)}
              allWeeks={p.model.weeks.filter((w) => w <= 16)}
              readOnly={p.readOnly}
              onClose={() => setOpen(null)}
              onMove={() => {
                setMoving(open);
                setOpen(null);
              }}
              onLock={(locked) => p.actions.lock([open.a.id], locked, open.a.label)}
              appear={false}
            />
          ) : null}
        </SheetContent>
      </Sheet>
      <MoveDialog
        model={p.model}
        ev={moving}
        week={p.week}
        open={moving !== null}
        onOpenChange={(o) => !o && setMoving(null)}
        onConfirm={async (target, scope) => {
          if (!moving) return false;
          const res = await p.actions.move([{ aid: moving.a.id, day: target.day, start_period: target.sp, end_period: target.ep, room_ids: [target.room], scope: scope.scope, week: scope.scope === "all" ? null : scope.week }], moving.a.label, p.model.roomById.get(target.room)?.name ?? "");
          return res.applied;
        }}
      />
    </div>
  );
}
