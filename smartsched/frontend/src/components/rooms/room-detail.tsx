"use client";

import { ArrowLeft, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useRoom } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS, dayName, periodRangeLabel } from "@/lib/time";
import { cn } from "@/lib/utils";
import { RoomPhoto } from "./room-card";
import { SparklineBars } from "./sparkline-bars";
import { useRoomOccupancy } from "./use-room-occupancy";

export function RoomDetail({ id }: { id: number }) {
  const { t, locale } = useI18n();
  const room = useRoom(id);
  const [week, setWeek] = useState(7);
  const occ = useRoomOccupancy(week);
  const r = room.data;
  if (room.isError) return <p className="text-muted-foreground">{t("rooms.notFound")}</p>;
  if (!r) return <Skeleton className="h-64 rounded-xl" />;
  const mine = occ.data?.assignments.filter((a) => a.room_ids.includes(r.id)) ?? [];
  const myBlocks = occ.data?.blocks.filter((b) => b.room_id === r.id) ?? [];
  return (
    <div data-testid="room-detail">
      <Link href="/rooms" className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> {t("rooms.back")}</Link>
      <PageHeader
        title={r.display_name}
        subtitle={`${r.building_code} ${t("common.building").toLocaleLowerCase()}${r.floor !== null ? ` · ${r.floor === 0 ? "Z" : r.floor}. ${t("rooms.floor").toLocaleLowerCase()}` : ""}`}
        actions={<div className="flex gap-1">{r.tags.map((tg) => (tg === "TIP" ? <StatusBadge key={tg} kind="tip" label={t("rooms.tag.TIP")} /> : tg === "PC" ? <StatusBadge key={tg} kind="pclab" label={t("rooms.tag.PC")} /> : <Badge key={tg} variant="outline">{t(`rooms.tag.${tg}`)}</Badge>))}</div>}
      />
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="overflow-hidden rounded-xl border bg-muted lg:col-span-3">
          <RoomPhoto room={r} className="aspect-video w-full" />
        </div>
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>{t("rooms.detail")}</CardTitle></CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted-foreground">{t("common.capacity")}</dt><dd className="inline-flex items-center gap-1 tabular-nums"><Users className="size-3.5" aria-hidden />{r.capacity}</dd>
              <dt className="text-muted-foreground">{t("rooms.examCapacity")}</dt><dd className="tabular-nums">{r.exam_capacity}{r.exam_capacity === Math.round(r.capacity / 2) ? <span className="ml-1 text-xs text-muted-foreground">≈ ½</span> : null}</dd>
              <dt className="text-muted-foreground">{t("rooms.code")}</dt><dd className="font-mono">{r.code}</dd>
              <dt className="text-muted-foreground">{t("rooms.bookable")}</dt><dd>{r.is_bookable ? t("common.yes") : t("common.no")}</dd>
              <dt className="text-muted-foreground">{t("rooms.legacyId")}</dt><dd className="font-mono">{r.legacy_crbs_room_id ?? "—"}</dd>
              <dt className="text-muted-foreground">{t("rooms.utilisation")}</dt><dd className="tabular-nums">{Math.round((r.utilisation ?? 0) * 100)}%</dd>
              {r.notes ? <><dt className="text-muted-foreground">{t("rooms.notes")}</dt><dd>{r.notes}</dd></> : null}
            </dl>
          </CardContent>
        </Card>
      </div>
      <Card className="mt-4">
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>{t("rooms.weekUsage")}</CardTitle>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon-sm" aria-label={t("grid.prevWeek")} onClick={() => setWeek((w) => Math.max(1, w - 1))}>‹</Button>
            <span className="min-w-12 text-center text-sm tabular-nums">W{week}</span>
            <Button variant="outline" size="icon-sm" aria-label={t("grid.nextWeek")} onClick={() => setWeek((w) => Math.min(16, w + 1))}>›</Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {occ.data ? <SparklineBars data={occ.data.byRoom.get(r.id) ?? []} height={40} /> : <Skeleton className="h-10 w-40" />}
          <div className="overflow-x-auto">
            <table role="grid" aria-label={t("rooms.weekUsage")} className="border-separate border-spacing-0.5 text-[10px]">
              <thead>
                <tr><th scope="col" className="w-10" /> {PERIODS.map((p) => <th key={p.index} scope="col" className="w-[18px] font-medium text-muted-foreground sm:w-6">{p.index}</th>)}</tr>
              </thead>
              <tbody>
                {[1, 2, 3, 4, 5, 6, 7].map((day) => (
                  <tr key={day}>
                    <th scope="row" className="pr-1 text-left font-medium">{dayName(day, locale, "short")}</th>
                    {PERIODS.map((p) => {
                      const a = mine.find((x) => x.day === day && x.start_period <= p.index && x.end_period >= p.index);
                      const b = !a ? myBlocks.find((x) => x.day === day && x.start_period <= p.index && x.end_period >= p.index) : undefined;
                      const label = `${dayName(day, locale)} P${p.index} ${p.start}–${p.end}${a ? `, ${a.label}, ${a.size}/${r.capacity}` : b ? `, ${b.label}` : ""}`;
                      return (
                        <td key={p.index} role="gridcell" aria-label={label} title={label} className={cn("h-5 rounded-[2px] border", a ? (a.conflict ? "bg-status-infeasible border-status-infeasible-border" : "bg-primary/80 border-primary") : b ? "hatch-preoccupied" : "bg-transparent")} />
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("common.day")}</TableHead><TableHead>{t("common.periods")}</TableHead><TableHead>{t("requests.course")}</TableHead><TableHead>{t("requests.program")}</TableHead><TableHead className="text-right">{t("requests.enrolment")}</TableHead><TableHead>Origin</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mine.length === 0 ? <TableRow><TableCell colSpan={6} className="text-muted-foreground">{t("common.noData")}</TableCell></TableRow> : null}
              {mine.sort((a, b) => a.day - b.day || a.start_period - b.start_period).map((a) => (
                <TableRow key={a.id}>
                  <TableCell>{dayName(a.day, locale, "short")}</TableCell>
                  <TableCell className="tabular-nums">P{a.start_period}–P{a.end_period} · {periodRangeLabel(a.start_period, a.end_period)}</TableCell>
                  <TableCell><Link href={`/runs/${a.run_id}?tab=grid&week=${week}&day=${a.day}&room=${r.id}`} className="font-mono hover:underline">{a.label}</Link></TableCell>
                  <TableCell className="text-muted-foreground">{a.program_name}</TableCell>
                  <TableCell className="text-right tabular-nums">{a.size} / {r.capacity}</TableCell>
                  <TableCell><Badge variant="outline">{a.origin}</Badge></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
