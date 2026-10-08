"use client";
/**
 * The CRBS booking grid. Data cells are opaque (no glass on data, A8); only the sticky headers use the
 * thick material colour without blur. One roving tab stop: arrow keys / Home / End move between cells,
 * Enter or Space activates (book, open, or toggle in multi-select mode).
 */
import { Ban, CalendarOff, Check, GraduationCap, Plus, Repeat, User } from "lucide-react";
import { memo, useCallback, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import type { Grid, GridSlot } from "@/lib/api/crbs";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { crosshairCss, isSelectable, layoutGrid, moveFocus, slotKey, slotText, slotTone, type AxisItem, type SlotTone } from "./grid-model";
import { EntityIcon } from "@/components/admin/icons";
import type { DateFormatter } from "./date-format";

export const TONE_CLASS: Record<SlotTone, string> = {
  available: "bg-(--mat-thick-solid) text-label-3 hover:bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--accent)_9%)] hover:text-tint-text",
  "booked-single": "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--label-1)_8%)] text-label-1",
  "booked-recurring": "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--cat-7)_13%)] text-label-1",
  "booked-mine": "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--cat-3)_17%)] text-label-1",
  timetable: "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--status-locked-solid)_12%)] text-label-1",
  holiday: "hatch-preoccupied text-label-2",
  unavailable: "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--label-1)_3%)] text-label-4",
};

export const TONE_ICON: Record<SlotTone, typeof User> = {
  available: Plus,
  "booked-single": User,
  "booked-recurring": Repeat,
  "booked-mine": User,
  timetable: GraduationCap,
  holiday: CalendarOff,
  unavailable: Ban,
};

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
};

export function reasonKey(reason: string | null | undefined): MessageKey {
  return (reason && REASON_KEYS[reason]) || "crbs.slot.reason.unavailable";
}

interface Props {
  grid: Grid;
  columns: "periods" | "rooms" | "days";
  fmt: DateFormatter;
  multi: boolean;
  selected: ReadonlySet<string>;
  onActivate: (slot: GridSlot) => void;
  /** CRBS `grid_highlight`: tint the row and column under the pointer */
  crosshair?: boolean;
  /** CRBS `?highlight=<booking id>`: outline that booking's slot */
  highlightBookingId?: number | null;
  /** room id → icon name (from /bookings/rooms) */
  roomIcons?: ReadonlyMap<number, string | null | undefined>;
  onRoomInfo?: (roomId: number) => void;
}

