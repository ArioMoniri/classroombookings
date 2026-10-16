"use client";

import { AlertTriangle, ArrowLeft, CheckCircle2, Download, XOctagon } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ChatPanel } from "@/components/chat/chat-panel";
import { PageHeader } from "@/components/common/page-header";
import { KpiNumber } from "@/components/dashboard/kpi-number";
import { useRememberRunOnView } from "@/components/shell/workspace";
import { Button } from "@/components/ui/button";
import { BusyGlyph } from "@/components/ui/busy-label";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { GlassPanel } from "@/components/ui/glass-panel";
import { TaskRows, type TaskRow } from "@/components/ui/beautifului/task-rows";
import { Progress, ProgressIndicator, ProgressTrack } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { optionIndex } from "@/lib/api/adapters";
import { api } from "@/lib/api/endpoints";
import { useApplyFix, useConstraints, useRun, useRuns } from "@/lib/api/hooks";
import type { ScheduleRun } from "@/lib/api/schemas";
import { useRunDataIssues, useRunSummary } from "@/lib/api/shell-extra";
import { useI18n } from "@/lib/i18n/provider";
import { DiagnosisCard } from "./diagnosis-card";
import { groupDiagnoses } from "./diagnosis-format";
import { IssueGroups, LocalIssueGroups } from "./issue-groups";
import { isImportBoard, partialCounts, runStatusBadge, useDuration } from "./runs-list";
import { SoftBreakdown } from "./soft-breakdown";
import { usePermissions } from "@/lib/permissions";
import { CancelRunButton } from "./cancel-run";
import { MissingWeeks } from "./missing-weeks";
import { BaselineRunCard } from "./baseline-card";
import { RunPolicyLine } from "./relaxation";
import { ResolveRunButton } from "./resolve-run";
import { isBaselineRun } from "@/lib/api/council";
import { PublishRunButton } from "./publish-run";
import { runIssueCounts, summaryExtras, verdictExceptions, waiverOf, type VerdictException } from "./run-truth";
import { useCalendarIndex } from "@/lib/api/calendar";

/** Built-in rule names as the planner says them (the solver's codes are English). */
const RULE_TR: Record<string, string> = { capacity: "kapasite", room_tags: "derslik özelliği", tags: "derslik özelliği", pins: "sabitlenen derslik", fixed_times: "sabit saat", forbids: "yasak derslik", locks: "kilitli derslik" };

/** The status headline: honest for partial runs (amber "660/683 placed · no rule broken", never green 100/100). */
function Verdict({ r, headline, exceptions = [] }: { r: ScheduleRun; headline?: string; exceptions?: VerdictException[] }) {
  const { t, n, locale } = useI18n();
  const partial = partialCounts(r);
  const complete = !partial && (r.status === "FEASIBLE" || r.status === "OPTIMAL");
  if ((partial || complete) && exceptions.length) {
    // never "no rule broken" while a waiver, a grid conflict or a too-small locked room is on record (M-06..M-08)
    const ruleName = (k: string) => (locale === "tr" ? (RULE_TR[k] ?? k) : k.replace(/_/g, " "));
    return (
      <div className="flex items-start gap-2 text-status-warning-fg" data-testid="run-verdict" data-state="exceptions">
        <AlertTriangle className="mt-1 size-5 shrink-0 stroke-[2]" aria-hidden />
        <div>
          <p className="type-title-3">{partial ? t("glass.report.partialHeld", { placed: n(partial.placed), total: n(partial.total) }) : t("glass.report.heldWithExceptions")}</p>
          <ul className="mt-1 list-disc pl-5 type-callout text-label-1" data-testid="verdict-exceptions">
            {exceptions.map((e) => (
              <li key={e.key} data-key={e.key}>{t(`glass.report.exc.${e.key}`, { n: n(e.n), rules: (e.rules ?? []).map(ruleName).join(", ") })}</li>
            ))}
          </ul>
        </div>
      </div>
    );
  }
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
      className="mt-4 ![background:var(--fill-3)] ![backdrop-filter:none] ![-webkit-backdrop-filter:none] !edge-hairline"
    />
  );
}

