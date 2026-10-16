"use client";

import { AlertTriangle, CheckCircle2, Clock, Copy as CopyIcon, OctagonX, RotateCcw, XCircle } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BusyGlyph } from "@/components/ui/busy-label";
import { Progress } from "@/components/ui/progress";
import { api } from "@/lib/api/endpoints";
import { useRun, useRuns } from "@/lib/api/hooks";
import type { ScheduleRun } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { springs, useReduce } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { plannerText } from "@/components/runs/diagnosis-format";
import { BROKEN_RULE_TR, placedOf, truthOf, type RunTruth } from "@/components/runs/run-truth";
import { CopyDialog } from "./copy-dialog";
import { useStudio, useStudioStore } from "./studio-context";

const ACTIVE = new Set(["QUEUED", "RUNNING"]);
const GOOD = new Set(["FEASIBLE", "OPTIMAL", "TIMEOUT"]);
/** runs with a stored timetable to open: a best-effort FEASIBLE_PARTIAL run is one too (not a failed run) */
const HAS_TIMETABLE = new Set([...GOOD, "FEASIBLE_PARTIAL"]);

/** good = every class placed; partial = a usable best-effort timetable (amber, never green 100/100). */
export function runTone(status: string): "good" | "partial" | "bad" | "running" {
  if (status === "QUEUED" || status === "RUNNING") return "running";
  if (GOOD.has(status)) return "good";
  return status === "FEASIBLE_PARTIAL" ? "partial" : "bad";
}

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
    placed: diff(placedOf(cur.stats).placed, placedOf(prev.stats).placed),
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

/** The run's verdict line from `stats.truth`: broken rules (red, listed), accepted exceptions (amber), clean (green). */
function TruthLine({ truth }: { truth: RunTruth }) {
  const { n, locale } = useI18n();
  const tr = locale === "tr";
  const tone = truth.verdict === "broken" ? "text-status-infeasible-fg" : truth.verdict === "exceptions" ? "text-status-warning-fg" : "text-status-feasible-fg";
  return (
    <div data-testid="run-result" data-verdict={truth.verdict} className={tone}>
      <p>{tr ? truth.headline.tr : truth.headline.en || truth.headline.tr}</p>
      {truth.verdict === "broken" ? (
        <ul className="mt-1 list-disc pl-5 text-xs text-label-1" data-testid="run-result-broken">
          {truth.broken.slice(0, 4).map((b, i) => (
            <li key={`${b.rule}-${i}`}>
              {(tr ? BROKEN_RULE_TR[b.rule] : null) ?? b.rule}: {b.message}
              {b.explained && b.reason ? ` · “${b.reason}”` : ""}
            </li>
          ))}
        </ul>
      ) : truth.verdict === "exceptions" ? (
        <ul className="mt-1 list-disc pl-5 text-xs text-label-2" data-testid="run-result-exceptions">
          {truth.exceptions.filter((e) => e.rule).slice(0, 4).map((e) => (
            <li key={e.cause}>
              {tr ? e.label.tr : e.label.en} · {n(e.classes)} {tr ? "ders" : "classes"}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Run status → result card; the summary panel and Step 5 both show it. */
export function RunCard({ compact }: { compact?: boolean }) {
  const { t, n, locale } = useI18n();
  const reduce = useReduce();
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
      transition={springs.smooth}
      aria-labelledby="run-status-title"
      className={cn("rounded-xl border bg-card p-4 text-sm", r && runTone(r.status) === "good" && "border-status-feasible-border", r && runTone(r.status) === "partial" && "border-status-warning-border", r && r.status === "INFEASIBLE" && "border-status-infeasible-border")}
      data-testid="run-card"
      data-status={r?.status ?? "QUEUED"}
    >
      <h3 id="run-status-title" tabIndex={-1} className="flex items-center gap-2 font-semibold outline-hidden" aria-live={live}>
        {!r || running ? <BusyGlyph className="size-4 text-tint-text" /> : GOOD.has(r.status) ? <CheckCircle2 className="size-4 text-status-feasible-fg" aria-hidden /> : r.status === "FEASIBLE_PARTIAL" ? <AlertTriangle className="size-4 text-status-warning-fg" aria-hidden /> : r.status === "INFEASIBLE" ? <OctagonX className="size-4 text-status-infeasible-fg" aria-hidden /> : <XCircle className="size-4 text-status-infeasible-fg" aria-hidden />}
        {t("studio.run.title", { id: active.runId })} · {r ? t(`runs.status.${r.status}`) : t("runs.status.QUEUED")}
      </h3>

      {!r || running ? (
        <div className="mt-2 space-y-2">
          <Progress value={r?.progress ?? 0} aria-label={t("generate.progress", { pct: r?.progress ?? 0 })} />
          <p className="flex flex-wrap gap-x-3 text-xs text-label-2">
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
      ) : HAS_TIMETABLE.has(r.status) ? (
        <div className="mt-2 space-y-2">
          {truthOf(r.stats.truth) && truthOf(r.stats.truth)?.verdict !== "none" ? (
            // round-1 R1-M-04: the backend's one truth (planner-level check), the same sentence as the run report
            <TruthLine truth={truthOf(r.stats.truth) as RunTruth} />
          ) : r.status === "FEASIBLE_PARTIAL" ? (
            // a best-effort run: the honest count, amber (UX fix "partial runs never show a green 100/100")
            <p data-testid="run-result" className="text-status-warning-fg">
              {t("runs.partialRing", { placed: n(num(r.stats.placed) ?? 0), total: n(num(r.stats.events_total) ?? 0) })}
            </p>
          ) : (
            <p data-testid="run-result">
              {t("studio.run.resultLine", { soft: r.soft_score ?? "—", placed: n(placedOf(r.stats).placed ?? 0), total: n(placedOf(r.stats).total ?? 0) })}
              {r.hard_score === 100 ? ` · ${t("studio.run.allMust")}` : ""}
            </p>
          )}
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
          <ul className="space-y-1 text-xs text-label-2">
            {r.diagnosis.slice(0, 3).map((d) => (
              <li key={d.id}>· {plannerText(d, locale)}</li>
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
          <p className="font-mono text-xs text-label-2">{String(r.stats.error_id ?? r.stats.error ?? `run-${r.id}`)}</p>
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
    <p className="text-xs text-label-2" data-testid="run-delta">
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
    { label: t("studio.run.placed"), a: placedOf(prev.stats).placed, b: placedOf(cur.stats).placed, delta: d.placed },
    { label: t("dashboard.conflicts"), a: num(prev.stats.conflicts), b: num(cur.stats.conflicts), delta: d.conflicts },
    { label: t("runs.unplaced"), a: num(prev.stats.unplaced), b: num(cur.stats.unplaced), delta: d.unplaced },
  ];
  return (
    <table className="w-full text-xs" data-testid="compare-table">
      <thead>
        <tr className="text-left text-label-2">
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
            <Link href={`/runs/${r.id}`} className="font-mono text-tint-text hover:underline">
              #{r.id}
            </Link>
            <span className="text-xs">{t(`runs.status.${r.status}`)}</span>
            <span className="text-xs text-label-2">
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
