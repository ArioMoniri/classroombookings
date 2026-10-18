"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo } from "react";
import { PageHeader } from "@/components/common/page-header";
import { CompareEntry } from "@/components/compare/compare-entry";
import type { StatusKind } from "@/components/common/status-badge";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Button } from "@/components/ui/button";
import { DataTable, StatusDot, type DataColumn } from "@/components/ui/data-table";
import { useMe, useRuns } from "@/lib/api/hooks";
import type { RunStatus, ScheduleRun } from "@/lib/api/schemas";
import type { MessageKey, Vars } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { isBaselineRun } from "@/lib/api/council";

export const RUN_STATUS_KIND: Record<RunStatus, StatusKind> = { QUEUED: "preoccupied", RUNNING: "pclab", FEASIBLE: "feasible", OPTIMAL: "feasible", FEASIBLE_PARTIAL: "warning", INFEASIBLE: "infeasible", TIMEOUT: "infeasible", ERROR: "infeasible", FAILED: "infeasible", CANCELLED: "preoccupied" };

/** A best-effort run: status ``FEASIBLE_PARTIAL`` (older runs: INFEASIBLE with ``stats.partial``) with
 * ``placed`` of ``events_total`` events stored; shown as "Partial · placed/total" with the warning badge. */
export function partialCounts(r: ScheduleRun): { placed: number; total: number } | null {
  const placed = Number(r.stats.placed ?? 0);
  const total = Number(r.stats.events_total ?? 0);
  const partial = r.status === "FEASIBLE_PARTIAL" || (r.status === "INFEASIBLE" && Boolean(r.stats.partial ?? placed > 0));
  return partial && placed > 0 && total > 0 ? { placed, total } : null;
}

// moved to ./run-kinds (CH-08: the score-history model needs it without importing this component)
import { isImportBoard } from "./run-kinds";
export { isImportBoard };

export function runStatusBadge(r: ScheduleRun, t: (k: MessageKey, p?: Vars) => string): { kind: StatusKind; label: string } {
  const partial = partialCounts(r);
  if (partial) return { kind: "warning", label: t("runs.partial", partial) };
  return { kind: RUN_STATUS_KIND[r.status], label: `${t(`runs.status.${r.status}`)}${r.status === "RUNNING" ? ` ${r.progress}%` : ""}` };
}

export function horizonLabel(r: ScheduleRun, t: (k: "generate.week" | "generate.month" | "generate.wholeTerm") => string): string {
  const base = t(r.horizon === "WEEK" ? "generate.week" : r.horizon === "MONTH" ? "generate.month" : "generate.wholeTerm");
  const w = r.horizon_params.weeks;
  return w.length ? `${base} W${w[0]}${w.length > 1 ? `–${w[w.length - 1]}` : ""}` : base;
}

function seconds(r: ScheduleRun): number | null {
  if (!r.finished_at) return null;
  return Math.max(0, Math.round((new Date(r.finished_at).getTime() - new Date(r.created_at).getTime()) / 1000));
}

/** "44 sn" / "1 dk 12 sn" in Turkish, "44 s" / "1 min 12 s" in English. */
export function useDuration() {
  const { t } = useI18n();
  return (r: ScheduleRun) => {
    const s = seconds(r);
    if (s === null) return "—";
    return s >= 60 ? t("glass.report.minSec", { m: Math.floor(s / 60), s: s % 60 }) : t("glass.report.sec", { s });
  };
}

export function durationLabel(r: ScheduleRun): string {
  if (!r.finished_at) return "—";
  const s = Math.max(0, Math.round((new Date(r.finished_at).getTime() - new Date(r.created_at).getTime()) / 1000));
  return s >= 60 ? `${Math.floor(s / 60)} dk ${s % 60} sn` : `${s} sn`;
}

/** Dot tone for a run status (Vercel H6: one dot + one word; never a badge next to the same text). */
export function runDotTone(r: ScheduleRun): "feasible" | "warning" | "infeasible" | "neutral" | "tint" {
  if (partialCounts(r)) return "warning";
  const k = RUN_STATUS_KIND[r.status];
  return k === "pclab" ? "tint" : k === "preoccupied" ? "neutral" : k === "feasible" ? "feasible" : k === "warning" ? "warning" : "infeasible";
}

