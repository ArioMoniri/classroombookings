"use client";
/**
 * Pano · Hafta şeridi (calendar.md §6.2): rooms × (7 days × 18 periods). Rows are virtualised (row 32 /
 * 24 compact, overscan 8); each row is one element with a gradient background plus absolutely positioned
 * bars. Codes show from 14 px slots; below that only the fill and bar (the tooltip and inspector carry the
 * rest). Per-day totals row is sticky. Empty weekend days collapse to 24 px.
 */
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { PERIODS_PER_DAY, dayName } from "@/lib/time";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { chipVars } from "./event-chip";
import type { HeatValue } from "./model/heat";
import type { CalBlock, CalEvent, CalendarModel } from "./model/index-model";
import { visibleRange } from "./model/geometry";
import type { IndexRoom } from "@/lib/api/calendar";

const LABEL_W = 96;
const HEAD_H = 44;

export interface BoardStripProps {
  model: CalendarModel;
  rooms: IndexRoom[];
  events: CalEvent[];
  blocks: CalBlock[];
  slotW: number;
  rowH: number;
  heat: Map<string, HeatValue>;
  week: number;
  dates: (string | null)[];
  selection: ReadonlySet<number>;
  onSelect: (aid: number | null, mode: "replace" | "toggle" | "range") => void;
  onOpen: (ev: CalEvent) => void;
  onPickDay: (day: number) => void;
  onPickRoom: (roomId: number) => void;
  todayDay: number | null;
  ariaFor: (ev: CalEvent) => string;
}

