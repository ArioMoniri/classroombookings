"use client";
/**
 * The "Free slots" lens: only the periods the user may reserve, for the chosen day or week, grouped by
 * room (the department's rooms first), consecutive periods kept together. Every period is a 44 px tap
 * target that opens the booking sheet; a room name opens the room details. The default lens on phones.
 * Data list, so no glass (A8): opaque rows on the thick material colour.
 */
import { Info } from "lucide-react";
import type { GridSlot } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { Loading } from "@/components/admin/kit";
import { EmptyState } from "@/components/ui/empty-state";
import type { BookTarget } from "./book-sheet";
import type { DateFormatter } from "./date-format";
import { slotKey } from "./grid-model";
import type { FreeRoom } from "./reserve-model";

export function FreeSlotsList({ rooms, loading, week, fmt, deptFirst, onReserve, onRoomInfo }: { rooms: FreeRoom[]; loading: boolean; week: boolean; fmt: DateFormatter; deptFirst: boolean; onReserve: (target: BookTarget) => void; onRoomInfo: (roomId: number, date: string) => void }) {
  const { t } = useI18n();
  if (loading && !rooms.length) return <Loading label={t("reserve.free.loading")} />;
  const total = rooms.reduce((n, r) => n + r.count, 0);
  if (!rooms.length) return <EmptyState title={week ? t("reserve.free.emptyWeek") : t("reserve.free.empty")} size="sm" />;
  return (
    <section aria-labelledby="free-title" className="flex flex-col gap-3" data-testid="free-slots">
      <p id="free-title" className="type-callout text-label-2" aria-live="polite">
        {t("reserve.free.count", { n: total })} {t("reserve.free.rooms", { n: rooms.length })}
        {deptFirst ? ` · ${t("reserve.free.deptFirst")}` : ""}
      </p>
      <ul className="flex flex-col overflow-hidden rounded-xl bg-(--mat-thick-solid) shadow-[0_0_0_1px_var(--hairline)]">
        {rooms.map((r) => (
          <li key={r.room.id} className="flex flex-col gap-2 px-3 py-3 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none sm:flex-row sm:items-start sm:gap-4" data-testid={`free-room-${r.room.code}`}>
            <button
              type="button"
              onClick={() => onRoomInfo(r.room.id, r.days[0]?.date ?? r.grid.date)}
              aria-label={t("crbs.roomInfo.open", { name: r.room.name })}
              className="flex min-h-11 w-full shrink-0 items-center justify-between gap-2 rounded-md text-left outline-none focus-visible:outline-2 focus-visible:outline-(--focus) sm:w-40 sm:flex-col sm:items-start sm:justify-start sm:gap-0"
            >
              <span className="type-headline text-label-1">{r.room.name}</span>
              <span className="flex items-center gap-1 type-footnote text-label-3">
                {r.room.capacity ? t("reserve.free.seats", { n: r.room.capacity }) : null}
                <Info className="size-3.5" aria-hidden />
              </span>
            </button>
            <div className="flex min-w-0 flex-1 flex-col gap-2">
              {r.days.map((d) => (
                <div key={d.date} className="flex flex-col gap-1">
                  {week ? <span className="type-footnote font-medium text-label-2">{fmt.weekday(d.date)}</span> : null}
                  <div className="flex flex-wrap gap-x-3 gap-y-1.5">
                    {d.runs.map((run) => (
                      <div key={slotKey(run[0]!)} className="flex flex-wrap gap-1">
                        {run.map((s) => (
                          <SlotButton key={s.period_id} slot={s} room={r} fmt={fmt} onReserve={onReserve} />
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function SlotButton({ slot, room, fmt, onReserve }: { slot: GridSlot; room: FreeRoom; fmt: DateFormatter; onReserve: (target: BookTarget) => void }) {
  const { t } = useI18n();
  const p = room.grid.periods.find((x) => x.id === slot.period_id);
  const time = p ? `${fmt.time(p.time_start)}–${fmt.time(p.time_end)}` : "";
  return (
    <button
      type="button"
      onClick={() => onReserve({ slot, grid: room.grid })}
      aria-label={t("reserve.free.reserveAt", { room: room.room.name, date: fmt.weekday(slot.date), time: `${p?.name ?? ""} ${time}` })}
      data-slot-key={slotKey(slot)}
      data-testid="free-slot"
      className="flex min-h-11 min-w-16 flex-col items-start justify-center rounded-md bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--accent)_7%)] px-2.5 py-1 text-left shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--accent)_22%,transparent)] outline-none transition-transform duration-(--dur-fast) ease-(--spring-snappy) hover:bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--accent)_13%)] focus-visible:outline-2 focus-visible:outline-(--focus) active:scale-[0.97]"
    >
      <span className="type-caption font-semibold text-tint-text">{p?.name}</span>
      <span className="type-caption text-label-2 tabular-nums">{p ? fmt.time(p.time_start) : ""}</span>
    </button>
  );
}
