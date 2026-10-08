"use client";

import { AlertTriangle, ArrowLeft, CheckCircle2, Download, Loader2, XOctagon } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ChatPanel } from "@/components/chat/chat-panel";
import { PageHeader } from "@/components/common/page-header";
import { KpiNumber } from "@/components/dashboard/kpi-number";
import { useRememberRunOnView } from "@/components/shell/workspace";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { GlassPanel } from "@/components/ui/glass-panel";
import { TaskRows, type TaskRow } from "@/components/ui/beautifului/task-rows";
import { Progress, ProgressIndicator, ProgressTrack } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { optionIndex } from "@/lib/api/adapters";
import { api } from "@/lib/api/endpoints";
import { useApplyFix, useConstraints, useRun } from "@/lib/api/hooks";
import type { ScheduleRun } from "@/lib/api/schemas";
import { useRunDataIssues, useRunSummary } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { DiagnosisCard } from "./diagnosis-card";
import { groupDiagnoses } from "./diagnosis-format";
import { IssueGroups, LocalIssueGroups } from "./issue-groups";
import { isImportBoard, partialCounts, runStatusBadge, useDuration } from "./runs-list";
import { ScoreRing } from "./score-ring";
import { SoftBreakdown } from "./soft-breakdown";

/** The status headline: honest for partial runs (amber "660/683 placed · no rule broken", never green 100/100). */
function Verdict({ r, headline }: { r: ScheduleRun; headline?: string }) {
  const { t, n } = useI18n();
  const partial = partialCounts(r);
  const complete = !partial && (r.status === "FEASIBLE" || r.status === "OPTIMAL");
  if (partial)
    return (
      <p className="flex items-start gap-2 type-title-3 text-status-warning-fg" data-testid="run-verdict" data-state="partial">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 stroke-[2]" aria-hidden />
        <span>{headline || t("runs.partialRing", { placed: n(partial.placed), total: n(partial.total) })}</span>
      </p>
    );
  if (complete)
    return (
      <p className="flex items-start gap-2 type-title-3 text-status-feasible-fg" data-testid="run-verdict" data-state="complete">
        <CheckCircle2 className="mt-0.5 size-5 shrink-0 stroke-[2]" aria-hidden />
        <span>{isImportBoard(r) ? t("glass.report.importedBoard") : t("glass.report.allPlaced")}</span>
      </p>
    );
  return (
    <p className="flex items-start gap-2 type-title-3 text-status-infeasible-fg" data-testid="run-verdict" data-state="failed">
      <XOctagon className="mt-0.5 size-5 shrink-0 stroke-[2]" aria-hidden />
      <span>{t("glass.report.noTimetable")}</span>
    </p>
  );
}

/** Solve pipeline from the worker's real phases (loading 5 % → building 15 % → solving 20–90 % → persisting 92 %). */
function useSolveSteps(r: ScheduleRun): TaskRow[] {
  const { t } = useI18n();
  const p = r.status === "QUEUED" ? -1 : r.progress;
  const phase = typeof r.stats.phase === "string" ? r.stats.phase : "";
  const steps: { key: string; label: string; from: number; to: number }[] = [
    { key: "loading", label: t("glass.report.stepLoading"), from: 0, to: 15 },
    { key: "building", label: t("glass.report.stepBuilding"), from: 15, to: 20 },
    { key: "solving", label: t("glass.report.stepSolving"), from: 20, to: 92 },
    { key: "persisting", label: t("glass.report.stepSaving"), from: 92, to: 100 },
  ];
  return steps.map((s, i) => ({
    key: s.key,
    step: i + 1,
    label: s.label,
    status: p >= s.to ? "done" : p >= s.from ? "running" : "pending",
    meta: s.key === "solving" && p >= s.from && p < s.to && phase && !["solving", "building", "loading"].includes(phase) ? t("glass.report.subPhase", { phase: phase.replace(/_/g, " ") }) : undefined,
  }));
}

function SolveProgress({ r }: { r: ScheduleRun }) {
  const { t } = useI18n();
  const rows = useSolveSteps(r);
  return (
    <TaskRows
      variant="list"
      rows={rows}
      labels={{ completed: t("glass.report.taskDone"), failed: t("glass.report.taskFailed"), retry: t("common.retry"), running: t("glass.report.taskRunning"), pending: t("glass.report.taskPending") }}
      className="mt-4"
    />
  );
}

