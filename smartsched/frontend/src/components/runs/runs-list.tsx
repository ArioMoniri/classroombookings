"use client";

import Link from "next/link";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge, type StatusKind } from "@/components/common/status-badge";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useRuns } from "@/lib/api/hooks";
import type { RunStatus, ScheduleRun } from "@/lib/api/schemas";
import type { MessageKey, Vars } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { ScoreRing } from "./score-ring";

export const RUN_STATUS_KIND: Record<RunStatus, StatusKind> = { QUEUED: "preoccupied", RUNNING: "pclab", FEASIBLE: "feasible", OPTIMAL: "feasible", FEASIBLE_PARTIAL: "warning", INFEASIBLE: "infeasible", TIMEOUT: "infeasible", ERROR: "infeasible", FAILED: "infeasible", CANCELLED: "preoccupied" };

/** A best-effort run: status ``FEASIBLE_PARTIAL`` (older runs: INFEASIBLE with ``stats.partial``) with
 * ``placed`` of ``events_total`` events stored; shown as "Partial · placed/total" with the warning badge. */
export function partialCounts(r: ScheduleRun): { placed: number; total: number } | null {
  const placed = Number(r.stats.placed ?? 0);
  const total = Number(r.stats.events_total ?? 0);
  const partial = r.status === "FEASIBLE_PARTIAL" || (r.status === "INFEASIBLE" && Boolean(r.stats.partial ?? placed > 0));
  return partial && placed > 0 && total > 0 ? { placed, total } : null;
}

/** An imported published board (grid import) rather than a solver run: it has no solver stats. The run
 * schema drops `params.source`, so this reads the stats the solver always writes (`solver`, `events`). */
export function isImportBoard(r: ScheduleRun): boolean {
  return r.stats.solver === undefined && r.stats.events === undefined && r.prompt_text === null && r.diagnosis.length === 0;
}

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

export function RunsList() {
  const { t, locale } = useI18n();
  const { term } = useActiveTerm();
  const runs = useRuns(term ? { term_id: term.id } : undefined);
  const duration = useDuration();
  return (
    <div data-testid="runs">
      <PageHeader title={t("runs.title")} subtitle={term ? `${term.name} · ${t("runs.subtitle")}` : t("runs.subtitle")} actions={<Button nativeButton={false} render={<Link href="/generate" />}>{t("nav.generate")}</Button>} />
      <div className="glass-regular overflow-x-auto rounded-2xl" data-glass="regular">
        {runs.isLoading ? (
          <div className="space-y-1 p-2">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-10" />)}</div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("runs.run")}</TableHead>
                <TableHead>{t("common.status")}</TableHead>
                <TableHead>{t("runs.kind")}</TableHead>
                <TableHead>{t("runs.horizon")}</TableHead>
                <TableHead>{t("glass.report.placed")}</TableHead>
                <TableHead className="text-right">{t("runs.soft")}</TableHead>
                <TableHead>{t("runs.duration")}</TableHead>
                <TableHead>{t("runs.created")}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(runs.data ?? []).map((r) => (
                <TableRow key={r.id} data-testid="run-row">
                  <TableCell className="font-medium">
                    {isImportBoard(r) ? t("glass.dashboard.importedBoard", { id: r.id }) : `#${r.id}`}
                    {r.parent_run_id ? <span className="ml-1.5 text-[12px] font-normal text-label-3">{t("glass.report.childOf", { id: r.parent_run_id })}</span> : null}
                  </TableCell>
                  <TableCell><StatusBadge variant="plain" {...runStatusBadge(r, t)} /></TableCell>
                  <TableCell>{t(r.kind === "COURSE" ? "generate.course" : "generate.exam")}</TableCell>
                  <TableCell>{r.horizon_params.weeks.length ? t("glass.dashboard.weeksN", { list: r.horizon_params.weeks.join(", ") }) : t("glass.dashboard.wholeTerm")}</TableCell>
                  <TableCell><ScoreRing size="sm" value={r.hard_score} partial={partialCounts(r)} label={t("glass.report.placed")} /></TableCell>
                  <TableCell className="text-right tabular-nums">{r.soft_score ?? "—"}</TableCell>
                  <TableCell className="tabular-nums">{duration(r)}</TableCell>
                  <TableCell className="text-[12px] text-label-3">{new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(r.created_at))}</TableCell>
                  <TableCell><Link href={`/runs/${r.id}`} className="font-medium text-tint-text hover:underline">{t("runs.open")}</Link></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
