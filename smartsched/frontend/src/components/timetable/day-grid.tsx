"use client";

import { useDroppable } from "@dnd-kit/core";
import { useVirtualizer } from "@tanstack/react-virtual";
import { memo, useRef } from "react";
import { PERIODS } from "@/lib/time";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import type { Room } from "@/lib/api/schemas";
import { DraggableEvent } from "./grid-event";
import type { DropTarget } from "./timetable-types";
import type { GridEvent, GridModel } from "./use-grid-model";

export const ROOM_COL_W = 128;
export const TIME_COL_W = 72;
export const HEADER_H = 56;

interface CellProps {
  roomId: number;
  day: number;
  period: number;
  target: DropTarget | null;
  isDragging: boolean;
}

/** Droppable period cell (one per room × period). Highlight state comes from the live drop target. */
const Cell = memo(function Cell({ roomId, day, period, target, isDragging }: CellProps) {
  const { setNodeRef, isOver } = useDroppable({ id: `cell:${roomId}:${day}:${period}`, data: { roomId, day, period }, disabled: !isDragging });
  const inTarget = target !== null && target.roomId === roomId && period >= target.startPeriod && period <= target.endPeriod;
  return (
    <div
      ref={setNodeRef}
      role="gridcell"
      aria-rowindex={period + 1}
      data-period={period}
      data-over={isOver || undefined}
      className={cn(
        "border-b border-r border-border/70 bg-background",
        period === 12 && "bg-muted/40",
        inTarget && (target.ok ? "bg-primary-tint outline-2 outline-[var(--dropok-outline)] -outline-offset-2" : "bg-status-infeasible/60 outline-2 outline-dashed outline-[var(--conflict-outline)] -outline-offset-2"),
      )}
      style={{ gridRow: period, gridColumn: 1 }}
    />
  );
});

interface ColumnProps {
  room: Room;
  day: number;
  events: GridEvent[];
  target: DropTarget | null;
  isDragging: boolean;
  activeId: string | null;
  selectedId: string | null;
  highlightIds: ReadonlySet<number>;
  changedIds: ReadonlySet<number>;
  conflictIds: ReadonlySet<string>;
  compact: boolean;
  readOnly: boolean;
  onOpen: (e: GridEvent) => void;
  onKeyAction: (e: GridEvent, key: string) => void;
}

const RoomColumn = memo(function RoomColumn({ room, day, events, target, isDragging, activeId, selectedId, highlightIds, changedIds, conflictIds, compact, readOnly, onOpen, onKeyAction }: ColumnProps) {
  return (
    <div role="row" className="relative grid" style={{ gridTemplateRows: `repeat(${PERIODS.length}, var(--period-row-h))`, gridTemplateColumns: "1fr", width: ROOM_COL_W }} data-room-id={room.id}>
      {PERIODS.map((p) => <Cell key={p.index} roomId={room.id} day={day} period={p.index} target={target} isDragging={isDragging} />)}
      {events.map((e) => {
        const lane = events.filter((o) => o !== e && o.startPeriod <= e.endPeriod && e.startPeriod <= o.endPeriod).length > 0 && events.indexOf(e) % 2 === 1;
        return (
          <DraggableEvent
            key={e.id}
            event={e}
            roomName={room.display_name}
            compact={compact}
            disabled={readOnly}
            selected={selectedId === e.id}
            highlighted={e.assignment ? highlightIds.has(e.assignment.id) : false}
            changed={e.assignment ? changedIds.has(e.assignment.id) : false}
            conflictPulse={conflictIds.has(e.id)}
            dragging={activeId === e.id}
            onOpen={onOpen}
            onKeyAction={onKeyAction}
            style={{ gridRow: `${e.startPeriod} / span ${e.endPeriod - e.startPeriod + 1}`, gridColumn: 1, margin: 1, ...(lane ? { marginLeft: "50%" } : {}), ...(events.some((o) => o !== e && o.startPeriod <= e.endPeriod && e.startPeriod <= o.endPeriod) && !lane ? { marginRight: "50%" } : {}) }}
          />
        );
      })}
    </div>
  );
});

export interface DayGridProps {
  model: GridModel;
  rooms: Room[];
  day: number;
  target: DropTarget | null;
  isDragging: boolean;
  activeId: string | null;
  selectedId: string | null;
  highlightIds: ReadonlySet<number>;
  changedIds: ReadonlySet<number>;
  conflictIds: ReadonlySet<string>;
  compact: boolean;
  readOnly: boolean;
  examWeek: boolean;
  onOpen: (e: GridEvent) => void;
  onKeyAction: (e: GridEvent, key: string) => void;
}