export function RunView({ id }: { id: number }) {
  const { t, n, locale } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") ?? "report";
  const run = useRun(id);
  const constraints = useConstraints({ run_id: id });
  const applyFix = useApplyFix(id);
  const duration = useDuration();
  const r = run.data;
  const active = r ? r.status === "QUEUED" || r.status === "RUNNING" : false;
  const finished = Boolean(r) && !active;
  const issues = useRunDataIssues(id, finished && Boolean(r?.diagnosis.length));
  const summary = useRunSummary(id, finished);
  useRememberRunOnView(r?.term_id, r?.id);
  // the ring draws and numbers tick only if the run finishes while this page is open (motion.md §3.5)
  const [sawActive, setSawActive] = useState(false);
  const [allUnplaced, setAllUnplaced] = useState(false);
  if (active && !sawActive) setSawActive(true);
  const live = sawActive && finished;
  const sections = useMemo(() => (r ? groupDiagnoses(r.diagnosis, locale) : []), [r, locale]);
  const setTab = (next: string) => {
    const sp = new URLSearchParams(params.toString());
    sp.set("tab", next);
    router.replace(`/runs/${id}?${sp.toString()}`);
  };
  if (run.isError) return <EmptyState title={t("runs.notFound")} actions={<Button nativeButton={false} render={<Link href="/runs" />}>{t("runs.title")}</Button>} />;
  if (!r) return <Skeleton className="h-64 rounded-2xl" />;

  const partial = partialCounts(r);
  const placed = partial?.placed ?? Number(r.stats.placed ?? r.stats.events ?? 0);
  const total = partial?.total ?? Number(r.stats.events_total ?? r.stats.events ?? 0);
  const unplaced = partial ? partial.total - partial.placed : Number(r.stats.unplaced ?? 0);
  const headline = summary.data?.headline ? (locale === "tr" ? summary.data.headline.tr : summary.data.headline.en) : undefined;
  const unplacedCards = sections.find((s) => s.section === "unplaced");
  const ruleCards = sections.find((s) => s.section === "rules");
  const cardCount = (s: typeof unplacedCards) => (s ? [...s.codes.values()].reduce((a, rows) => a + rows.reduce((b, x) => b + x.count, 0), 0) : 0);
  const problems = r.diagnosis.filter((d) => d.code !== "partial" && d.code !== "unplaced_summary").length;

  const onApply = async (diagnosisIndex: number, suggestionId: string) => {
    try {
      const res = await applyFix.mutateAsync({ diagnosisIndex, optionIndex: optionIndex(suggestionId) });
      toast.success(t("glass.report.fixApplied"), { description: res.child_run_id ? t("glass.report.childQueued", { id: res.child_run_id }) : undefined });
      if (res.child_run_id) router.push(`/runs/${res.child_run_id}`);
    } catch {
      toast.error(t("glass.report.fixFailed"));
    }
  };

  const kindText = t(r.kind === "COURSE" ? "glass.dashboard.kindCourse" : "glass.dashboard.kindExam");
  const scope = r.horizon_params.weeks.length ? t("glass.dashboard.weeksN", { list: r.horizon_params.weeks.join(", ") }) : t("glass.dashboard.wholeTerm");

  return (
    <div data-testid="run-view">
      <Link href="/runs" className="mb-2 inline-flex items-center gap-1 text-[13px] text-label-2 hover:text-label-1">
        <ArrowLeft className="size-4" aria-hidden /> {t("runs.title")}
      </Link>
      <PageHeader
        title={t("glass.shell.runShort", { id: r.id })}
        subtitle={`${r.term_code} · ${kindText} · ${scope}${r.parent_run_id ? ` · ${t("glass.report.childOf", { id: r.parent_run_id })}` : ""}`}
        actions={
          <>
            <Button variant="outline" nativeButton={false} render={<a href={api.runs.exportUrl(r.id, "xlsx")} download />}>
              <Download /> {t("runs.export")}
            </Button>
            <Button nativeButton={false} render={<Link href="/generate" />}>
              {t("glass.report.editAndSolve")}
            </Button>
          </>
        }
      />

      {active ? (
        <GlassPanel material="regular" radius="2xl" className="max-w-xl p-6" render={<section role="status" aria-live="polite" data-testid="run-status" />}>
          <p className="flex items-center gap-2 type-title-3 text-label-1">
            <Loader2 className="size-5 animate-spin text-tint-text motion-reduce:animate-none" aria-hidden />
            {r.status === "QUEUED" ? t("generate.queued") : t("glass.shell.solving", { pct: r.progress })}
          </p>
          <Progress value={r.progress} aria-label={t("generate.status")} className="mt-4">
            <ProgressTrack>
              <ProgressIndicator />
            </ProgressTrack>
          </Progress>
          <SolveProgress r={r} />
          <p className="mt-3 text-[12px] text-label-3">{t("glass.report.solverInfo", { s: r.params.time_limit_s })}</p>
        </GlassPanel>
      ) : (
        <>
          <GlassPanel material="regular" radius="2xl" className="p-5 sm:p-6" render={<section aria-label={t("runs.report")} data-testid="run-hero" />}>
            <div className="grid gap-6 md:grid-cols-[auto_minmax(0,1fr)] xl:grid-cols-[auto_minmax(0,1fr)_minmax(280px,380px)]">
              <ScoreRing live={live} value={r.hard_score} partial={partial} label={partial ? t("glass.report.placedShort") : r.hard_score === 100 ? t("runs.status.FEASIBLE") : t("runs.status.INFEASIBLE")} />
              <div className="min-w-0">
                <Verdict r={r} headline={headline} />
                <p className="mt-1 text-[13px] text-label-2">{partial ? t("glass.report.partialHint", { n: n(unplaced) }) : null}</p>
                <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 pt-4 hairline-t sm:grid-cols-4">
                  {[
                    { k: t("glass.report.placed"), v: placed, suffix: total ? ` / ${n(total)}` : "" },
                    { k: t("runs.unplaced"), v: unplaced },
                    { k: t("glass.report.problems"), v: problems },
                  ].map((x) => (
                    <div key={x.k}>
                      <dt className="text-[12px] text-label-3">{x.k}</dt>
                      <dd className="text-[22px] leading-7 font-semibold tracking-[-0.017em] text-label-1">
                        <KpiNumber value={x.v} format={(v) => new Intl.NumberFormat(locale).format(v)} />
                        {x.suffix ? <span className="text-[13px] font-normal text-label-3">{x.suffix}</span> : null}
                      </dd>
                    </div>
                  ))}
                  <div>
                    <dt className="text-[12px] text-label-3">{t("runs.solveTime")}</dt>
                    <dd className="text-[22px] leading-7 font-semibold tracking-[-0.017em] text-label-1">{duration(r)}</dd>
                  </div>
                </dl>
              </div>
              <SoftBreakdown className="md:col-span-2 xl:col-span-1" score={r.soft_score} breakdown={r.objective_breakdown} weights={r.params.weights} />
            </div>
          </GlassPanel>

          <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
            <Tabs value={tab} onValueChange={(v) => setTab(String(v))} className="min-w-0">
              <TabsList>
                <TabsTrigger value="report" data-testid="tab-report">
                  {t("glass.report.problemsTab")} <span className="text-label-3 tabular-nums">{n(problems)}</span>
                </TabsTrigger>
                <TabsTrigger value="grid" data-testid="tab-grid">{t("runs.grid")}</TabsTrigger>
                <TabsTrigger value="constraints">
                  {t("glass.report.rulesTab")} <span className="text-label-3 tabular-nums">{constraints.data?.length ?? 0}</span>
                </TabsTrigger>
                <TabsTrigger value="chat" className="xl:hidden">{t("runs.chat")}</TabsTrigger>
              </TabsList>
              <TabsContent value="report" className="space-y-5 pt-4">
                {problems === 0 ? (
                  <Card>
                    <CardContent className="flex items-center gap-2 text-[13px] text-status-feasible-fg">
                      <CheckCircle2 className="size-4" aria-hidden /> {t("runs.noDiagnosis")}
                    </CardContent>
                  </Card>
                ) : null}
                {unplacedCards ? (
                  <Card data-testid="unplaced-section">
                    <CardContent>
                      <h3 className="type-headline text-label-1">
                        {t("glass.report.unplacedTitle")} <span className="font-normal text-label-3 tabular-nums">{n(cardCount(unplacedCards))}</span>
                      </h3>
                      <p className="text-[12.5px] text-label-2">{t("glass.report.unplacedHint")}</p>
                      <div className="mt-1">
                        {[...unplacedCards.codes.values()].flat().slice(0, allUnplaced ? undefined : 8).map((row) => (
                          <DiagnosisCard key={row.d.id} d={row.d} section="unplaced" count={row.count} applying={applyFix.isPending} onApply={(sid) => void onApply(row.d.index ?? Number(row.d.id), sid)} onChat={() => setTab("chat")} />
                        ))}
                      </div>
                      {!allUnplaced && [...unplacedCards.codes.values()].flat().length > 8 ? (
                        <Button size="sm" variant="secondary" onClick={() => setAllUnplaced(true)}>
                          {t("glass.report.showAll", { n: [...unplacedCards.codes.values()].flat().length })}
                        </Button>
                      ) : null}
                    </CardContent>
                  </Card>
                ) : null}
                {ruleCards ? (
                  <Card>
                    <CardContent>
                      <h3 className="type-headline text-label-1">
                        {t("glass.report.rulesTitle")} <span className="font-normal text-label-3 tabular-nums">{n(cardCount(ruleCards))}</span>
                      </h3>
                      <p className="text-[12.5px] text-label-2">{t("glass.report.rulesHint")}</p>
                      <div className="mt-1">
                        {[...ruleCards.codes.values()].flat().map((row) => (
                          <DiagnosisCard key={row.d.id} d={row.d} section="rules" count={row.count} applying={applyFix.isPending} onApply={(sid) => void onApply(row.d.index ?? Number(row.d.id), sid)} />
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                ) : null}
                {problems > 0 ? (
                  <Card>
                    <CardContent>{issues.data ? <IssueGroups runId={r.id} groups={issues.data.groups} /> : issues.isLoading ? <Skeleton className="h-24" /> : <LocalIssueGroups sections={sections} />}</CardContent>
                  </Card>
                ) : null}
              </TabsContent>
              <TabsContent value="grid" className="pt-4">
                {/* the calendar lives on its own page (owned by the calendar view); deep-link run + week */}
                <Card>
                  <CardContent className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-[13px] text-label-2">{t("glass.report.gridHint", { week: r.horizon_params.weeks[0] ?? 1 })}</p>
                    <Button nativeButton={false} render={<Link href={`/timetable?run=${r.id}&week=${r.horizon_params.weeks[0] ?? 1}`} />} data-testid="open-grid">
                      {t("glass.report.openGrid")}
                    </Button>
                  </CardContent>
                </Card>
              </TabsContent>
              <TabsContent value="constraints" className="pt-4">
                <Card>
                  <CardContent>
                    {(constraints.data ?? []).length === 0 ? <p className="text-[13px] text-label-2">{t("glass.report.noRules")}</p> : null}
                    <ul>
                      {(constraints.data ?? []).map((c) => (
                        <li key={c.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-2 text-[13px] [&:not(:last-child)]:hairline-b">
                          <span className="min-w-0 flex-1 text-label-1">{c.nl_text ?? t("glass.report.ruleOf", { kind: c.kind.replace(/_/g, " ") })}</span>
                          <span className="text-[12px] text-label-3">
                            {c.hardness === "hard" ? t("glass.report.must") : t("glass.report.try")}
                            {!c.enabled ? ` · ${t("glass.report.off")}` : ""}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              </TabsContent>
              <TabsContent value="chat" className="pt-4 xl:hidden">
                <ChatPanel runId={r.id} className="h-[70dvh]" />
              </TabsContent>
            </Tabs>
            <div className="hidden xl:block">
              <ChatPanel runId={r.id} className="sticky top-16 h-[calc(100dvh-120px)]" />
            </div>
          </div>
        </>
      )}
      <span className="sr-only" aria-live="polite">
        {finished ? `${t("glass.shell.runShort", { id: r.id })}: ${runStatusBadge(r, t).label}` : ""}
      </span>
    </div>
  );
}
