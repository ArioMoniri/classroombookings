"use client";

import { type ColumnDef, getCoreRowModel, getSortedRowModel, type SortingState, useReactTable } from "@tanstack/react-table";
import { Lock, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/common/page-header";
import { NativeSelect } from "@/components/common/native-select";
import { StatusBadge, type StatusKind } from "@/components/common/status-badge";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { DataTable } from "@/components/common/data-table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useExams, useMeetings, usePrograms } from "@/lib/api/hooks";
import type { ExamRequest, MeetingRequest, RequestStatus } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { dayName, formatDate, periodRangeLabel } from "@/lib/time";
import { RequestDrawer } from "./request-drawer";

export const STATUS_KIND: Record<RequestStatus, StatusKind> = { NEW: "preoccupied", PARSED: "feasible", NEEDS_REVIEW: "warning", LOCKED: "locked" };

export function weeksLabel(weeks: number[]): string {
  if (weeks.length === 0) return "—";
  const sorted = [...weeks].sort((a, b) => a - b);
  const contiguous = sorted.every((w, i) => i === 0 || w === sorted[i - 1] + 1);
  return contiguous ? `${sorted[0]}–${sorted[sorted.length - 1]}` : sorted.join(",");
}

function useDebouncedValue(value: string, ms = 200): string {
  const [v, setV] = useState(value);
  useMemo(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export function RequestsView() {
  const { t, locale, n } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const kind = params.get("kind") === "exams" ? "exams" : "meetings";
  const status = params.get("status") ?? "";
  const programId = params.get("program_id") ?? "";
  const selectedId = params.get("id") ? Number(params.get("id")) : null;
  const [query, setQuery] = useState(params.get("q") ?? "");
  const q = useDebouncedValue(query);
  const [sorting, setSorting] = useState<SortingState>([]);
  const programs = usePrograms();
  const filters = { q, status: status || undefined, program_id: programId || undefined, page_size: 200 };
  const meetings = useMeetings(filters);
  const exams = useExams(filters);

  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    router.replace(`/requests?${next.toString()}`);
  };

  const meetingCols = useMemo<ColumnDef<MeetingRequest>[]>(
    () => [
      { id: "status", accessorKey: "status", header: t("common.status"), cell: ({ row }) => <StatusBadge kind={STATUS_KIND[row.original.status]} label={t(`requests.status.${row.original.status}`)} /> },
      { id: "course", accessorKey: "course_code", header: t("requests.course"), cell: ({ row }) => <span><span className="font-mono font-medium">{row.original.course_code}</span> <span className="text-muted-foreground">§{row.original.section_label}</span><span className="block max-w-[220px] truncate text-xs text-muted-foreground">{row.original.course_name}</span></span> },
      { id: "program", accessorKey: "program_name", header: t("requests.program"), cell: ({ row }) => <span className="text-xs">{row.original.program_name}{row.original.class_year ? ` · ${row.original.class_year}` : ""}</span> },
      { id: "day", accessorFn: (r) => r.day ?? 99, header: t("common.day"), cell: ({ row }) => (row.original.day ? dayName(row.original.day, locale, "short") : <span className="text-muted-foreground">—</span>) },
      { id: "periods", accessorFn: (r) => r.start_period ?? 99, header: t("common.periods"), cell: ({ row }) => (row.original.start_period && row.original.end_period ? <span className="tabular-nums">P{row.original.start_period}–P{row.original.end_period} <span className="text-xs text-muted-foreground">{periodRangeLabel(row.original.start_period, row.original.end_period)}</span></span> : <span className="text-muted-foreground">—</span>) },
      { id: "weeks", accessorFn: (r) => r.weeks.length, header: t("requests.weeks"), cell: ({ row }) => <Badge variant="outline" className="font-mono">{weeksLabel(row.original.weeks)}</Badge> },
      { id: "enrolment", accessorKey: "enrolment", header: t("requests.enrolment"), cell: ({ getValue }) => <span className="tabular-nums">{getValue<number | null>() ?? "—"}</span> },
      { id: "requested", accessorKey: "requested_room_text", header: t("requests.requested"), cell: ({ row }) => <RequestChips r={row.original} /> },
      { id: "mode", accessorKey: "mode", header: t("requests.mode"), cell: ({ getValue }) => <Badge variant="secondary">{getValue<string>()}</Badge> },
      { id: "instructor", accessorKey: "instructor", header: t("requests.instructor"), cell: ({ getValue }) => <span className="block max-w-[180px] truncate text-xs">{getValue<string | null>() ?? "—"}</span> },
      { id: "warnings", accessorFn: (r) => r.parse_warnings.length, header: t("import.warnings"), cell: ({ getValue }) => (getValue<number>() > 0 ? <StatusBadge kind="warning" label={String(getValue<number>())} /> : null) },
    ],
    [t, locale],
  );

  const examCols = useMemo<ColumnDef<ExamRequest>[]>(
    () => [
      { id: "status", accessorKey: "status", header: t("common.status"), cell: ({ row }) => <StatusBadge kind={STATUS_KIND[row.original.status]} label={t(`requests.status.${row.original.status}`)} /> },
      { id: "course", accessorKey: "course_code", header: t("requests.course"), cell: ({ row }) => <span><span className="font-mono font-medium">{row.original.course_code}</span><span className="block max-w-[220px] truncate text-xs text-muted-foreground">{row.original.course_name}</span></span> },
      { id: "program", accessorKey: "program_name", header: t("requests.program"), cell: ({ row }) => <span className="text-xs">{row.original.program_name}{row.original.merge_key ? <Badge variant="outline" className="ml-1">merge</Badge> : null}</span> },
      { id: "date", accessorKey: "date", header: t("requests.date"), cell: ({ getValue }) => { const v = getValue<string | null>(); return v ? formatDate(v, locale, { weekday: "short" }) : <span className="text-muted-foreground">—</span>; } },
      { id: "time", accessorFn: (r) => r.start_period ?? 99, header: t("requests.time"), cell: ({ row }) => (row.original.start_period && row.original.end_period ? <span className="tabular-nums">{periodRangeLabel(row.original.start_period, row.original.end_period)}</span> : "—") },
      { id: "enrolment", accessorKey: "enrolment", header: t("requests.enrolment"), cell: ({ getValue }) => <span className="tabular-nums">{getValue<number | null>() ?? "—"}</span> },
      { id: "venue", accessorKey: "requested_venue_text", header: t("requests.venue"), cell: ({ row }) => <span className="flex flex-wrap gap-1 text-xs">{row.original.requested_room_count && row.original.requested_room_count > 1 ? <Badge variant="outline">{row.original.requested_room_count} {t("common.rooms").toLocaleLowerCase(locale)}</Badge> : null}{row.original.requested_min_capacity ? <Badge variant="outline">≥ {row.original.requested_min_capacity}</Badge> : null}{row.original.requested_tags.map((tg) => <Badge key={tg} variant="outline">{tg}</Badge>)}{row.original.invigilators_requested ? <Badge variant="outline">{row.original.invigilators_requested} inv.</Badge> : null}<span className="text-muted-foreground">{row.original.requested_venue_text}</span></span> },
      { id: "flags", header: t("requests.onCampus"), cell: ({ row }) => <span className="text-xs">{row.original.on_campus_written ? "✓" : ""}{row.original.no_exam ? ` ${t("requests.noExam")}` : ""}</span> },
    ],
    [t, locale],
  );

  const meetingTable = useReactTable({ data: meetings.data?.items ?? [], columns: meetingCols, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });
  const examTable = useReactTable({ data: exams.data?.items ?? [], columns: examCols, state: { sorting }, onSortingChange: setSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });
  const total = kind === "meetings" ? meetings.data?.total : exams.data?.total;
  const loading = kind === "meetings" ? meetings.isLoading : exams.isLoading;
  const shown = kind === "meetings" ? meetingTable.getRowModel().rows.length : examTable.getRowModel().rows.length;
  const selected = kind === "meetings" ? meetings.data?.items.find((m) => m.id === selectedId) ?? null : null;
  const selectedExam = kind === "exams" ? exams.data?.items.find((m) => m.id === selectedId) ?? null : null;

  return (
    <div data-testid="requests">
      <PageHeader title={t("requests.title")} subtitle={t("requests.subtitle")} />
      <Tabs value={kind} onValueChange={(v) => set({ kind: String(v), id: null })} className="mb-3">
        <TabsList>
          <TabsTrigger value="meetings" data-testid="tab-meetings">{t("requests.meetings")}</TabsTrigger>
          <TabsTrigger value="exams" data-testid="tab-exams">{t("requests.exams")}</TabsTrigger>
        </TabsList>
      </Tabs>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input aria-label={t("common.search")} placeholder={t("requests.searchPlaceholder")} value={query} onChange={(e) => setQuery(e.target.value)} className="pl-8" />
        </div>
        <NativeSelect aria-label={t("requests.filterStatus")} value={status} onChange={(e) => set({ status: e.target.value })} className="w-44">
          <option value="">{t("requests.filterStatus")}: {t("common.all")}</option>
          {(["NEW", "PARSED", "NEEDS_REVIEW", "LOCKED"] as const).map((s) => <option key={s} value={s}>{t(`requests.status.${s}`)}</option>)}
        </NativeSelect>
        {kind === "meetings" ? (
          <NativeSelect aria-label={t("requests.filterProgram")} value={programId} onChange={(e) => set({ program_id: e.target.value })} className="w-56">
            <option value="">{t("requests.filterProgram")}: {t("common.all")}</option>
            {(programs.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </NativeSelect>
        ) : null}
        <span className="ml-auto text-xs text-muted-foreground">{total !== undefined ? t("common.showing", { count: n(shown), total: n(total) }) : ""}</span>
      </div>
      <div className="overflow-x-auto rounded-lg border">
        {loading ? (
          <div className="space-y-1 p-2">{Array.from({ length: 10 }, (_, i) => <Skeleton key={i} className="h-10" />)}</div>
        ) : kind === "meetings" ? (
          <DataTable table={meetingTable} emptyLabel={t("common.noData")} selectedId={selectedId} getId={(r) => r.id} onSelect={(r) => set({ id: String(r.id) })} rowTestId="request-row" />
        ) : (
          <DataTable table={examTable} emptyLabel={t("common.noData")} selectedId={selectedId} getId={(r) => r.id} onSelect={(r) => set({ id: String(r.id) })} rowTestId="request-row" />
        )}
      </div>
      <RequestDrawer meeting={selected} exam={selectedExam} onClose={() => set({ id: null })} />
    </div>
  );
}

function RequestChips({ r }: { r: MeetingRequest }) {
  const { t } = useI18n();
  return (
    <span className="flex max-w-[260px] flex-wrap gap-1">
      {r.requested_room_ids.length > 0 ? <Badge variant="outline" className="font-mono">{r.requested_room_text?.split("(")[0].trim()}</Badge> : null}
      {r.requested_building ? <Badge variant="outline">{r.requested_building} {t("common.building").toLocaleLowerCase()}</Badge> : null}
      {r.requested_tags.map((tg) => <Badge key={tg} variant="outline">{tg}</Badge>)}
      {r.requested_capacity ? <Badge variant="outline">≥ {r.requested_capacity}</Badge> : null}
      {r.flexible_day ? <Badge variant="outline">{t("requests.flexibleDay")}</Badge> : null}
      {r.status === "LOCKED" ? <Lock className="size-3.5 text-status-locked-fg" aria-label={t("common.locked")} /> : null}
      {r.requested_room_ids.length === 0 && !r.requested_building && r.requested_tags.length === 0 && !r.requested_capacity && r.requested_room_text ? <span className="truncate text-xs text-muted-foreground" title={r.requested_room_text}>“{r.requested_room_text}”</span> : null}
    </span>
  );
}
