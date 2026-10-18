"use client";
/**
 * Gözetmen ataması (`/exams/invigilation?run=&plan=&tab=plans|pool&view=posts|people`): invigilator plans of an exam
 * run (backend /invigilation/*; CP-SAT, one worker, fixed seed) and the staff pool with its rules. A plan is solved
 * in the job queue (202 + poll with backoff); its result names every missing invigilator (INFEASIBLE is shown,
 * never hidden), and a planner can lock a duty, reassign it to a free candidate, re-run keeping the locks and
 * publish one plan per exam run. Writes need planning.edit; viewers read.
 */
import { Plus } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { pageActionsCapsule } from "@/components/admin/kit";
import { PageHeader } from "@/components/common/page-header";
import { useRunText } from "@/components/compare/run-text";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatusDot } from "@/components/ui/data-table";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText, pairOf, useRunOptions } from "@/lib/api/analytics";
import { PLAN_ACTIVE, useAllPlans, usePlans, type PlanBrief } from "@/lib/api/invigilation";
import type { ScheduleRun } from "@/lib/api/schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import { isBoardRun, knownPhase, planStatusKey, planTone, progressView } from "./invigilation-model";
import { PlanDetailView } from "./plan-detail";
import { PlanFormDialog } from "./plan-form";
import { PoolView } from "./pool-view";

const STAFFABLE = new Set(["OPTIMAL", "FEASIBLE", "FEASIBLE_PARTIAL"]);
const int = (v: string | null) => (v && /^\d+$/.test(v) ? Number(v) : null);

/** the default exam run: the one of the newest plan, else the active term's published exam run, else its newest
 *  solved one (an imported board, whose rows carry no exam link, only when nothing else exists; T-R1-42) */
export function pickExamRun(runs: readonly ScheduleRun[], termId: number | undefined, newestPlanRun?: number | null): ScheduleRun | undefined {
  const exams = runs.filter((r) => r.kind === "EXAM" && STAFFABLE.has(r.status));
  const planned = exams.find((r) => r.id === newestPlanRun);
  if (planned) return planned;
  const inTerm = exams.filter((r) => r.term_id === termId);
  return inTerm.find((r) => r.is_active) ?? inTerm.find((r) => !isBoardRun(r)) ?? inTerm[0] ?? exams.find((r) => r.is_active) ?? exams.find((r) => !isBoardRun(r)) ?? exams[0];
}

