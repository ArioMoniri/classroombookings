"use client";
/**
 * The three public pages (V2, no sign-in): /public (buildings and rooms), /public/rooms/[code] (one room's day) and
 * /public/buildings/[code] (every room of a building that day, now / next per room). Each refreshes every 60 s and
 * shows the one "not found" page when the view is off, the code is unknown or the date is outside the window.
 */
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Loading } from "@/components/admin/kit";
import { Card } from "@/components/ui/card";
import { coarseHitArea } from "@/components/ui/hit-area";
import { currentItem, isNotFound, nextItem, publicApi, publicKeys, usePublicBuilding, usePublicIndex, usePublicRoom, type PublicItem } from "@/lib/api/public-schedule";
import { useI18n } from "@/lib/i18n/provider";
import { ItemList, KioskFrame, PublicError, PublicNotFound, useClock, useKioskDate } from "./kiosk";

/**
 * The backend's today (the booking clock, not the browser's): the answer for the default date carries it. With a
 * `?date=` in the URL that answer is fetched once more (shared cache, refreshed every 10 min) so the date switcher
 * always knows its window.
 */
function useBackendToday(kind: "room" | "building", code: string, date: string | null, answered: string | undefined): string | null {
  const q = useQuery<{ date: string }>({
    queryKey: kind === "room" ? publicKeys.room(code, null) : publicKeys.building(code, null),
    queryFn: (): Promise<{ date: string }> => (kind === "room" ? publicApi.room(code, null) : publicApi.building(code, null)),
    enabled: !!date,
    staleTime: 10 * 60_000,
    refetchInterval: 10 * 60_000,
    retry: false,
  });
  return date ? (q.data?.date ?? null) : (answered ?? null);
}