/** Day zoom: 18 period rows × N room columns (Excel-like), room columns virtualised horizontally. */
export function DayGrid({ model, rooms, day, target, isDragging, activeId, selectedId, highlightIds, changedIds, conflictIds, compact, readOnly, examWeek, onOpen, onKeyAction }: DayGridProps) {
  const { t } = useI18n();
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({ horizontal: true, count: rooms.length, getScrollElement: () => scrollRef.current, estimateSize: () => ROOM_COL_W, overscan: 4 });
  const items = virtualizer.getVirtualItems();
  const totalW = virtualizer.getTotalSize();
  const rowH = compact ? 28 : 40;
  return (
    <div ref={scrollRef} className="relative h-full overflow-auto overscroll-contain scrollbar-thin" style={{ touchAction: "pan-x pan-y" }} data-testid="day-grid">
      <div role="grid" aria-rowcount={PERIODS.length + 1} aria-colcount={rooms.length + 1} aria-label={t("grid.title")} className="relative" style={{ width: TIME_COL_W + totalW, ["--period-row-h" as string]: `${rowH}px` }}>
        {/* header row */}
        <div role="row" className="sticky top-0 z-10 flex bg-card shadow-[0_1px_0_var(--border)]" style={{ height: HEADER_H, paddingLeft: TIME_COL_W }}>
          <div role="columnheader" className="sticky left-0 z-20 flex items-end border-r bg-card px-2 pb-1 text-[11px] font-medium text-muted-foreground" style={{ width: TIME_COL_W, marginLeft: -TIME_COL_W, height: HEADER_H }}>
            {t("common.period")}
          </div>
          <div className="relative" style={{ width: totalW, height: HEADER_H }}>
            {items.map((vi) => {
              const room = rooms[vi.index];
              const cap = examWeek ? room.exam_capacity : room.capacity;
              const occ = (model.byRoom.get(room.id) ?? []).filter((e) => e.day === day).reduce((s, e) => s + e.endPeriod - e.startPeriod + 1, 0);
              return (
                <div key={room.id} role="columnheader" aria-label={`${room.display_name}, ${cap} ${t("common.seats")}${room.tags.length ? `, ${room.tags.join(" ")}` : ""}`} className="absolute top-0 flex h-full flex-col justify-end border-r px-2 pb-1" style={{ left: vi.start, width: vi.size }}>
                  <div className="flex items-baseline justify-between">
                    <span className="truncate font-mono text-sm font-semibold">{room.display_name}</span>
                    <span className="text-[11px] tabular-nums text-muted-foreground">{cap}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    {room.tags.filter((tg) => tg === "TIP" || tg === "PC").map((tg) => (
                      <span key={tg} className={cn("rounded px-1 text-[9px] font-semibold", tg === "TIP" ? "bg-status-tip text-status-tip-fg" : "bg-status-pclab text-status-pclab-fg")}>{tg}</span>
                    ))}
                    <span className="ml-auto h-1 w-10 overflow-hidden rounded-full bg-muted" aria-hidden><span className="block h-full bg-primary" style={{ width: `${Math.min(100, (occ / 18) * 100)}%` }} /></span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        {/* body */}
        <div className="flex" style={{ paddingLeft: TIME_COL_W }}>
          <div role="row" className="sticky left-0 z-10 grid border-r bg-card" style={{ width: TIME_COL_W, marginLeft: -TIME_COL_W, gridTemplateRows: `repeat(${PERIODS.length}, var(--period-row-h))` }}>
            {PERIODS.map((p) => (
              <div key={p.index} role="rowheader" className={cn("flex flex-col justify-center border-b px-2 leading-tight", p.index === 12 && "bg-muted/40")}>
                <span className="font-mono text-[11px] font-semibold">P{p.index}</span>
                <span className="text-[10px] tabular-nums text-muted-foreground">{p.start}–{p.end}</span>
              </div>
            ))}
          </div>
          <div className="relative" style={{ width: totalW, height: PERIODS.length * rowH }}>
            {items.map((vi) => {
              const room = rooms[vi.index];
              const events = (model.byRoom.get(room.id) ?? []).filter((e) => e.day === day);
              return (
                <div key={room.id} className="absolute top-0" style={{ left: vi.start, width: vi.size }}>
                  <RoomColumn room={room} day={day} events={events} target={target && target.roomId === room.id ? target : null} isDragging={isDragging} activeId={activeId} selectedId={selectedId} highlightIds={highlightIds} changedIds={changedIds} conflictIds={conflictIds} compact={compact} readOnly={readOnly} onOpen={onOpen} onKeyAction={onKeyAction} />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
