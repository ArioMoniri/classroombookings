"use client";
/**
 * Gün (Day timeline, calendar.md §6.4): rooms × proportional time 08:30–22:50 (1.4 px/min standard),
 * a vertical now-line with its time capsule, past time shaded, "Şu an boş" / "≥ 60" / "PC" quick filters.
 * Drag across a free range creates (booking default); chips drag horizontally (period snap, 16 px magnet)
 * and vertically (room rows) with the same live check as the board.
 */
import { animate, motion, useMotionValue } from "motion/react";
import { memo, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { PERIODS, PERIODS_PER_DAY } from "@/lib/time";
import { springs, useReduce } from "@/lib/motion";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import type { IndexRoom } from "@/lib/api/calendar";
import { chipVars } from "./event-chip";
import { checkMove, slotFree, spanText, whenText, type CheckResult } from "./model/check";
import { DAY_END_MIN, DAY_START_MIN, minuteX, periodEndMin, periodStartMin, visibleRange } from "./model/geometry";
import type { CalBlock, CalBooking, CalEvent, CalendarModel, WeekMask } from "./model/index-model";
import { pullFactor } from "./model/magnet";
import type { CreateIntent, GridColumn, MoveIntent } from "./time-grid";

const LABEL_W = 104;
const ROW_H = 40;
const HEAD_H = 32;

export interface DayTimelineProps {
  model: CalendarModel;
  rooms: IndexRoom[];
  day: number;
  mask: WeekMask;
  pxPerMin: number;
  events: CalEvent[];
  blocks: CalBlock[];
  bookings: CalBooking[];
  nowMin: number | null;
  isToday: boolean;
  selection: ReadonlySet<number>;
  readOnly?: boolean;
  onSelect: (aid: number | null, mode: "replace" | "toggle" | "range") => void;
  onOpen: (ev: CalEvent) => void;
  onMove: (intent: MoveIntent) => void;
  onCreate: (intent: CreateIntent) => void;
  onAnnounce: (msg: string) => void;
  ariaFor: (ev: CalEvent) => string;
  label: string;
}

function nearestPeriodByX(x: number, pxPerMin: number): { p: number; x: number } {
  let best = 1;
  let bx = 0;
  let d = Number.POSITIVE_INFINITY;
  for (let p = 1; p <= PERIODS_PER_DAY; p++) {
    const px = minuteX(periodStartMin(p), pxPerMin);
    if (Math.abs(px - x) < d) {
      d = Math.abs(px - x);
      best = p;
      bx = px;
    }
  }
  return { p: best, x: bx };
}

function periodAtX(x: number, pxPerMin: number): number {
  const min = DAY_START_MIN + x / pxPerMin;
  for (let p = 1; p <= PERIODS_PER_DAY; p++) if (min < periodEndMin(p)) return p;
  return PERIODS_PER_DAY;
}

function DayTimelineImpl(p: DayTimelineProps) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const reduce = useReduce();
  const ref = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ top: 0, height: 600 });
  const [drag, setDrag] = useState<{ ev: CalEvent; grabX: number; grabY: number; row: number; sp: number; check: CheckResult | null } | null>(null);
  const [create, setCreate] = useState<{ row: number; p0: number; p1: number } | null>(null);
  const ptr = useRef<{ id: number; x: number; y: number; ev: CalEvent | null; started: boolean; meta: boolean } | null>(null);
  const gx = useMotionValue(0);
  const gy = useMotionValue(0);
  const width = LABEL_W + minuteX(DAY_END_MIN, p.pxPerMin);
  const rowIndex = useMemo(() => new Map(p.rooms.map((r, i) => [r.id, i])), [p.rooms]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setView({ top: el.scrollTop, height: el.clientHeight });
    measure();
    let raf: number | null = null;
    const onScroll = () => {
      if (raf === null)
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

  // scroll the now-line into view once when the day is today
  const scrolled = useRef(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || scrolled.current || !p.isToday || p.nowMin === null) return;
    scrolled.current = true;
    el.scrollLeft = Math.max(0, minuteX(p.nowMin, p.pxPerMin) - el.clientWidth / 3);
  }, [p.isToday, p.nowMin, p.pxPerMin]);

  const [r0, r1] = visibleRange(Math.max(0, view.top - HEAD_H), view.height, ROW_H, p.rooms.length, 8);
  const xOf = (sp: number) => LABEL_W + minuteX(periodStartMin(sp), p.pxPerMin);
  const wOf = (sp: number, ep: number) => Math.max(6, minuteX(periodEndMin(ep), p.pxPerMin) - minuteX(periodStartMin(sp), p.pxPerMin) - 1);
  const content = (cx: number, cy: number) => {
    const el = ref.current;
    if (!el) return { x: 0, y: 0 };
    const r = el.getBoundingClientRect();
    return { x: cx - r.left + el.scrollLeft, y: cy - r.top + el.scrollTop - HEAD_H };
  };
  const target = (ev: CalEvent, row: number, sp: number) => ({ room: p.rooms[row]?.id ?? ev.room, day: p.day, sp, ep: sp + (ev.ep - ev.sp) });

  const onDown = (e: ReactPointerEvent<HTMLDivElement>, ev: CalEvent | null) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    ptr.current = { id: e.pointerId, x: e.clientX, y: e.clientY, ev, started: false, meta: e.metaKey || e.ctrlKey };
    ref.current?.setPointerCapture(e.pointerId);
  };
  const onMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const pt = ptr.current;
    if (!pt || pt.id !== e.pointerId) return;
    const c = content(e.clientX, e.clientY);
    if (!pt.started) {
      if (Math.hypot(e.clientX - pt.x, e.clientY - pt.y) < 6 || p.readOnly) return;
      pt.started = true;
      const c0 = content(pt.x, pt.y);
      if (pt.ev) {
        const row = rowIndex.get(pt.ev.room) ?? 0;
        const left = xOf(pt.ev.sp);
        const top = HEAD_H + row * ROW_H + 4;
        gx.set(left);
        gy.set(top);
        setDrag({ ev: pt.ev, grabX: c0.x - left, grabY: c0.y + HEAD_H - top, row, sp: pt.ev.sp, check: null });
        p.onAnnounce(t("calendar.drag.pickedUp", { label: pt.ev.a.label }));
      } else {
        const row = Math.floor(c0.y / ROW_H);
        const per = periodAtX(c0.x - LABEL_W, p.pxPerMin);
        setCreate({ row, p0: per, p1: per });
      }
    }
    if (drag) {
      const left = c.x - drag.grabX;
      const top = c.y + HEAD_H - drag.grabY;
      const snap = nearestPeriodByX(left - LABEL_W, p.pxPerMin);
      const row = Math.min(p.rooms.length - 1, Math.max(0, Math.round((top - HEAD_H - 4) / ROW_H)));
      const slotX = LABEL_W + snap.x;
      const slotY = HEAD_H + row * ROW_H + 4;
      const pull = reduce ? 0 : pullFactor(Math.hypot(slotX - left, slotY - top));
      gx.set(left + (slotX - left) * pull);
      gy.set(top + (slotY - top) * pull);
      const sp = Math.min(snap.p, PERIODS_PER_DAY - (drag.ev.ep - drag.ev.sp));
      if (row !== drag.row || sp !== drag.sp || !drag.check) {
        const check = checkMove(p.model, drag.ev, { ...target(drag.ev, row, sp), mask: p.mask });
        setDrag({ ...drag, row, sp, check });
      }
    } else if (create) {
      const per = periodAtX(c.x - LABEL_W, p.pxPerMin);
      if (per !== create.p1) setCreate({ ...create, p1: per });
    }
  };
  const onUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    const pt = ptr.current;
    if (!pt || pt.id !== e.pointerId) return;
    ptr.current = null;
    if (!pt.started) {
      if (pt.ev) {
        p.onSelect(pt.ev.a.id, pt.meta ? "toggle" : "replace");
        if (!pt.meta) p.onOpen(pt.ev);
      } else p.onSelect(null, "replace");
      return;
    }
    if (drag) {
      const d = drag;
      setDrag(null);
      const tg = target(d.ev, d.row, d.sp);
      if (tg.room === d.ev.room && tg.sp === d.ev.sp) return;
      if (!reduce) {
        void animate(gx, xOf(tg.sp), springs.snappy);
        void animate(gy, HEAD_H + d.row * ROW_H + 4, springs.snappy);
      }
      const check = checkMove(p.model, d.ev, { ...tg, mask: p.mask });
      p.onMove({ ev: d.ev, target: tg, extra: [], check, skipPopover: e.shiftKey, anchor: { x: e.clientX, y: e.clientY } });
      return;
    }
    if (create) {
      const c = create;
      setCreate(null);
      const room = p.rooms[c.row];
      if (!room) return;
      const column: GridColumn = { key: `r${room.id}`, room: room.id, day: p.day, label: room.name, ariaLabel: room.name };
      p.onCreate({ column, sp: Math.min(c.p0, c.p1), ep: Math.max(c.p0, c.p1), anchor: { x: e.clientX, y: e.clientY } });
    }
  };

  const nowX = p.isToday && p.nowMin !== null && p.nowMin >= DAY_START_MIN && p.nowMin <= DAY_END_MIN ? LABEL_W + minuteX(p.nowMin, p.pxPerMin) : null;
  const nowLabel = p.nowMin !== null ? `${String(Math.floor(p.nowMin / 60)).padStart(2, "0")}:${String(p.nowMin % 60).padStart(2, "0")}` : "";
  const byRoom = useMemo(() => {
    const m = new Map<number, CalEvent[]>();
    for (const e of p.events) m.set(e.room, [...(m.get(e.room) ?? []), e]);
    return m;
  }, [p.events]);

  return (
    <div
      ref={ref}
      role="grid"
      aria-label={p.label}
      aria-rowcount={p.rooms.length + 1}
      tabIndex={0}
      className="cal-canvas relative h-full overflow-auto outline-none"
      onPointerDown={(e) => onDown(e, null)}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={() => {
        ptr.current = null;
        setDrag(null);
        setCreate(null);
      }}
      data-testid="day-timeline"
    >
      <div className="relative" style={{ width, height: HEAD_H + p.rooms.length * ROW_H }}>
        <div className="cal-sticky sticky top-0 z-20 hairline-b" style={{ width, height: HEAD_H }} role="row">
          <div className="cal-sticky sticky left-0 z-10 h-full" style={{ width: LABEL_W }} />
          {PERIODS.map((per) => (
            <span key={per.index} role="columnheader" className="absolute top-2 text-[11px] text-label-3 tabular-nums" style={{ left: LABEL_W + minuteX(periodStartMin(per.index), p.pxPerMin) + 3 }} title={`P${per.index}`}>
              {per.start}
            </span>
          ))}
          {nowX !== null ? <span className="cal-now-pill" style={{ left: nowX - 20, top: 8 }}>{nowLabel}</span> : null}
        </div>
        {/* period ticks + past shading */}
        <div aria-hidden className="pointer-events-none absolute" style={{ left: 0, top: HEAD_H, width, height: p.rooms.length * ROW_H }}>
          {PERIODS.map((per) => (
            <div key={per.index} className="absolute inset-y-0 w-px" style={{ left: LABEL_W + minuteX(periodStartMin(per.index), p.pxPerMin), background: "var(--cal-line)" }} />
          ))}
          {nowX !== null ? <div className="absolute inset-y-0" style={{ left: LABEL_W, width: nowX - LABEL_W, background: "var(--cal-past)" }} /> : null}
        </div>
        {p.rooms.slice(r0, r1 + 1).map((room, i) => {
          const row = r0 + i;
          const top = HEAD_H + row * ROW_H;
          return (
            <div key={room.id} role="row" aria-rowindex={row + 2} className="absolute left-0" style={{ top, width, height: ROW_H, boxShadow: "inset 0 -1px 0 var(--cal-line)" }}>
              <div role="rowheader" className="cal-canvas sticky left-0 z-10 flex h-full items-center justify-between px-2" style={{ width: LABEL_W, boxShadow: "inset -1px 0 0 var(--cal-line-strong)" }} aria-label={t("calendar.roomAria", { room: room.name, cap: room.capacity })}>
                <span className="text-[12px] font-semibold">{room.name}</span>
                <span className="text-[11px] text-label-3 tabular-nums">{p.model.exam ? room.exam_capacity : room.capacity}{room.tags.includes("PC") ? " · PC" : ""}</span>
              </div>
              {PERIODS.map((per) => {
                const free = slotFree(p.model, room.id, p.day, per.index, per.index, p.mask);
                return (
                  <div key={per.index} role="gridcell" data-testid="grid-drop-cell" data-room-id={room.id} data-day={p.day} data-period={per.index} data-free={free ? "true" : undefined} className={cn("absolute inset-y-0", free && !p.readOnly && "hover:bg-fill-3")} style={{ left: xOf(per.index), width: wOf(per.index, per.index) + 1 }} aria-label={`${room.name} ${whenText(p.day, per.index, per.index)[lang]}`} />
                );
              })}
              {p.blocks.filter((b) => b.room === room.id).map((b) => (
                <div key={b.key} className="cal-block" style={{ left: xOf(b.sp), width: wOf(b.sp, b.ep), top: 4, height: ROW_H - 8 }} role="note" aria-label={t("calendar.insp.blockLabel", { label: b.b.label })}>{b.b.label}</div>
              ))}
              {p.bookings.filter((b) => b.room === room.id).map((b) => (
                <div key={b.key} className="cal-chip cal-booking" style={{ left: xOf(b.sp), width: wOf(b.sp, b.ep), top: 4, height: ROW_H - 8, pointerEvents: "none" }} role="note">
                  <span className="cal-code truncate">{b.bk.title}</span>
                </div>
              ))}
              {(byRoom.get(room.id) ?? []).map((ev) => {
                const past = nowX !== null && periodEndMin(ev.ep) < (p.nowMin ?? 0);
                return (
                  <div
                    key={ev.key}
                    role="button"
                    tabIndex={-1}
                    className="cal-chip"
                    data-testid="calendar-event"
                    data-assignment-id={ev.a.id}
                    data-selected={p.selection.has(ev.a.id) ? "true" : undefined}
                    data-conflict={ev.conflict ? "true" : undefined}
                    data-locked={ev.a.locked ? "true" : undefined}
                    data-past={past ? "true" : undefined}
                    data-origin-drag={drag?.ev.key === ev.key ? "true" : undefined}
                    data-culprit={drag?.check?.culprits.includes(ev.key) ? "true" : undefined}
                    aria-label={p.ariaFor(ev)}
                    style={{ ...chipVars(ev.a.slot), left: xOf(ev.sp), width: wOf(ev.sp, ev.ep), top: 4, height: ROW_H - 8, justifyContent: "center" }}
                    onPointerDown={(e) => onDown(e, ev)}
                  >
                    <span className="cal-code truncate">{ev.a.code ?? ev.a.label}</span>
                  </div>
                );
              })}
            </div>
          );
        })}
        {nowX !== null ? <div className="cal-now" aria-hidden style={{ left: nowX - 1, width: 2, top: HEAD_H, height: p.rooms.length * ROW_H }} /> : null}
        {create ? (
          <div className="cal-slot" data-state="create" style={{ left: xOf(Math.min(create.p0, create.p1)), width: wOf(Math.min(create.p0, create.p1), Math.max(create.p0, create.p1)), top: HEAD_H + create.row * ROW_H + 3, height: ROW_H - 6 }}>
            <span className="absolute -top-5 left-0 text-[11px] font-medium whitespace-nowrap text-tint-text tabular-nums">{spanText(Math.min(create.p0, create.p1), Math.max(create.p0, create.p1))}</span>
          </div>
        ) : null}
        {drag ? (
          <>
            <motion.div className="cal-slot" layoutId={reduce ? undefined : "drop-slot"} transition={reduce ? { duration: 0 } : springs.snappy} data-state={!drag.check ? "ok" : !drag.check.ok ? "hard" : drag.check.soft.some((s) => s.code === "capacity") ? "soft" : "ok"} style={{ left: xOf(drag.sp), width: wOf(drag.sp, drag.sp + drag.ev.ep - drag.ev.sp), top: HEAD_H + drag.row * ROW_H + 4, height: ROW_H - 8 }} />
            <motion.div className="pointer-events-none absolute top-0 left-0 z-30" style={{ x: gx, y: gy }}>
              <motion.div initial={{ scale: 1 }} animate={{ scale: reduce ? 1 : 1.03 }} transition={springs.snappy} className="cal-chip shadow-[0_12px_32px_-8px_rgb(0_0_0/0.35)]" style={{ ...chipVars(drag.ev.a.slot), position: "relative", width: wOf(drag.ev.sp, drag.ev.ep), height: ROW_H - 8, justifyContent: "center" }}>
                <span className="cal-code truncate">{drag.ev.a.code ?? drag.ev.a.label}</span>
              </motion.div>
              <div className="glass-thick mt-1 w-max max-w-[320px] rounded-full px-2.5 py-1 text-[11px] font-medium" role="status">
                {drag.check ? (drag.check.ok ? `${p.rooms[drag.row]?.name ?? ""} · ${spanText(drag.sp, drag.sp + drag.ev.ep - drag.ev.sp)} ✓` : `✕ ${drag.check.hard[0]?.text[lang] ?? ""}`) : ""}
              </div>
            </motion.div>
          </>
        ) : null}
      </div>
    </div>
  );
}

export const DayTimeline = memo(DayTimelineImpl);
