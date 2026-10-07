"use client";

import { STATUS_ICON } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import type { Room } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS } from "@/lib/time";
import { cn } from "@/lib/utils";
import { STATUS_EVENT_CLASS } from "./grid-event";
import { STATUS_TO_KIND, type GridEvent, type GridModel } from "./use-grid-model";

/** 360 px fallback: periods as section headers, events across the filtered rooms, "Move…" instead of drag. */
export function AgendaView({ model, rooms, day, onOpen, onMove, readOnly }: { model: GridModel; rooms: Room[]; day: number; onOpen: (e: GridEvent) => void; onMove: (e: GridEvent) => void; readOnly: boolean }) {
  const { t } = useI18n();
  const roomIds = new Set(rooms.map((r) => r.id));
  const events = model.events.filter((e) => e.day === day && roomIds.has(e.roomId));
  if (events.length === 0) return <p className="p-4 text-sm text-muted-foreground">{t("grid.noEvents")}</p>;
  return (
    <div className="space-y-3 overflow-y-auto p-1" data-testid="agenda">
      {PERIODS.map((p) => {
        const starting = events.filter((e) => e.startPeriod === p.index).sort((a, b) => a.roomId - b.roomId);
        if (starting.length === 0) return null;
        return (
          <section key={p.index} aria-labelledby={`agenda-p${p.index}`}>
            <h3 id={`agenda-p${p.index}`} className="sticky top-0 bg-background py-1 text-xs font-semibold text-muted-foreground">P{p.index} · {p.start}</h3>
            <ul className="space-y-1.5">
              {starting.map((e) => {
                const Icon = STATUS_ICON[STATUS_TO_KIND[e.status]];
                return (
                  <li key={e.id} className={cn("flex items-center gap-2 rounded-md border p-2 text-sm", STATUS_EVENT_CLASS[e.status])} data-assignment-id={e.assignment?.id ?? undefined}>
                    <span className="h-8 w-[3px] rounded-full" style={{ background: e.kind === "block" ? "var(--status-preoccupied-border)" : `var(--cat-${e.facultySlot})` }} aria-hidden />
                    <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onOpen(e)}>
                      <span className="block truncate font-mono font-semibold">{e.label}</span>
                      <span className="block text-xs opacity-80">{model.roomById.get(e.roomId)?.display_name} · P{e.startPeriod}–P{e.endPeriod}{e.kind === "assignment" ? ` · ${e.size}/${e.capacity}` : ""}</span>
                    </button>
                    <Icon className="size-4 shrink-0" aria-hidden />
                    {e.kind === "assignment" && !e.locked && !readOnly ? <Button size="xs" variant="outline" className="min-h-9" onClick={() => onMove(e)}>{t("grid.move")}…</Button> : null}
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