function BoardStripImpl(p: BoardStripProps) {
  const { t, locale } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ top: 0, height: 600 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setView({ top: el.scrollTop, height: el.clientHeight });
    measure();
    let raf: number | null = null;
    const onScroll = () => {
      if (raf !== null) return;
      raf = requestAnimationFrame(() => {
        raf = null;
        measure();
      });
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", onScroll);
      ro.disconnect();
    };
  }, []);

  const busyDays = useMemo(() => new Set(p.events.map((e) => e.day)), [p.events]);
  const dayW = useMemo(() => [1, 2, 3, 4, 5, 6, 7].map((d) => (d >= 6 && !busyDays.has(d) ? 24 : PERIODS_PER_DAY * p.slotW)), [busyDays, p.slotW]);
  const dayX = useMemo(() => {
    const xs = [LABEL_W];
    for (const w of dayW) xs.push(xs[xs.length - 1] + w);
    return xs;
  }, [dayW]);
  const width = dayX[7];
  const byRoom = useMemo(() => {
    const m = new Map<number, CalEvent[]>();
    for (const e of p.events) {
      const l = m.get(e.room) ?? [];
      l.push(e);
      m.set(e.room, l);
    }
    return m;
  }, [p.events]);
  const blocksByRoom = useMemo(() => {
    const m = new Map<number, CalBlock[]>();
    for (const b of p.blocks) {
      const l = m.get(b.room) ?? [];
      l.push(b);
      m.set(b.room, l);
    }
    return m;
  }, [p.blocks]);
  const [r0, r1] = visibleRange(Math.max(0, view.top - HEAD_H), view.height, p.rowH, p.rooms.length, 8);

  const x = (day: number, period: number) => dayX[day - 1] + (dayW[day - 1] < PERIODS_PER_DAY * p.slotW ? 0 : (period - 1) * p.slotW);
  const w = (day: number, sp: number, ep: number) => (dayW[day - 1] < PERIODS_PER_DAY * p.slotW ? dayW[day - 1] : (ep - sp + 1) * p.slotW - 1);

  return (
    <div ref={ref} className="cal-canvas relative h-full overflow-auto" role="grid" aria-label={t("calendar.stripLabel", { week: p.week })} aria-rowcount={p.rooms.length + 1} aria-colcount={8} data-testid="board-strip">
      <div className="relative" style={{ width, height: HEAD_H + p.rooms.length * p.rowH }}>
        <div className="cal-sticky sticky top-0 z-20 hairline-b" style={{ width, height: HEAD_H }} role="row">
          <div className="cal-sticky sticky left-0 z-10 h-full" style={{ width: LABEL_W }} />
          {[1, 2, 3, 4, 5, 6, 7].map((d) => {
            const h = p.heat.get(`${p.week}:${d}`);
            const pct = Math.round((h?.occupancy ?? 0) * 100);
            return (
              <button
                key={d}
                type="button"
                role="columnheader"
                onClick={() => p.onPickDay(d)}
                className={cn("absolute top-0 flex h-full flex-col items-start justify-center overflow-hidden px-2 text-left hover:bg-fill-3", p.todayDay === d && "text-tint-text")}
                style={{ left: dayX[d - 1], width: dayW[d - 1], boxShadow: "inset 1px 0 0 var(--cal-line-strong)" }}
                aria-label={`${dayName(d, locale)} ${p.dates[d - 1] ?? ""}, ${t("calendar.totals", { p: pct, c: h?.conflicts ?? 0 })}`}
              >
                {dayW[d - 1] > 40 ? (
                  <>
                    <span className="text-[12px] leading-4 font-semibold">{dayName(d, locale, "short")} {p.dates[d - 1]?.slice(8) ?? ""}</span>
                    <span className="text-[11px] leading-[14px] text-label-2 tabular-nums">{t("calendar.heat.cellShort", { p: pct })}{h?.conflicts ? ` · ${t("calendar.issues.conflicts", { n: h.conflicts })}` : ""}</span>
                  </>
                ) : (
                  <span className="text-[11px] text-label-3">{dayName(d, locale, "narrow" as "short")}</span>
                )}
              </button>
            );
          })}
        </div>
        {p.rooms.slice(r0, r1 + 1).map((room, i) => {
          const idx = r0 + i;
          const top = HEAD_H + idx * p.rowH;
          const evs = byRoom.get(room.id) ?? [];
          return (
            <div key={room.id} role="row" aria-rowindex={idx + 2} className="absolute left-0" style={{ top, width, height: p.rowH, boxShadow: "inset 0 -1px 0 var(--cal-line)" }}>
              <button type="button" role="rowheader" onClick={() => p.onPickRoom(room.id)} className="cal-canvas sticky left-0 z-10 flex h-full items-center justify-between gap-1 px-2 text-left hover:bg-fill-3" style={{ width: LABEL_W, boxShadow: "inset -1px 0 0 var(--cal-line-strong)" }} aria-label={t("calendar.roomAria", { room: room.name, cap: room.capacity })}>
                <span className="truncate text-[12px] font-semibold">{room.name}</span>
                <span className="text-[11px] text-label-3 tabular-nums">{p.model.exam ? room.exam_capacity : room.capacity}</span>
              </button>
              {(blocksByRoom.get(room.id) ?? []).map((b) => (
                <div key={b.key} className="cal-block" style={{ left: x(b.day, b.sp), width: w(b.day, b.sp, b.ep), top: 2, height: p.rowH - 4, padding: 0 }} aria-hidden />
              ))}
              {evs.map((ev) => {
                const bw = w(ev.day, ev.sp, ev.ep);
                const showCode = p.slotW >= 14 && bw > 30;
                return (
                  <button
                    key={ev.key}
                    type="button"
                    className="cal-chip"
                    data-testid="calendar-event"
                    data-assignment-id={ev.a.id}
                    data-selected={p.selection.has(ev.a.id) ? "true" : undefined}
                    data-conflict={ev.conflict ? "true" : undefined}
                    data-locked={ev.a.locked ? "true" : undefined}
                    aria-label={p.ariaFor(ev)}
                    title={`${ev.a.label} · ${room.name}`}
                    style={{ ...chipVars(ev.a.slot), left: x(ev.day, ev.sp), width: bw, top: 2, height: p.rowH - 4, padding: showCode ? "0 4px 0 7px" : 0, justifyContent: "center" }}
                    onClick={(e) => {
                      if (e.metaKey || e.ctrlKey) p.onSelect(ev.a.id, "toggle");
                      else {
                        p.onSelect(ev.a.id, "replace");
                        p.onOpen(ev);
                      }
                    }}
                  >
                    {showCode ? <span className="cal-code truncate text-[11px]">{ev.a.code ?? ev.a.label}</span> : null}
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export const BoardStrip = memo(BoardStripImpl);
