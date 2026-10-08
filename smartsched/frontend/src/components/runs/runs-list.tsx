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
import { useI18n } from "@/lib/i18n/provider";
import { ScoreRing } from "./score-ring";

export const RUN_STATUS_KIND: Record<RunStatus, StatusKind> = { QUEUED: "preoccupied", RUNNING: "pclab", FEASIBLE: "feasible", OPTIMAL: "feasible", INFEASIBLE: "infeasible", TIMEOUT: "infeasible", ERROR: "infeasible", FAILED: "infeasible", CANCELLED: "preoccupied" };

export function horizonLabel(r: ScheduleRun, t: (k: "generate.week" | "generate.month" | "generate.wholeTerm") => string): string {
  const base = t(r.horizon === "WEEK" ? "generate.week" : r.horizon === "MONTH" ? "generate.month" : "generate.wholeTerm");
  const w = r.horizon_params.weeks;
  return w.length ? `${base} W${w[0]}${w.length > 1 ? `–${w[w.length - 1]}` : ""}` : base;
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
  return (
    <div data-testid="runs">
      <PageHeader title={t("runs.title")} subtitle={t("runs.subtitle")} actions={<Button nativeButton={false} render={<Link href="/generate" />}>{t("nav.generate")}</Button>} />
      <div className="overflow-x-auto rounded-lg border">
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
                <TableHead>{t("runs.hard")}</TableHead>
                <TableHead className="text-right">{t("runs.soft")}</TableHead>
                <TableHead>{t("runs.duration")}</TableHead>
                <TableHead>{t("runs.created")}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(runs.data ?? []).map((r) => (
                <TableRow key={r.id} data-testid="run-row">
                  <TableCell className="font-mono font-medium">#{r.id}{r.parent_run_id ? <span className="ml-1 text-xs text-muted-foreground">← #{r.parent_run_id}</span> : null}</TableCell>
                  <TableCell><StatusBadge kind={RUN_STATUS_KIND[r.status]} label={`${t(`runs.status.${r.status}`)}${r.status === "RUNNING" ? ` ${r.progress}%` : ""}`} /></TableCell>
                  <TableCell>{t(r.kind === "COURSE" ? "generate.course" : "generate.exam")}</TableCell>
                  <TableCell>{horizonLabel(r, t)}</TableCell>
                  <TableCell><ScoreRing size="sm" value={r.hard_score} label={t("runs.hard")} /></TableCell>
                  <TableCell className="text-right tabular-nums">{r.soft_score ?? "—"}</TableCell>
                  <TableCell className="tabular-nums">{durationLabel(r)}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(r.created_at))}</TableCell>
                  <TableCell><Link href={`/runs/${r.id}`} className="text-primary hover:underline">{t("runs.open")}</Link></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
