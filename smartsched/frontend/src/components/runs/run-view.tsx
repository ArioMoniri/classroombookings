"use client";

import { ArrowLeft, Download, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { ChatPanel } from "@/components/chat/chat-panel";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Timetable } from "@/components/timetable/timetable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress, ProgressIndicator, ProgressTrack } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { optionIndex } from "@/lib/api/adapters";
import { api } from "@/lib/api/endpoints";
import { useApplyFix, useConstraints, useRun } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { DiagnosisCard } from "./diagnosis-card";
import { RUN_STATUS_KIND, durationLabel, horizonLabel, partialCounts, runStatusBadge } from "./runs-list";
import { ScoreRing } from "./score-ring";
import { SoftBreakdown } from "./soft-breakdown";

export function RunView({ id }: { id: number }) {
  const { t, n } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") ?? "report";
  const run = useRun(id);
  const constraints = useConstraints({ run_id: id });
  const applyFix = useApplyFix(id);
  const r = run.data;
  const setTab = (next: string) => {
    const sp = new URLSearchParams(params.toString());
    sp.set("tab", next);
    router.replace(`/runs/${id}?${sp.toString()}`);
  };
  if (run.isError) return <p className="text-muted-foreground">{t("runs.notFound")}</p>;
  if (!r) return <Skeleton className="h-64 rounded-xl" />;
  const active = r.status === "QUEUED" || r.status === "RUNNING";
  const onApply = async (diagnosisIndex: number, suggestionId: string) => {
    try {
      const res = await applyFix.mutateAsync({ diagnosisIndex, optionIndex: optionIndex(suggestionId) });
      toast.success(t("runs.applied"), { description: res.message });
      if (res.child_run_id) router.push(`/runs/${res.child_run_id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e)); // 422: no structured fix for this suggestion
    }
  };
  return (
    <div data-testid="run-view">
      <Link href="/runs" className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> {t("runs.title")}</Link>
      <PageHeader
        title={`Run #${r.id} — ${r.term_code}`}
        subtitle={`${t(r.kind === "COURSE" ? "generate.course" : "generate.exam")} · ${horizonLabel(r, t)}${r.parent_run_id ? ` · ${t("runs.parent", { id: r.parent_run_id })}` : ""}`}
        actions={
          <>
            <StatusBadge {...(active ? { kind: RUN_STATUS_KIND[r.status], label: `${t(`runs.status.${r.status}`)} ${r.progress}%` } : runStatusBadge(r, t))} />
            <Button variant="outline" size="sm" nativeButton={false} render={<a href={api.runs.exportUrl(r.id, "xlsx")} download />}><Download /> {t("runs.export")}</Button>
            <Button size="sm" variant="outline" nativeButton={false} render={<Link href="/generate" />}>{t("runs.resolve")}</Button>
          </>
        }
      />
      {active ? (
        <Card className="mx-auto max-w-xl" role="status" aria-live="polite" data-testid="run-status">
          <CardContent className="space-y-3 py-6 text-center">
            <Loader2 className="mx-auto size-8 animate-spin text-primary" aria-hidden />
            <p className="text-lg font-medium">{r.status === "QUEUED" ? t("generate.queued") : t("generate.progress", { pct: r.progress })}</p>
            <Progress value={r.progress} aria-label={t("generate.status")}><ProgressTrack><ProgressIndicator /></ProgressTrack></Progress>
            <p className="text-xs text-muted-foreground">CP-SAT · {t("generate.timeLimit")} {r.params.time_limit_s}s · seed {r.params.seed}</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 rounded-xl border bg-card p-4 md:grid-cols-[auto_1fr] lg:grid-cols-[auto_1fr_auto]" role="group" aria-label={t("runs.report")}>
            <ScoreRing value={r.hard_score} partial={partialCounts(r)} label={partialCounts(r) ? t("runs.partialRing", partialCounts(r) ?? {}) : r.hard_score === 100 ? t("runs.status.FEASIBLE") : t("runs.status.INFEASIBLE")} />
            <SoftBreakdown score={r.soft_score} breakdown={r.objective_breakdown} weights={r.params.weights} />
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm lg:grid-cols-1">
              <dt className="text-muted-foreground">{t("runs.assignments")}</dt><dd className="tabular-nums">{n(Number(r.stats.events ?? 0))}</dd>
              <dt className="text-muted-foreground">{t("runs.unplaced")}</dt><dd className="tabular-nums">{n(Number(r.stats.unplaced ?? 0))}</dd>
              <dt className="text-muted-foreground">{t("grid.conflict")}</dt><dd className="tabular-nums">{n(Number(r.stats.conflicts ?? 0))}</dd>
              <dt className="text-muted-foreground">{t("runs.solveTime")}</dt><dd className="tabular-nums">{durationLabel(r)}</dd>
            </dl>
          </div>
          {r.prompt_text ? <p className="mt-2 text-xs text-muted-foreground">{t("runs.prompt")}: “{r.prompt_text}”</p> : null}
          <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_400px]">
            <Tabs value={tab} onValueChange={(v) => setTab(String(v))} className="min-w-0">
              <TabsList>
                <TabsTrigger value="report" data-testid="tab-report">{t("runs.diagnosis")} ({r.diagnosis.length})</TabsTrigger>
                <TabsTrigger value="grid" data-testid="tab-grid">{t("runs.grid")}</TabsTrigger>
                <TabsTrigger value="constraints">{t("runs.constraints")} ({constraints.data?.length ?? 0})</TabsTrigger>
                <TabsTrigger value="chat" className="xl:hidden">{t("runs.chat")}</TabsTrigger>
              </TabsList>
              <TabsContent value="report" className="space-y-3 pt-3">
                {r.diagnosis.length === 0 ? (
                  <div className="rounded-xl border border-status-feasible-border bg-status-feasible/40 p-6 text-center text-sm text-status-feasible-fg">{t("runs.noDiagnosis")}</div>
                ) : (
                  r.diagnosis.map((d) => <DiagnosisCard key={d.id} d={d} applying={applyFix.isPending} onApply={(sid) => void onApply(d.index ?? Number(d.id) ?? 0, sid)} onChat={() => setTab("chat")} />)
                )}
              </TabsContent>
              <TabsContent value="grid" className="pt-3">
                <Timetable runId={r.id} week={r.horizon_params.weeks[0] ?? 7} className="h-[calc(100dvh-280px)] min-h-[480px]" />
              </TabsContent>
              <TabsContent value="constraints" className="pt-3">
                <ul className="divide-y rounded-xl border bg-card">
                  {(constraints.data ?? []).map((c) => (
                    <li key={c.id} className="flex flex-wrap items-center gap-2 px-4 py-2 text-sm">
                      <Badge variant={c.hardness === "hard" ? "default" : "secondary"}>{c.hardness}</Badge>
                      <span className="font-mono text-xs">{c.kind}</span>
                      <span className="text-muted-foreground">{c.nl_text ?? JSON.stringify(c.params)}</span>
                      <span className="ml-auto flex items-center gap-2 text-xs text-muted-foreground"><Badge variant="outline">{c.source}</Badge> w{c.weight}{!c.enabled ? " · off" : ""}</span>
                    </li>
                  ))}
                </ul>
              </TabsContent>
              <TabsContent value="chat" className="pt-3 xl:hidden">
                <ChatPanel runId={r.id} className="h-[60dvh]" />
              </TabsContent>
            </Tabs>
            <div className="hidden xl:block">
              <ChatPanel runId={r.id} className="sticky top-16 h-[calc(100dvh-120px)]" />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

