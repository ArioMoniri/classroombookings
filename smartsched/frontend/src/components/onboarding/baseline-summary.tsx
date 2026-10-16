"use client";
/**
 * Schedule map → baseline import run (P19-I5, backend `app/council/baseline.py`), in the onboarding Fark and Kaydet
 * steps.
 *
 * A commit writes the course entries of every schedule map in it (a weekly board, an ICS feed, an intake.v1 or a
 * general timetable) to the term's ONE run "Baseline: imported schedule" (`params.source = COUNCIL_BASELINE`). The
 * backend picks that run itself: the same board uploaded again updates the same rows, never a second run. So there is
 * nothing to choose; the Fark step says which run the map goes to (the term's existing baseline run, or a new one),
 * and after Kaydet the commit's `baseline_run` counts are shown with links to the run and to a re-solve that keeps it
 * (`/runs/{id}?resolve=1`: the run becomes the new solve's parent, so placements stay where the board has them).
 */
import { ArrowRight, Layers } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useRuns, useTerms } from "@/lib/api/hooks";
import type { ScheduleRun } from "@/lib/api/schemas";
import { isBaselineRun, type BaselineRunResult, type CouncilJob } from "@/lib/api/council";

export { isBaselineRun };
import { useI18n } from "@/lib/i18n/provider";

/** The job carries a schedule map when its files produced booking records (board cells, ICS events, timetables). */
export function hasScheduleMap(job: Pick<CouncilJob, "summary">): boolean {
  const records = job.summary.records;
  if (!records || typeof records !== "object") return false;
  return Number((records as Record<string, unknown>).booking ?? 0) > 0;
}

/** The term's baseline run (newest first), by term code: the run a commit's schedule map goes to. */
export function baselineFor(runs: ScheduleRun[] | undefined, termCode: string): ScheduleRun | undefined {
  const code = termCode.trim();
  if (!code) return undefined;
  return (runs ?? []).filter((r) => r.term_code === code && r.kind === "COURSE" && isBaselineRun(r)).sort((a, b) => b.id - a.id)[0];
}

/** Fark: where the schedule map will go (no choice: the backend keeps one baseline run per term). */
export function BaselinePreview({ job, termCode }: { job: CouncilJob; termCode: string }) {
  const { t } = useI18n();
  const map = hasScheduleMap(job);
  const terms = useTerms({ enabled: map });
  const term = terms.data?.find((x) => x.code === termCode.trim());
  // a term that does not exist yet has no baseline run: the commit creates both
  const runs = useRuns(term ? { term_id: term.id, kind: "COURSE", limit: 500 } : undefined, { enabled: map && !!term });
  if (!map) return null;
  const loading = terms.isLoading || (!!term && runs.isLoading);
  const existing = term ? baselineFor(runs.data, termCode) : undefined;
  return (
    <section aria-labelledby={`baseline-${job.id}`} className="grid gap-1.5 rounded-lg bg-fill-3 p-3 edge-hairline" data-testid="onboarding-baseline-preview" data-state={loading ? "loading" : existing ? "existing" : "new"}>
      <h3 id={`baseline-${job.id}`} className="flex items-center gap-2 type-headline text-label-1">
        <Layers className="size-4 text-label-3" aria-hidden />
        {t("baseline.title")}
      </h3>
      <p className="type-callout text-label-1">
        {loading
          ? t("baseline.checking")
          : existing
            ? t("baseline.intoExisting", { id: existing.id, term: termCode.trim() })
            : t("baseline.intoNew", { term: termCode.trim() })}
      </p>
      <p className="type-footnote text-label-2">{t("baseline.keeps")}</p>
      {existing ? (
        <Link href={`/runs/${existing.id}`} className="type-footnote font-medium text-tint-text underline-offset-4 hover:underline" data-testid="onboarding-baseline-existing">
          {t("baseline.openRun", { id: existing.id })}
        </Link>
      ) : null}
    </section>
  );
}

const EXTRA = ["clipped_outside_term", "entries_unplaceable", "exam_entries_skipped", "duplicates_in_commit"] as const;

/** Kaydet: the commit's `baseline_run` counts, the run and a re-solve that keeps it. */
export function BaselineResult({ baseline }: { baseline: BaselineRunResult }) {
  const { t, n } = useI18n();
  const extra = EXTRA.map((k) => ({ k, v: Number(baseline[k] ?? 0) })).filter((x) => x.v > 0);
  const rows: { k: string; v: number }[] = [
    { k: t("baseline.created"), v: baseline.created },
    { k: t("baseline.updated"), v: baseline.updated },
    { k: t("baseline.unchanged"), v: baseline.unchanged },
    { k: t("baseline.linked"), v: baseline.linked },
    { k: t("baseline.unlinked"), v: baseline.unlinked },
  ];
  return (
    <section aria-labelledby="baseline-result" className="grid gap-2 rounded-lg p-3 edge-hairline" data-testid="onboarding-baseline-result">
      <h3 id="baseline-result" className="flex items-center gap-2 type-headline text-label-1">
        <Layers className="size-4 text-label-3" aria-hidden />
        {baseline.run_created ? t("baseline.resultNew", { id: baseline.run_id }) : t("baseline.resultUpdated", { id: baseline.run_id })}
      </h3>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 type-callout sm:grid-cols-5">
        {rows.map((r) => (
          <div key={r.k} className="min-w-0">
            <dt className="type-footnote text-label-2">{r.k}</dt>
            <dd className="font-medium text-label-1" data-numeric>{n(r.v)}</dd>
          </div>
        ))}
      </dl>
      <p className="type-footnote text-label-2">{t("baseline.linkedHint")}</p>
      {extra.length ? (
        <ul className="grid gap-0.5 type-footnote text-status-warning-fg" data-testid="onboarding-baseline-skipped">
          {extra.map((x) => (
            <li key={x.k}>{t(`baseline.skip.${x.k}`, { n: n(x.v) })}</li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" nativeButton={false} render={<Link href={`/runs/${baseline.run_id}`} data-testid="onboarding-baseline-open" />}>
          {t("baseline.openRun", { id: baseline.run_id })}
        </Button>
        <Button size="sm" nativeButton={false} render={<Link href={`/runs/${baseline.run_id}?resolve=1`} data-testid="onboarding-baseline-resolve" />}>
          {t("baseline.resolve")}
          <ArrowRight aria-hidden />
        </Button>
      </div>
    </section>
  );
}
