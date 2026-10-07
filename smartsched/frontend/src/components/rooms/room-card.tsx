"use client";

import { Users } from "lucide-react";
import Link from "next/link";
import { StatusBadge } from "@/components/common/status-badge";
import type { Room } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { SparklineBars, type DayOccupancy } from "./sparkline-bars";

const BUILDING_WASH: Record<string, string> = { A: "var(--cat-1)", B: "var(--cat-3)", C: "var(--cat-7)", D: "var(--cat-4)" };

export function RoomPhoto({ room, className }: { room: Room; className?: string }) {
  if (room.photo_url) {
    // eslint-disable-next-line @next/next/no-img-element -- external demo photos, sized by container
    return <img src={room.photo_url} alt={room.display_name} loading="lazy" className={`${className ?? ""} object-cover`} />;
  }
  return (
    <div className={`${className ?? ""} flex items-center justify-center font-mono text-4xl font-bold text-white/90`} style={{ background: `linear-gradient(135deg, ${BUILDING_WASH[room.building_code] ?? "var(--cat-8)"}, var(--surface-2))` }} aria-hidden>
      {room.display_name}
    </div>
  );
}

export function RoomCard({ room, occupancy, selectedDay }: { room: Room; occupancy?: DayOccupancy[]; selectedDay?: number }) {
  const { t } = useI18n();
  const util = Math.round((room.utilisation ?? 0) * 100);
  const floorLabel = room.floor === null ? "" : room.floor === 0 ? "Z" : `${room.floor}. ${t("rooms.floor").toLocaleLowerCase()}`;
  return (
    <Link
      href={`/rooms/${room.id}`}
      aria-label={`${room.display_name}, ${room.building_code}, ${room.capacity} ${t("common.seats")}, ${t("rooms.examCapacity")} ${room.exam_capacity}, ${room.tags.join(" ")}, ${util}%`}
      className="group overflow-hidden rounded-xl border bg-card outline-none transition-[box-shadow,transform] hover:-translate-y-0.5 hover:shadow-elev-1 focus-visible:ring-2 focus-visible:ring-ring motion-reduce:hover:translate-y-0"
      data-testid="room-card"
    >
      <div className="relative aspect-[4/3] overflow-hidden bg-muted">
        <RoomPhoto room={room} className="size-full" />
        <div className="absolute top-2 left-2 flex gap-1">
          {room.tags.includes("TIP") ? <StatusBadge kind="tip" label="TIP" /> : null}
          {room.tags.includes("PC") ? <StatusBadge kind="pclab" label="PC" /> : null}
          {!room.is_bookable ? <StatusBadge kind="preoccupied" label={t("rooms.notBookable")} /> : null}
        </div>
      </div>
      <div className="space-y-1 p-3">
        <div className="flex items-center justify-between">
          <span className="font-mono text-md font-semibold">{room.display_name}</span>
          <span className="inline-flex items-center gap-1 text-sm tabular-nums"><Users className="size-3.5 text-muted-foreground" aria-hidden />{room.capacity}</span>
        </div>
        <p className="truncate text-xs text-muted-foreground">
          {room.building_code} {t("common.building").toLocaleLowerCase()}{floorLabel ? ` · ${floorLabel}` : ""}{room.tags.includes("AMPHI") ? ` · ${t("rooms.tag.AMPHI").toLocaleLowerCase()}` : ""}
        </p>
        <p className="text-xs text-muted-foreground">{t("rooms.examCapacity")} {room.exam_capacity}</p>
        <div className="flex items-center justify-between pt-1">
          {occupancy ? <SparklineBars data={occupancy} selectedDay={selectedDay} /> : <span className="h-7" />}
          <span className="text-xs tabular-nums text-muted-foreground">{util}%</span>
        </div>
      </div>
    </Link>
  );
}
