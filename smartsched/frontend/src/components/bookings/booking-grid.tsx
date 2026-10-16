"use client";
/**
 * The CRBS booking grid. Data cells are opaque (no glass on data, A8); only the sticky headers use the
 * thick material colour without blur. One roving tab stop: arrow keys / Home / End move between cells,
 * Enter or Space activates (book, open, or toggle in multi-select mode).
 *
 * Reservation panel: every reservable cell says "Free" and turns into "Reserve" on hover or focus. A
 * press-and-drag across consecutive periods (mouse / pen), Shift-click, or Shift+arrow selects a span of
 * periods in one room; the sheet opens with the span. Cells that cannot be booked explain why in one hint
 * overlay (hover after a short delay, or touch-and-hold); booked cells show their full notes there. The
 * hint never animates (frequent action, motion.md §2) and is aria-hidden: the same text is in the
 * cell's accessible name.
 */
import { Ban, CalendarClock, CalendarOff, CalendarX, Check, GraduationCap, History, Hourglass, Lock, OctagonX, Plus, Repeat, ShieldAlert, Stamp, User } from "lucide-react";
import { memo, useCallback, useEffect, useId, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type MouseEvent, type PointerEvent } from "react";
import type { Grid, GridSlot } from "@/lib/api/crbs";
import { BareButton } from "@/components/shell/bare-button";
import { cn } from "@/lib/utils";
import { useI18n, useT } from "@/lib/i18n/provider";
import { violationText } from "@/lib/api/booking-policies";
import type { MessageKey } from "@/lib/i18n";
import { crosshairCss, isSelectable, layoutGrid, moveFocus, slotKey, slotText, slotTone, type AxisItem, type SlotTone } from "./grid-model";
import { EntityIcon } from "@/components/admin/icons";
import type { DateFormatter } from "./date-format";
import { clampSpan, departmentColor, type DepartmentLens } from "./reserve-model";

export const TONE_CLASS: Record<SlotTone, string> = {
  available: "bg-(--mat-thick-solid) text-label-3 hover:bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--accent)_9%)] hover:text-tint-text",
  "booked-single": "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--label-1)_8%)] text-label-1",
  "booked-recurring": "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--cat-7)_13%)] text-label-1",
  "booked-mine": "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--cat-3)_17%)] text-label-1",
  // P1: a held request; dashed inner edge + hourglass, so it never reads as a confirmed booking
  "booked-pending": "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--accent)_8%)] text-label-1 outline-1 -outline-offset-2 outline-dashed outline-(--accent)",
  timetable: "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--status-locked-solid)_12%)] text-label-1",
  holiday: "hatch-preoccupied text-label-2",
  unavailable: "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--label-1)_3%)] text-label-3",
};

export const TONE_ICON: Record<SlotTone, typeof User> = {
  available: Plus,
  "booked-single": User,
  "booked-recurring": Repeat,
  "booked-mine": User,
  "booked-pending": Hourglass,
  timetable: GraduationCap,
  holiday: CalendarOff,
  unavailable: Ban,
};

/** CRBS shows a distinct glyph per unavailable reason (lock, quota stop, past, future). */
const REASON_ICON: Record<string, typeof User> = {
  permissions: Lock,
  limit: OctagonX,
  range_min: History,
  range_max: CalendarClock,
  date_range: CalendarX,
  past: History,
  // P8: a booking policy refuses the slot
  policy: ShieldAlert,
};

/** The cell glyph: a check when selected, else per tone, and per reason for unavailable cells. */
export function SlotGlyph({ slot, selected, className }: { slot: GridSlot | undefined; selected?: boolean; className?: string }) {
  const tone = slotTone(slot);
  const reason = tone === "unavailable" && slot?.reason ? REASON_ICON[slot.reason] : undefined;
  const Glyph = selected ? Check : (reason ?? TONE_ICON[tone]);
  return <Glyph className={className} aria-hidden data-reason-icon={reason ? slot?.reason : undefined} />;
}

const REASON_KEYS: Record<string, MessageKey> = {
  holiday: "crbs.slot.reason.holiday",
  period: "crbs.slot.reason.period",
  limit: "crbs.slot.reason.limit",
  permissions: "crbs.slot.reason.permissions",
  range_min: "crbs.slot.reason.range_min",
  range_max: "crbs.slot.reason.range_max",
  date_range: "crbs.slot.reason.date_range",
  no_week: "crbs.slot.reason.no_week",
  timetable: "crbs.slot.reason.timetable",
  block: "crbs.slot.reason.block",
  schedule: "reserve.reason.schedule",
  past: "crbs.slot.reason.past",
};

