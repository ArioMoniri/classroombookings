"use client";
/**
 * One invigilation plan: status and actions, the progress while it is QUEUED / RUNNING (polled with backoff; the
 * backend's own phase and percentage as a determinate bar, and while it solves, when the percentage stays at 30,
 * the elapsed time against the time limit as the moving part; never a made-up percentage), then the headline, the counts, the
 * diagnoses with their suggestions (an INFEASIBLE plan says so at the top, with every missing invigilator
 * explained below) and the duties by date and room, or the load per person.
 */
import { Download, RefreshCw, Trash2, Upload } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FadePanel } from "@/components/analytics/fade-panel";
import { ResponsiveDialog } from "@/components/moderation/responsive-dialog";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { BusyButton, BusyGlyph } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { StatusDot } from "@/components/ui/data-table";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Progress, ProgressLabel } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText, pairOf } from "@/lib/api/analytics";
import { invigilationCsv, PLAN_ACTIVE, useActivatePlan, useDeletePlan, usePlan, useRerunPlan, type PlanDetail } from "@/lib/api/invigilation";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { DiagnosisList } from "./diagnosis-list";
import { allInstructorsParams, knownPhase, planIsEmpty, planStatusKey, planTone, poolEmptyDiag, progressView } from "./invigilation-model";
import { PeopleView } from "./people-view";
import { PostsView } from "./posts-view";

function useElapsed(since: string | null, running: boolean): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [running]);
  if (!since) return null;
  const start = new Date(since.endsWith("Z") ? since : `${since}Z`).getTime();
  return Number.isFinite(start) ? Math.max(0, Math.round((now - start) / 1000)) : null;
}

