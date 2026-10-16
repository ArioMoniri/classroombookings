"use client";
/**
 * /rooms (Liquid Glass v2): every room (also closed and ungrouped ones; this is the catalogue, not the
 * booking grid) and the week's occupancy from the calendar index of the term's working run (one fetch, shared
 * with /timetable). Design-system overhaul 2026-10-15 (review §3 Rooms): the default view is a TABLE on the
 * column system (code, building, seats, exam seats, tags, % use bar, now; resizable, per-user persisted),
 * because 87 identical cards read as a template (Airtable grid, Linear H4); cards stay optional and lose the
 * avatar circle. One toolbar row: field-styled search, building / seats / sort selects, tag chips and the
 * layout switch, all on --control-h-sm.
 */
import { ChevronLeft, ChevronRight, LayoutGrid, Search, TableProperties, X } from "lucide-react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { PageHeader } from "@/components/common/page-header";
import { Button, IconButton } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { DataTable, StatusDot, type DataColumn } from "@/components/ui/data-table";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { useCalendarData } from "@/components/timetable/use-calendar-data";
import { fold } from "@/components/timetable/model/filters";
import { useBuildings, useMe, useRooms } from "@/lib/api/hooks";
import type { Room, RoomTag } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { RoomCard, floorText, nowLine, tagWords } from "./room-card";
import { heldAt, roomWeek, weekShare, type RoomWeek } from "./room-occupancy";
import { defaultWeek, useRunNow } from "./use-room-week";

const TAGS: RoomTag[] = ["PC", "LAB", "AMPHI", "TIP"];
const SEAT_STEPS = [0, 30, 60, 100, 150] as const;
type Sort = "code" | "capacity" | "busy" | "free";

