"use client";
/**
 * The "Free slots" lens: only the periods the user may reserve, for the chosen day or week, grouped by
 * room (the department's rooms first), consecutive periods kept together. Every period is a 44 px tap
 * target that opens the booking sheet; a room name opens the room details. The default lens on phones.
 * Data list, so no glass (A8): opaque rows on the thick material colour.
 */
import { Hourglass, Info } from "lucide-react";
import type { GridSlot } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { Loading } from "@/components/admin/kit";
import { EmptyState } from "@/components/ui/empty-state";
import type { BookTarget } from "./book-sheet";
import type { DateFormatter } from "./date-format";
import { slotKey } from "./grid-model";
import { isOwnPending, type FreeRoom } from "./reserve-model";
import Link from "next/link";
import { BareButton } from "@/components/shell/bare-button";
import { DEFAULT_SLOT_DISPLAY, slotLabel, type SlotDisplay } from "./slot-display";

export function FreeSlotsList({ rooms, loading, week, fmt, deptFirst, onReserve, onRoomInfo, approvalFirst = false, requestFor, slotDisplay = DEFAULT_SLOT_DISPLAY }: { rooms: FreeRoom[]; loading: boolean; week: boolean; fmt: DateFormatter; deptFirst: boolean; onReserve: (target: BookTarget) => void; onRoomInfo: (roomId: number, date: string) => void; approvalFirst?: boolean; requestFor?: (bookingId: number) => number | null; slotDisplay?: SlotDisplay }) {
  const { t } = useI18n();
  if (loading && !rooms.length) return <Loading label={t("reserve.free.loading")} />;
  const total = rooms.reduce((n, r) => n + r.count, 0);
  if (!rooms.length) return <EmptyState title={week ? t("reserve.free.emptyWeek") : t("reserve.free.empty")} size="sm" />;
  return (
    <section aria-labelledby="free-title" className="flex flex-col gap-3" data-testid="free-slots">
      {/* T-R1-12: where focus returns after a booking from this list when the slot left it */}
      <p id="free-title" className="type-callout text-label-2 outline-hidden" aria-live="polite" tabIndex={-1} data-focus-fallback>
        {t("reserve.free.count", { n: total })} {t("reserve.free.rooms", { n: rooms.length })}
        {deptFirst ? ` · ${t("reserve.free.deptFirst")}` : ""}
        {approvalFirst ? ` · ${t("reserve.free.approvalFirst")}` : ""}
      </p>
      <ul className="flex flex-col overflow-hidden rounded-xl bg-(--mat-thick-solid) edge-hairline">
        {rooms.map((r) => (
          <li key={r.room.id} className="flex flex-col gap-2 px-3 py-3 not-last:edge-hairline-b sm:flex-row sm:items-start sm:gap-4" data-testid={`free-room-${r.room.code}`}>
            <BareButton
              onClick={() => onRoomInfo(r.room.id, r.days[0]?.date ?? r.grid.date)}
              aria-label={t("crbs.roomInfo.open", { name: r.room.name })}
              className="flex min-h-11 w-full shrink-0 items-center justify-between gap-2 rounded-md text-left sm:w-40 sm:flex-col sm:items-start sm:justify-start sm:gap-0"
            >
              <span className="type-headline text-label-1">{r.room.name}</span>
              <span className="flex items-center gap-1 type-footnote text-label-3">
                {r.room.capacity ? t("reserve.free.seats", { n: r.room.capacity }) : null}
                <Info className="size-3.5" aria-hidden />
              </span>
            </BareButton>
            <div className="flex min-w-0 flex-1 flex-col gap-2">
              {r.days.map((d) => (
                <div key={d.date} className="flex flex-col gap-1">
                  {week ? <span className="type-footnote font-medium text-label-2">{fmt.weekday(d.date)}</span> : null}
                  <div className="flex flex-wrap gap-x-3 gap-y-1.5">
                    {d.runs.map((run) => (
                      <div key={slotKey(run[0]!)} className="flex flex-wrap gap-1">
                        {run.map((s) => (
                          isOwnPending(s) ? (
                            <PendingChip key={s.period_id} slot={s} room={r} fmt={fmt} requestId={s.booking ? (requestFor?.(s.booking.id) ?? null) : null} />
                          ) : (
                            <SlotButton key={s.period_id} slot={s} room={r} fmt={fmt} onReserve={onReserve} request={approvalFirst || !!s.request_only} sd={slotDisplay} />
                          )
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

function SlotButton({ slot, room, fmt, onReserve, request, sd }: { slot: GridSlot; room: FreeRoom; fmt: DateFormatter; onReserve: (target: BookTarget) => void; request: boolean; sd: SlotDisplay }) {
  const { t } = useI18n();
  const p = room.grid.periods.find((x) => x.id === slot.period_id);
  const time = p ? `${fmt.time(p.time_start)}–${fmt.time(p.time_end)}` : "";
  // the list shows the start time under the period (its rows are narrow); "time" labels keep the chosen format
  const label = p ? slotLabel(p, sd.label === "both" ? { ...sd, time_format: "start" } : sd, { time: fmt.time, ordinal: (n) => t("slotDisplay.ordinal", { n }) }) : null;
  return (
    <BareButton
      onClick={() => onReserve({ slot, grid: room.grid })}
      aria-label={t(request ? "reserve.free.requestAt" : "reserve.free.reserveAt", { room: room.room.name, date: fmt.weekday(slot.date), time: label ? (sd.label === "time" ? label.a11y : label.a11y.replace(", ", " ")) : time })}
      data-slot-key={slotKey(slot)}
      data-testid="free-slot"
      className="flex min-h-11 min-w-16 flex-col items-start justify-center rounded-md bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--accent)_7%)] px-2.5 py-1 text-left inset-ring inset-ring-[color-mix(in_oklab,var(--accent)_22%,transparent)] hover:bg-[color-mix(in_oklab,var(--mat-thick-solid),var(--accent)_13%)]"
    >
      {/* W3-SLOT: one label rule (slot-display.md §5): primary over secondary, the accessible name stays complete */}
      <span className="type-caption font-semibold text-tint-text tabular-nums">{label?.primary}</span>
      {label?.secondary ? <span className="type-caption text-label-2 tabular-nums">{label.secondary}</span> : null}
    </BareButton>
  );
}

/** T-R1-14 (R1-A-06): the viewer's own request in this slot, waiting for the approvers: a link to it, not a free slot */
function PendingChip({ slot, room, fmt, requestId }: { slot: GridSlot; room: FreeRoom; fmt: DateFormatter; requestId: number | null }) {
  const { t } = useI18n();
  const p = room.grid.periods.find((x) => x.id === slot.period_id);
  const time = p ? `${fmt.time(p.time_start)}–${fmt.time(p.time_end)}` : "";
  return (
    <Link
      href={requestId ? `/my-bookings?request=${requestId}` : "/my-bookings"}
      aria-label={t("reserve.free.pendingAt", { room: room.room.name, date: fmt.weekday(slot.date), time: `${p?.name ?? ""} ${time}` })}
      data-slot-key={slotKey(slot)}
      data-testid="free-slot-pending"
      className="flex min-h-11 min-w-16 flex-col items-start justify-center rounded-md bg-fill-3 px-2.5 py-1 text-left outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)"
    >
      <span className="flex items-center gap-1 type-caption font-semibold text-label-1">
        <Hourglass className="size-3" aria-hidden />
        {p?.name}
      </span>
      <span className="type-caption text-label-2">{t("reserve.free.pendingTag")}</span>
    </Link>
  );
}
