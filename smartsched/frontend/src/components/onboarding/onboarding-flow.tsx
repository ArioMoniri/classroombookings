"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { AiNotice } from "@/components/admin/ai/ai-kit";
import { AiUsageBanner } from "@/components/admin/ai/my-ai-usage";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { BusyGlyph } from "@/components/ui/busy-label";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { ACTIVE_JOB, councilApi, type CommitIn, type CommitOut, type DecisionIn } from "@/lib/api/council";
import { problemText } from "@/lib/api/error-text";
import { aiRefusalText } from "@/components/studio/write-it";
import { pairLang } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { CommitPanel } from "./commit-panel";
import { CouncilProgress } from "./council-progress";
import { useOnboardingCopy } from "./copy";
import { FileDrop, type DropOptions } from "./file-drop";
import { IntakeMemoryPanel, memoryKey } from "./intake-memory";
import { ReviewPanel } from "./review-panel";
import { RowsPanel, rowsKey } from "./rows-panel";
import { councilKey, useCouncilJob } from "./use-council-job";

/**
 * Universal onboarding: drop any files -> the Ingestion Council reads them one by one (live progress per
 * file and agent) -> review the low-confidence items -> commit into a term.
 */
export function OnboardingFlow({ initialJobId = null }: { initialJobId?: number | null } = {}) {
  const { t, n, locale } = useI18n();
  const qc = useQueryClient();
  const [jobId, setJobIdState] = useState<number | null>(initialJobId);
  // the job lives in the address: /onboarding/<id> (its own route, T-R2-20) or ?job=<id> (T-R1-26): a reload or a
  // shared link reopens it. window.history, not the router: the page needs no Suspense boundary and the URL
  // change re-renders nothing else
  const setJobId = (id: number | null) => {
    setJobIdState(id);
    try {
      const url = new URL(window.location.href);
      if (/\/onboarding\/\d+\/?$/.test(url.pathname)) {
        url.pathname = id === null ? url.pathname.replace(/\/\d+\/?$/, "") : url.pathname.replace(/\d+\/?$/, String(id));
        url.searchParams.delete("job");
      } else if (id === null) url.searchParams.delete("job");
      else url.searchParams.set("job", String(id));
      window.history.replaceState(window.history.state, "", url);
    } catch {
      /* no history API (tests): state only */
    }
  };
  useEffect(() => {
    // The job id comes from the address after hydration (the server does not know it): a deferred
    // update, so the first client render matches the server's and the effect sets no state synchronously.
    if (initialJobId !== null) return;
    const id = Number(new URLSearchParams(window.location.search).get("job"));
    if (!Number.isInteger(id) || id <= 0) return;
    const timer = window.setTimeout(() => setJobIdState(id), 0);
    return () => window.clearTimeout(timer);
  }, [initialJobId]);
  const recent = useQuery({ queryKey: ["council-jobs"], queryFn: () => councilApi.list(5), enabled: jobId === null });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CommitOut | null>(null);
  const [follow, setFollow] = useState(0);
  const c = useOnboardingCopy();
  const job = useCouncilJob(jobId, follow);
  const status = job.data?.status;
  const reviewable = status === "REVIEW" || status === "READY" || status === "COMMITTED";
  const review = useQuery({
    queryKey: ["council-review", jobId ?? 0, status, locale],
    queryFn: () => councilApi.review(jobId ?? 0, locale),
    enabled: jobId !== null && reviewable,
    placeholderData: (prev) => prev,
    // T-R2-20 / R2-M-25: the commit bar follows the review state. While blockers remain they may be decided
    // elsewhere (another tab, the API): poll, and refetch when the tab comes back, so "N engel" does not go stale
    refetchInterval: (q) => ((q.state.data?.blocking ?? 0) > 0 ? 5000 : false),
    refetchOnWindowFocus: true,
  });

  const start = async (files: File[], opts: DropOptions) => {
    setBusy(true);
    setError(null);
    try {
      const created = await councilApi.create(files, { mode: opts.forceGeneral ? "general" : "auto", lang: locale, ai: opts.useAi });
      qc.setQueryData(councilKey(created.id), created);
      setJobId(created.id);
      setResult(null);
    } catch (e) {
      // a coded AI refusal (422 / 429: quota, guard) reads in the user's words, like the Studio's (write-it.tsx)
      setError(aiRefusalText(e, pairLang(locale)) ?? problemText(e, locale) ?? (e instanceof Error ? e.message : String(e)));
    } finally {
      setBusy(false);
    }
  };

  const decide = async (decisions: DecisionIn[]) => {
    if (jobId === null) return;
    setBusy(true);
    try {
      const out = await councilApi.decide(jobId, decisions, locale);
      qc.setQueryData(["council-review", jobId, status, locale], out);
      if (out.rerun_queued) {
        // the job is RUNNING again until the re-read finished: show progress, hide commit, follow /events
        qc.setQueryData(councilKey(jobId), (old: typeof job.data) => (old ? { ...old, status: "RUNNING" as const } : old));
        setFollow((f) => f + 1);
      }
      await qc.invalidateQueries({ queryKey: councilKey(jobId) });
      void qc.invalidateQueries({ queryKey: memoryKey }); // the decisions are remembered for the next upload
    } finally {
      setBusy(false);
    }
  };

  const commit = async (body: CommitIn) => {
    if (jobId === null) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await councilApi.commit(jobId, body));
      await qc.invalidateQueries({ queryKey: councilKey(jobId) });
    } catch (e) {
      setError(problemText(e, locale) ?? (e instanceof Error ? e.message : String(e)));
    } finally {
      setBusy(false);
    }
  };

  // ① Dosyalar ② İnceleme ③ Fark ④ Kaydet: where the job is (phase19-intake, one header stepper)
  const stepNow = jobId === null || !job.data || ACTIVE_JOB.has(job.data.status) ? 0 : result ? 3 : review.data && review.data.blocking > 0 ? 1 : 2;
  const rerunning = review.data?.rerun_queued && job.data && ACTIVE_JOB.has(job.data.status);

  return (
    <div data-testid="onboarding" className={cn("space-y-4", job.data && !ACTIVE_JOB.has(job.data.status) && review.data && !result ? "max-lg:pb-20" : undefined)}>
      <PageHeader
        title={t("onboarding.title")}
        subtitle={t("onboarding.subtitle")}
        actions={
          jobId !== null ? (
            <Button variant="outline" onClick={() => { setJobId(null); setResult(null); }}>
              {t("onboarding.newJob")}
            </Button>
          ) : null
        }
      />
      <ol aria-label={c.stepsLabel} className="flex flex-wrap items-center gap-x-2 gap-y-1 type-callout" data-testid="onboarding-steps">
        {c.steps.map((label, i) => (
          <li key={label} aria-current={i === stepNow ? "step" : undefined} className={cn("flex items-center gap-2", i === stepNow ? "font-semibold text-label-1" : i < stepNow ? "text-label-1" : "text-label-2")}>
            <span aria-hidden className={cn("flex size-5 items-center justify-center rounded-full type-caption tnum", i === stepNow ? "bg-tint text-tint-foreground" : i < stepNow ? "bg-fill-1 text-label-1" : "bg-fill-3 text-label-2")}>{i + 1}</span>
            {label}
            {i < c.steps.length - 1 ? <span aria-hidden className="text-label-3">›</span> : null}
          </li>
        ))}
      </ol>
      {error ? <p className="type-callout text-status-infeasible-fg" role="alert">{error}</p> : null}
      {rerunning ? (
        <p role="status" className="flex items-center gap-2 type-callout text-label-1" data-testid="onboarding-rerun">
          <BusyGlyph /> {c.rerunning}
        </p>
      ) : null}
      {jobId === null ? (
        <>
          <AiUsageBanner />
          <FileDrop busy={busy} onStart={start} />
          <AiNotice />
        </>
      ) : null}
      {jobId === null && recent.data?.length ? (
        <nav aria-label={c.recentJobs} data-testid="onboarding-recent">
          <h2 className="mb-1 type-footnote font-semibold text-label-2">{c.recentJobs}</h2>
          <ul className="flex flex-wrap gap-2">
            {recent.data.map((j) => (
              <li key={j.id}>
                <Button size="sm" variant="outline" className="min-h-11 sm:min-h-8" aria-label={c.openJob(j.id)} onClick={() => { setResult(null); setJobId(j.id); }} data-testid={`onboarding-recent-${j.id}`}>
                  {c.recentJob(j.id, n(j.files), c.status[j.status] ?? j.status, j.created_at.slice(0, 16).replace("T", " "))}
                </Button>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
      {/* what earlier reviews taught the intake (resettable): inspect and forget before the next upload */}
      {jobId === null ? <IntakeMemoryPanel compact /> : null}
      {/* mobile-b phase 2 (CLS 0.55 at 390 on /onboarding/<id>): the progress card and the review land in slots that
          already hold their height, instead of the page growing twice as the job and then the review arrive */}
      {jobId !== null && !job.data && !job.isError ? (
        <div className="min-h-[70dvh] space-y-4" aria-busy="true" data-testid="onboarding-loading">
          <Skeleton className="h-40 rounded-2xl" />
          <Skeleton className="h-80 rounded-2xl" />
        </div>
      ) : null}
      {job.data ? <CouncilProgress job={job.data} /> : null}
      {job.data && reviewable && !ACTIVE_JOB.has(job.data.status) && !review.data && !review.isError ? (
        <div className="min-h-[50dvh]" aria-busy="true" data-testid="onboarding-review-loading">
          <Skeleton className="h-80 rounded-2xl" />
        </div>
      ) : null}
      {job.data?.status === "FAILED" ? <p className="type-callout text-status-infeasible-fg" role="alert">{job.data.error}</p> : null}
      {job.data && !ACTIVE_JOB.has(job.data.status) && review.data ? (
        <>
          <ReviewPanel review={review.data} busy={busy} onDecide={(d) => void decide(d)} />
          {review.data.content && jobId !== null ? (
            <RowsPanel
              jobId={jobId}
              onChanged={() => {
                void qc.invalidateQueries({ queryKey: ["council-review", jobId] });
                void qc.invalidateQueries({ queryKey: rowsKey(jobId) });
              }}
            />
          ) : null}
          <CommitPanel job={job.data} blocking={review.data.blocking} busy={busy} result={result} onCommit={(b) => void commit(b)} />
        </>
      ) : null}
    </div>
  );
}