export function reasonKey(reason: string | null | undefined): MessageKey {
  return (reason && REASON_KEYS[reason]) || "crbs.slot.reason.unavailable";
}

/** In multi-select: free cells are picked to book, cancellable booked cells to cancel (CRBS cancel_multi). */
export function pickKind(slot: GridSlot | undefined): "book" | "cancel" | null {
  if (isSelectable(slot)) return "book";
  if (slot?.status === "booked" && slot.booking?.can_cancel) return "cancel";
  return null;
}

interface Props {
  grid: Grid;
  columns: "periods" | "rooms" | "days";
  fmt: DateFormatter;
  multi: boolean;
  selected: ReadonlySet<string>;
  onActivate: (slot: GridSlot) => void;
  /** a span of 2+ consecutive reservable periods in one room (drag, Shift-click, Shift+arrow) */
  onSpan?: (slots: GridSlot[]) => void;
  /** CRBS `grid_highlight`: tint the row and column under the pointer */
  crosshair?: boolean;
  /** CRBS `?highlight=<booking id>`: outline that booking's slot */
  highlightBookingId?: number | null;
  /** room id → icon name (from /bookings/rooms) */
  roomIcons?: ReadonlyMap<number, string | null | undefined>;
  onRoomInfo?: (roomId: number) => void;
  /** department view: colour every booking by its department; a chosen department mutes the others */
  department?: DepartmentLens;
}

interface Hint {
  text: string;
  left: number;
  top: number;
  key: string;
}

const HOVER_MS = 350;
const HOLD_MS = 450;

/**
 * Memoised (motion audit T3): opening the book sheet, the room sheet or the bell re-renders the bookings page,
 * and re-rendering 300+ cells cost the 344-653 ms frame that delayed the sheet. With stable props it skips.
 */