export function PublicIndexView() {
  const { t } = useI18n();
  const q = usePublicIndex();
  if (q.isError && isNotFound(q.error)) return <PublicNotFound />;
  return (
    <KioskFrame title={t("publicSchedule.indexTitle")} subtitle={t("publicSchedule.indexLead")} today={null} date={null} onDate={() => undefined} updatedAt={q.dataUpdatedAt || undefined}>
      {q.isLoading ? <Loading /> : null}
      {q.isError ? <PublicError error={q.error} /> : null}
      {q.data && !q.data.buildings.length ? <p className="type-title-3 font-normal text-label-2">{t("publicSchedule.noRooms")}</p> : null}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" data-testid="public-index">
        {q.data?.buildings.map((b) => (
          <Card key={b.code} className="gap-3 px-4 py-4">
            <Link href={`/public/buildings/${encodeURIComponent(b.code)}`} className="type-title-2 text-label-1 underline-offset-4 hover:underline" data-testid={`public-building-${b.code}`}>
              {b.name}
            </Link>
            <ul className="flex flex-wrap gap-2">
              {b.rooms.map((r) => (
                <li key={r.code}>
                  <Link href={`/public/rooms/${encodeURIComponent(r.code)}`} className="inline-flex min-h-11 items-center rounded-full bg-fill-2 px-3 type-headline text-label-1 hover:bg-fill-1" data-testid={`public-room-link-${r.code}`}>
                    {r.name}
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </KioskFrame>
  );
}

export function PublicRoomView({ code }: { code: string }) {
  const { t, locale } = useI18n();
  const label = (it: PublicItem) => (locale === "tr" ? it.label.tr : it.label.en);
  const [date, setDate] = useKioskDate();
  const q = usePublicRoom(code, date);
  const today = useBackendToday("room", code, date, q.data?.date);
  const clock = useClock();
  if (q.isError && isNotFound(q.error)) return <PublicNotFound />;
  const d = q.data;
  const live = !!d && d.date === clock.iso;
  const now = d && live ? currentItem(d.items, clock.hhmm) : null;
  const next = d && live ? nextItem(d.items, clock.hhmm) : null;
  return (
    <KioskFrame
      title={d?.room.name ?? code}
      subtitle={d ? [d.room.capacity ? t("publicSchedule.seats", { n: d.room.capacity }) : null].filter(Boolean).join(" · ") || undefined : undefined}
      back={d?.room.building ? { href: `/public/buildings/${encodeURIComponent(d.room.building)}`, label: t("publicSchedule.building", { code: d.room.building }) } : { href: "/public", label: t("publicSchedule.allRooms") }}
      today={today}
      date={date}
      onDate={setDate}
      updatedAt={q.dataUpdatedAt || undefined}
    >
      {q.isLoading ? <Loading /> : null}
      {q.isError ? <PublicError error={q.error} /> : null}
      {d ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          {live ? (
            <Card className="gap-2 px-5 py-5" data-testid="public-now">
              <p className="type-headline text-label-2">{t("publicSchedule.nowTitle")}</p>
              <p className="type-title-1 text-label-1">{now ? label(now) : t("publicSchedule.free")}</p>
              {now ? <p className="type-title-3 font-normal text-label-2 tabular-nums">{now.start}–{now.end}</p> : null}
              <p className="mt-2 type-headline text-label-2">{t("publicSchedule.nextTitle")}</p>
              <p className="type-title-3 text-label-1">{next ? `${next.start} · ${label(next)}` : t("publicSchedule.nothingNext")}</p>
            </Card>
          ) : null}
          <section aria-label={t("publicSchedule.dayList")} className={live ? undefined : "lg:col-span-2"} data-testid="public-room-items">
            <ItemList items={d.items} live={live} hhmm={clock.hhmm} large emptyText={t("publicSchedule.emptyRoom")} slotDisplay={d.slot_display} />
          </section>
        </div>
      ) : null}
    </KioskFrame>
  );
}

export function PublicBuildingView({ code }: { code: string }) {
  const { t, locale } = useI18n();
  const [date, setDate] = useKioskDate();
  const q = usePublicBuilding(code, date);
  const today = useBackendToday("building", code, date, q.data?.date);
  const clock = useClock();
  if (q.isError && isNotFound(q.error)) return <PublicNotFound />;
  const d = q.data;
  const live = !!d && d.date === clock.iso;
  const lbl = (it: PublicItem) => (locale === "tr" ? it.label.tr : it.label.en);
  return (
    <KioskFrame title={d?.building.name ?? code} back={{ href: "/public", label: t("publicSchedule.allRooms") }} today={today} date={date} onDate={setDate} updatedAt={q.dataUpdatedAt || undefined}>
      {q.isLoading ? <Loading /> : null}
      {q.isError ? <PublicError error={q.error} /> : null}
      {d && !d.rooms.length ? <p className="type-title-3 font-normal text-label-2">{t("publicSchedule.noRooms")}</p> : null}
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4" data-testid="public-building-rooms">
        {d?.rooms.map((r) => {
          const now = live ? currentItem(r.items, clock.hhmm) : null;
          const next = live ? nextItem(r.items, clock.hhmm) : null;
          return (
            <li key={r.code}>
              <Card className="h-full gap-3 px-4 py-4" data-testid={`public-room-${r.code}`}>
                <div className="flex items-baseline justify-between gap-2">
                  <Link href={`/public/rooms/${encodeURIComponent(r.code)}${date ? `?date=${date}` : ""}`} className={`relative type-title-2 text-label-1 underline-offset-4 hover:underline ${coarseHitArea}`}>
                    {r.name}
                  </Link>
                  {r.capacity ? <span className="type-footnote text-label-3">{t("publicSchedule.seats", { n: r.capacity })}</span> : null}
                </div>
                {live ? (
                  <p className="type-headline text-label-1">
                    {now ? t("publicSchedule.nowLine", { what: lbl(now), until: now.end }) : t("publicSchedule.freeNow")}
                    {next ? <span className="block type-callout font-normal text-label-2">{t("publicSchedule.nextLine", { time: next.start, what: lbl(next) })}</span> : null}
                  </p>
                ) : null}
                <ItemList items={r.items} live={live} hhmm={clock.hhmm} emptyText={t("publicSchedule.emptyRoomShort")} slotDisplay={d.slot_display} />
              </Card>
            </li>
          );
        })}
      </ul>
    </KioskFrame>
  );
}
