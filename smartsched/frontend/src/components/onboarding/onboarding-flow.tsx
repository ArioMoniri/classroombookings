"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { ACTIVE_JOB, councilApi, type CommitIn, type CommitOut, type DecisionIn } from "@/lib/api/council";
import { useI18n } from "@/lib/i18n/provider";
import { CommitPanel } from "./commit-panel";
import { CouncilProgress } from "./council-progress";
import { FileDrop, type DropOptions } from "./file-drop";
import { ReviewPanel } from "./review-panel";
import { councilKey, useCouncilJob } from "./use-council-job";

/**
 * Universal onboarding: drop any files -> the Ingestion Council reads them one by one (live progress per
 * file and agent) -> review the low-confidence items -> commit into a term.
 */
export function OnboardingFlow() {
  const { t, locale } = useI18n();
  const qc = useQueryClient();
  const [jobId, setJobId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CommitOut | null>(null);
  const job = useCouncilJob(jobId);
  const status = job.data?.status;
  const reviewable = status === "REVIEW" || status === "READY" || status === "COMMITTED";
  const review = useQuery({
    queryKey: ["council-review", jobId ?? 0, status],
    queryFn: () => councilApi.review(jobId ?? 0),
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
      const out = await councilApi.decide(jobId, decisions);
      qc.setQueryData(["council-review", jobId, status], out);
      await qc.invalidateQueries({ queryKey: councilKey(jobId) });
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
      {error ? <p className="text-sm text-destructive" role="alert">{error}</p> : null}
      {jobId === null ? <FileDrop busy={busy} onStart={start} /> : null}
      {job.data ? <CouncilProgress job={job.data} /> : null}
      {job.data?.status === "FAILED" ? <p className="text-sm text-destructive" role="alert">{job.data.error}</p> : null}
      {job.data && !ACTIVE_JOB.has(job.data.status) && review.data ? (
        <>
          <ReviewPanel review={review.data} busy={busy} onDecide={(d) => void decide(d)} />
          <CommitPanel job={job.data} blocking={review.data.blocking} busy={busy} result={result} onCommit={(b) => void commit(b)} />
        </>
      ) : null}
    </div>
  );
}
