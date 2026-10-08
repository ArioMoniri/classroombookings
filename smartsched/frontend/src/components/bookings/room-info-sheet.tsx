"use client";
/** Room card from the grid (CRBS `Rooms::info` / `room_info`): photo, group, location, owner, notes, custom fields. */
import { useQuery } from "@tanstack/react-query";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { crbs, crbsError } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { Alert, Loading } from "@/components/admin/kit";
import { EntityIcon } from "@/components/admin/icons";
import { bookingErrorMessage } from "./booking-errors";
import { useIsPhone } from "./use-is-phone";

export function RoomInfoSheet({ roomId, onOpenChange }: { roomId: number | null; onOpenChange: (o: boolean) => void }) {
  const { t } = useI18n();
  const phone = useIsPhone();
  const q = useQuery({ queryKey: ["crbs", "room-info", roomId], queryFn: () => crbs.bookings.room(roomId ?? 0), enabled: roomId !== null, retry: false });
  const r = q.data;
  return (
    <Sheet open={roomId !== null} onOpenChange={onOpenChange}>
      <SheetContent side={phone ? "bottom" : "right"} className="gap-0 data-[side=right]:sm:max-w-md" data-testid="room-info">
        {q.isLoading ? <Loading className="px-5" /> : null}
        {q.isError ? (
          <div className="p-5">
            <SheetTitle className="sr-only">{t("crbs.detail.room")}</SheetTitle>
            <Alert tone="error">{bookingErrorMessage(crbsError(q.error), t)}</Alert>
          </div>
        ) : null}
        {r ? (
          <>
            <SheetHeader className="px-5 pt-5">
              <SheetTitle className="flex items-center gap-2 type-title-3">
                <EntityIcon name={r.icon} className="size-5" />
                {r.name}
              </SheetTitle>
              <SheetDescription>{[r.group, r.capacity ? t("crbs.grid.seats", { n: r.capacity }) : null].filter(Boolean).join(" · ")}</SheetDescription>
            </SheetHeader>
            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 pb-5">
              {/* eslint-disable-next-line @next/next/no-img-element -- uploaded by an administrator, served by the backend */}
              {r.photo_url ? <img src={r.photo_url} alt={t("crbs.rooms.photoAlt", { name: r.name })} className="max-h-60 w-full rounded-xl object-cover" /> : null}
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 type-callout">
                {r.location ? (
                  <>
                    <dt className="text-label-3">{t("crbs.rooms.location")}</dt>
                    <dd className="text-label-1">{r.location}</dd>
                  </>
                ) : null}
                {r.owner ? (
                  <>
                    <dt className="text-label-3">{t("crbs.rooms.owner")}</dt>
                    <dd className="text-label-1">{r.owner}</dd>
                  </>
                ) : null}
                {r.tags.length ? (
                  <>
                    <dt className="text-label-3">{t("crbs.roomInfo.tags")}</dt>
                    <dd className="text-label-1">{r.tags.join(", ")}</dd>
                  </>
                ) : null}
                {r.fields
                  .filter((f) => f.value !== null && f.value !== "" && f.value !== undefined)
                  .map((f) => (
                    <div key={f.field_id} className="contents">
                      <dt className="text-label-3">{f.name}</dt>
                      <dd className="text-label-1">{f.value === true ? t("crbs.common.yes") : f.value === false ? t("crbs.common.no") : String(f.value)}</dd>
                    </div>
                  ))}
              </dl>
              {r.notes ? <p className="whitespace-pre-wrap type-callout text-label-2">{r.notes}</p> : null}
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