export function RunsList() {
  const { t, locale } = useI18n();
  const router = useRouter();
  const { term } = useActiveTerm();
  const me = useMe();
  const runs = useRuns(term ? { term_id: term.id } : undefined);
  const duration = useDuration();
  const dateFmt = useMemo(() => new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }), [locale]);
  const columns = useMemo<DataColumn<ScheduleRun>[]>(
    () => [
      {
        id: "run",
        header: t("runs.run"),
        pin: "left",
        priority: 1,
        minSize: 72,
        grow: 1,
        maxSize: 320,
        text: (r) => (isBaselineRun(r) ? t("baseline.listName", { id: r.id }) : isImportBoard(r) ? t("glass.dashboard.importedBoard", { id: r.id }) : [`#${r.id}`, r.label?.trim()].filter(Boolean).join(" · ")) + (r.parent_run_id ? `  ${t("glass.report.childOf", { id: r.parent_run_id })}` : ""),
        sortValue: (r) => r.id,
        cell: (r) => (
          <span className="flex min-w-0 items-baseline gap-1.5">
            <Link href={`/runs/${r.id}`} className="truncate font-medium text-label-1 hover:underline focus-visible:outline-2 focus-visible:outline-(--focus)" onClick={(e) => e.stopPropagation()}>
              {isBaselineRun(r) ? t("baseline.listName", { id: r.id }) : isImportBoard(r) ? t("glass.dashboard.importedBoard", { id: r.id }) : `#${r.id}`}
            </Link>
            {/* the planner's own name for the run (ScheduleRun.label); an import board already names its file */}
            {!isImportBoard(r) && r.label?.trim() ? <span className="truncate type-callout text-label-2" data-testid="run-label">{r.label.trim()}</span> : null}
            {r.parent_run_id ? <span className="truncate type-footnote text-label-3">{t("glass.report.childOf", { id: r.parent_run_id })}</span> : null}
          </span>
        ),
      },
      {
        id: "status",
        header: t("common.status"),
        priority: 1,
        minSize: 96,
        text: (r) => (partialCounts(r) ? t("runs.status.FEASIBLE_PARTIAL") : t(`runs.status.${r.status}`)),
        extra: 16,
        sortValue: (r) => r.status,
        cell: (r) => (
          <StatusDot tone={runDotTone(r)}>
            {partialCounts(r) ? t("runs.status.FEASIBLE_PARTIAL") : t(`runs.status.${r.status}`)}
            {r.status === "RUNNING" ? ` ${r.progress}%` : ""}
          </StatusDot>
        ),
      },
      { id: "kind", header: t("runs.kind"), priority: 3, text: (r) => t(r.kind === "COURSE" ? "generate.course" : "generate.exam"), sortValue: (r) => r.kind, cell: (r) => t(r.kind === "COURSE" ? "generate.course" : "generate.exam") },
      {
        id: "horizon",
        header: t("runs.horizon"),
        priority: 4,
        text: (r) => (r.horizon_params.weeks.length ? t("glass.dashboard.weeksN", { list: r.horizon_params.weeks.join(", ") }) : t("glass.dashboard.wholeTerm")),
        maxSize: 240,
        cell: (r) => <span className="truncate">{r.horizon_params.weeks.length ? t("glass.dashboard.weeksN", { list: r.horizon_params.weeks.join(", ") }) : t("glass.dashboard.wholeTerm")}</span>,
      },
      {
        id: "placed",
        header: t("glass.report.placed"),
        align: "end",
        priority: 2,
        text: (r) => placedText(r),
        sortValue: (r) => partialCounts(r)?.placed ?? r.hard_score ?? -1,
        cell: (r) => <span data-numeric>{placedText(r)}</span>,
      },
      { id: "soft", header: t("runs.soft"), align: "end", priority: 3, text: (r) => String(r.soft_score ?? "—"), sortValue: (r) => r.soft_score ?? -1, cell: (r) => <span data-numeric>{r.soft_score ?? "—"}</span> },
      { id: "duration", header: t("runs.duration"), align: "end", priority: 4, text: (r) => duration(r), cell: (r) => <span data-numeric>{duration(r)}</span> },
      {
        id: "created",
        header: t("runs.created"),
        priority: 2,
        text: (r) => dateFmt.format(new Date(r.created_at)),
        sortValue: (r) => r.created_at,
        cell: (r) => <time dateTime={r.created_at} className="truncate text-label-2">{dateFmt.format(new Date(r.created_at))}</time>,
      },
    ],
    [t, duration, dateFmt],
  );
  return (
    <div data-testid="runs">
      <PageHeader title={t("runs.title")} subtitle={term ? `${term.name} · ${t("runs.subtitle")}` : t("runs.subtitle")} actions={<><CompareEntry /><Button nativeButton={false} render={<Link href="/generate" />}>{t("nav.generate")}</Button></>} />
      <DataTable
        tableId="runs"
        userId={me.data?.id}
        label={t("runs.title")}
        columns={columns}
        rows={runs.data}
        getRowId={(r) => String(r.id)}
        onRowActivate={(r) => router.push(`/runs/${r.id}`)}
        rowProps={() => ({ "data-testid": "run-row" })}
        defaultSort={[{ id: "run", desc: true }]}
      />
    </div>
  );
}

/** Plain numerals: "517 / 530" for a partial run, "100 / 100" hard score otherwise (no ring, no badge). */
function placedText(r: ScheduleRun): string {
  const p = partialCounts(r);
  if (p) return `${p.placed} / ${p.total}`;
  return r.hard_score === null ? "—" : `${r.hard_score} / 100`;
}