export function PlanDetailView({ planId, canEdit, onOpenPlan, onRerun }: { planId: number; canEdit: boolean; onOpenPlan: (id: number) => void; onRerun: () => void }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const person = params.get("person");
  const view = params.get("view") === "people" ? "people" : "posts";
  const q = usePlan(planId, null);
  const p = q.data;
  const running = p ? PLAN_ACTIVE.has(p.status) : false;
  const elapsed = useElapsed(p?.created_at ?? null, running);
  const [ask, setAsk] = useState<"publish" | "delete" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const activate = useActivatePlan();
  const remove = useDeletePlan();

  const go = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  if (q.isError) return <Alert tone="error" data-testid="invig-plan-error" action={<Button size="sm" variant="ghost" onClick={() => void q.refetch()}>{t("common.retry")}</Button>}>{errorText(q.error, lang)}</Alert>;
  if (!p) return <div className="flex flex-col gap-3" aria-busy="true" aria-label={t("invigilation.loadingPlan")}><Skeleton className="h-12 w-2/3" /><Skeleton className="h-24 w-full" /><Skeleton className="h-96 w-full" /></div>;

  const finished = !running;
  const publishable = finished && !p.is_active && ["OPTIMAL", "FEASIBLE", "INFEASIBLE"].includes(p.status) && !planIsEmpty(p);
  const confirm = async () => {
    setActionError(null);
    try {
      if (ask === "publish") {
        await activate.mutateAsync(p.id);
        toast.success(t("invigilation.publishedToast", { id: p.id }));
      } else if (ask === "delete") {
        await remove.mutateAsync(p.id);
        toast.success(t("invigilation.deletedToast", { id: p.id }));
        go({ plan: null, person: null });
      }
      setAsk(null);
    } catch (e) {
      setActionError(errorText(e, lang));
    }
  };

  return (
    <article className="flex min-w-0 flex-col gap-4" aria-labelledby="invig-plan-title" data-testid="invig-plan" data-status={p.status}>
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h2 id="invig-plan-title" className="type-title-2">{p.label?.trim() || t("invigilation.planN", { id: p.id })}</h2>
          <StatusDot tone={planTone(p)}>
            <span data-testid="invig-plan-status">{t(planStatusKey(p) as MessageKey)}</span>
          </StatusDot>
          {p.is_active ? <Badge tone="feasible" data-testid="invig-published">{t("invigilation.published")}</Badge> : null}
          {p.hard_score !== null ? <span className="type-footnote text-label-2 tnum">{t("invigilation.scores", { hard: n(p.hard_score), soft: p.soft_score === null ? "—" : n(p.soft_score) })}</span> : null}
          {p.parent_plan_id ? (
            <Button variant="link" size="sm" onClick={() => onOpenPlan(p.parent_plan_id!)}>{t("invigilation.childOf", { id: p.parent_plan_id })}</Button>
          ) : null}
        </div>
        {finished ? (
          <div className="flex flex-wrap items-center gap-2" data-testid="invig-actions">
            {canEdit ? (
              <>
                <Button variant="outline" size="sm" className="max-md:h-11" onClick={onRerun} data-testid="invig-rerun">
                  <RefreshCw aria-hidden />
                  {t("invigilation.rerun")}
                </Button>
                {publishable ? (
                  <Button size="sm" className="max-md:h-11" onClick={() => (setActionError(null), setAsk("publish"))} data-testid="invig-publish">
                    <Upload aria-hidden />
                    {t("invigilation.publish")}
                  </Button>
                ) : null}
              </>
            ) : null}
            {p.status !== "FAILED" && p.status !== "ERROR" ? (
              <>
                <Button variant="outline" size="sm" className="max-md:h-11" nativeButton={false} render={<a href={invigilationCsv.roster(p.id)} download />} data-testid="invig-roster-csv">
                  <Download aria-hidden />
                  {t("invigilation.rosterCsv")}
                </Button>
                <Button variant="outline" size="sm" className="max-md:h-11" nativeButton={false} render={<a href={invigilationCsv.load(p.id)} download />} data-testid="invig-load-csv">
                  <Download aria-hidden />
                  {t("invigilation.loadCsv")}
                </Button>
              </>
            ) : null}
            {canEdit && !p.is_active ? (
              <Button variant="ghost" size="sm" className="max-md:h-11" onClick={() => (setActionError(null), setAsk("delete"))} data-testid="invig-delete">
                <Trash2 aria-hidden />
                {t("common.delete")}
              </Button>
            ) : null}
          </div>
        ) : null}
      </header>

      {running ? (
        <RunningPanel p={p} elapsed={elapsed} />
      ) : (
        <FadePanel panelKey={`done-${p.id}`} className="flex min-w-0 flex-col gap-4">
          <Result p={p} canEdit={canEdit} onOpenPlan={onOpenPlan} />
          <DiagnosisList items={p.diagnosis} onPost={(key) => go({ view: null, post: key, person: null })} postLabel={(key) => { const x = p.posts.find((y) => y.key === key); return x ? `${x.room} · ${x.date.slice(8, 10)}.${x.date.slice(5, 7)} ${x.time}` : key; }} />
          <div className="flex flex-wrap items-center gap-3">
            <SegmentedControl
              aria-label={t("invigilation.views")}
              options={[
                { value: "posts", label: t("invigilation.view.posts"), testId: "invig-view-posts", controls: "invig-view-panel" },
                { value: "people", label: t("invigilation.view.people"), testId: "invig-view-people", controls: "invig-view-panel" },
              ]}
              value={view}
              onValueChange={(v) => go({ view: v === "posts" ? null : v })}
            />
            {person ? (
              <span className="flex items-center gap-2 type-callout" data-testid="invig-person-filter">
                {t("invigilation.personFilter", { name: p.people.find((x) => x.person_key === person)?.name ?? person })}
                <Button size="xs" variant="ghost" className="max-md:h-11" onClick={() => go({ person: null })}>{t("invigilation.clearPerson")}</Button>
              </span>
            ) : null}
          </div>
          <div id="invig-view-panel" role="tabpanel" aria-label={t(`invigilation.view.${view}`)}>
            {view === "posts" ? (
              <PostsView plan={p} canEdit={canEdit} person={person} focusPost={params.get("post")} />
            ) : (
              <PeopleView plan={p} canEdit={canEdit} onPerson={(key) => go({ view: null, person: key })} />
            )}
          </div>
        </FadePanel>
      )}

      <ResponsiveDialog
        open={ask !== null}
        onOpenChange={(o) => !o && setAsk(null)}
        alert
        title={ask === "delete" ? t("invigilation.deleteTitle", { id: p.id }) : t("invigilation.publishTitle", { id: p.id })}
        description={ask === "delete" ? t("invigilation.deleteBody") : (p.counts.missing ?? 0) > 0 ? t("invigilation.publishMissing", { n: n(p.counts.missing ?? 0) }) : t("invigilation.publishBody")}
        testId="invig-confirm"
        footer={
          <>
            <Button variant="ghost" className="max-md:h-11" onClick={() => setAsk(null)}>{t("common.cancel")}</Button>
            <BusyButton busy={activate.isPending || remove.isPending} busyLabel={t("busy.working")} variant={ask === "delete" ? "destructive" : "default"} className="max-md:h-11" onClick={() => void confirm()} data-testid="invig-confirm-ok">
              {ask === "delete" ? t("common.delete") : t("invigilation.publish")}
            </BusyButton>
          </>
        }
      >
        {actionError ? <Alert tone="error">{actionError}</Alert> : null}
      </ResponsiveDialog>
    </article>
  );
}