export function BookingGrid({ grid, columns, fmt, multi, selected, onActivate, crosshair, highlightBookingId, roomIcons, onRoomInfo }: Props) {
  const t = useT();
  const layout = useMemo(() => layoutGrid(grid, columns), [grid, columns]);
  const [focus, setFocus] = useState({ r: 0, c: 0 });
  const [hover, setHover] = useState<{ r: number; c: number } | null>(null);
  const tableRef = useRef<HTMLTableElement>(null);
  const scope = useId().replace(/[^a-zA-Z0-9]/g, "");
  const onPointerOver = (e: PointerEvent<HTMLTableElement>) => {
    if (!crosshair) return;
    const cell = (e.target as HTMLElement).closest<HTMLElement>("[data-cell]")?.dataset.cell;
    if (!cell) return setHover(null);
    const [r, c] = cell.split("-").map(Number);
    if (hover?.r !== r || hover?.c !== c) setHover({ r: r ?? 0, c: c ?? 0 });
  };

  const header = useCallback(
    (item: AxisItem): { title: string; sub: string | null; tone?: string } => {
      if (item.kind === "room" && item.room) return { title: item.room.name, sub: item.room.capacity ? t("crbs.grid.seats", { n: item.room.capacity }) : null };
      if (item.kind === "period" && item.period) return { title: item.period.name, sub: `${fmt.time(item.period.time_start)}–${fmt.time(item.period.time_end)}` };
      if (item.kind === "date" && item.date) return { title: fmt.weekday(item.date.date), sub: item.date.holiday ?? null };
      return { title: "", sub: null };
    },
    [fmt, t],
  );

  const cellLabel = useCallback(
    (row: AxisItem, col: AxisItem, slot: GridSlot | undefined): string => {
      const parts = [header(row).title, header(col).title];
      const period = [row, col].find((x) => x.kind === "period")?.period;
      if (period) parts.push(`${fmt.time(period.time_start)}–${fmt.time(period.time_end)}`);
      if (!slot) return [...parts, t("crbs.slot.reason.unavailable")].join(", ");
      const text = slotText(slot, { booked: t("crbs.slot.booked"), mine: t("crbs.slot.mine") });
      const state =
        slot.status === "available"
          ? isSelectable(slot)
            ? multi
              ? selected.has(slotKey(slot))
                ? t("crbs.slot.selected")
                : t("crbs.slot.selectable")
              : t("crbs.slot.free")
            : t("crbs.slot.reason.permissions")
          : slot.status === "booked"
            ? [slot.reason === "recurring" ? t("crbs.legend.recurring") : t("crbs.legend.single"), text.primary, text.secondary].filter(Boolean).join(" · ")
            : slot.status === "timetable"
              ? `${t("crbs.legend.timetable")} · ${slot.label ?? ""}`
              : t(reasonKey(slot.reason), { name: slot.label ?? "" });
      return [...parts, state].join(", ");
    },
    [fmt, header, multi, selected, t],
  );

  const onKeyDown = (e: KeyboardEvent<HTMLTableElement>) => {
    const next = moveFocus(focus, e.key, { rows: layout.rows.length, cols: layout.cols.length });
    if (!next) return;
    e.preventDefault();
    setFocus(next);
    tableRef.current?.querySelector<HTMLButtonElement>(`[data-cell="${next.r}-${next.c}"]`)?.focus();
  };

  if (!layout.rows.length || !layout.cols.length) return null;

  const corner = columns === "periods" ? (grid.display === "day" ? t("crbs.grid.room") : t("crbs.grid.day")) : t("crbs.grid.period");

  return (
    <div className="booking-grid-scroll max-h-[calc(100dvh-15rem)] overflow-auto overscroll-x-contain rounded-xl bg-(--mat-thick-solid) shadow-[0_0_0_1px_var(--hairline)] scrollbar-thin print:max-h-none print:overflow-visible print:shadow-none" data-testid="booking-grid" data-grid-scope={scope}>
      {crosshair ? <style>{crosshairCss(scope, hover)}</style> : null}
      <table
        ref={tableRef}
        role="grid"
        aria-label={t("crbs.grid.label")}
        aria-rowcount={layout.rows.length + 1}
        className="w-max min-w-full table-fixed border-separate border-spacing-0 type-caption print:w-full"
        onKeyDown={onKeyDown}
        onPointerOver={onPointerOver}
        onPointerLeave={() => setHover(null)}
      >
        <colgroup>
          <col className="w-[96px]" />
          {layout.cols.map((col) => (
            <col key={col.key} className={col.kind === "date" ? "w-[112px]" : "w-[78px]"} />
          ))}
        </colgroup>
        <thead>
          <tr>
            <th scope="col" className="sticky top-0 left-0 z-30 bg-(--mat-thick-solid) px-2 py-2 text-left font-medium text-label-3 shadow-[inset_-1px_-1px_0_var(--hairline)]">
              {corner}
            </th>
            {layout.cols.map((col) => {
              const h = header(col);
              const closed = col.kind === "date" && col.date && !col.date.open;
              return (
                <th
                  key={col.key}
                  scope="col"
                  className={cn("sticky top-0 z-20 bg-(--mat-thick-solid) px-1.5 py-1.5 text-left align-bottom font-semibold text-label-1 shadow-[inset_0_-1px_0_var(--hairline)]", closed && "text-label-3")}
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
                <th scope="row" className="sticky left-0 z-10 bg-(--mat-thick-solid) px-2 py-1 text-left align-middle font-semibold whitespace-nowrap text-label-1 shadow-[inset_-1px_0_0_var(--hairline),inset_0_-1px_0_var(--hairline)]">
                  <HeaderLabel item={row} title={h.title} sub={h.sub} icon={row.room ? roomIcons?.get(row.room.id) : undefined} onRoomInfo={onRoomInfo} />
                </th>
                {layout.cols.map((col, c) => {
                  const slot = layout.slot(row, col);
                  return (
                    <td key={col.key} data-c={c} className="p-0 shadow-[inset_-1px_-1px_0_var(--hairline)]">
                      <Cell
                        slot={slot}
                        index={`${r}-${c}`}
                        focusable={focus.r === r && focus.c === c}
                        label={cellLabel(row, col, slot)}
                        multi={multi}
                        isSelected={!!slot && selected.has(slotKey(slot))}
                        highlighted={!!highlightBookingId && slot?.booking?.id === highlightBookingId}
                        booked={t("crbs.slot.booked")}
                        mine={t("crbs.slot.mine")}
                        onFocus={() => setFocus({ r, c })}
                        onActivate={onActivate}
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
  );
}

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
      <button type="button" onClick={() => onRoomInfo(id)} aria-label={t("crbs.roomInfo.open", { name: title })} className="block w-full rounded-sm text-left outline-none hover:text-tint-text focus-visible:outline-2 focus-visible:outline-(--focus)" data-testid={`room-info-${item.room.code}`}>
        {inner}
      </button>
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
  booked,
  mine,
  onFocus,
  onActivate,
}: {
  slot: GridSlot | undefined;
  index: string;
  focusable: boolean;
  label: string;
  multi: boolean;
  isSelected: boolean;
  highlighted?: boolean;
  booked: string;
  mine: string;
  onFocus: () => void;
  onActivate: (slot: GridSlot) => void;
}) {
  const tone = slotTone(slot);
  const Icon = isSelected ? Check : TONE_ICON[tone];
  const text = slotText(slot, { booked, mine });
  const selectable = isSelectable(slot);
  return (
    <button
      type="button"
      data-cell={index}
      data-status={slot?.status ?? "none"}
      data-tone={tone}
      data-slot-key={slot ? slotKey(slot) : undefined}
      tabIndex={focusable ? 0 : -1}
      aria-label={label}
      aria-pressed={multi && selectable ? isSelected : undefined}
      disabled={!slot}
      onFocus={onFocus}
      onClick={() => slot && onActivate(slot)}
      className={cn(
        "group/cell relative flex h-11 w-full flex-col items-start justify-center gap-0.5 overflow-hidden px-1.5 py-1 text-left outline-none focus-visible:z-10 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)",
        TONE_CLASS[tone],
        isSelected && "bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--accent)_18%)] text-label-1 shadow-[inset_0_0_0_2px_var(--accent)]",
        multi && !selectable && "cursor-not-allowed",
        highlighted && "z-10 shadow-[inset_0_0_0_2px_var(--status-warning-solid)]",
      )}
      data-highlight={highlighted ? "true" : undefined}
    >
      {text.primary ? (
        <span className="flex w-full min-w-0 items-center gap-1 font-medium">
          <Icon className="size-3 shrink-0 stroke-[1.75]" aria-hidden />
          <span className="truncate">{text.primary}</span>
        </span>
      ) : (
        <Icon
          className={cn("size-3.5 stroke-[1.75]", tone === "available" && !isSelected && "opacity-0 transition-opacity duration-(--dur-fast) group-hover/cell:opacity-100 group-focus-visible/cell:opacity-100", tone === "unavailable" && "opacity-60")}
          aria-hidden
        />
      )}
      {text.secondary ? <span className="w-full truncate text-label-2">{text.secondary}</span> : null}
    </button>
  );
});
