"use client";
/**
 * The time grid behind Board · Gün (columns = rooms) and the Week lens (columns = days):
 * calendar.md §6.1, §6.3, §9.1–§9.4, §12, §13; motion.md §3.2; motion_designer patterns §7 (lift / magnetic
 * snap / settle), §8 (resize), §9 (conflict shake).
 *
 * - Columns are virtualised (only the visible window ± 4 renders); the grid background is a gradient, not
 *   1,080 cell divs. Hit-testing is arithmetic (content coordinates → column, period), never elementFromPoint.
 * - Drag is 1:1 with the pointer; the ghost's top-left snaps to the nearest period/column within 16 px
 *   (full pull inside 5 px) and a single drop-slot outline glides between slots. The live check is the pure
 *   `checkMove` (< 1 ms), run only when the slot changes.
 * - ⇧-drag on empty space lassos; a plain drag on empty space quick-creates; edges resize per period.
 * - Keyboard: one tab stop (role=grid, aria-activedescendant), arrows / PageUp / Home / End / ⌘↑↓ move the
 *   cell cursor, Enter opens or creates, N creates, Space picks up (arrows move, Space/Enter drop, Esc cancel),
 *   ⇧↑↓ / ⌥↑↓ resize, X toggles selection.
 */
import { animate, motion, useMotionValue } from "motion/react";
import {
  forwardRef,
  memo,
  useCallback,
  useEffect,
  useId,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { PERIODS, PERIODS_PER_DAY } from "@/lib/time";
import { springs, useReduce } from "@/lib/motion";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { EventChip, chipVars } from "./event-chip";
import { checkMove, slotFree, spanText, whenText, type CheckResult } from "./model/check";
import type { GhostPlacement } from "./model/compare";
import { GUTTER_W, layoutLanes, nowOffset, periodAt, rowTable, spanHeight, visibleRange, type RowTable } from "./model/geometry";
import type { CalBlock, CalBooking, CalEvent, CalendarModel, WeekMask } from "./model/index-model";
import { roomCap } from "./model/index-model";
import { nearestValidStart, snapGhost } from "./model/magnet";

export interface GridColumn {
  key: string;
  /** room this column books into; null = keep the event's room (Week lens of an instructor / cohort) */
  room: number | null;
  day: number;
  label: string;
  sub?: string;
  ariaLabel: string;
  building?: string;
  today?: boolean;
  tag?: string;
}

export interface MoveIntent {
  ev: CalEvent;
  target: { room: number; day: number; sp: number; ep: number };
  /** the rest of a multi-move, with the same relative offsets */
  extra: { ev: CalEvent; target: { room: number; day: number; sp: number; ep: number } }[];
  check: CheckResult;
  skipPopover: boolean;
  anchor: { x: number; y: number };
}

export interface CreateIntent {
  column: GridColumn;
  sp: number;
  ep: number;
  anchor: { x: number; y: number };
}

export interface TimeGridHandle {
  focusGrid: () => void;
  scrollToEvent: (aid: number) => void;
}

export interface TimeGridProps {
  model: CalendarModel;
  mask: WeekMask;
  columns: GridColumn[];
  colW: number;
  rowH: number;
  events: CalEvent[];
  colOf: (ev: CalEvent) => number;
  blocks: CalBlock[];
  blockCol: (b: CalBlock) => number;
  bookings: CalBooking[];
  bookingCol: (b: CalBooking) => number;
  ghosts?: GhostPlacement[];
  ghostCol?: (g: GhostPlacement) => number;
  movedAids?: ReadonlySet<number>;
  selection: ReadonlySet<number>;
  onSelect: (aid: number | null, mode: "replace" | "toggle" | "range") => void;
  onSelectMany: (aids: number[], additive: boolean) => void;
  onOpen: (ev: CalEvent) => void;
  onMove: (intent: MoveIntent) => void;
  onCreate: (intent: CreateIntent) => void;
  onResize: (ev: CalEvent, sp: number, ep: number) => void;
  onZoom?: (delta: number, anchor: { x: number; y: number }) => void;
  onAnnounce: (msg: string) => void;
  readOnly?: boolean;
  /** minutes of the day, when "now" falls in this view; nowCols = column indices that are today */
  nowMin?: number | null;
  nowCols?: readonly number[];
  gridLabel: string;
  header?: ReactNode;
  headerH: number;
  /** pending (optimistic) placements awaiting confirmation */
  pending?: { ev: CalEvent; col: number; sp: number; ep: number }[];
  shakeAid?: number | null;
  focusAid?: number | null;
  line2: (ev: CalEvent) => string;
  ariaFor: (ev: CalEvent) => string;
  /** Week lens with overlapping chips: draw a red bracket for conflicting pairs */
  emptyHint?: ReactNode;
}

interface DragState {
  kind: "move";
  ev: CalEvent;
  aids: number[];
  grabX: number;
  grabY: number;
  span: number;
  originCol: number;
}

interface Hover {
  col: number;
  sp: number;
}

const DRAG_THRESHOLD = 6;
const TOUCH_DELAY = 250;
const TOUCH_TOLERANCE = 8;
const PAUSE_MS = 600;

function TimeGridImpl(props: TimeGridProps, ref: React.Ref<TimeGridHandle>) {
  const { model, mask, columns, colW, rowH, events, colOf, selection, readOnly, headerH } = props;
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const reduce = useReduce();
  const gridId = useId();
  const scroller = useRef<HTMLDivElement>(null);
  const rows: RowTable = useMemo(() => rowTable(rowH), [rowH]);
  const [view, setView] = useState({ left: 0, top: 0, width: 1200, height: 800 });
  const [cursor, setCursor] = useState<{ col: number; p: number }>({ col: 0, p: 1 });
  const [drag, setDrag] = useState<DragState | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);
  const [hint, setHint] = useState<number | null>(null);
  const [lasso, setLasso] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  const [create, setCreate] = useState<{ col: number; p0: number; p1: number } | null>(null);
  const [resize, setResize] = useState<{ ev: CalEvent; col: number; sp: number; ep: number } | null>(null);
  const [kbMove, setKbMove] = useState<{ ev: CalEvent; col: number; sp: number } | null>(null);
  const ghostX = useMotionValue(0);
  const ghostY = useMotionValue(0);
  const ghostRef = useRef<HTMLDivElement>(null);
  const pointer = useRef<{ id: number; x: number; y: number; ev: CalEvent | null; type: string; started: boolean; timer: ReturnType<typeof setTimeout> | null; mod: { shift: boolean; meta: boolean; alt: boolean } } | null>(null);
  const pauseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const raf = useRef<number | null>(null);
  const scrollRaf = useRef<number | null>(null);
  const [shaking, setShaking] = useState<number | null>(null);

  const contentW = GUTTER_W + columns.length * colW;
  const contentH = headerH + rows.total;
  const [c0, c1] = visibleRange(Math.max(0, view.left - GUTTER_W), view.width, colW, columns.length, 4);

  // ------------------------------------------------------------------ measure + scroll (rAF-throttled)
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const measure = () => setView({ left: el.scrollLeft, top: el.scrollTop, width: el.clientWidth, height: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    const onScroll = () => {
      if (scrollRaf.current !== null) return;
      scrollRaf.current = requestAnimationFrame(() => {
        scrollRaf.current = null;
        measure();
      });
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      ro.disconnect();
      el.removeEventListener("scroll", onScroll);
    };
  }, []);

  // ⌘/Ctrl + wheel and trackpad pinch (wheel + ctrlKey) zoom the canvas only; browser zoom keys are never intercepted
  const zoomAcc = useRef(0);
  const onZoomRef = useRef(props.onZoom);
  useEffect(() => {
    onZoomRef.current = props.onZoom;
  }, [props.onZoom]);
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      zoomAcc.current += e.deltaY;
      if (Math.abs(zoomAcc.current) < 40) return;
      const step = zoomAcc.current < 0 ? 1 : -1;
      zoomAcc.current = 0;
      const r = el.getBoundingClientRect();
      onZoomRef.current?.(step, { x: e.clientX - r.left, y: e.clientY - r.top });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // a long-press lift owns the touch: stop the page from panning while the ghost is dragged
  useEffect(() => {
    if (!drag && !create && !lasso) return;
    const stop = (e: TouchEvent) => e.preventDefault();
    window.addEventListener("touchmove", stop, { passive: false });
    return () => window.removeEventListener("touchmove", stop);
  }, [drag, create, lasso]);

  // ------------------------------------------------------------------ geometry helpers
  const laneLayout = useMemo(() => {
    const byCol = new Map<number, CalEvent[]>();
    for (const e of events) {
      const c = colOf(e);
      if (c < 0) continue;
      const list = byCol.get(c) ?? [];
      list.push(e);
      byCol.set(c, list);
    }
    // at most two side-by-side lanes (calendar.md §7.3 double booking); deeper clashes fold into one "+N" stack
    const out = new Map<string, { lane: number; lanes: number; col: number }>();
    const stacks: { key: string; col: number; sp: number; ep: number; aids: number[] }[] = [];
    for (const [c, list] of byCol) {
      const l = layoutLanes(list.map((e) => ({ id: e.key, sp: e.sp, ep: e.ep })));
      const overflow = new Map<number, CalEvent[]>();
      for (const e of list) {
        const x = l.get(e.key) ?? { lane: 0, lanes: 1, cluster: -1 };
        if (x.lanes > 2 && x.lane >= 1) {
          overflow.set(x.cluster, [...(overflow.get(x.cluster) ?? []), e]);
          continue;
        }
        out.set(e.key, { lane: x.lane, lanes: Math.min(2, x.lanes), col: c });
      }
      for (const [cl, evs] of overflow) {
        stacks.push({ key: `stack-${c}-${cl}`, col: c, sp: Math.min(...evs.map((e) => e.sp)), ep: Math.max(...evs.map((e) => e.ep)), aids: evs.map((e) => e.a.id) });
      }
    }
    return { lanes: out, stacks };
  }, [events, colOf]);
  const lanes = laneLayout.lanes;

  const rectFor = useCallback(
    (col: number, sp: number, ep: number, lane = 0, laneCount = 1) => {
      const inner = colW - 4;
      const w = inner / laneCount;
      return { left: GUTTER_W + col * colW + 2 + lane * w, top: headerH + rows.tops[sp - 1], width: Math.max(8, w - (laneCount > 1 ? 1 : 0)), height: spanHeight(rows, sp, ep) };
    },
    [colW, headerH, rows],
  );

  const toContent = useCallback((clientX: number, clientY: number) => {
    const el = scroller.current;
    if (!el) return { x: 0, y: 0 };
    const r = el.getBoundingClientRect();
    return { x: clientX - r.left + el.scrollLeft - GUTTER_W, y: clientY - r.top + el.scrollTop - headerH };
  }, [headerH]);

  const targetFor = useCallback(
    (ev: CalEvent, col: number, sp: number) => {
      const c = columns[col];
      const span = ev.ep - ev.sp;
      return { room: c.room ?? ev.room, day: c.day, sp, ep: sp + span };
    },
    [columns],
  );

  const eventAt = useCallback(
    (col: number, p: number) => events.find((e) => colOf(e) === col && e.sp <= p && p <= e.ep) ?? null,
    [events, colOf],
  );

  // ------------------------------------------------------------------ live check (once per slot change)
  const dragAids = drag?.aids;
  const check = useMemo<CheckResult | null>(() => {
    const src = drag ? { ev: drag.ev, col: hover?.col, sp: hover?.sp } : kbMove ? { ev: kbMove.ev, col: kbMove.col, sp: kbMove.sp } : resize ? null : null;
    if (resize) return checkMove(model, resize.ev, { ...targetFor(resize.ev, resize.col, resize.sp), ep: resize.ep, mask });
    if (!src || src.col === undefined || src.sp === undefined) return null;
    return checkMove(model, src.ev, { ...targetFor(src.ev, src.col, src.sp), mask }, new Set(dragAids ?? []));
  }, [drag, hover, kbMove, resize, model, targetFor, mask, dragAids]);

  const culprits = useMemo(() => new Set(check?.culprits ?? []), [check]);

  // valid-slot pull (calendar.md §9.2 level 2): after a 600 ms pause over an invalid target
  useEffect(() => {
    if (pauseTimer.current) clearTimeout(pauseTimer.current);
    if (!drag || !hover || !check || check.ok) return;
    pauseTimer.current = setTimeout(() => {
      const s = nearestValidStart(hover.sp, drag.span, (start) => checkMove(model, drag.ev, { ...targetFor(drag.ev, hover.col, start), mask }, new Set(drag.aids)).ok);
      setHint(s);
    }, PAUSE_MS);
    return () => {
      if (pauseTimer.current) clearTimeout(pauseTimer.current);
    };
  }, [drag, hover, check, model, targetFor, mask]);

  // ------------------------------------------------------------------ auto-scroll near the edges (gentle; only while dragging)
  const autoScroll = useCallback((clientX: number, clientY: number) => {
    const el = scroller.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const edge = 28;
    const speed = (d: number) => Math.min(10, Math.max(0, (edge - d) / 3));
    let dx = 0;
    let dy = 0;
    if (clientX < r.left + GUTTER_W + edge) dx = -speed(clientX - r.left - GUTTER_W);
    else if (clientX > r.right - edge) dx = speed(r.right - clientX);
    if (clientY < r.top + headerH + edge) dy = -speed(clientY - r.top - headerH);
    else if (clientY > r.bottom - edge) dy = speed(r.bottom - clientY);
    if (dx || dy) el.scrollBy(dx, dy);
  }, [headerH]);

  // ------------------------------------------------------------------ pointer: chips
  const beginDrag = useCallback(
    (ev: CalEvent, clientX: number, clientY: number) => {
      const col = colOf(ev);
      const r = rectFor(col, ev.sp, ev.ep);
      const p = toContent(clientX, clientY);
      const aids = selection.has(ev.a.id) && selection.size > 1 ? [...selection] : [ev.a.id];
      const grabX = p.x + GUTTER_W - r.left;
      const grabY = p.y + headerH - r.top;
      ghostX.set(r.left);
      ghostY.set(r.top);
      setDrag({ kind: "move", ev, aids, grabX, grabY, span: ev.ep - ev.sp + 1, originCol: col });
      setHover({ col, sp: ev.sp });
      setHint(null);
      props.onAnnounce(t("calendar.drag.pickedUp", { label: ev.a.label }));
      if (ghostRef.current) ghostRef.current.style.willChange = "transform";
    },
    [colOf, rectFor, toContent, selection, headerH, ghostX, ghostY, props, t],
  );

  const onChipPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLButtonElement>, ev: CalEvent) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      const mod = { shift: e.shiftKey, meta: e.metaKey || e.ctrlKey, alt: e.altKey };
      pointer.current = { id: e.pointerId, x: e.clientX, y: e.clientY, ev, type: e.pointerType, started: false, timer: null, mod };
      if (e.pointerType === "touch" && !readOnly && !ev.a.locked) {
        pointer.current.timer = setTimeout(() => {
          if (pointer.current && !pointer.current.started) {
            pointer.current.started = true;
            beginDrag(ev, pointer.current.x, pointer.current.y);
          }
        }, TOUCH_DELAY);
      }
      scroller.current?.setPointerCapture(e.pointerId);
    },
    [readOnly, beginDrag],
  );

  const onResizeStart = useCallback((e: ReactPointerEvent<HTMLSpanElement>, ev: CalEvent, edge: "start" | "end") => {
    if (readOnly) return;
    e.stopPropagation();
    e.preventDefault();
    const col = colOf(ev);
    setResize({ ev, col, sp: ev.sp, ep: ev.ep });
    pointer.current = { id: e.pointerId, x: e.clientX, y: e.clientY, ev, type: edge, started: true, timer: null, mod: { shift: false, meta: false, alt: false } };
    scroller.current?.setPointerCapture(e.pointerId);
  }, [readOnly, colOf]);

  // ------------------------------------------------------------------ pointer: empty canvas
  const onCanvasPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || pointer.current) return;
    const el = scroller.current;
    if (!el) return;
    const p = toContent(e.clientX, e.clientY);
    if (p.x < 0 || p.y < 0) return; // gutter / header
    const col = Math.floor(p.x / colW);
    if (col < 0 || col >= columns.length) return;
    const period = periodAt(rows, p.y);
    setCursor({ col, p: period });
    pointer.current = { id: e.pointerId, x: e.clientX, y: e.clientY, ev: null, type: e.shiftKey ? "lasso" : "create", started: false, timer: null, mod: { shift: e.shiftKey, meta: e.metaKey || e.ctrlKey, alt: e.altKey } };
    el.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const pt = pointer.current;
    if (!pt || pt.id !== e.pointerId) return;
    const dist = Math.hypot(e.clientX - pt.x, e.clientY - pt.y);
    if (!pt.started) {
      if (pt.ev && pt.type === "touch") {
        if (dist > TOUCH_TOLERANCE && pt.timer) {
          clearTimeout(pt.timer);
          pointer.current = null; // a scroll, not a long-press
        }
        return;
      }
      if (dist < DRAG_THRESHOLD) return;
      pt.started = true;
      if (pt.ev) {
        if (readOnly) return;
        beginDrag(pt.ev, pt.x, pt.y);
      } else if (pt.type === "lasso") {
        const p0 = toContent(pt.x, pt.y);
        setLasso({ x0: p0.x, y0: p0.y, x1: p0.x, y1: p0.y });
      } else if (!readOnly) {
        const p0 = toContent(pt.x, pt.y);
        const col = Math.floor(p0.x / colW);
        const p = periodAt(rows, p0.y);
        setCreate({ col, p0: p, p1: p });
      }
    }
    const cx = e.clientX;
    const cy = e.clientY;
    if (raf.current !== null) return;
    raf.current = requestAnimationFrame(() => {
      raf.current = null;
      const p = toContent(cx, cy);
      if (resize) {
        const period = periodAt(rows, p.y);
        const next = pt.type === "start" ? { sp: Math.min(period, resize.ep), ep: resize.ep } : { sp: resize.sp, ep: Math.max(period, resize.sp) };
        if (next.sp !== resize.sp || next.ep !== resize.ep) setResize({ ...resize, ...next });
        return;
      }
      if (drag) {
        autoScroll(cx, cy);
        const gx = p.x - drag.grabX + GUTTER_W;
        const gy = p.y - drag.grabY + headerH;
        const snap = snapGhost(gx - GUTTER_W - 2, gy - headerH, colW, columns.length, rows, drag.span);
        const pull = reduce ? 0 : snap.pull;
        ghostX.set(gx + (snap.slotX + GUTTER_W + 2 - gx) * pull);
        ghostY.set(gy + (snap.slotY + headerH - gy) * pull);
        if (!hover || hover.col !== snap.col || hover.sp !== snap.period) {
          setHover({ col: snap.col, sp: snap.period });
          setHint(null);
        }
        return;
      }
      if (lasso) {
        setLasso((l) => (l ? { ...l, x1: p.x, y1: p.y } : l));
        return;
      }
      if (create) {
        const period = periodAt(rows, p.y);
        if (period !== create.p1) setCreate({ ...create, p1: period });
      }
    });
  };

  const finishPointer = (e: ReactPointerEvent<HTMLDivElement>, cancelled = false) => {
    const pt = pointer.current;
    if (!pt || pt.id !== e.pointerId) return;
    if (pt.timer) clearTimeout(pt.timer);
    pointer.current = null;
    try {
      scroller.current?.releasePointerCapture(e.pointerId);
    } catch {
      /* already released */
    }
    if (ghostRef.current) ghostRef.current.style.willChange = "";
    if (resize) {
      const r = resize;
      setResize(null);
      if (!cancelled && (r.sp !== r.ev.sp || r.ep !== r.ev.ep)) props.onResize(r.ev, r.sp, r.ep);
      return;
    }
    if (!pt.started) {
      // click
      if (pt.ev) {
        if (pt.mod.meta) props.onSelect(pt.ev.a.id, "toggle");
        else if (pt.mod.shift) props.onSelect(pt.ev.a.id, "range");
        else {
          props.onSelect(pt.ev.a.id, "replace");
          props.onOpen(pt.ev);
        }
      } else if (!pt.mod.shift) {
        props.onSelect(null, "replace");
      }
      return;
    }
    if (drag) {
      const d = drag;
      const h = hover;
      // releasing after the 600 ms pause (or with ⌥) over an invalid slot takes the offered free slot
      const sp = hint !== null && check && !check.ok ? hint : h?.sp;
      setDrag(null);
      setHover(null);
      setHint(null);
      if (cancelled || !h || sp === undefined) return settleBack(d);
      const target = targetFor(d.ev, h.col, sp);
      if (target.room === d.ev.room && target.day === d.ev.day && target.sp === d.ev.sp) return settleBack(d, false);
      const final = checkMove(model, d.ev, { ...target, mask }, new Set(d.aids));
      const slot = rectFor(h.col, target.sp, target.ep);
      if (!reduce) {
        void animate(ghostX, slot.left, springs.snappy);
        void animate(ghostY, slot.top, springs.snappy);
      }
      const extra = d.aids
        .filter((aid) => aid !== d.ev.a.id)
        .map((aid) => model.eventByAid.get(aid)?.[0])
        .filter((x): x is CalEvent => !!x)
        .map((ev) => {
          const dc = h.col - d.originCol;
          const c = Math.min(columns.length - 1, Math.max(0, colOf(ev) + dc));
          const dp = sp - d.ev.sp;
          return { ev, target: { ...targetFor(ev, c, Math.max(1, ev.sp + dp)), ep: Math.max(1, ev.sp + dp) + (ev.ep - ev.sp) } };
        });
      if (!final.ok) {
        setShaking(d.ev.a.id);
        setTimeout(() => setShaking(null), 300);
      }
      props.onMove({ ev: d.ev, target, extra, check: final, skipPopover: e.shiftKey, anchor: { x: e.clientX, y: e.clientY } });
      return;
    }
    if (lasso) {
      const l = lasso;
      setLasso(null);
      const x0 = Math.min(l.x0, l.x1) + GUTTER_W;
      const x1 = Math.max(l.x0, l.x1) + GUTTER_W;
      const y0 = Math.min(l.y0, l.y1) + headerH;
      const y1 = Math.max(l.y0, l.y1) + headerH;
      const hit: number[] = [];
      for (const ev of events) {
        const ln = lanes.get(ev.key);
        if (!ln) continue;
        const r = rectFor(ln.col, ev.sp, ev.ep, ln.lane, ln.lanes);
        if (r.left < x1 && r.left + r.width > x0 && r.top < y1 && r.top + r.height > y0) hit.push(ev.a.id);
      }
      props.onSelectMany([...new Set(hit)], pt.mod.meta);
      props.onAnnounce(t("calendar.selected", { n: new Set(hit).size }));
      return;
    }
    if (create) {
      const c = create;
      setCreate(null);
      if (cancelled) return;
      const sp = Math.min(c.p0, c.p1);
      const ep = Math.max(c.p0, c.p1);
      props.onCreate({ column: columns[c.col], sp, ep, anchor: { x: e.clientX, y: e.clientY } });
    }
  };

  const settleBack = (d: DragState, shake = true) => {
    const r = rectFor(d.originCol, d.ev.sp, d.ev.ep);
    if (!reduce) {
      void animate(ghostX, r.left, springs.snappy);
      void animate(ghostY, r.top, springs.snappy);
    }
    if (shake) props.onAnnounce(t("calendar.drag.cancelled"));
  };

  useEffect(() => {
    if (!drag && !lasso && !create && !resize) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      pointer.current = null;
      setDrag(null);
      setHover(null);
      setLasso(null);
      setCreate(null);
      setResize(null);
      props.onAnnounce(t("calendar.drag.cancelled"));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drag, lasso, create, resize, props, t]);

  // ------------------------------------------------------------------ keyboard (roving cursor)
  const ensureVisible = useCallback(
    (col: number, p: number) => {
      const el = scroller.current;
      if (!el) return;
      const x = GUTTER_W + col * colW;
      if (x < el.scrollLeft + GUTTER_W) el.scrollLeft = x - GUTTER_W;
      else if (x + colW > el.scrollLeft + el.clientWidth) el.scrollLeft = x + colW - el.clientWidth;
      const y = headerH + rows.tops[p - 1];
      if (y < el.scrollTop + headerH) el.scrollTop = y - headerH;
      else if (y + rows.heights[p - 1] > el.scrollTop + el.clientHeight) el.scrollTop = y + rows.heights[p - 1] - el.clientHeight;
    },
    [colW, headerH, rows],
  );

  const moveCursor = (col: number, p: number) => {
    const c = Math.min(columns.length - 1, Math.max(0, col));
    const q = Math.min(PERIODS_PER_DAY, Math.max(1, p));
    setCursor({ col: c, p: q });
    ensureVisible(c, q);
  };

  const onGridKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const meta = e.metaKey || e.ctrlKey;
    const at = eventAt(cursor.col, cursor.p);
    if (kbMove) {
      const span = kbMove.ev.ep - kbMove.ev.sp;
      let next = kbMove;
      if (e.key === "ArrowUp") next = { ...kbMove, sp: Math.max(1, kbMove.sp - 1) };
      else if (e.key === "ArrowDown") next = { ...kbMove, sp: Math.min(PERIODS_PER_DAY - span, kbMove.sp + 1) };
      else if (e.key === "ArrowLeft") next = { ...kbMove, col: Math.max(0, kbMove.col - 1) };
      else if (e.key === "ArrowRight") next = { ...kbMove, col: Math.min(columns.length - 1, kbMove.col + 1) };
      else if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        const target = targetFor(kbMove.ev, kbMove.col, kbMove.sp);
        const final = checkMove(model, kbMove.ev, { ...target, mask });
        setKbMove(null);
        const r = scroller.current?.getBoundingClientRect();
        const rect = rectFor(kbMove.col, target.sp, target.ep);
        props.onMove({ ev: kbMove.ev, target, extra: [], check: final, skipPopover: false, anchor: { x: (r?.left ?? 0) + rect.left - (scroller.current?.scrollLeft ?? 0) + rect.width, y: (r?.top ?? 0) + rect.top - (scroller.current?.scrollTop ?? 0) } });
        return;
      } else if (e.key === "Escape") {
        e.preventDefault();
        setKbMove(null);
        props.onAnnounce(t("calendar.drag.cancelled"));
        return;
      } else return;
      e.preventDefault();
      setKbMove(next);
      ensureVisible(next.col, next.sp);
      const tgt = targetFor(next.ev, next.col, next.sp);
      const c = checkMove(model, next.ev, { ...tgt, mask });
      const room = model.roomById.get(tgt.room)?.name ?? "";
      props.onAnnounce(t("calendar.drag.over", { label: next.ev.a.label, room, when: whenText(tgt.day, tgt.sp, tgt.ep)[lang], state: c.ok ? t("calendar.drag.fits") : c.hard[0]?.text[lang] ?? "" }));
      return;
    }
    switch (e.key) {
      case "ArrowUp":
        if (e.shiftKey && at && !readOnly) return void (e.preventDefault(), at.ep > at.sp && props.onResize(at, at.sp, at.ep - 1));
        if (e.altKey && at && !readOnly) return void (e.preventDefault(), at.sp > 1 && props.onResize(at, at.sp - 1, at.ep));
        e.preventDefault();
        return moveCursor(cursor.col, meta ? 1 : cursor.p - 1);
      case "ArrowDown":
        if (e.shiftKey && at && !readOnly) return void (e.preventDefault(), at.ep < PERIODS_PER_DAY && props.onResize(at, at.sp, at.ep + 1));
        if (e.altKey && at && !readOnly) return void (e.preventDefault(), at.sp < at.ep && props.onResize(at, at.sp + 1, at.ep));
        e.preventDefault();
        return moveCursor(cursor.col, meta ? PERIODS_PER_DAY : cursor.p + 1);
      case "ArrowLeft":
        e.preventDefault();
        return moveCursor(cursor.col - 1, cursor.p);
      case "ArrowRight":
        e.preventDefault();
        return moveCursor(cursor.col + 1, cursor.p);
      case "PageUp":
        e.preventDefault();
        return moveCursor(cursor.col, cursor.p - 6);
      case "PageDown":
        e.preventDefault();
        return moveCursor(cursor.col, cursor.p + 6);
      case "Home":
        e.preventDefault();
        return moveCursor(0, cursor.p);
      case "End":
        e.preventDefault();
        return moveCursor(columns.length - 1, cursor.p);
      case "Enter":
        e.preventDefault();
        if (at) {
          props.onSelect(at.a.id, "replace");
          props.onOpen(at);
        } else if (!readOnly) openCreateAtCursor();
        return;
      case " ":
        if (at && !readOnly) {
          e.preventDefault();
          setKbMove({ ev: at, col: cursor.col, sp: at.sp });
          props.onSelect(at.a.id, "replace");
          props.onAnnounce(t("calendar.drag.pickedUp", { label: at.a.label }));
        }
        return;
      case "x":
      case "X":
        if (at) {
          e.preventDefault();
          props.onSelect(at.a.id, "toggle");
        }
        return;
      case "n":
      case "N":
        if (!meta && !readOnly) {
          e.preventDefault();
          openCreateAtCursor();
        }
        return;
      default:
    }
  };

  const openCreateAtCursor = () => {
    const el = scroller.current;
    const r = el?.getBoundingClientRect();
    const rect = rectFor(cursor.col, cursor.p, cursor.p);
    props.onCreate({ column: columns[cursor.col], sp: cursor.p, ep: cursor.p, anchor: { x: (r?.left ?? 0) + rect.left - (el?.scrollLeft ?? 0) + rect.width, y: (r?.top ?? 0) + rect.top - (el?.scrollTop ?? 0) } });
  };

  useImperativeHandle(ref, () => ({
    focusGrid: () => scroller.current?.focus(),
    scrollToEvent: (aid: number) => {
      const ev = events.find((e) => e.a.id === aid);
      if (!ev) return;
      const col = colOf(ev);
      if (col < 0) return;
      setCursor({ col, p: ev.sp });
      ensureVisible(col, ev.sp);
    },
  }), [events, colOf, ensureVisible]);

  // keep the selected event in view after a lens switch / deep link
  const focusAid = props.focusAid;
  useEffect(() => {
    if (!focusAid) return;
    const ev = events.find((e) => e.a.id === focusAid);
    if (!ev) return;
    const col = colOf(ev);
    if (col >= 0) {
      const id = requestAnimationFrame(() => ensureVisible(col, ev.sp));
      return () => cancelAnimationFrame(id);
    }
  }, [focusAid, events, colOf, ensureVisible]);

  // ------------------------------------------------------------------ render
  const lines = (sp: number, ep: number): 1 | 2 | 3 | 4 => {
    const h = spanHeight(rows, sp, ep);
    return h >= 78 ? 4 : h >= 58 ? 3 : h >= 34 ? 2 : 1;
  };

  const slotState = (c: CheckResult | null): "ok" | "soft" | "hard" => (!c ? "ok" : !c.ok ? "hard" : c.soft.some((s) => s.code === "capacity") ? "soft" : "ok");
  const dragTarget = drag && hover ? targetFor(drag.ev, hover.col, hover.sp) : null;
  const dragSlot = drag && hover ? rectFor(hover.col, hover.sp, hover.sp + drag.span - 1) : null;
  const hintSlot = drag && hover && hint !== null ? rectFor(hover.col, hint, hint + drag.span - 1) : null;
  const kbTarget = kbMove ? targetFor(kbMove.ev, kbMove.col, kbMove.sp) : null;
  const kbSlot = kbMove && kbTarget ? rectFor(kbMove.col, kbTarget.sp, kbTarget.ep) : null;
  const resizeSlot = resize ? rectFor(resize.col, resize.sp, resize.ep) : null;
  const createSlot = create ? rectFor(create.col, Math.min(create.p0, create.p1), Math.max(create.p0, create.p1)) : null;
  const cursorRect = rectFor(cursor.col, cursor.p, cursor.p);
  const reason = (c: CheckResult | null, tgt: { room: number; day: number; sp: number; ep: number } | null) => {
    if (!c || !tgt) return "";
    if (!c.ok) return `✕ ${c.hard[0]?.text[lang] ?? ""}`;
    const room = model.roomById.get(tgt.room);
    const soft = c.soft.find((s) => s.code === "capacity");
    if (soft) return `⚠ ${soft.text[lang]}`;
    return `${t("calendar.drag.ok", { room: room?.name ?? "", when: whenText(tgt.day, tgt.sp, tgt.ep)[lang], cap: roomCap(model, room) })} ✓`;
  };
  const multi = drag && drag.aids.length > 1;

  const nowTop = props.nowMin !== null && props.nowMin !== undefined ? nowOffset(rows, props.nowMin) : null;
  const nowLabel = props.nowMin !== null && props.nowMin !== undefined ? `${String(Math.floor(props.nowMin / 60)).padStart(2, "0")}:${String(props.nowMin % 60).padStart(2, "0")}` : "";

  const visibleEvents = events.filter((ev) => {
    const ln = lanes.get(ev.key);
    return ln && ln.col >= c0 && ln.col <= c1;
  });

  return (
    <div
      ref={scroller}
      role="grid"
      aria-label={props.gridLabel}
      aria-rowcount={PERIODS_PER_DAY + 1}
      aria-colcount={columns.length + 1}
      aria-activedescendant={`${gridId}-${cursor.col}-${cursor.p}`}
      aria-describedby="cal-grid-help"
      tabIndex={0}
      className="cal-canvas relative h-full min-h-0 overflow-auto overscroll-contain outline-none focus-visible:outline-none"
      style={{ touchAction: drag || create || lasso ? "none" : "pan-x pan-y" }}
      onPointerDown={onCanvasPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={(e) => finishPointer(e)}
      onPointerCancel={(e) => finishPointer(e, true)}
      onKeyDown={onGridKeyDown}
      data-testid="time-grid"
    >
      <p id="cal-grid-help" className="sr-only">{t("calendar.lassoHint")}</p>
      <div className="relative" style={{ width: contentW, height: contentH }}>
        {/* sticky header (room or day headers): thick material, Apple "hard" edge */}
        <div className="cal-sticky sticky top-0 z-20 hairline-b" style={{ width: contentW, height: headerH }} role="row" aria-rowindex={1}>
          <div className="cal-sticky sticky left-0 z-10 h-full" style={{ width: GUTTER_W }} />
          {props.header}
          {columns.slice(c0, c1 + 1).map((c, i) => {
            const col = c0 + i;
            return (
              <div
                key={c.key}
                role="columnheader"
                aria-colindex={col + 2}
                aria-label={c.ariaLabel}
                className={cn("absolute bottom-0 flex h-12 flex-col justify-center px-2 hairline-b", c.today && "text-tint-text")}
                style={{ left: GUTTER_W + col * colW, width: colW }}
              >
                <span className="flex items-baseline justify-between gap-1">
                  <span className="truncate text-[13px] leading-4 font-semibold">{c.label}</span>
                  {c.tag ? <span className="text-[10px] font-semibold text-status-tip-fg">{c.tag}</span> : null}
                </span>
                {c.sub ? <span className="truncate text-[11px] leading-[14px] text-label-2 tabular-nums">{c.sub}</span> : null}
              </div>
            );
          })}
        </div>

        {/* sticky time gutter */}
        <div className="cal-canvas sticky left-0 z-10" style={{ width: GUTTER_W, height: rows.total, marginTop: 0 }} aria-hidden>
          {PERIODS.map((p, i) => (
            <div key={p.index} className={cn("absolute right-2 -translate-y-1.5 text-[11px] leading-[14px] tabular-nums", cursor.p === p.index ? "text-tint-text" : "text-label-3")} style={{ top: rows.tops[i] + (i === 0 ? 6 : 0) }} title={`P${p.index} · ${p.start}–${p.end}${p.index === 12 ? ` · ${t("calendar.transition")}` : ""}`}>
              {p.start}
            </div>
          ))}
          {nowTop !== null && (props.nowCols?.length ?? 0) > 0 ? (
            <span className="cal-now-pill" style={{ top: nowTop - 8, right: 4 }}>{nowLabel}</span>
          ) : null}
        </div>

        {/* body: hairlines (one gradient for columns + 18 row lines) */}
        <div className="cal-cols pointer-events-none absolute" aria-hidden style={{ left: GUTTER_W, top: headerH, width: columns.length * colW, height: rows.total, ["--col-w" as string]: `${colW}px` }}>
          {rows.tops.slice(1, -1).map((y, i) => (
            <div key={i} className="absolute inset-x-0 h-px" style={{ top: y, background: "var(--cal-line)" }} />
          ))}
        </div>

        {/* grid cells for the visible window: roving-focus targets + stable test hooks */}
        {columns.slice(c0, c1 + 1).map((c, i) => {
          const col = c0 + i;
          return (
            <div key={`cells-${c.key}`} role="row" className="contents">
              {PERIODS.map((p, j) => {
                const room = c.room;
                const free = room !== null ? slotFree(model, room, c.day, p.index, p.index, mask) : !eventAt(col, p.index);
                return (
                  <div
                    key={p.index}
                    id={`${gridId}-${col}-${p.index}`}
                    role="gridcell"
                    aria-rowindex={p.index + 1}
                    aria-colindex={col + 2}
                    aria-label={`${c.ariaLabel}, ${t("calendar.periodRow", { n: p.index, range: `${p.start}–${p.end}` })}`}
                    aria-selected={cursor.col === col && cursor.p === p.index}
                    data-testid="grid-drop-cell"
                    data-room-id={room ?? undefined}
                    data-day={c.day}
                    data-period={p.index}
                    data-free={free ? "true" : undefined}
                    className={cn("group absolute", free && !readOnly && "hover:bg-fill-3")}
                    style={{ left: GUTTER_W + col * colW, top: headerH + rows.tops[j], width: colW, height: rows.heights[j] }}
                  >
                    {free && !readOnly ? <span aria-hidden className="pointer-events-none absolute inset-0 hidden items-center justify-center text-label-4 group-hover:flex">+</span> : null}
                  </div>
                );
              })}
            </div>
          );
        })}

        {/* pre-occupied blocks and bookings */}
        {props.blocks.map((b) => {
          const col = props.blockCol(b);
          if (col < c0 || col > c1) return null;
          const r = rectFor(col, b.sp, b.ep);
          return (
            <div key={b.key} className="cal-block" style={{ left: r.left, top: r.top, width: r.width, height: r.height, outline: culprits.has(b.key) ? "2px solid var(--status-infeasible-solid)" : undefined }} aria-label={t("calendar.insp.blockLabel", { label: b.b.label })} role="note">
              {b.b.label.toLocaleUpperCase(locale)}
            </div>
          );
        })}
        {props.bookings.map((bk) => {
          const col = props.bookingCol(bk);
          if (col < c0 || col > c1) return null;
          const r = rectFor(col, bk.sp, bk.ep);
          return (
            <div key={bk.key} className="cal-chip cal-booking" style={{ left: r.left, top: r.top, width: r.width, height: r.height, pointerEvents: "none" }} aria-label={`${t("calendar.state.booking")}: ${bk.bk.title}`} role="note">
              <span className="cal-code truncate">{t("calendar.state.booking")}</span>
              <span className="cal-line2 truncate">{bk.bk.title}{bk.bk.owner ? ` · ${bk.bk.owner}` : ""}</span>
            </div>
          );
        })}

        {/* compare ghosts (run B where it differs) */}
        {(props.ghosts ?? []).map((g) => {
          const col = props.ghostCol?.(g) ?? -1;
          if (col < c0 || col > c1) return null;
          const r = rectFor(col, g.sp, g.ep);
          return (
            <div key={g.key} className="cal-ghost" style={{ left: r.left, top: r.top, width: r.width, height: r.height }} aria-hidden>
              {g.kind === "onlyB" ? "− " : "↔ "}
              {g.label}
            </div>
          );
        })}

        {/* chips */}
        {visibleEvents.map((ev) => {
          const ln = lanes.get(ev.key);
          if (!ln) return null;
          const r = rectFor(ln.col, ev.sp, ev.ep, ln.lane, ln.lanes);
          const pendingHere = props.pending?.some((p) => p.ev.a.id === ev.a.id);
          return (
            <ShakeWrap key={ev.key} active={shaking === ev.a.id || props.shakeAid === ev.a.id} reduce={reduce} left={r.left} top={r.top}>
              <EventChip
                ev={ev}
                rect={{ left: 0, top: 0, width: r.width, height: r.height }}
                lines={lines(ev.sp, ev.ep)}
                line2={props.line2(ev)}
                ariaLabel={props.ariaFor(ev)}
                selected={selection.has(ev.a.id)}
                culprit={culprits.has(ev.key)}
                originDrag={(drag?.aids.includes(ev.a.id) ?? false) || (kbMove?.ev.a.id === ev.a.id) || pendingHere}
                editable={!readOnly}
                exam={model.exam}
                compareMoved={props.movedAids?.has(ev.a.id)}
                tabIndex={-1}
                onPointerDown={onChipPointerDown}
                resizable={!readOnly && selection.has(ev.a.id) && selection.size === 1 && !model.exam}
                onResizeStart={onResizeStart}
              />
            </ShakeWrap>
          );
        })}

        {laneLayout.stacks.map((st) => {
          if (st.col < c0 || st.col > c1) return null;
          const r = rectFor(st.col, st.sp, st.ep, 1, 2);
          return (
            <button
              key={st.key}
              type="button"
              className="cal-chip items-center justify-center"
              data-conflict="true"
              style={{ ...chipVars(8), left: r.left, top: r.top, width: r.width, height: r.height, zIndex: 2 }}
              aria-label={t("calendar.issues.conflicts", { n: st.aids.length + 1 })}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => props.onSelectMany(st.aids, false)}
            >
              <span className="cal-code">+{st.aids.length}</span>
            </button>
          );
        })}

        {/* double-booking bracket: a red rule left of each clashing pair */}
        {[...new Set(visibleEvents.filter((ev) => (lanes.get(ev.key)?.lanes ?? 1) > 1 && lanes.get(ev.key)?.lane === 0).map((ev) => ev.key))].map((k) => {
          const ev = visibleEvents.find((e) => e.key === k);
          const ln = lanes.get(k);
          if (!ev || !ln) return null;
          const r = rectFor(ln.col, ev.sp, ev.ep);
          return <div key={`br-${k}`} aria-hidden className="pointer-events-none absolute z-[1] w-[2px] rounded-full" style={{ left: r.left - 2, top: r.top, height: r.height, background: "var(--status-infeasible-solid)" }} />;
        })}

        {/* optimistic placements awaiting the Move popover */}
        {(props.pending ?? []).map((p) => {
          const r = rectFor(p.col, p.sp, p.ep);
          return (
            <div key={`pending-${p.ev.key}`} className="cal-chip" data-saving="true" style={{ ...chipVars(p.ev.a.slot), left: r.left, top: r.top, width: r.width, height: r.height, zIndex: 6 }} aria-hidden>
              <span className="cal-code truncate">{p.ev.a.code ?? p.ev.a.label}</span>
              <span className="cal-line2 truncate">{spanText(p.sp, p.ep)}</span>
            </div>
          );
        })}

        {/* now-line across today's columns only */}
        {nowTop !== null
          ? (props.nowCols ?? []).map((c) =>
              c >= c0 && c <= c1 ? <div key={`now-${c}`} className="cal-now" style={{ left: GUTTER_W + c * colW, width: colW, top: headerH + nowTop - 1, height: 2 }} aria-hidden /> : null,
            )
          : null}

        {/* keyboard cursor */}
        <div aria-hidden className="pointer-events-none absolute z-[7] rounded-[6px] outline-2 outline-(--focus) [[role=grid]:not(:focus-visible)_&]:hidden" style={{ left: cursorRect.left, top: cursorRect.top, width: cursorRect.width, height: cursorRect.height + 1 }} />

        {/* the single drop-slot outline that glides between slots */}
        {dragSlot ? (
          <motion.div
            layoutId={reduce ? undefined : "drop-slot"}
            transition={reduce ? { duration: 0 } : springs.snappy}
            className="cal-slot"
            data-state={slotState(check)}
            style={{ left: dragSlot.left, top: dragSlot.top, width: dragSlot.width, height: dragSlot.height }}
          />
        ) : null}
        {hintSlot ? (
          <div className="cal-slot" data-state="hint" style={{ left: hintSlot.left, top: hintSlot.top, width: hintSlot.width, height: hintSlot.height }}>
            <span className="glass-thick absolute -top-6 left-0 rounded-full px-2 py-0.5 text-[11px] whitespace-nowrap text-label-1">{t("calendar.drag.free", { range: spanText(hint ?? 1, (hint ?? 1) + (drag?.span ?? 1) - 1) })}</span>
          </div>
        ) : null}
        {kbSlot ? <div className="cal-slot" data-state={slotState(check)} style={{ left: kbSlot.left, top: kbSlot.top, width: kbSlot.width, height: kbSlot.height }} /> : null}
        {resizeSlot && resize ? (
          <div className="cal-slot" data-state={slotState(check)} style={{ left: resizeSlot.left, top: resizeSlot.top, width: resizeSlot.width, height: resizeSlot.height }}>
            <span className="glass-thick absolute -bottom-7 left-0 rounded-full px-2 py-0.5 text-[11px] whitespace-nowrap text-label-1">
              {t("calendar.drag.resize", { range: `P${resize.sp}–P${resize.ep} · ${spanText(resize.sp, resize.ep)}`, delta: `${resize.ep - resize.sp - (resize.ev.ep - resize.ev.sp) >= 0 ? "+" : ""}${resize.ep - resize.sp - (resize.ev.ep - resize.ev.sp)}` })}
            </span>
          </div>
        ) : null}
        {createSlot && create ? (
          <div className="cal-slot" data-state="create" style={{ left: createSlot.left, top: createSlot.top, width: createSlot.width, height: createSlot.height }}>
            <span className="absolute top-1 left-2 text-[11px] font-medium text-tint-text tabular-nums">
              {t("calendar.create.slot", { room: columns[create.col]?.label ?? "", when: whenText(columns[create.col]?.day ?? 1, Math.min(create.p0, create.p1), Math.max(create.p0, create.p1))[lang], n: Math.abs(create.p1 - create.p0) + 1 })}
            </span>
          </div>
        ) : null}
        {lasso ? (
          <div className="cal-lasso" style={{ left: Math.min(lasso.x0, lasso.x1) + GUTTER_W, top: Math.min(lasso.y0, lasso.y1) + headerH, width: Math.abs(lasso.x1 - lasso.x0), height: Math.abs(lasso.y1 - lasso.y0) }} />
        ) : null}

        {/* the lifted ghost + its reason capsule (1:1 with the pointer, magnetic pull, settle spring) */}
        {drag ? (
          <motion.div ref={ghostRef} className="pointer-events-none absolute top-0 left-0 z-30" style={{ x: ghostX, y: ghostY, width: colW - 4 }}>
            <motion.div initial={{ scale: 1 }} animate={{ scale: reduce ? 1 : 1.03 }} transition={springs.snappy} className="relative">
              <motion.div aria-hidden className="pointer-events-none absolute inset-0 -z-10 rounded-[6px] shadow-[0_12px_32px_-8px_rgb(0_0_0/0.35)]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.12 }} />
              <div className="cal-chip" style={{ ...chipVars(drag.ev.a.slot), position: "relative", height: spanHeight(rows, drag.ev.sp, drag.ev.ep) }}>
                <span className="cal-code truncate">{drag.ev.a.code ?? drag.ev.a.label}{multi ? ` +${drag.aids.length - 1}` : ""}</span>
                <span className="cal-line2 truncate">{props.line2(drag.ev)}</span>
              </div>
            </motion.div>
            <div className="glass-thick mt-1.5 w-max max-w-[340px] rounded-full px-2.5 py-1 text-[11px] leading-[14px] font-medium text-label-1" role="status">
              {reason(check, dragTarget)}
            </div>
          </motion.div>
        ) : null}

        {props.emptyHint}
      </div>
    </div>
  );
}

/** Conflict shake (pattern §9): one 240 ms burst, 3 px, never under reduced motion. Positions its child. */
const ShakeWrap = memo(function ShakeWrap({ active, reduce, left, top, children }: { active: boolean; reduce: boolean; left: number; top: number; children: ReactNode }) {
  return (
    <motion.div
      className="absolute"
      style={{ left, top }}
      animate={active && !reduce ? { x: [0, -3, 3, -2, 2, 0] } : { x: 0 }}
      transition={{ duration: 0.24, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
});

export const TimeGrid = memo(forwardRef(TimeGridImpl));
