"use client";

import { CheckCircle2, Clock, Copy as CopyIcon, Loader2, OctagonX, RotateCcw, XCircle } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { api } from "@/lib/api/endpoints";
import { useRun, useRuns } from "@/lib/api/hooks";
import type { ScheduleRun } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { CopyDialog } from "./copy-dialog";
import { useStudio, useStudioStore } from "./studio-context";

const ACTIVE = new Set(["QUEUED", "RUNNING"]);
const GOOD = new Set(["FEASIBLE", "OPTIMAL", "TIMEOUT"]);

export interface RunDelta {
  soft: number | null;
  hard: number | null;
  placed: number | null;
  conflicts: number | null;
  unplaced: number | null;
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v)) ? Number(v) : null);
const diff = (a: number | null, b: number | null) => (a === null || b === null ? null : a - b);

/** Client-side comparison of two runs (scores and counts; `/runs/compare` is v2). */
export function compareRuns(cur: ScheduleRun, prev: ScheduleRun): RunDelta {
  return {
    soft: diff(cur.soft_score, prev.soft_score),
    hard: diff(cur.hard_score, prev.hard_score),
    placed: diff(num(cur.stats.events), num(prev.stats.events)),
    conflicts: diff(num(cur.stats.conflicts), num(prev.stats.conflicts)),
    unplaced: diff(num(cur.stats.unplaced), num(prev.stats.unplaced)),
  };
}

function signed(n: number | null, fmt: (x: number) => string): string {
  if (n === null) return "—";
  return n > 0 ? `+${fmt(n)}` : n < 0 ? `−${fmt(Math.abs(n))}` : "±0";
}

function useElapsed(since: number, running: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [running]);
  return since ? Math.max(0, Math.round((now - since) / 1000)) : 0;
}

