"use client";
/**
 * /rooms (Liquid Glass v2): every room (also closed and ungrouped ones; this is the catalogue, not the
 * booking grid), grouped by building with the section heading on the scene, a glass capsule for search /
 * building / tags / seats / sort / layout, and the week's occupancy from the calendar index of the term's
 * working run (one fetch, shared with /timetable). Cards or a plain table; both link to the room detail.
 */
import { ChevronLeft, ChevronRight, LayoutGrid, Search, TableProperties, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { Skeleton } from "@/components/ui/skeleton";
import { useCalendarData } from "@/components/timetable/use-calendar-data";
import { fold } from "@/components/timetable/model/filters";
import { useBuildings, useRooms } from "@/lib/api/hooks";
import type { Room, RoomTag } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { RoomCard, RoomVisual, floorText, nowLine, tagWords } from "./room-card";
import { heldAt, roomWeek, weekShare, type RoomWeek } from "./room-occupancy";
import { defaultWeek, useRunNow } from "./use-room-week";

const TAGS: RoomTag[] = ["PC", "LAB", "AMPHI", "TIP"];
const SEAT_STEPS = [0, 30, 60, 100, 150] as const;
type Sort = "code" | "capacity" | "busy" | "free";

export function RoomsView() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const layout = params.get("layout") === "table" ? "table" : "cards";
  const building = params.get("building") ?? "";
  const tagsParam = params.get("tags") ?? "";
  const tags = useMemo(() => tagsParam.split(",").filter(Boolean) as RoomTag[], [tagsParam]);
  const minSeats = Number(params.get("seats") ?? 0) || 0;
  const q = params.get("q") ?? "";
  const sort = (["code", "capacity", "busy", "free"].includes(params.get("sort") ?? "") ? params.get("sort") : "code") as Sort;
  const requestedWeek = Number(params.get("week") ?? "") || null;

  const rooms = useRooms();
  const buildings = useBuildings();
  const cal = useCalendarData(Number(params.get("run") ?? "") || null);
  const now = useRunNow(cal.model);
  const week = defaultWeek(cal.model, now, requestedWeek);
  const weekList = cal.model?.weeks ?? [];

  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    router.replace(`/rooms${next.size ? `?${next.toString()}` : ""}`, { scroll: false });
  };

  const grids = useMemo(() => {
    const out = new Map<number, RoomWeek>();
    if (!cal.model || week === null) return out;
    for (const r of rooms.data ?? []) out.set(r.id, roomWeek(cal.model, r.id, week));
    return out;
  }, [cal.model, week, rooms.data]);

  const list = useMemo(() => {
    const needle = fold(q);
    const filtered = (rooms.data ?? []).filter(
      (r) =>
        (!building || r.building_code === building) &&
        tags.every((tg) => r.tags.includes(tg)) &&
        r.capacity >= minSeats &&
        (!needle || fold(`${r.display_name} ${r.code} ${r.tags.join(" ")} ${r.capacity} ${r.notes ?? ""}`).includes(needle)),
    );
    const share = (r: Room) => {
      const g = grids.get(r.id);
      return g ? weekShare(g) : 0;
    };
    const byCode = (a: Room, b: Room) => a.display_name.localeCompare(b.display_name, "tr", { numeric: true });
    return filtered.sort((a, b) =>
      sort === "capacity" ? b.capacity - a.capacity || byCode(a, b) : sort === "busy" ? share(b) - share(a) || byCode(a, b) : sort === "free" ? share(a) - share(b) || byCode(a, b) : byCode(a, b),
    );
  }, [rooms.data, building, tags, minSeats, q, sort, grids]);

  const groups = useMemo(() => {
    if (sort !== "code") return [{ key: "all", label: null as string | null, rooms: list }];
    const map = new Map<string, Room[]>();
    for (const r of list) map.set(r.building_code, [...(map.get(r.building_code) ?? []), r]);
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b, "tr")).map(([key, rs]) => ({ key, label: t("roomsV2.building", { b: key }), rooms: rs }));
  }, [list, sort, t]);

  const href = (r: Room) => `/rooms/${r.id}${week !== null ? `?week=${week}` : ""}${cal.runId && params.get("run") ? `${week !== null ? "&" : "?"}run=${cal.runId}` : ""}`;
  const nowFor = (r: Room) => {
    if (!now || week !== now.week) return undefined;
    const g = grids.get(r.id);
    return g ? heldAt(g, now.day, now.period) : undefined;
  };
  const filtersOn = !!(building || tags.length || minSeats || q);
  const total = rooms.data?.length ?? 0;
  const weekIdx = week !== null ? weekList.indexOf(week) : -1;

  return (
    <div className="flex flex-col gap-4" data-testid="rooms">
      <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
        <div className="flex flex-col gap-0.5">
          <h1 className="type-title-2">{t("roomsV2.title")}</h1>
          <p className="text-[13px] text-label-2 tabular-nums">
            {rooms.data ? t("roomsV2.subtitle", { n: total, b: buildings.data?.length ?? new Set(rooms.data.map((r) => r.building_code)).size }) : " "}
            {cal.runId ? ` · ${t("roomsV2.run", { run: cal.runId })}` : ""}
          </p>
        </div>
        {week !== null && weekList.length ? (
          <div className="ml-auto flex items-center gap-1" role="group" aria-label={t("roomsV2.week")}>
            <Button variant="ghost" size="icon-sm" aria-label={t("roomsV2.prevWeek")} disabled={weekIdx <= 0} onClick={() => set({ week: String(weekList[weekIdx - 1]) })}><ChevronLeft /></Button>
            <span className="min-w-20 text-center text-[13px] font-semibold tabular-nums" aria-live="polite" data-testid="rooms-week">{t("roomsV2.weekLabel", { w: week })}</span>
            <Button variant="ghost" size="icon-sm" aria-label={t("roomsV2.nextWeek")} disabled={weekIdx < 0 || weekIdx >= weekList.length - 1} onClick={() => set({ week: String(weekList[weekIdx + 1]) })}><ChevronRight /></Button>
          </div>
        ) : null}
      </div>

      {/* one glass capsule over the scene: search, building, tags, seats, sort, layout */}
      <div className="glass-chrome flex flex-wrap items-center gap-2 rounded-[22px] p-1.5">
        <label className="flex h-8 min-w-0 flex-1 basis-56 items-center gap-2 rounded-full bg-fill-3 px-3 text-[13px]">
          <Search aria-hidden className="size-4 shrink-0 text-label-2" />
          <input
            value={q}
            onChange={(e) => set({ q: e.target.value })}
            placeholder={t("roomsV2.search")}
            aria-label={t("roomsV2.search")}
            className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-label-3"
            data-testid="rooms-search"
          />
          {q ? <button type="button" aria-label={t("roomsV2.clearFilters")} onClick={() => set({ q: null })} className="text-label-2 hover:text-label-1"><X className="size-3.5" /></button> : null}
        </label>
        <SegmentedGlass
          size="sm"
          aria-label={t("common.building")}
          value={building || "all"}
          onValueChange={(v) => set({ building: v === "all" ? null : v })}
          options={[{ value: "all", label: t("roomsV2.allBuildings") }, ...[...new Set((rooms.data ?? []).map((r) => r.building_code))].sort().map((b) => ({ value: b, label: b }))]}
        />
        <span className="flex flex-wrap items-center gap-1" role="group" aria-label={t("roomsV2.tags")}>
          {TAGS.map((tg) => (
            <Chip key={tg} size="sm" selected={tags.includes(tg)} onSelectedChange={(on) => set({ tags: (on ? [...tags, tg] : tags.filter((x) => x !== tg)).join(",") || null })}>
              {tagWords({ tags: [tg] }, t)[0]}
            </Chip>
          ))}
        </span>
        <label className="flex items-center gap-1.5 text-[12px] text-label-2">
          {t("roomsV2.minCapacity")}
          <select value={minSeats} onChange={(e) => set({ seats: e.target.value === "0" ? null : e.target.value })} className="h-7 rounded-full bg-fill-2 px-2 text-[12px] text-label-1" data-testid="rooms-seats">
            {SEAT_STEPS.map((s) => <option key={s} value={s}>{s === 0 ? t("roomsV2.any") : `≥ ${s}`}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-[12px] text-label-2">
          {t("roomsV2.sort")}
          <select value={sort} onChange={(e) => set({ sort: e.target.value === "code" ? null : e.target.value })} className="h-7 rounded-full bg-fill-2 px-2 text-[12px] text-label-1">
            <option value="code">{t("roomsV2.sortCode")}</option>
            <option value="capacity">{t("roomsV2.sortCapacity")}</option>
            <option value="busy" disabled={!cal.model}>{t("roomsV2.sortBusy")}</option>
            <option value="free" disabled={!cal.model}>{t("roomsV2.sortFree")}</option>
          </select>
        </label>
        <SegmentedGlass
          size="sm"
          className="ml-auto"
          aria-label={t("roomsV2.viewMode")}
          value={layout}
          onValueChange={(v) => set({ layout: v === "table" ? "table" : null })}
          options={[
            { value: "cards", label: <span className="flex items-center gap-1"><LayoutGrid className="size-3.5" aria-hidden /><span className="max-sm:sr-only">{t("roomsV2.cards")}</span></span> },
            { value: "table", label: <span className="flex items-center gap-1"><TableProperties className="size-3.5" aria-hidden /><span className="max-sm:sr-only">{t("roomsV2.table")}</span></span> },
          ]}
        />
      </div>

      <p className="text-[12px] text-label-2 tabular-nums" role="status">
        {t("roomsV2.count", { shown: list.length, total })}
        {cal.noRun ? ` · ${t("roomsV2.noRun")}` : ""}
      </p>

      {rooms.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 3xl:grid-cols-6">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-[132px] rounded-2xl" />)}</div>
      ) : list.length === 0 ? (
        <div className="flex flex-col items-start gap-2 py-8">
          <p className="text-[15px]">{t("roomsV2.noMatch")}</p>
          {filtersOn ? <Button variant="outline" size="sm" onClick={() => set({ building: null, tags: null, seats: null, q: null })}>{t("roomsV2.clearFilters")}</Button> : null}
        </div>
      ) : layout === "cards" ? (
        <div className="flex flex-col gap-6">
          {groups.map((g) => {
            const avg = g.rooms.length && cal.model ? Math.round((g.rooms.reduce((s, r) => s + (grids.get(r.id) ? weekShare(grids.get(r.id) as RoomWeek) : 0), 0) / g.rooms.length) * 100) : null;
            return (
              <section key={g.key} aria-labelledby={g.label ? `bld-${g.key}` : undefined} className="flex flex-col gap-2">
                {g.label ? (
                  <h2 id={`bld-${g.key}`} className="flex items-baseline gap-2">
                    <span className="type-title-3">{g.label}</span>
                    <span className="text-[13px] text-label-2 tabular-nums">{avg !== null ? t("roomsV2.buildingSummary", { n: g.rooms.length, p: avg }) : t("roomsV2.count", { shown: g.rooms.length, total: g.rooms.length })}</span>
                  </h2>
                ) : null}
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 3xl:grid-cols-6">
                  {g.rooms.map((r) => <RoomCard key={r.id} room={r} grid={grids.get(r.id) ?? null} week={week} now={nowFor(r)} href={href(r)} />)}
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <Card variant="plain" className="overflow-x-auto p-0">
          <table className="w-full min-w-[760px] text-[13px]" data-testid="rooms-table">
            <thead>
              <tr className="hairline-b text-left text-[12px] text-label-2">
                <th scope="col" className="py-2 pr-2 pl-4 font-semibold">{t("roomsV2.code")}</th>
                <th scope="col" className="px-2 font-semibold">{t("roomsV2.floor")}</th>
                <th scope="col" className="px-2 text-right font-semibold">{t("roomsV2.capacity")}</th>
                <th scope="col" className="px-2 text-right font-semibold">{t("roomsV2.examCapacity")}</th>
                <th scope="col" className="px-2 font-semibold">{t("roomsV2.tags")}</th>
                <th scope="col" className="px-2 font-semibold">{t("roomsV2.bookable")}</th>
                <th scope="col" className="px-2 text-right font-semibold">{week !== null ? t("roomsV2.weekCol", { w: week }) : "—"}</th>
                <th scope="col" className="py-2 pr-4 pl-2 font-semibold">{t("roomsV2.nowCol")}</th>
              </tr>
            </thead>
            <tbody>
              {list.map((r) => {
                const g = grids.get(r.id);
                const n = nowFor(r);
                return (
                  <tr key={r.id} className="hairline-b hover:bg-fill-3" data-testid="room-row">
                    <td className="py-1.5 pr-2 pl-4">
                      <Link href={href(r)} className="flex items-center gap-2 font-semibold hover:underline">
                        <RoomVisual room={r} variant="tile" className="size-7 rounded-md [&>span:first-child]:hidden [&>span:last-child]:mt-0 [&>span:last-child]:text-[11px]" />
                        {r.display_name}
                      </Link>
                    </td>
                    <td className="px-2 text-label-2">{floorText(r.floor, t) ?? "—"}</td>
                    <td className="px-2 text-right tabular-nums">{r.capacity}</td>
                    <td className="px-2 text-right tabular-nums">{r.exam_capacity}</td>
                    <td className="px-2 text-label-2">{tagWords(r, t).join(" · ") || "—"}</td>
                    <td className="px-2">{r.is_bookable ? <span className="text-label-2">{t("common.yes")}</span> : <Badge variant="secondary" tone="preoccupied">{t("roomsV2.notBookable")}</Badge>}</td>
                    <td className="px-2 text-right tabular-nums">{g ? t("roomsV2.occupancyShort", { p: Math.round(weekShare(g) * 100) }) : "—"}</td>
                    <td className={cn("py-1.5 pr-4 pl-2", n === null && "text-status-feasible-fg")}>{n !== undefined ? nowLine(n, t) : <span className="text-label-3">—</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
