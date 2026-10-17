"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { BusyGlyph } from "@/components/ui/busy-label";
import { cn } from "@/lib/utils";
import { ACTIVE_JOB, councilApi, type CommitIn, type CommitOut, type DecisionIn } from "@/lib/api/council";
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
export function OnboardingFlow() {
  const { t, n, locale } = useI18n();
  const qc = useQueryClient();
  const [jobId, setJobIdState] = useState<number | null>(null);
  // the job lives in the address (?job=<id>): a reload or a shared link reopens it (T-R1-26). window.history, not
  // the router: the page needs no Suspense boundary and the URL change re-renders nothing else
  const setJobId = (id: number | null) => {
    setJobIdState(id);
    try {
      const url = new URL(window.location.href);
      if (id === null) url.searchParams.delete("job");
      else url.searchParams.set("job", String(id));
      window.history.replaceState(window.history.state, "", url);
    } catch {
      /* no history API (tests): state only */
    }
  };
  useEffect(() => {
    // The job id comes from the address after hydration (the server does not know it): a deferred
    // update, so the first client render matches the server's and the effect sets no state synchronously.
    const id = Number(new URLSearchParams(window.location.search).get("job"));
    if (!Number.isInteger(id) || id <= 0) return;
    const timer = window.setTimeout(() => setJobIdState(id), 0);
    return () => window.clearTimeout(timer);
  }, []);
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
      setError(e instanceof Error ? e.message : String(e));
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
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  // ① Dosyalar ② İnceleme ③ Fark ④ Kaydet: where the job is (phase19-intake, one header stepper)
  const stepNow = jobId === null || !job.data || ACTIVE_JOB.has(job.data.status) ? 0 : result ? 3 : review.data && review.data.blocking > 0 ? 1 : 2;
  const rerunning = review.data?.rerun_queued && job.data && ACTIVE_JOB.has(job.data.status);

  return (
    <div data-testid="onboarding" className="space-y-4">
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
      {jobId === null ? <FileDrop busy={busy} onStart={start} /> : null}
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
      {job.data ? <CouncilProgress job={job.data} /> : null}
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