export function RunView({ id }: { id: number }) {
  const { t, n, locale } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") ?? "report";
  const run = useRun(id);
  const canPlan = usePermissions().can("planning.edit");
  const constraints = useConstraints({ run_id: id });
  const applyFix = useApplyFix(id);
  const duration = useDuration();
  const r = run.data;
  const active = r ? r.status === "QUEUED" || r.status === "RUNNING" : false;
  const finished = Boolean(r) && !active;
  // every finished run: an imported board has no solver diagnoses but the data checks still find issues (M-08)
  const issues = useRunDataIssues(id, finished);
  // the grid's own conflict / capacity flags, so the report and the grid header count the same things (M-07)
  const index = useCalendarIndex(finished ? id : null);
  // the term's published run of this kind (the one a publish replaces)
  const termRuns = useRuns(r ? { term_id: r.term_id } : undefined, { enabled: Boolean(r) && finished });
  const publishedId = termRuns.data?.find((x) => x.is_active && x.kind === r?.kind && x.id !== r?.id)?.id ?? null;
  const summary = useRunSummary(id, finished);
  useRememberRunOnView(r?.term_id, r?.id);
  const [allUnplaced, setAllUnplaced] = useState(false);
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
  const solverProblems = r.diagnosis.filter((d) => d.code !== "partial" && d.code !== "unplaced_summary").length;
  const dataProblems = issues.data ? issues.data.groups.reduce((a, g) => a + g.items.filter((i) => i.severity !== "info").length, 0) : 0;
  const extras = summaryExtras(summary.data as Record<string, unknown> | undefined);
  // the summary's data-issue count (2026-10-15) is the same definition the headline uses
  const problems = Math.max(solverProblems, dataProblems, extras.dataIssues ?? 0);
  const exceptions = verdictExceptions({
    waiver: waiverOf(r.stats_detail ?? r.stats, r.diagnosis),
    counts: index.data ? runIssueCounts(index.data.assignments) : { conflicts: 0, overCapacity: 0 },
    lockedTooSmall: issues.data?.groups.find((g) => g.code === "locked_room_too_small")?.count ?? 0,
  });

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
      <Link href="/runs" className="mb-2 inline-flex min-h-11 items-center gap-1 type-callout text-label-2 hover:text-label-1 pointer-fine:min-h-0">
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
            {/* a new solve with this run as its parent (stability on) and its relaxation policy */}
            {canPlan && finished && r.status !== "CANCELLED" ? <ResolveRunButton run={r} autoOpen={params.get("resolve") === "1"} /> : null}
            <Button nativeButton={false} render={<Link href="/generate" />}>
              {t("glass.report.editAndSolve")}
            </Button>
          </>
        }
      />

      {active ? (
        <GlassPanel material="regular" radius="2xl" className="max-w-xl p-6" render={<section role="status" aria-live="polite" data-testid="run-status" />}>
          <p className="flex items-center gap-2 type-title-3 text-label-1">
            <BusyGlyph className="size-5 text-tint-text" />
            {r.status === "QUEUED" ? t("generate.queued") : t("glass.shell.solving", { pct: r.progress })}
          </p>
          <Progress value={r.progress} aria-label={t("generate.status")} className="mt-4">
            <ProgressTrack>
              <ProgressIndicator />
            </ProgressTrack>
          </Progress>
          <SolveProgress r={r} />
          <p className="mt-3 type-footnote text-label-3">{t("glass.report.solverInfo", { s: r.params.time_limit_s })}</p>
          {canPlan ? <CancelRunButton runId={r.id} className="mt-3" /> : null}
        </GlassPanel>
      ) : (
        <>
          {/* One plain card: the headline sentence, then one KPI row (Vercel H7). The 517/530 ring gauge is gone — it
              repeated the KPI and the headline (review 2026-10-15 §3 Run report). */}
          <Card className="gap-0 p-5 sm:p-6" role="region" data-testid="run-hero" aria-label={t("runs.report")}>
            <div className="grid gap-6 @container/hero xl:grid-cols-[minmax(0,1fr)_minmax(280px,380px)]">
              <div className="min-w-0">
                <Verdict r={r} headline={headline} exceptions={exceptions} />
                {partial ? <p className="mt-1 type-callout text-label-2">{t("glass.report.partialHint", { n: n(unplaced) })}</p> : null}
                <MissingWeeks runId={r.id} stats={r.stats_detail ?? r.stats} />
                <RunPolicyLine r={r} />
                {canPlan && finished && r.status !== "CANCELLED" ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <PublishRunButton run={r} published={publishedId} exceptions={exceptions} />
                  </div>
                ) : null}
                <dl className="mt-5 grid gap-x-6 gap-y-4 pt-4 hairline-t [grid-template-columns:repeat(auto-fit,minmax(8.5rem,1fr))]">
                  {[
                    { k: t("glass.report.placed"), v: placed, suffix: total ? ` / ${n(total)}` : "" },
                    { k: t("runs.unplaced"), v: unplaced },
                    { k: t("glass.report.problems"), v: problems },
                  ].map((x) => (
                    <div key={x.k} className="min-w-0">
                      <dt className="type-footnote text-label-2">{x.k}</dt>
                      <dd className="flex items-baseline type-kpi text-label-1">
                        <KpiNumber value={x.v} format={(v) => new Intl.NumberFormat(locale).format(v)} />
                        {x.suffix ? <span className="type-callout font-normal text-label-2">{x.suffix}</span> : null}
                      </dd>
                    </div>
                  ))}
                  <div className="min-w-0">
                    <dt className="type-footnote text-label-2">{t("runs.solveTime")}</dt>
                    <dd className="type-kpi text-label-1">{duration(r)}</dd>
                  </div>
                </dl>
                {isBaselineRun(r) ? <BaselineRunCard r={r} /> : null}
                {extras.forcedOverrides.length ? (
                  <section className="mt-4 grid gap-1.5 rounded-lg bg-status-warning px-3 py-2" data-testid="forced-overrides" aria-labelledby="forced-title">
                    <h3 id="forced-title" className="flex items-center gap-1.5 type-callout font-semibold text-status-warning-fg">
                      <AlertTriangle aria-hidden className="size-4" />
                      {locale === "tr" ? `${n(extras.forcedOverrides.length)} gerekçeli zorunlu taşıma` : `${n(extras.forcedOverrides.length)} forced move(s) with a reason`}
                    </h3>
                    <ul className="grid gap-1 type-footnote text-label-1">
                      {extras.forcedOverrides.map((o, i) => (
                        <li key={i}>
                          <span className="font-medium">{o.reason}</span>
                          {o.conflicts.length ? <span className="text-label-2"> · {o.conflicts.slice(0, 3).join("; ")}</span> : null}
                          {o.by_name ? <span className="text-label-2"> · {o.by_name}</span> : null}
                          {o.at ? <time dateTime={o.at} className="text-label-2"> · {new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(o.at))}</time> : null}
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}
              </div>
              <SoftBreakdown score={r.soft_score} breakdown={r.objective_breakdown} weights={r.params.weights} />
            </div>
          </Card>

          <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(0,1fr)_400px]">
            <Tabs value={tab} onValueChange={(v) => setTab(String(v))} className="min-w-0">
              {/* phones: the four tabs are wider than 390 px; they scroll in their own row (MOBILE.md M-01), padded so the
                  triggers' touch hit areas are not clipped by the scroller (tokens.md A.9 hit areas) */}
              <div className="max-w-full overflow-x-auto [scrollbar-width:none] pointer-coarse:-my-1.5 pointer-coarse:py-1.5" data-testid="run-tabs-scroller">
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
              </div>
              <TabsContent value="report" keepMounted className="space-y-5 pt-4 data-[hidden]:hidden">
                {problems === 0 ? (
                  <Card>
                    <CardContent className="flex items-center gap-2 type-callout text-status-feasible-fg">
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
                      <p className="type-footnote text-label-2">{t("glass.report.unplacedHint")}</p>
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
                      <p className="type-footnote text-label-2">{t("glass.report.rulesHint")}</p>
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
                    <p className="type-callout text-label-2">{t("glass.report.gridHint", { week: r.horizon_params.weeks[0] ?? 1 })}</p>
                    <Button nativeButton={false} render={<Link href={`/timetable?run=${r.id}&week=${r.horizon_params.weeks[0] ?? 1}`} />} data-testid="open-grid">
                      {t("glass.report.openGrid")}
                    </Button>
                  </CardContent>
                </Card>
              </TabsContent>
              <TabsContent value="constraints" className="pt-4">
                <Card>
                  <CardContent>
                    {(constraints.data ?? []).length === 0 ? <p className="type-callout text-label-2">{t("glass.report.noRules")}</p> : null}
                    <ul>
                      {(constraints.data ?? []).map((c) => (
                        <li key={c.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-2 type-callout [&:not(:last-child)]:hairline-b">
                          <span className="min-w-0 flex-1 text-label-1">{c.nl_text ?? t("glass.report.ruleOf", { kind: c.kind.replace(/_/g, " ") })}</span>
                          <span className="type-footnote text-label-3">
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
