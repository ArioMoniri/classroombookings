"use client";
/**
 * Room card (Liquid Glass v2): an opaque content card on the scene (A8: content is not glass; 80+ cards would also be 80+ blur passes). A real photo when the room has one; otherwise a
 * code tile (fills + type only: no gradient, no placeholder image, liquid-glass.md A1/A3). One state badge
 * at most ("Kapalı"), tags as plain words (A4). The Mon–Fri bars are opaque marks (A8), their heights are
 * the day shares of the chosen week; the line under them says what holds the room right now.
 */
import Link from "next/link";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import type { Room } from "@/lib/api/schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { TEACHING_DAYS, dayShare, type RoomCell, type RoomWeek } from "./room-occupancy";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

const TAG_KEY: Record<Room["tags"][number], MessageKey> = { PC: "roomsV2.tagPC", TIP: "roomsV2.tagTIP", LAB: "roomsV2.tagLAB", AMPHI: "roomsV2.tagAMPHI" };

export function tagWords(room: Pick<Room, "tags">, t: T): string[] {
  return room.tags.map((tg) => t(TAG_KEY[tg]));
}

export function floorText(floor: number | null | undefined, t: T): string | null {
  if (floor === null || floor === undefined) return null;
  return floor === 0 ? t("roomsV2.ground") : t("roomsV2.floorLabel", { n: floor });
}

/** Photo when it loads; the code tile otherwise (also when the upload 404s in dev). */
export function RoomVisual({ room, variant, className }: { room: Pick<Room, "photo_url" | "display_name" | "building_code" | "code">; variant: "tile" | "hero"; className?: string }) {
  const { t } = useI18n();
  const [failed, setFailed] = useState(false);
  if (room.photo_url && !failed) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- uploaded room photos, served by /uploads/rooms (nginx → backend)
      <img
        src={room.photo_url}
        alt={t("roomsV2.photoOf", { room: room.display_name })}
        loading="lazy"
        onError={() => setFailed(true)}
        className={cn("object-cover", variant === "tile" ? "size-14 rounded-xl" : "aspect-video w-full rounded-xl", className)}
      />
    );
  }
  const number = room.display_name.replace(new RegExp(`^${room.building_code}\\s*`), "") || room.code;
  if (variant === "hero") return null;
  return (
    <span aria-hidden className={cn("flex size-14 shrink-0 flex-col items-center justify-center rounded-xl bg-fill-2 leading-none shadow-[inset_0_0_0_1px_var(--hairline)]", className)}>
      <span className="text-[11px] font-semibold text-label-2">{room.building_code}</span>
      <span className="mt-0.5 text-[17px] font-semibold tracking-[-0.01em] text-label-1 tabular-nums">{number}</span>
    </span>
  );
}

export function nowLine(cell: Exclude<RoomCell, { kind: "free" }> | null | undefined, t: T): string {
  if (!cell) return t("roomsV2.todayFree");
  return t("roomsV2.todayBusy", { label: cell.kind === "block" ? `${t("roomsV2.blocked")} · ${cell.label}` : cell.label });
}

export function RoomCard({ room, grid, week, now, href }: { room: Room; grid: RoomWeek | null; week: number | null; now: Exclude<RoomCell, { kind: "free" }> | null | undefined; href: string }) {
  const { t, locale } = useI18n();
  const shares = grid ? TEACHING_DAYS.map((d) => dayShare(grid, d)) : null;
  const pct = shares ? Math.round((shares.reduce((a, b) => a + b, 0) / shares.length) * 100) : null;
  const floor = floorText(room.floor, t);
  const tags = tagWords(room, t);
  const meta = [t("roomsV2.seats", { n: room.capacity }), t("roomsV2.examSeats", { n: room.exam_capacity })].join(" · ");
  const label = [room.display_name, meta, floor, ...tags, !room.is_bookable ? t("roomsV2.notBookable") : null, pct !== null && week !== null ? t("roomsV2.occupancy", { p: pct, w: week }) : null].filter(Boolean).join(", ");
  return (
    <Link
      href={href}
      aria-label={label}
      data-testid="room-card"
      data-room-id={room.id}
      className="group/room flex flex-col gap-3 rounded-2xl bg-(--mat-regular-solid) p-3 shadow-[0_0_0_1px_var(--hairline),var(--ambient-1)] outline-none transition-colors duration-(--dur-fast) hover:bg-[color-mix(in_srgb,var(--mat-regular-solid),var(--label-1)_4%)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus)"
    >
      <div className="flex items-start gap-3">
        <RoomVisual room={room} variant="tile" />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="flex items-center gap-2">
            <span className="type-headline truncate">{room.display_name}</span>
            {!room.is_bookable ? <Badge variant="secondary" tone="preoccupied">{t("roomsV2.notBookable")}</Badge> : null}
          </span>
          <span className="truncate text-[13px] text-label-1 tabular-nums">{meta}</span>
          <span className="truncate text-[12px] text-label-2">{[floor, ...tags].filter(Boolean).join(" · ") || " "}</span>
        </div>
      </div>
      <div className="flex items-end gap-3">
        {shares ? (
          <span className="flex h-8 items-end gap-[3px]" aria-hidden>
            {shares.map((s, i) => (
              <span key={TEACHING_DAYS[i]} className="flex w-3 flex-col items-center gap-0.5">
                <span className="flex h-6 w-full items-end overflow-hidden rounded-[3px] bg-fill-3">
                  <span className="w-full rounded-[3px] bg-label-2" style={{ height: `${Math.max(s > 0 ? 8 : 0, Math.round(s * 100))}%` }} />
                </span>
                <span className="text-[9px] leading-none text-label-3">{dayName(TEACHING_DAYS[i], locale, "short").slice(0, 1)}</span>
              </span>
            ))}
          </span>
        ) : null}
        <span className="flex min-w-0 flex-1 flex-col items-end gap-0.5 text-right">
          {pct !== null ? <span className="text-[15px] font-semibold tabular-nums">{t("roomsV2.occupancyShort", { p: pct })}</span> : null}
          {now !== undefined ? (
            <span className={cn("max-w-full truncate text-[12px]", now ? "text-label-1" : "text-status-feasible-fg")}>{nowLine(now, t)}</span>
          ) : null}
        </span>
      </div>
    </Link>
  );
}