export function RoomsView() {
  const { t } = useI18n();
  const router = useRouter();
  const me = useMe();
  const params = useSearchParams();
  const layout = params.get("layout") === "cards" ? "cards" : "table";
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
    // native history: syncs useSearchParams without an RSC round trip per keystroke
    window.history.replaceState(null, "", `/rooms${next.size ? `?${next.toString()}` : ""}`);
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

  const buildingCodes = [...new Set((rooms.data ?? []).map((r) => r.building_code))].sort((a, b) => a.localeCompare(b, "tr"));
  const share = (r: Room) => {
    const g = grids.get(r.id);
    return g ? Math.round(weekShare(g) * 100) : null;
  };
  const columns: DataColumn<Room>[] = [
    {
      id: "code",
      header: t("roomsV2.code"),
      pin: "left",
      priority: 1,
      minSize: 88,
      text: (r) => r.display_name,
      sortValue: (r) => r.display_name,
      cell: (r) => (
        <Link href={href(r)} onClick={(e) => e.stopPropagation()} className="truncate font-semibold hover:underline focus-visible:outline-2 focus-visible:outline-(--focus)">
          {r.display_name}
        </Link>
      ),
    },
    { id: "building", header: t("common.building"), priority: 3, minSize: 72, text: (r) => t("roomsV2.building", { b: r.building_code }), sortValue: (r) => r.building_code, cell: (r) => <span className="truncate text-label-2">{t("roomsV2.building", { b: r.building_code })}</span> },
    { id: "floor", header: t("roomsV2.floor"), priority: 5, text: (r) => floorText(r.floor, t) ?? "—", sortValue: (r) => r.floor ?? -99, cell: (r) => <span className="truncate text-label-2">{floorText(r.floor, t) ?? "—"}</span> },
    { id: "capacity", header: t("roomsV2.capacity"), align: "end", priority: 1, text: (r) => String(r.capacity), sortValue: (r) => r.capacity, cell: (r) => <span data-numeric>{r.capacity}</span> },
    { id: "exam", header: t("roomsV2.examCapacity"), align: "end", priority: 3, text: (r) => String(r.exam_capacity), sortValue: (r) => r.exam_capacity, cell: (r) => <span data-numeric>{r.exam_capacity}</span> },
    { id: "tags", header: t("roomsV2.tags"), priority: 2, grow: 1, maxSize: 320, text: (r) => tagWords(r, t).join(" · "), cell: (r) => <span className="truncate text-label-2">{tagWords(r, t).join(" · ") || "—"}</span> },
    {
      id: "bookable",
      header: t("roomsV2.bookable"),
      priority: 4,
      text: (r) => (r.is_bookable ? t("common.yes") : t("roomsV2.notBookable")),
      extra: 16,
      sortValue: (r) => (r.is_bookable ? 1 : 0),
      cell: (r) => (r.is_bookable ? <span className="text-label-2">{t("common.yes")}</span> : <StatusDot tone="neutral">{t("roomsV2.notBookable")}</StatusDot>),
    },
    {
      id: "use",
      header: week !== null ? t("roomsV2.weekCol", { w: week }) : t("roomsV2.weekly"),
      priority: 2,
      minSize: 120,
      size: 148,
      sortValue: (r) => share(r) ?? -1,
      cell: (r) => {
        const p = share(r);
        if (p === null) return <span className="text-label-3">—</span>;
        return (
          <span className="flex w-full items-center gap-2" title={t("roomsV2.occupancy", { p, w: week ?? 0 })}>
            <span aria-hidden className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-fill-2">
              <span className="block h-full rounded-full bg-label-2" style={{ width: `${p}%` }} />
            </span>
            <span className="w-10 shrink-0 text-right tnum" data-numeric>{t("roomsV2.occupancyShort", { p })}</span>
          </span>
        );
      },
    },
    {
      id: "now",
      header: t("roomsV2.nowCol"),
      priority: 3,
      grow: 1,
      maxSize: 360,
      cell: (r) => {
        const n = nowFor(r);
        return n !== undefined ? <span className={cn("truncate", n === null && "text-status-feasible-fg")}>{nowLine(n, t)}</span> : <span className="text-label-3">—</span>;
      },
    },
  ];

  const toolbar = (
    <div role="toolbar" aria-label={t("roomsV2.title")} className="flex w-full flex-wrap items-center gap-2 [--control-h-md:var(--control-h-sm)]">
      <InputGroup className="w-auto min-w-48 flex-1 basis-56">
        <InputGroupAddon><Search aria-hidden /></InputGroupAddon>
        <InputGroupInput value={q} onChange={(e) => set({ q: e.target.value })} placeholder={t("roomsV2.search")} aria-label={t("roomsV2.search")} data-testid="rooms-search" />
        {q ? (
          <InputGroupAddon align="inline-end">
            <IconButton label={t("roomsV2.clearFilters")} size="xs" onClick={() => set({ q: null })}><X aria-hidden /></IconButton>
          </InputGroupAddon>
        ) : null}
      </InputGroup>
      <NativeSelect selectClassName="max-md:pointer-coarse:text-base" size="sm" className="w-auto min-w-32" aria-label={t("common.building")} value={building} onChange={(e) => set({ building: e.target.value || null })} data-testid="rooms-building">
        <option value="">{`${t("common.building")}: ${t("roomsV2.allBuildings")}`}</option>
        {buildingCodes.map((b) => <option key={b} value={b}>{t("roomsV2.building", { b })}</option>)}
      </NativeSelect>
      <span className="flex flex-wrap items-center gap-1" role="group" aria-label={t("roomsV2.tags")}>
        {TAGS.map((tg) => (
          <Chip key={tg} size="sm" selected={tags.includes(tg)} onSelectedChange={(on) => set({ tags: (on ? [...tags, tg] : tags.filter((x) => x !== tg)).join(",") || null })}>
            {tagWords({ tags: [tg] }, t)[0]}
          </Chip>
        ))}
      </span>
      <NativeSelect selectClassName="max-md:pointer-coarse:text-base" size="sm" className="w-auto min-w-32" aria-label={t("roomsV2.minCapacity")} value={String(minSeats)} onChange={(e) => set({ seats: e.target.value === "0" ? null : e.target.value })} data-testid="rooms-seats">
        {SEAT_STEPS.map((s) => <option key={s} value={s}>{s === 0 ? `${t("roomsV2.minCapacity")}: ${t("roomsV2.any")}` : `${t("roomsV2.minCapacity")} ≥ ${s}`}</option>)}
      </NativeSelect>
      {layout === "cards" ? (
        <NativeSelect selectClassName="max-md:pointer-coarse:text-base" size="sm" className="w-auto min-w-36" aria-label={t("roomsV2.sort")} value={sort} onChange={(e) => set({ sort: e.target.value === "code" ? null : e.target.value })}>
          <option value="code">{t("roomsV2.sortCode")}</option>
          <option value="capacity">{t("roomsV2.sortCapacity")}</option>
          <option value="busy" disabled={!cal.model}>{t("roomsV2.sortBusy")}</option>
          <option value="free" disabled={!cal.model}>{t("roomsV2.sortFree")}</option>
        </NativeSelect>
      ) : null}
      <SegmentedControl
        size="sm"
        className="ml-auto"
        aria-label={t("roomsV2.viewMode")}
        value={layout}
        onValueChange={(v) => set({ layout: v === "cards" ? "cards" : null })}
        options={[
          { value: "table", text: t("roomsV2.table"), label: <><TableProperties aria-hidden />{t("roomsV2.table")}</> },
          { value: "cards", text: t("roomsV2.cards"), label: <><LayoutGrid aria-hidden />{t("roomsV2.cards")}</> },
        ]}
      />
    </div>
  );

  return (
    <div className="flex flex-col gap-4" data-testid="rooms">
      <PageHeader
        className="mb-0 lg:mb-0"
        title={t("roomsV2.title")}
        subtitle={
          <span className="tnum">
            {rooms.data ? t("roomsV2.subtitle", { n: total, b: buildings.data?.length ?? new Set(rooms.data.map((r) => r.building_code)).size }) : <Skeleton className="inline-block h-3.5 w-40 align-middle" />}
            {cal.runId ? ` · ${t("roomsV2.run", { run: cal.runId })}` : ""}
          </span>
        }
        actions={
          week !== null && weekList.length ? (
            <div className="flex items-center gap-1" role="group" aria-label={t("roomsV2.week")}>
              <IconButton label={t("roomsV2.prevWeek")} size="sm" className="pointer-coarse:size-11" disabled={weekIdx <= 0} onClick={() => set({ week: String(weekList[weekIdx - 1]) })}><ChevronLeft aria-hidden /></IconButton>
              <span className="min-w-20 text-center type-callout font-semibold tnum" aria-live="polite" data-testid="rooms-week">{t("roomsV2.weekLabel", { w: week })}</span>
              <IconButton label={t("roomsV2.nextWeek")} size="sm" className="pointer-coarse:size-11" disabled={weekIdx < 0 || weekIdx >= weekList.length - 1} onClick={() => set({ week: String(weekList[weekIdx + 1]) })}><ChevronRight aria-hidden /></IconButton>
            </div>
          ) : null
        }
      />

      {layout === "table" ? (
        <DataTable
          tableId="rooms"
          userId={me.data?.id}
          label={t("roomsV2.title")}
          columns={columns}
          rows={rooms.isLoading ? undefined : list}
          getRowId={(r) => String(r.id)}
          onRowActivate={(r) => router.push(href(r))}
          rowProps={(r) => ({ "data-testid": "room-row", "data-room-id": String(r.id) })}
          data-testid="rooms-table"
          toolbar={toolbar}
          empty={
            <span className="flex flex-col items-start gap-2">
              {t("roomsV2.noMatch")}
              {filtersOn ? <Button variant="outline" size="sm" onClick={() => set({ building: null, tags: null, seats: null, q: null })}>{t("roomsV2.clearFilters")}</Button> : null}
            </span>
          }
        />
      ) : (
        <>
          {toolbar}
          <p className="type-footnote text-label-2 tnum" role="status">
            {rooms.data ? t("roomsV2.count", { shown: list.length, total }) : null}
            {cal.noRun ? ` · ${t("roomsV2.noRun")}` : ""}
          </p>
          {rooms.isLoading ? (
            <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(15rem,1fr))]">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-[120px] rounded-xl" />)}</div>
          ) : list.length === 0 ? (
            <div className="flex flex-col items-start gap-2 py-8">
              <p className="type-headline">{t("roomsV2.noMatch")}</p>
              {filtersOn ? <Button variant="outline" size="sm" onClick={() => set({ building: null, tags: null, seats: null, q: null })}>{t("roomsV2.clearFilters")}</Button> : null}
            </div>
          ) : (
            <div className="flex flex-col gap-6">
              {groups.map((g) => {
                const avg = g.rooms.length && cal.model ? Math.round((g.rooms.reduce((s, r) => s + (grids.get(r.id) ? weekShare(grids.get(r.id) as RoomWeek) : 0), 0) / g.rooms.length) * 100) : null;
                return (
                  <section key={g.key} aria-labelledby={g.label ? `bld-${g.key}` : undefined} className="flex flex-col gap-2">
                    {g.label ? (
                      <h2 id={`bld-${g.key}`} className="flex items-baseline gap-2">
                        <span className="type-title-3">{g.label}</span>
                        <span className="type-callout text-label-2 tnum">{avg !== null ? t("roomsV2.buildingSummary", { n: g.rooms.length, p: avg }) : t("roomsV2.count", { shown: g.rooms.length, total: g.rooms.length })}</span>
                      </h2>
                    ) : null}
                    <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(15rem,1fr))]">
                      {g.rooms.map((r) => <RoomCard key={r.id} room={r} grid={grids.get(r.id) ?? null} week={week} now={nowFor(r)} href={href(r)} />)}
                    </div>
                  </section>
                );
              })}
            </div>
          )}
        </>
      )}
      {layout === "table" && cal.noRun ? <p className="type-footnote text-label-2">{t("roomsV2.noRun")}</p> : null}
    </div>
  );
}
