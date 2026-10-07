"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Room } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS_PER_DAY, dayName, periodRangeLabel } from "@/lib/time";
import { cn } from "@/lib/utils";
import { STATUS_EVENT_CLASS } from "./grid-event";
import type { GridEvent, GridModel } from "./use-grid-model";

const MINI_W = 6;
const DAY_W = MINI_W * PERIODS_PER_DAY;
const LABEL_W = 160;
const ROW_H = 28;

/** Week zoom: rooms as rows (virtualised), 7 days × 18 mini-columns; events as colour bars. */
export function WeekGrid({ model, rooms, onPickDay, onOpen, selectedId }: { model: GridModel; rooms: Room[]; onPickDay: (day: number) => void; onOpen: (e: GridEvent) => void; selectedId: string | null }) {
  const { t, locale } = useI18n();
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({ count: rooms.length, getScrollElement: () => scrollRef.current, estimateSize: () => ROW_H, overscan: 8 });
  const days = [1, 2, 3, 4, 5, 6, 7];
  const occupancyByDay = days.map((d) => {
    const total = rooms.length * PERIODS_PER_DAY;
    const used = model.events.filter((e) => e.day === d && rooms.some((r) => r.id === e.roomId)).reduce((s, e) => s + e.endPeriod - e.startPeriod + 1, 0);
    return total ? Math.round((used / total) * 100) : 0;
  });
  return (
    <div ref={scrollRef} className="h-full overflow-auto overscroll-contain scrollbar-thin" data-testid="week-grid">
      <div style={{ width: LABEL_W + DAY_W * 7 }}>
        <div className="sticky top-0 z-10 flex border-b bg-card" style={{ height: 44 }}>
          <div className="sticky left-0 z-20 flex items-end border-r bg-card px-2 pb-1 text-[11px] text-muted-foreground" style={{ width: LABEL_W }}>{t("common.rooms")}</div>
          {days.map((d, i) => (
            <button key={d} type="button" onClick={() => onPickDay(d)} className="flex flex-col items-start justify-end border-r px-1.5 pb-1 text-left hover:bg-accent" style={{ width: DAY_W }} aria-label={`${dayName(d, locale)} · ${occupancyByDay[i]}%`}>
              <span className="text-xs font-medium">{dayName(d, locale, "short")}</span>
              <span className="text-[10px] tabular-nums text-muted-foreground">{occupancyByDay[i]}%</span>
            </button>
          ))}
        </div>
        <div className="relative" style={{ height: virtualizer.getTotalSize() }}>
          {virtualizer.getVirtualItems().map((vi) => {
            const room = rooms[vi.index];
            const events = model.byRoom.get(room.id) ?? [];
            return (
              <div key={room.id} className="absolute left-0 flex w-full border-b" style={{ top: vi.start, height: vi.size }} role="row">
                <div className="sticky left-0 z-10 flex items-center gap-1 border-r bg-background px-2 text-xs" style={{ width: LABEL_W }}>
                  <span className="font-mono font-medium">{room.display_name}</span>
                  <span className="text-[10px] text-muted-foreground">{room.capacity}</span>
                  {room.tags.includes("TIP") ? <span className="rounded bg-status-tip px-1 text-[9px] text-status-tip-fg">TIP</span> : null}
                  {room.tags.includes("PC") ? <span className="rounded bg-status-pclab px-1 text-[9px] text-status-pclab-fg">PC</span> : null}
                </div>
                <div className="relative flex-1" style={{ backgroundImage: `repeating-linear-gradient(90deg, transparent 0 ${DAY_W - 1}px, var(--border) ${DAY_W - 1}px ${DAY_W}px)` }}>
                  {events.map((e) => {
                    const left = (e.day - 1) * DAY_W + (e.startPeriod - 1) * MINI_W;
                    const width = (e.endPeriod - e.startPeriod + 1) * MINI_W;
                    return (
                      <Tooltip key={e.id}>
                        <TooltipTrigger
                          render={
                            <button
                              type="button"
                              data-assignment-id={e.assignment?.id ?? undefined}
                              aria-label={`${e.label} ${dayName(e.day, locale, "short")} ${periodRangeLabel(e.startPeriod, e.endPeriod)}`}
                              onClick={() => onOpen(e)}
                              className={cn("absolute top-1 h-[calc(100%-8px)] rounded-[2px] border outline-none focus-visible:ring-2 focus-visible:ring-ring", STATUS_EVENT_CLASS[e.status], selectedId === e.id && "ring-2 ring-primary")}
                              style={{ left, width: Math.max(2, width - 1), borderLeftWidth: 3, borderLeftColor: e.kind === "block" ? "var(--status-preoccupied-border)" : `var(--cat-${e.facultySlot})` }}
                            />
                          }
                        />
                        <TooltipContent>{e.label} · {dayName(e.day, locale)} P{e.startPeriod}–P{e.endPeriod}{e.kind === "assignment" ? ` · ${e.size}/${e.capacity}` : ""}</TooltipContent>
                      </Tooltip>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