/** phase + the backend's percentage; while solving (pct stays at 30) the elapsed time against the limit moves */
export function RunningPanel({ p, elapsed }: { p: Pick<PlanDetail, "status" | "progress" | "params">; elapsed: number | null }) {
  const { t, n } = useI18n();
  const v = progressView(p, elapsed);
  const phase = knownPhase(v.phase) ? t(`invigilation.phase.${v.phase}`) : v.phase;
  return (
    <div className="flex flex-col gap-2 rounded-xl bg-tint-soft px-4 py-3" data-testid="invig-running" data-phase={v.phase} data-pct={v.pct ?? undefined}>
      <p className="flex items-center gap-2 type-headline" role="status" aria-live="polite" data-testid="invig-phase">
        <BusyGlyph className="size-4" />
        {phase}
      </p>
      {v.pct !== null ? (
        <Progress value={v.pct} aria-label={t("invigilation.progressLabel")} getAriaValueText={() => `${phase} · ${t("invigilation.pct", { n: n(v.pct ?? 0) })}`} className="gap-1.5" data-testid="invig-progress">
          <ProgressLabel className="type-footnote font-medium text-label-2">{t("invigilation.progressLabel")}</ProgressLabel>
          <span className="ml-auto type-footnote text-label-2 tnum" aria-hidden>{t("invigilation.pct", { n: n(v.pct) })}</span>
        </Progress>
      ) : null}
      {v.solving && v.meter !== null ? (
        <Progress value={v.meter} max={v.limit} aria-label={t("invigilation.solveTime")} getAriaValueText={() => t("invigilation.solveTimeValue", { s: n(elapsed ?? 0), limit: n(v.limit) })} className="gap-1.5" data-testid="invig-solve-time">
          <ProgressLabel className="type-footnote font-medium text-label-2">{t("invigilation.solveTime")}</ProgressLabel>
          <span className="ml-auto type-footnote text-label-2 tnum" aria-hidden>{t("invigilation.solveTimeValue", { s: n(elapsed ?? 0), limit: n(v.limit) })}</span>
        </Progress>
      ) : null}
      <p className="type-callout text-label-2 tnum">{t("invigilation.elapsed", { s: n(elapsed ?? 0), limit: n(v.limit) })}</p>
      {v.solving ? <p className="type-footnote text-label-2">{t("invigilation.solvingNote")}</p> : null}
      <p className="type-footnote text-label-2">{t("invigilation.runningHint")}</p>
    </div>
  );
}

