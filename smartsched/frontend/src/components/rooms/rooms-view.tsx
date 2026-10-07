"use client";

import { LayoutGrid, Search, TableProperties } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useBuildings, useRooms } from "@/lib/api/hooks";
import type { RoomTag } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { RoomCard } from "./room-card";
import { useRoomOccupancy } from "./use-room-occupancy";

const TAGS: RoomTag[] = ["TIP", "PC", "LAB", "AMPHI"];

function fold(s: string): string {
  return s.toLocaleLowerCase("tr-TR").replace(/ı/g, "i").replace(/ş/g, "s").replace(/ğ/g, "g").replace(/ç/g, "c").replace(/ö/g, "o").replace(/ü/g, "u").replace(/\s+/g, "");
}

export function RoomsView() {
  const { t, n } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const view = params.get("view") === "table" ? "table" : "cards";
  const building = params.get("building") ?? "";
  const tag = params.get("tag") ?? "";
  const q = params.get("q") ?? "";
  const rooms = useRooms();
  const buildings = useBuildings();
  const occ = useRoomOccupancy(7);

  const set = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    router.replace(`/rooms?${next.toString()}`);
  };

  const list = useMemo(() => {
    const needle = fold(q);
    return (rooms.data ?? []).filter((r) => (!building || r.building_code === building) && (!tag || r.tags.includes(tag as RoomTag)) && (!needle || fold(`${r.display_name} ${r.code} ${r.tags.join(" ")} ${r.capacity}`).includes(needle)));
  }, [rooms.data, building, tag, q]);

  return (
    <div data-testid="rooms">
      <PageHeader title={t("rooms.title")} subtitle={rooms.data ? t("rooms.subtitle", { count: n(rooms.data.length), buildings: buildings.data?.length ?? 4 }) : undefined} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input aria-label={t("common.search")} placeholder={t("rooms.searchPlaceholder")} value={q} onChange={(e) => set({ q: e.target.value })} className="pl-8" />
        </div>
        <div role="group" aria-label={t("common.building")} className="flex flex-wrap gap-1">
          <button type="button" aria-pressed={!building} onClick={() => set({ building: "" })} className={cn("rounded-full border px-2.5 py-1 text-xs", !building ? "bg-primary text-primary-foreground" : "hover:bg-accent")}>{t("rooms.allBuildings")}</button>
          {(buildings.data ?? []).map((b) => (
            <button key={b.id} type="button" aria-pressed={building === b.code} onClick={() => set({ building: building === b.code ? "" : b.code })} className={cn("rounded-full border px-2.5 py-1 text-xs", building === b.code ? "bg-primary text-primary-foreground" : "hover:bg-accent")}>{b.code}</button>
          ))}
        </div>
        <div role="group" aria-label={t("rooms.tags")} className="flex flex-wrap gap-1">
          {TAGS.map((tg) => (
            <button key={tg} type="button" aria-pressed={tag === tg} onClick={() => set({ tag: tag === tg ? "" : tg })} className={cn("rounded-full border px-2.5 py-1 text-xs", tag === tg ? "bg-primary text-primary-foreground" : "hover:bg-accent")}>{tg}</button>
          ))}
        </div>
        <div role="radiogroup" aria-label="View" className="ml-auto inline-flex rounded-md border p-0.5">
          <button type="button" role="radio" aria-checked={view === "cards"} aria-label={t("rooms.cards")} onClick={() => set({ view: "" })} className={cn("rounded-sm p-1.5", view === "cards" ? "bg-primary text-primary-foreground" : "text-muted-foreground")}><LayoutGrid className="size-4" /></button>
          <button type="button" role="radio" aria-checked={view === "table"} aria-label={t("rooms.table")} onClick={() => set({ view: "table" })} className={cn("rounded-sm p-1.5", view === "table" ? "bg-primary text-primary-foreground" : "text-muted-foreground")}><TableProperties className="size-4" /></button>
        </div>
      </div>
      <p className="mb-2 text-xs text-muted-foreground">{t("common.showing", { count: n(list.length), total: n(rooms.data?.length ?? 0) })}</p>
      {rooms.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="aspect-[4/5] rounded-xl" />)}</div>
      ) : view === "cards" ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
          {list.map((r) => <RoomCard key={r.id} room={r} occupancy={occ.data?.byRoom.get(r.id)} selectedDay={3} />)}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("rooms.code")}</TableHead>
                <TableHead>{t("common.building")}</TableHead>
                <TableHead>{t("rooms.floor")}</TableHead>
                <TableHead className="text-right">{t("common.capacity")}</TableHead>
                <TableHead className="text-right">{t("rooms.examCapacity")}</TableHead>
                <TableHead>{t("rooms.tags")}</TableHead>
                <TableHead>{t("rooms.bookable")}</TableHead>
                <TableHead className="text-right">{t("rooms.utilisation")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((r) => (
                <TableRow key={r.id}>
                  <TableCell><Link href={`/rooms/${r.id}`} className="font-mono font-medium hover:underline">{r.display_name}</Link></TableCell>
                  <TableCell>{r.building_code}</TableCell>
                  <TableCell>{r.floor === 0 ? "Z" : (r.floor ?? "—")}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.capacity}</TableCell>
                  <TableCell className="text-right tabular-nums">{r.exam_capacity}</TableCell>
                  <TableCell className="space-x-1">{r.tags.map((tg) => (tg === "TIP" ? <StatusBadge key={tg} kind="tip" label="TIP" /> : tg === "PC" ? <StatusBadge key={tg} kind="pclab" label="PC" /> : <Badge key={tg} variant="outline">{tg}</Badge>))}</TableCell>
                  <TableCell>{r.is_bookable ? t("common.yes") : t("common.no")}</TableCell>
                  <TableCell className="text-right tabular-nums">{Math.round((r.utilisation ?? 0) * 100)}%</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