export function InvigilationView() {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { can } = usePermissions();
  const canEdit = can("planning.edit");
  const { term } = useActiveTerm();
  const runs = useRunOptions();
  const runText = useRunText();
  const exams = useMemo(() => (runs.data ?? []).filter((r) => r.kind === "EXAM" && STAFFABLE.has(r.status)), [runs.data]);
  const allPlans = useAllPlans();
  const urlRun = int(params.get("run"));
  const run = exams.find((r) => r.id === urlRun) ?? pickExamRun(runs.data ?? [], term?.id, allPlans.data?.[0]?.exam_run_id);
  const tab = params.get("tab") === "pool" ? "pool" : "plans";
  const plans = usePlans(run?.id ?? null);
  const urlPlan = int(params.get("plan"));
  const planId = urlPlan ?? plans.data?.find((p) => p.is_active)?.id ?? plans.data?.[0]?.id ?? null;
  const [form, setForm] = useState<"new" | "rerun" | null>(null);

  const href = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    return `${pathname}?${next.toString()}`;
  };
  const go = (patch: Record<string, string | null>) => router.replace(href(patch), { scroll: false });

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="invigilation-page">
      <PageHeader
        title={t("invigilation.title")}
        subtitle={t("invigilation.subtitle")}
        actions={canEdit && run && tab === "plans" ? (
          // a capsule above the tab bar below lg (MOBILE.md M-05; mobile-b phase 2: it sat at y 145)
          <div data-slot="page-actions" className={pageActionsCapsule}>
            <Button onClick={() => setForm("new")} data-testid="invig-new">
              <Plus aria-hidden />
              {t("invigilation.newPlan")}
            </Button>
          </div>
        ) : undefined}
      />
      <section aria-label={t("invigilation.examRun")} className="flex flex-wrap items-end gap-3 rounded-xl bg-card p-3 edge-hairline">
        <label className="flex w-full min-w-0 flex-col gap-1 sm:w-auto sm:max-w-xl sm:flex-1">
          <span className="type-footnote font-medium text-label-2">{t("invigilation.examRun")}</span>
          <NativeSelect value={run?.id ?? ""} disabled={runs.isLoading || exams.length === 0} onChange={(e) => go({ run: e.target.value || null, plan: null, person: null })} data-testid="invig-run">
            {exams.length === 0 ? <option value="">{runs.isLoading ? t("invigilation.loadingRuns") : t("invigilation.noExamRuns")}</option> : null}
            {exams.map((r) => (
              <option key={r.id} value={r.id}>{`${r.term_code ?? ""} · ${runText(r)}${isBoardRun(r) ? ` · ${t("invigilation.noExamLinks")}` : ""}`}</option>
            ))}
          </NativeSelect>
        </label>
        <SegmentedControl
          aria-label={t("invigilation.sections")}
          options={[
            { value: "plans", label: t("invigilation.tab.plans"), testId: "invig-tab-plans", controls: "invig-panel-plans" },
            { value: "pool", label: t("invigilation.tab.pool"), testId: "invig-tab-pool", controls: "invig-panel-pool" },
          ]}
          value={tab}
          onValueChange={(v) => go({ tab: v === "plans" ? null : v })}
        />
      </section>

      {runs.isError ? <Alert tone="error">{errorText(runs.error, lang)}</Alert> : null}
      {run && tab === "plans" && isBoardRun(run) ? (
        <Alert tone="warning" title={t("invigilation.boardRunTitle")} data-testid="invig-board-run">
          {t("invigilation.boardRunBody")}
        </Alert>
      ) : null}
      {runs.isLoading || (tab === "plans" && run && plans.isLoading) ? (
        // mobile-b phase 2 (CLS 0.39–0.56): one placeholder of the panel's height until the runs and the plans are in,
        // instead of "Plan yok" flashing and the list and the detail pushing each other down
        <div className="grid min-h-[60dvh] min-w-0 gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]" aria-busy="true" data-testid="invig-loading">
          <div className="flex flex-col gap-2">
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-24 w-full" />
          </div>
          <Skeleton className="h-80 w-full rounded-2xl" />
        </div>
      ) : !runs.isLoading && exams.length === 0 ? (
        <div className="rounded-xl bg-fill-3 px-4 py-5" data-testid="invig-no-runs">
          <p className="type-headline">{t("invigilation.noExamRunsTitle")}</p>
          <p className="mt-1 type-callout text-label-2">{t("invigilation.noExamRunsBody")}</p>
        </div>
      ) : tab === "pool" ? (
        <div id="invig-panel-pool" role="tabpanel" aria-label={t("invigilation.tab.pool")}>
          <PoolView termId={run?.term_id ?? term?.id ?? null} canEdit={canEdit} />
        </div>
      ) : (
        <div id="invig-panel-plans" role="tabpanel" aria-label={t("invigilation.tab.plans")} className="grid min-w-0 gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <aside aria-label={t("invigilation.planList")} className="flex min-w-0 flex-col gap-2">
            <h2 className="type-headline">{t("invigilation.planList")}</h2>
            {plans.isLoading ? (
              <Skeleton className="h-24 w-full" />
            ) : plans.isError ? (
              <Alert tone="error">{errorText(plans.error, lang)}</Alert>
            ) : !plans.data?.length ? (
              <div className="rounded-xl bg-fill-3 px-3 py-3" data-testid="invig-no-plans">
                <p className="type-callout">{t("invigilation.noPlans")}</p>
                <p className="type-footnote text-label-2">{canEdit ? t("invigilation.noPlansHint") : t("invigilation.noPlansViewer")}</p>
              </div>
            ) : (
              <ul className="flex flex-col gap-1.5 max-lg:max-h-72 max-lg:overflow-auto" data-testid="invig-plans">
                {plans.data.map((p) => (
                  <PlanItem key={p.id} p={p} active={p.id === planId} href={href({ plan: String(p.id), person: null })} lang={lang} />
                ))}
              </ul>
            )}
          </aside>
          <div className="min-w-0">
            {planId !== null && run ? (
              <PlanDetailView key={planId} planId={planId} canEdit={canEdit} onOpenPlan={(id) => go({ plan: String(id), person: null })} onRerun={() => setForm("rerun")} />
            ) : null}
          </div>
        </div>
      )}
      {run ? <PlanFormDialog open={form !== null} mode={form ?? "new"} onOpenChange={(o) => !o && setForm(null)} examRunId={run.id} parent={planId !== null ? (plans.data?.find((p) => p.id === planId) ?? null) : null} onStarted={(id) => go({ plan: String(id), person: null })} /> : null}
    </div>
  );
}

function PlanItem({ p, active, href, lang }: { p: PlanBrief; active: boolean; href: string; lang: "tr" | "en" }) {
  const { t, n } = useI18n();
  const c = p.counts;
  return (
    <li>
      <Link
        href={href}
        scroll={false}
        aria-current={active ? "true" : undefined}
        className={cn(
          "flex min-w-0 flex-col gap-0.5 rounded-xl px-3 py-2 edge-hairline transition-colors duration-(--dur-fast) hover:bg-fill-2 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)",
          active ? "bg-tint-soft" : "bg-card",
        )}
        data-testid="invig-plan-item"
        data-status={p.status}
      >
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate type-headline">{p.label?.trim() || t("invigilation.planN", { id: p.id })}</span>
          {p.is_active ? <Badge tone="feasible">{t("invigilation.published")}</Badge> : null}
        </span>
        <span className="flex flex-wrap items-center gap-x-2 type-footnote text-label-2">
          <StatusDot tone={planTone(p)}>{t(planStatusKey(p) as MessageKey)}</StatusDot>
          {PLAN_ACTIVE.has(p.status) ? <PhaseText p={p} /> : null}
          {c.required !== null && c.filled !== null ? <span className="tnum">{t("invigilation.filledOf", { filled: n(c.filled), required: n(c.required) })}</span> : null}
          {p.parent_plan_id ? <span>{t("invigilation.childOf", { id: p.parent_plan_id })}</span> : null}
        </span>
        {p.headline ? <span className="line-clamp-2 type-caption text-label-3">{pairOf(p.headline, lang)}</span> : null}
      </Link>
    </li>
  );
}

/** a running plan's phase and percentage in the list ("Çözülüyor · %30"), as the backend reports them */
function PhaseText({ p }: { p: PlanBrief }) {
  const { t, n } = useI18n();
  const v = progressView(p, null);
  return (
    <span className="tnum" data-testid="invig-plan-phase">
      {knownPhase(v.phase) ? t(`invigilation.phase.${v.phase}`) : v.phase}
      {v.pct !== null ? ` · ${t("invigilation.pct", { n: n(v.pct) })}` : ""}
    </span>
  );
}