export const BookingGrid = memo(function BookingGrid({ grid, columns, fmt, multi, selected, onActivate, onSpan, crosshair, highlightBookingId, roomIcons, onRoomInfo, department = "all" }: Props) {
  const { t, locale } = useI18n();
  const layout = useMemo(() => layoutGrid(grid, columns), [grid, columns]);
  // the roving tab stop lives in a ref: moving focus swaps tabIndex on two cells instead of re-rendering the
  // whole grid (persona U-18: every pointerdown ran a 39-120 ms focus handler)
  const focusRef = useRef({ r: 0, c: 0 });
  const [hover, setHover] = useState<{ r: number; c: number } | null>(null);
  // span and hint belong to the grid they were made on: a new grid (date, group, a booking made) drops them
  const [spanState, setSpanState] = useState<{ grid: Grid; slots: GridSlot[] }>({ grid, slots: [] });
  const span = useMemo(() => (spanState.grid === grid ? spanState.slots : []), [spanState, grid]);
  const spanRef = useRef<GridSlot[]>([]);
  const setSpan = useCallback(
    (next: GridSlot[]) => {
      spanRef.current = next;
      setSpanState({ grid, slots: next });
    },
    [grid],
  );
  const [hintState, setHintState] = useState<{ grid: Grid; hint: Hint | null }>({ grid, hint: null });
  const hint = hintState.grid === grid ? hintState.hint : null;
  const setHint = useCallback((h: Hint | null) => setHintState({ grid, hint: h }), [grid]);
  const tableRef = useRef<HTMLTableElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ anchor: GridSlot; moved: boolean } | null>(null);
  const anchorRef = useRef<{ grid: Grid; slot: GridSlot } | null>(null);
  const getAnchor = useCallback(() => (anchorRef.current?.grid === grid ? anchorRef.current.slot : null), [grid]);
  const setAnchor = useCallback((slot: GridSlot) => void (anchorRef.current = { grid, slot }), [grid]);
  const suppressClick = useRef(false);
  const hintTimer = useRef<number | null>(null);
  const scope = useId().replace(/[^a-zA-Z0-9]/g, "");
  const spanKeys = useMemo(() => new Set(span.length > 1 ? span.map(slotKey) : []), [span]);
  const slotsByKey = useMemo(() => new Map(grid.slots.map((s) => [slotKey(s), s])), [grid.slots]);

  useEffect(() => () => void (hintTimer.current && window.clearTimeout(hintTimer.current)), []);

  const cellOf = (target: EventTarget | null) => (target as HTMLElement | null)?.closest<HTMLButtonElement>("[data-cell]") ?? null;
  const slotOf = (el: HTMLElement | null) => (el?.dataset.slotKey ? slotsByKey.get(el.dataset.slotKey) : undefined);

  const header = useCallback(
    (item: AxisItem): { title: string; sub: string | null; tone?: string } => {
      if (item.kind === "room" && item.room) {
        // CRBS col_room.php: the owner under the room name; the seats stay as the secondary fact
        const sub = [item.room.owner, item.room.capacity ? t("crbs.grid.seats", { n: item.room.capacity }) : null].filter(Boolean).join(" · ");
        return { title: item.room.name, sub: sub || null };
      }
      if (item.kind === "period" && item.period) return { title: item.period.name, sub: `${fmt.time(item.period.time_start)}–${fmt.time(item.period.time_end)}` };
      if (item.kind === "date" && item.date) return { title: fmt.weekday(item.date.date), sub: item.date.holiday ?? null };
      return { title: "", sub: null };
    },
    [fmt, t],
  );

  /** why a cell cannot be booked, or the full text of a booking (hint overlay + accessible name) */
  const explain = useCallback(
    (slot: GridSlot | undefined): string | null => {
      if (!slot) return t("crbs.slot.reason.unavailable");
      if (slot.status === "booked" && slot.booking) {
        const text = slotText(slot, { booked: t("crbs.slot.booked"), mine: t("crbs.slot.mine"), class: t("reserve.cell.class"), pending: t("wave1.grid.pending") });
        const b = slot.booking;
        return [text.primary, b.status === "PENDING" ? text.secondary : null, b.notes, b.department_name && b.department_name !== text.secondary ? b.department_name : null].filter(Boolean).join(" · ") || null;
      }
      if (slot.status === "timetable") return `${t("crbs.legend.timetable")} · ${slot.label || t("reserve.cell.class")}`;
      // P8: request-only slots stay bookable; the hint says the booking goes to the approvers and why
      if (isSelectable(slot)) return slot.request_only ? t("policies.grid.requestOnly", { why: slot.policy ? violationText(slot.policy, locale) : "" }) : null;
      if (slot.status === "available") return t("crbs.slot.reason.permissions");
      if (slot.reason === "policy") return slot.policy ? violationText(slot.policy, locale) : t("policies.grid.refused");
      return t(reasonKey(slot.reason), { name: slot.label ?? "" });
    },
    [t, locale],
  );

  const cellLabel = useCallback(
    (row: AxisItem, col: AxisItem, slot: GridSlot | undefined, inSpan: boolean): string => {
      const parts = [header(row).title, header(col).title];
      const period = [row, col].find((x) => x.kind === "period")?.period;
      if (period) parts.push(`${fmt.time(period.time_start)}–${fmt.time(period.time_end)}`);
      if (!slot) return [...parts, t("crbs.slot.reason.unavailable")].join(", ");
      const kind = multi ? pickKind(slot) : null;
      let state: string;
      if (isSelectable(slot)) {
        state = multi ? (selected.has(slotKey(slot)) ? t("crbs.slot.selected") : t("crbs.slot.selectable")) : inSpan ? t("reserve.cell.selectedSpan", { n: span.length }) : `${t("crbs.slot.free")}, ${t("reserve.cell.reserve")}`;
        if (slot.request_only) state += `, ${t("policies.grid.requestOnlyShort")}`;
      } else if (slot.status === "booked") {
        const text = slotText(slot, { booked: t("crbs.slot.booked"), mine: t("crbs.slot.mine"), class: t("reserve.cell.class"), pending: t("wave1.grid.pending") });
        const b = slot.booking;
        state =
          b?.status === "PENDING"
            ? [text.primary, text.secondary, b.notes, b.department_name].filter(Boolean).join(" · ")
            : [slot.reason === "recurring" ? t("crbs.legend.recurring") : t("crbs.legend.single"), text.primary, b?.notes, b?.department_name].filter(Boolean).join(" · ");
        // never "free" for a booked cell (persona U-11): "press to select it for cancelling"
        if (kind === "cancel") state += `, ${selected.has(slotKey(slot)) ? t("reserve.multi.selectedCancel") : t("wave1.grid.pickToCancel")}`;
      } else state = explain(slot) ?? "";
      return [...parts, state].join(", ");
    },
    [explain, fmt, header, multi, selected, span.length, t],
  );

  const hideHint = useCallback(() => {
    if (hintTimer.current) window.clearTimeout(hintTimer.current);
    hintTimer.current = null;
    setHint(null);
  }, [setHint]);

  const showHintFor = useCallback(
    (el: HTMLElement) => {
      const slot = slotOf(el);
      const text = explain(slot);
      const wrap = wrapRef.current;
      if (!text || !wrap) return setHint(null);
      const a = el.getBoundingClientRect();
      const b = wrap.getBoundingClientRect();
      const left = Math.max(8, Math.min(a.left - b.left + a.width / 2, b.width - 8));
      setHint({ text, left, top: a.top - b.top, key: el.dataset.cell ?? "" });
    },
    // slotOf reads slotsByKey
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [explain, slotsByKey],
  );

  const onPointerOver = (e: PointerEvent<HTMLTableElement>) => {
    const cell = cellOf(e.target);
    if (crosshair) {
      if (!cell?.dataset.cell) setHover(null);
      else {
        const [r, c] = cell.dataset.cell.split("-").map(Number);
        if (hover?.r !== r || hover?.c !== c) setHover({ r: r ?? 0, c: c ?? 0 });
      }
    }
    if (drag.current && cell) {
      const target = slotOf(cell);
      if (target && slotKey(target) !== slotKey(drag.current.anchor)) {
        drag.current.moved = true;
        setSpan(clampSpan(grid, drag.current.anchor, target));
      }
    }
    if (e.pointerType !== "mouse") return;
    if (hintTimer.current) window.clearTimeout(hintTimer.current);
    if (!cell || drag.current) return setHint(null);
    if (hint && hint.key !== cell.dataset.cell) setHint(null);
    hintTimer.current = window.setTimeout(() => showHintFor(cell), HOVER_MS);
  };

  const onPointerDown = (e: PointerEvent<HTMLTableElement>) => {
    const cell = cellOf(e.target);
    const slot = slotOf(cell);
    hideHint();
    suppressClick.current = false;
    if (!cell || !slot) return;
    if (e.pointerType === "touch") {
      // touch and hold: say why a cell cannot be booked (or the full notes) instead of opening it
      const start = { x: e.clientX, y: e.clientY };
      const el = cell;
      const cancel = () => {
        if (hintTimer.current) window.clearTimeout(hintTimer.current);
        el.removeEventListener("pointerup", cancel);
        el.removeEventListener("pointercancel", cancel);
        el.removeEventListener("pointermove", move);
      };
      const move = (ev: globalThis.PointerEvent) => {
        if (Math.hypot(ev.clientX - start.x, ev.clientY - start.y) > 8) cancel();
      };
      el.addEventListener("pointerup", cancel);
      el.addEventListener("pointercancel", cancel);
      el.addEventListener("pointermove", move);
      hintTimer.current = window.setTimeout(() => {
        if (!explain(slot)) return;
        suppressClick.current = true;
        showHintFor(el);
      }, HOLD_MS);
      return;
    }
    if (multi || e.button !== 0 || e.shiftKey || !isSelectable(slot) || !onSpan) return;
    drag.current = { anchor: slot, moved: false };
    const end = () => {
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      const d = drag.current;
      drag.current = null;
      const cur = spanRef.current;
      if (!d?.moved || cur.length < 2) return setSpan([]);
      suppressClick.current = true;
      onSpan(cur);
    };
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
  };

  const onCellClick = useCallback(
    (slot: GridSlot, e: MouseEvent<HTMLButtonElement>) => {
      if (suppressClick.current) {
        suppressClick.current = false;
        return;
      }
      const from = getAnchor();
      if (!multi && e.shiftKey && onSpan && from && isSelectable(slot)) {
        const run = clampSpan(grid, from, slot);
        if (run.length > 1 && slotKey(run[0]!) !== slotKey(run[run.length - 1]!)) {
          setSpan(run);
          onSpan(run);
          return;
        }
      }
      if (isSelectable(slot)) setAnchor(slot);
      setSpan([]);
      onActivate(slot);
    },
    [getAnchor, grid, multi, onActivate, onSpan, setAnchor, setSpan],
  );

  const onKeyDown = (e: KeyboardEvent<HTMLTableElement>) => {
    if (e.key === "Escape" && span.length) {
      setSpan([]);
      return;
    }
    if (e.key === "Enter" && span.length > 1 && onSpan) {
      e.preventDefault();
      onSpan(span);
      return;
    }
    const focus = focusRef.current;
    const next = moveFocus(focus, e.key, { rows: layout.rows.length, cols: layout.cols.length });
    if (!next) return;
    e.preventDefault();
    const nextEl = tableRef.current?.querySelector<HTMLButtonElement>(`[data-cell="${next.r}-${next.c}"]`);
    if (e.shiftKey && !multi && onSpan) {
      const from = getAnchor() ?? slotOf(tableRef.current?.querySelector<HTMLButtonElement>(`[data-cell="${focus.r}-${focus.c}"]`) ?? null);
      const to = slotOf(nextEl ?? null);
      if (from && to && isSelectable(from)) {
        setAnchor(from);
        setSpan(clampSpan(grid, from, to));
      }
    } else if (span.length) setSpan([]);
    nextEl?.focus(); // onCellFocus moves the tab stop
  };

  // the rendered tab stop is the first cell; afterwards onCellFocus moves it in the DOM. A new layout that
  // dropped the moved stop gets one back on the first cell.
  useEffect(() => {
    const table = tableRef.current;
    if (!table || table.querySelector('[data-cell][tabindex="0"]')) return;
    table.querySelector<HTMLButtonElement>('[data-cell="0-0"]')?.setAttribute("tabindex", "0");
    focusRef.current = { r: 0, c: 0 };
  }, [layout]);

  /** a cell got focus (click, tap, arrow key, programmatic): it becomes the one tab stop, no re-render */
  const onCellFocus = useCallback((el: HTMLButtonElement) => {
    const [r, c] = (el.dataset.cell ?? "0-0").split("-").map(Number);
    const prev = focusRef.current;
    if (prev.r === r && prev.c === c) return;
    tableRef.current?.querySelector<HTMLButtonElement>(`[data-cell="${prev.r}-${prev.c}"]`)?.setAttribute("tabindex", "-1");
    el.setAttribute("tabindex", "0");
    focusRef.current = { r: r ?? 0, c: c ?? 0 };
  }, []);

  // stable between renders, so the memoised cells do not all re-render on every pointer / focus change (U-18)
  const labels = useMemo(
    () => ({ booked: t("crbs.slot.booked"), mine: t("crbs.slot.mine"), class: t("reserve.cell.class"), pending: t("wave1.grid.pending"), free: t("reserve.cell.free"), reserve: t("reserve.cell.reserve") }),
    [t],
  );

  if (!layout.rows.length || !layout.cols.length) return null;

  const spanAnnouncement = (() => {
    if (span.length < 2) return "";
    const byId = new Map(grid.periods.map((p) => [p.id, p]));
    const periods = span.map((s) => byId.get(s.period_id)).filter((p) => p !== undefined);
    const first = periods[0];
    const last = periods[periods.length - 1];
    const room = grid.rooms.find((x) => x.id === span[0]!.room_id)?.name ?? "";
    return t("reserve.cell.spanLive", { n: span.length, from: first ? fmt.time(first.time_start) : "", to: last ? fmt.time(last.time_end) : "", room });
  })();

  const corner = columns === "periods" ? (grid.display === "day" ? t("crbs.grid.room") : t("crbs.grid.day")) : t("crbs.grid.period");

  return (
    <div ref={wrapRef} className="relative">
      <div
        className="booking-grid-scroll max-h-[calc(100dvh-15rem)] overflow-auto overscroll-x-contain rounded-xl bg-(--mat-thick-solid) edge-hairline scrollbar-thin print:max-h-none print:overflow-visible print:shadow-none"
        data-testid="booking-grid"
        data-grid-scope={scope}
        onScroll={hint ? hideHint : undefined}
      >
        {crosshair ? <style>{crosshairCss(scope, hover)}</style> : null}
        <table
          ref={tableRef}
          role="grid"
          aria-label={t("crbs.grid.label")}
          aria-rowcount={layout.rows.length + 1}
          aria-describedby={`${scope}-hint`}
          className="w-max min-w-full table-fixed border-separate border-spacing-0 type-caption select-none print:w-full"
          onKeyDown={onKeyDown}
          onPointerOver={onPointerOver}
          onPointerDown={onPointerDown}
          onPointerLeave={() => {
            setHover(null);
            hideHint();
          }}
        >
          <colgroup>
            <col className="w-[96px]" />
            {layout.cols.map((col) => (
              <col key={col.key} className={col.kind === "date" ? "w-[112px]" : "w-[78px]"} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th scope="col" className="sticky top-0 left-0 z-30 bg-(--mat-thick-solid) px-2 py-2 text-left font-medium text-label-3 border-r border-b border-hairline">
                {corner}
              </th>
              {layout.cols.map((col) => {
                const h = header(col);
                const closed = col.kind === "date" && col.date && !col.date.open;
                return (
                  <th
                    key={col.key}
                    scope="col"
                    className={cn("sticky top-0 z-20 bg-(--mat-thick-solid) px-1.5 py-1.5 text-left align-bottom font-semibold text-label-1 edge-hairline-b", closed && "text-label-3")}
                  >
                    <HeaderLabel item={col} title={h.title} sub={h.sub} icon={col.room ? roomIcons?.get(col.room.id) : undefined} onRoomInfo={onRoomInfo} />
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {layout.rows.map((row, r) => {
              const h = header(row);
              return (
                <tr key={row.key} data-r={r}>
                  <th scope="row" className="sticky left-0 z-10 bg-(--mat-thick-solid) px-2 py-1 text-left align-middle font-semibold whitespace-nowrap text-label-1 border-r border-b border-hairline">
                    <HeaderLabel item={row} title={h.title} sub={h.sub} icon={row.room ? roomIcons?.get(row.room.id) : undefined} onRoomInfo={onRoomInfo} />
                  </th>
                  {layout.cols.map((col, c) => {
                    const slot = layout.slot(row, col);
                    const key = slot ? slotKey(slot) : "";
                    const inSpan = spanKeys.has(key);
                    const dept = slot?.status === "booked" ? (slot.booking?.department_id ?? null) : null;
                    const muted = department !== "all" && slot?.status === "booked" && dept !== department;
                    return (
                      <td key={col.key} data-c={c} className="p-0 border-r border-b border-hairline">
                        <Cell
                          slot={slot}
                          index={`${r}-${c}`}
                          focusable={r === 0 && c === 0}
                          label={cellLabel(row, col, slot, inSpan)}
                          multi={multi}
                          isSelected={!!slot && (selected.has(key) || inSpan)}
                          highlighted={!!highlightBookingId && slot?.booking?.id === highlightBookingId}
                          labels={labels}
                          deptColor={muted ? null : departmentColor(dept)}
                          muted={muted}
                          onFocus={onCellFocus}
                          onClick={onCellClick}
                        />
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p id={`${scope}-hint`} className="sr-only">
        {t("reserve.grid.hint")}
      </p>
      {/* persona U-24: the span is announced while it is drawn (pointer drag, Shift+arrows, Shift-click) */}
      <p role="status" aria-live="polite" className="sr-only" data-testid="grid-span-status">
        {spanAnnouncement}
      </p>
      {hint ? (
        <div
          aria-hidden
          data-testid="slot-hint"
          className="pointer-events-none absolute z-40 max-w-64 -translate-x-1/2 -translate-y-full rounded-lg bg-(--mat-thick-solid) px-2.5 py-1.5 type-footnote text-label-1 shadow-elev-3 print:hidden"
          style={{ left: hint.left, top: hint.top - 6 }}
        >
          {hint.text}
        </div>
      ) : null}
    </div>
  );
});

function HeaderLabel({ item, title, sub, icon, onRoomInfo }: { item: AxisItem; title: string; sub: string | null; icon?: string | null; onRoomInfo?: (id: number) => void }) {
  const t = useT();
  const inner = (
    <>
      <span className="flex items-center gap-1 whitespace-nowrap">
        <EntityIcon name={icon} />
        {title}
      </span>
      {sub ? <span className="block truncate font-normal text-label-3 tabular-nums">{sub}</span> : null}
    </>
  );
  if (item.kind === "room" && item.room && onRoomInfo) {
    const id = item.room.id;
    return (
      <BareButton onClick={() => onRoomInfo(id)} aria-label={t("crbs.roomInfo.open", { name: title })} title={sub ?? undefined} className="block w-full rounded-sm text-left hover:text-tint-text" data-testid={`room-info-${item.room.code}`}>
        {inner}
      </BareButton>
    );
  }
  return inner;
}

const Cell = memo(function Cell({
  slot,
  index,
  focusable,
  label,
  multi,
  isSelected,
  highlighted,
  labels,
  deptColor,
  muted,
  onFocus,
  onClick,
}: {
  slot: GridSlot | undefined;
  index: string;
  focusable: boolean;
  label: string;
  multi: boolean;
  isSelected: boolean;
  highlighted?: boolean;
  labels: { booked: string; mine: string; class: string; pending: string; free: string; reserve: string };
  deptColor: string | null;
  muted: boolean;
  onFocus: (el: HTMLButtonElement) => void;
  onClick: (slot: GridSlot, e: MouseEvent<HTMLButtonElement>) => void;
}) {
  const tone = slotTone(slot);
  const text = slotText(slot, labels);
  const kind = multi ? pickKind(slot) : isSelectable(slot) ? "book" : null;
  const free = tone === "available";
  const style: CSSProperties | undefined = deptColor && !isSelected && !highlighted ? { boxShadow: `inset 3px 0 0 ${deptColor}` } : undefined;
  return (
    <BareButton
      data-cell={index}
      data-status={slot?.status ?? "none"}
      data-tone={tone}
      data-slot-key={slot ? slotKey(slot) : undefined}
      data-department={slot?.booking?.department_id ?? undefined}
      data-muted={muted ? "true" : undefined}
      data-selected={isSelected ? "true" : undefined}
      tabIndex={focusable ? 0 : -1}
      aria-label={label}
      aria-pressed={multi && kind ? isSelected : undefined}
      disabled={!slot}
      onFocus={(e) => onFocus(e.currentTarget)}
      onClick={(e) => slot && onClick(slot, e)}
      style={style}
      className={cn(
        "group/cell relative flex h-11 w-full touch-manipulation flex-col items-start justify-center gap-0.5 overflow-hidden rounded-none px-1.5 py-1 text-left font-normal focus-visible:z-10 focus-visible:-outline-offset-2 disabled:opacity-100",
        TONE_CLASS[tone],
        free && "cursor-pointer",
        free && slot?.past && "text-label-3 opacity-60", // started: still bookable for administrators, but dim
        muted && "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--label-1)_4%)] text-label-3",
        isSelected && slot?.status !== "booked" && "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--accent)_18%)] text-label-1",
        isSelected && slot?.status === "booked" && "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--status-infeasible-solid)_14%)] text-label-1",
        isSelected && !highlighted && "inset-ring-2",
        isSelected && !highlighted && (slot?.status === "booked" ? "inset-ring-(--status-infeasible-solid)" : "inset-ring-(--accent)"),
        multi && !kind && "cursor-not-allowed",
        highlighted && "z-10 inset-ring-2 inset-ring-(--status-warning-solid)",
      )}
      data-highlight={highlighted ? "true" : undefined}
    >
      {text.primary ? (
        <span className="flex w-full min-w-0 items-center gap-1 font-medium">
          <SlotGlyph slot={slot} selected={isSelected} className="size-3 shrink-0 stroke-[1.75]" />
          <span className="truncate">{text.primary}</span>
        </span>
      ) : free && !isSelected ? (
        <>
          {/* UI/UX review §3: a blank cell at rest ("Free" ~100× was noise); "+ Reserve" on hover / focus. The
              accessible name still says "free, Reserve", and touch needs no hover: the cell is one tap. */}
          <span className="hidden items-center gap-1 font-medium text-tint-text group-hover/cell:flex group-focus-visible/cell:flex print:hidden!">
            <Plus className="size-3 shrink-0 stroke-[2]" aria-hidden />
            {multi ? labels.free : labels.reserve}
          </span>
        </>
      ) : (
        <SlotGlyph slot={slot} selected={isSelected} className={cn("size-3.5 stroke-[1.75]", tone === "unavailable" && "opacity-60")} />
      )}
      {text.secondary ? <span className="w-full truncate text-label-2">{text.secondary}</span> : null}
      {/* P8: a policy turns a booking here into a request (the accessible name says so) */}
      {free && slot?.request_only ? <Stamp className="absolute top-1 right-1 size-3 text-tint-text" aria-hidden data-request-only="true" /> : null}
    </BareButton>
  );
});