/** Run status → result card; the summary panel and Step 5 both show it. */
export function RunCard({ compact }: { compact?: boolean }) {
  const { t, n } = useI18n();
  const reduce = useReducedMotion();
  const active = useStudioStore((s) => s.activeRun);
  const setActive = useStudioStore((s) => s.setActiveRun);
  const { goStep, lastEdited } = useStudio();
  const run = useRun(active?.runId ?? null);
  const prev = useRun(active?.previousRunId ?? null);
  const [compare, setCompare] = useState(false);
  const r = run.data;
  const running = r ? ACTIVE.has(r.status) : true;
  const elapsed = useElapsed(active?.startedAt ?? 0, running && active !== null);
  if (!active) return null;

  const adjust = () => {
    setActive(null);
    goStep(lastEdited === "scope" ? "rules" : lastEdited);
  };

  const live = !r || running ? "polite" : "assertive";
  return (
    <motion.section
      layout={!reduce}
      initial={reduce ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      aria-labelledby="run-status-title"
      className={cn("rounded-xl border bg-card p-4 text-sm", r && GOOD.has(r.status) && "border-status-feasible-border", r && r.status === "INFEASIBLE" && "border-status-infeasible-border")}
      data-testid="run-card"
      data-status={r?.status ?? "QUEUED"}
    >
      <h3 id="run-status-title" tabIndex={-1} className="flex items-center gap-2 font-semibold outline-none" aria-live={live}>
        {!r || running ? <Loader2 className="size-4 animate-spin text-primary" aria-hidden /> : GOOD.has(r.status) ? <CheckCircle2 className="size-4 text-status-feasible-fg" aria-hidden /> : r.status === "INFEASIBLE" ? <OctagonX className="size-4 text-status-infeasible-fg" aria-hidden /> : <XCircle className="size-4 text-status-infeasible-fg" aria-hidden />}
        {t("studio.run.title", { id: active.runId })} · {r ? t(`runs.status.${r.status}`) : t("runs.status.QUEUED")}
      </h3>

      {!r || running ? (
        <div className="mt-2 space-y-2">
          <Progress value={r?.progress ?? 0} aria-label={t("generate.progress", { pct: r?.progress ?? 0 })} />
          <p className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
            <span>{r?.status === "RUNNING" ? t("studio.run.phaseSolving", { pct: r.progress }) : t("studio.run.phaseQueued")}</span>
            <span>{t("studio.run.mustBroken", { n: 0 })}</span>
            <span className="inline-flex items-center gap-1">
              <Clock className="size-3" aria-hidden /> {t("studio.run.elapsed", { s: elapsed })}
            </span>
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" render={<Link href={`/runs/${active.runId}`} />}>
              {t("studio.run.viewRun")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={async () => {
                await api.runs.cancel(active.runId);
                await run.refetch();
              }}
            >
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      ) : GOOD.has(r.status) ? (
        <div className="mt-2 space-y-2">
          <p data-testid="run-result">
            {t("studio.run.resultLine", { soft: r.soft_score ?? "—", placed: n(num(r.stats.events) ?? 0), conflicts: n(num(r.stats.conflicts) ?? 0) })}
            {r.hard_score === 100 ? ` · ${t("studio.run.allMust")}` : ""}
          </p>
          {r.status === "TIMEOUT" ? <p className="text-xs text-status-warning-fg">{t("studio.run.timeout")}</p> : null}
          {prev.data ? <DeltaLine cur={r} prev={prev.data} /> : null}
          <div className={cn("flex flex-wrap gap-2", compact && "flex-col items-stretch")}>
            <Button size="sm" render={<Link href={`/runs/${r.id}?tab=grid`} />} data-testid="run-view-timetable">
              {t("studio.run.viewTimetable")}
            </Button>
            <Button size="sm" variant="outline" render={<Link href={`/runs/${r.id}`} />} data-testid="run-open-report">
              {t("studio.run.openReport")}
            </Button>
            {prev.data ? (
              <Button size="sm" variant="outline" onClick={() => setCompare((v) => !v)} aria-expanded={compare}>
                {t("studio.run.compare", { id: prev.data.id })}
              </Button>
            ) : null}
            <Button size="sm" variant="outline" onClick={adjust} data-testid="run-adjust">
              <RotateCcw aria-hidden /> {t("studio.run.adjust")}
            </Button>
          </div>
          {compare && prev.data ? <CompareTable cur={r} prev={prev.data} /> : null}
        </div>
      ) : r.status === "INFEASIBLE" ? (
        <div className="mt-2 space-y-2">
          <p>{t("studio.run.infeasible", { n: r.diagnosis.length })}</p>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {r.diagnosis.slice(0, 3).map((d) => (
              <li key={d.id}>· {d.message}</li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => { setActive(null); goStep("check"); }}>
              {t("studio.run.fixInStudio")}
            </Button>
            <Button size="sm" variant="outline" render={<Link href={`/runs/${r.id}`} />} data-testid="run-open-report">
              {t("studio.run.openReport")}
            </Button>
            <Button size="sm" variant="outline" onClick={adjust} data-testid="run-adjust">
              {t("studio.run.adjust")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-2 space-y-2">
          <p>{t("studio.run.failed")}</p>
          <p className="font-mono text-xs text-muted-foreground">{String(r.stats.error_id ?? r.stats.error ?? `run-${r.id}`)}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={adjust}>
              {t("studio.run.tryAgain")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                void navigator.clipboard?.writeText(JSON.stringify({ id: r.id, status: r.status, stats: r.stats }, null, 2));
                toast.success(t("common.copied"));
              }}
            >
              <CopyIcon aria-hidden /> {t("studio.run.copyDetails")}
            </Button>
          </div>
        </div>
      )}
    </motion.section>
  );
}

function DeltaLine({ cur, prev }: { cur: ScheduleRun; prev: ScheduleRun }) {
  const { t, n } = useI18n();
  const d = compareRuns(cur, prev);
  return (
    <p className="text-xs text-muted-foreground" data-testid="run-delta">
      {t("studio.run.vs", { id: prev.id })}: {t("studio.run.deltaPrefs", { d: signed(d.soft, (x) => n(x)) })} · {t("studio.run.deltaPlaced", { d: signed(d.placed, (x) => n(x)) })}
    </p>
  );
}

export function CompareTable({ cur, prev }: { cur: ScheduleRun; prev: ScheduleRun }) {
  const { t, n } = useI18n();
  const d = compareRuns(cur, prev);
  const rows: { label: string; a: number | null; b: number | null; delta: number | null }[] = [
    { label: t("runs.hardScore"), a: prev.hard_score, b: cur.hard_score, delta: d.hard },
    { label: t("runs.softScore"), a: prev.soft_score, b: cur.soft_score, delta: d.soft },
    { label: t("studio.run.placed"), a: num(prev.stats.events), b: num(cur.stats.events), delta: d.placed },
    { label: t("dashboard.conflicts"), a: num(prev.stats.conflicts), b: num(cur.stats.conflicts), delta: d.conflicts },
    { label: t("runs.unplaced"), a: num(prev.stats.unplaced), b: num(cur.stats.unplaced), delta: d.unplaced },
  ];
  return (
    <table className="w-full text-xs" data-testid="compare-table">
      <thead>
        <tr className="text-left text-muted-foreground">
          <th className="py-1 font-medium" />
          <th className="py-1 text-right font-medium">#{prev.id}</th>
          <th className="py-1 text-right font-medium">#{cur.id}</th>
          <th className="py-1 text-right font-medium">Δ</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label} className="border-t">
            <td className="py-1">{r.label}</td>
            <td className="py-1 text-right tabular-nums">{r.a === null ? "—" : n(r.a)}</td>
            <td className="py-1 text-right tabular-nums">{r.b === null ? "—" : n(r.b)}</td>
            <td className="py-1 text-right tabular-nums">{signed(r.delta, (x) => n(x))}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Advanced: the last 5 runs of this term with scores, plus "Restore this run's rules". */
export function RunHistory() {
  const { t } = useI18n();
  const { termId, kind } = useStudio();
  const runs = useRuns({ term_id: termId });
  const [restore, setRestore] = useState<number | null>(null);
  const list = (runs.data ?? []).filter((r) => r.kind === kind).slice(0, 5);
  if (!list.length) return null;
  return (
    <section aria-labelledby="run-history" className="space-y-2">
      <h4 id="run-history" className="text-sm font-semibold">
        {t("studio.run.history")}
      </h4>
      <ul className="divide-y rounded-lg border text-sm">
        {list.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
            <Link href={`/runs/${r.id}`} className="font-mono text-primary hover:underline">
              #{r.id}
            </Link>
            <span className="text-xs">{t(`runs.status.${r.status}`)}</span>
            <span className="text-xs text-muted-foreground">
              {r.hard_score ?? "—"}/{r.soft_score ?? "—"}
            </span>
            {GOOD.has(r.status) ? (
              <Button size="xs" variant="ghost" className="ml-auto" onClick={() => setRestore(r.id)}>
                {t("studio.run.restoreRules")}
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
      <CopyDialog open={restore !== null} onOpenChange={(v) => !v && setRestore(null)} initialRunId={restore} />
    </section>
  );
}