function Result({ p, canEdit, onOpenPlan }: { p: PlanDetail; canEdit: boolean; onOpenPlan: (id: number) => void }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const c = p.counts;
  const st = p.stats;
  const pool = p.pool ?? null;
  const emptyPool = poolEmptyDiag(p.diagnosis);
  const rerun = useRerunPlan();
  const [poolError, setPoolError] = useState<string | null>(null);
  // the one-tap fix of an empty pool (T-R1-42): a child plan with the pool set to every instructor
  const widen = async () => {
    setPoolError(null);
    try {
      const res = await rerun.mutateAsync({ id: p.id, params: allInstructorsParams(p.params) });
      toast.success(t("invigilation.poolAllStarted", { id: res.plan_id }));
      onOpenPlan(res.plan_id);
    } catch (e) {
      setPoolError(errorText(e, lang));
    }
  };
  const poolLine = pool
    ? pool.instructor_pool === "exam_instructors"
      ? t("invigilation.poolMatch", { people: n(pool.exam_people), matched: n(pool.matched), ambiguous: n(pool.ambiguous), unmatched: n(pool.unmatched), size: n(pool.size) })
      : pool.instructor_pool === "all"
        ? t("invigilation.poolAll", { size: n(pool.size) })
        : t("invigilation.poolNone", { size: n(pool.size) })
    : null;
  const tiles: { key: string; label: string; value: number | null | undefined; tone?: "bad" }[] = [
    { key: "posts", label: t("invigilation.count.posts"), value: c.posts },
    { key: "required", label: t("invigilation.count.required"), value: c.required },
    { key: "filled", label: t("invigilation.count.filled"), value: c.filled },
    { key: "missing", label: t("invigilation.count.missing"), value: c.missing, tone: (c.missing ?? 0) > 0 ? "bad" : undefined },
    { key: "people", label: t("invigilation.count.people"), value: c.people },
  ];
  return (
    <section aria-label={t("invigilation.result")} className="flex flex-col gap-3">
      {planIsEmpty(p) ? (
        <Alert tone="warning" title={t("invigilation.emptyTitle")} data-testid="invig-empty">
          {p.empty_reason ? pairOf(p.empty_reason, lang) : t("invigilation.emptyBody")}
        </Alert>
      ) : p.status === "INFEASIBLE" ? (
        <Alert tone="error" title={t("invigilation.infeasibleTitle", { n: n(c.missing ?? 0) })} data-testid="invig-infeasible">
          {t("invigilation.infeasibleBody")}
        </Alert>
      ) : p.status === "FAILED" || p.status === "ERROR" ? (
        <Alert tone="error" title={t("invigilation.failedTitle")} data-testid="invig-failed">
          {p.error || t("invigilation.failedBody")}
        </Alert>
      ) : (c.missing ?? 0) > 0 ? (
        <Alert tone="warning">{t("invigilation.missingWarn", { n: n(c.missing ?? 0) })}</Alert>
      ) : null}
      {emptyPool && !PLAN_ACTIVE.has(p.status) ? (
        <Alert
          tone="error"
          title={t("invigilation.poolEmptyTitle")}
          data-testid="invig-pool-empty"
          action={
            canEdit && pool?.instructor_pool !== "all" ? (
              <BusyButton size="sm" busy={rerun.isPending} busyLabel={t("invigilation.form.starting")} className="max-md:h-11" onClick={() => void widen()} data-testid="invig-pool-all">
                {t("invigilation.poolAllRerun")}
              </BusyButton>
            ) : undefined
          }
        >
          {emptyPool.text?.[lang] || emptyPool.text?.tr}
          {poolError ? <span className="mt-1 block text-status-infeasible-fg">{poolError}</span> : null}
        </Alert>
      ) : null}
      {p.headline ? <p className="type-title-3" data-testid="invig-headline">{pairOf(p.headline, lang)}</p> : null}
      {poolLine ? <p className="type-footnote text-label-2 tnum" data-testid="invig-pool-line">{poolLine}</p> : null}
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5" data-testid="invig-counts">
        {tiles.map((x) => (
          <li key={x.key} className="flex min-w-0 flex-col gap-0.5 rounded-xl bg-card p-3 edge-hairline" data-key={x.key}>
            <span className="truncate type-footnote text-label-2">{x.label}</span>
            <span className={x.tone === "bad" ? "type-title-3 text-status-infeasible-fg tnum" : "type-title-3 tnum"}>{x.value === null || x.value === undefined ? "—" : n(x.value)}</span>
          </li>
        ))}
      </ul>
      {typeof st.max_periods === "number" && typeof st.fair_share_periods === "number" ? (
        <p className="type-footnote text-label-2 tnum">{t("invigilation.fairness", { max: n(st.max_periods), fair: n(st.fair_share_periods), wall: n(Number(st.wall_s ?? 0)) })}</p>
      ) : null}
    </section>
  );
}
