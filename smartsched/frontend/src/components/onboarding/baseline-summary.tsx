"use client";
/**
 * Schedule map → baseline import run (P19-I5, backend `app/council/baseline.py`), in the onboarding Fark and Kaydet
 * steps.
 *
 * By default a commit writes the course entries of every schedule map in it (a weekly board, an ICS feed, an
 * intake.v1 or a general timetable) to the term's ONE run "Baseline: imported schedule" (`params.source =
 * COUNCIL_BASELINE`): the same board uploaded again updates the same rows, never a second run. The Kaydet step can
 * instead skip the map (`baseline: {mode: "skip"}`) or write it into another COURSE run of the term (`{mode: "run",
 * run_id}`) — `BaselineTargetPicker`.
 *
 * Fark reads the dry run's `result.baseline_run` (the same writer, rolled back): which run the map goes to (the
 * existing baseline run, a new one, the chosen run, or nowhere) and the counts it would write. After Kaydet the
 * commit's `baseline_run` counts are shown with links to the run and to a re-solve that keeps it
 * (`/runs/{id}?resolve=1`: the run becomes the new solve's parent, so placements stay where the board has them).
 */
import { ArrowRight, Layers } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useRuns, useTerms } from "@/lib/api/hooks";
import type { ScheduleRun } from "@/lib/api/schemas";
import { isBaselineRun, type BaselineRunResult, type BaselineTarget, type CouncilJob } from "@/lib/api/council";
import { useI18n } from "@/lib/i18n/provider";

export { isBaselineRun };

/** The job carries a schedule map when its files produced booking records (board cells, ICS events, timetables). */
export function hasScheduleMap(job: Pick<CouncilJob, "summary">): boolean {
  const records = job.summary.records;
  if (!records || typeof records !== "object") return false;
  return Number((records as Record<string, unknown>).booking ?? 0) > 0;
}

/** The runs a schedule map may go into with `mode: run`: finished COURSE runs of the term that are not the active
 * schedule and not the baseline run itself (that is `auto`); newest first. */
export function targetRuns(runs: ScheduleRun[] | undefined, termCode: string): ScheduleRun[] {
  const code = termCode.trim();
  return (runs ?? [])
    .filter((r) => r.term_code === code && r.kind === "COURSE" && !r.is_active && r.status !== "QUEUED" && r.status !== "RUNNING" && !isBaselineRun(r))
    .sort((a, b) => b.id - a.id);
}

type Mode = BaselineTarget["mode"];

/** Kaydet: where the schedule map goes (the term's baseline run, another run of the term, or nowhere). */
export function BaselineTargetPicker({ job, termCode, value, onChange }: { job: CouncilJob; termCode: string; value: BaselineTarget; onChange: (v: BaselineTarget) => void }) {
  const { t } = useI18n();
  const map = hasScheduleMap(job);
  const terms = useTerms({ enabled: map });
  const term = terms.data?.find((x) => x.code === termCode.trim());
  const runs = useRuns(term ? { term_id: term.id, kind: "COURSE", limit: 200 } : undefined, { enabled: map && !!term });
  const options = targetRuns(runs.data, termCode);
  const firstId = options[0]?.id;
  const chosen = value.mode === "run" ? value.run_id : null;
  // "Başka çalıştırma" picked before the runs arrived (or the chosen run is gone): take the newest one
  useEffect(() => {
    if (chosen !== null && firstId !== undefined && !options.some((r) => r.id === chosen)) onChange({ mode: "run", run_id: firstId });
  }, [chosen, firstId, options, onChange]);
  if (!map) return null;
  const id = `baseline-target-${job.id}`;
  const pick = (mode: Mode) => {
    if (mode === "run") {
      const first = options[0];
      onChange(first ? { mode: "run", run_id: first.id } : { mode: "run", run_id: 0 });
    } else onChange({ mode });
  };
  return (
    <div className="grid gap-1.5" data-testid="onboarding-baseline-target" data-mode={value.mode}>
      <span id={`${id}-label`} className="type-footnote font-semibold text-label-2">
        {t("baseline.target.label")}
      </span>
      <SegmentedControl
        size="sm"
        semantics="radiogroup"
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-desc`}
        value={value.mode}
        onValueChange={pick}
        options={[
          { value: "auto" as const, label: t("baseline.target.auto"), testId: "baseline-mode-auto" },
          { value: "run" as const, label: t("baseline.target.run"), testId: "baseline-mode-run", disabled: !term },
          { value: "skip" as const, label: t("baseline.target.skip"), testId: "baseline-mode-skip" },
        ]}
      />
      <p id={`${id}-desc`} className="type-footnote text-label-2">
        {value.mode === "run" && !term ? t("baseline.target.noTerm") : t(`baseline.target.desc.${value.mode}`)}
      </p>
      {value.mode === "run" && term ? (
        runs.isLoading ? (
          <p className="type-footnote text-label-2">{t("busy.loading")}</p>
        ) : options.length ? (
          <label className="grid gap-1 type-footnote text-label-2">
            {t("baseline.target.pickRun")}
            <NativeSelect value={String(value.run_id)} onChange={(e) => onChange({ mode: "run", run_id: Number(e.target.value) })} data-testid="baseline-target-run">
              {options.map((r) => (
                <option key={r.id} value={r.id}>
                  {t("baseline.target.runOption", { id: r.id, label: r.label ?? t("baseline.target.unnamed"), status: r.status })}
                </option>
              ))}
            </NativeSelect>
          </label>
        ) : (
          <p className="type-footnote text-status-warning-fg" data-testid="baseline-target-none">{t("baseline.target.noRuns", { term: termCode.trim() })}</p>
        )
      ) : null}
    </div>
  );
}

/** A target the commit can send: `mode: run` needs a chosen run. */
export function targetReady(v: BaselineTarget): boolean {
  return v.mode !== "run" || v.run_id > 0;
}

function Counts({ baseline }: { baseline: BaselineRunResult }) {
  const { t, n } = useI18n();
  const rows: { k: string; v: number }[] = [
    { k: t("baseline.created"), v: baseline.created },
    { k: t("baseline.updated"), v: baseline.updated },
    { k: t("baseline.unchanged"), v: baseline.unchanged },
    { k: t("baseline.linked"), v: baseline.linked },
    { k: t("baseline.unlinked"), v: baseline.unlinked },
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 type-callout sm:grid-cols-5">
      {rows.map((r) => (
        <div key={r.k} className="min-w-0">
          <dt className="type-footnote text-label-2">{r.k}</dt>
          <dd className="font-medium text-label-1" data-numeric>{n(r.v)}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Fark: where the schedule map goes and what it would write, from the dry run's `result.baseline_run`. */
export function BaselinePreview({ job, termCode, baseline, diffDone }: { job: CouncilJob; termCode: string; baseline: BaselineRunResult | null | undefined; diffDone: boolean }) {
  const { t, n } = useI18n();
  if (!hasScheduleMap(job)) return null;
  const term = termCode.trim();
  const state = !diffDone ? "pending" : !baseline ? "none" : baseline.skipped ? "skip" : baseline.mode === "run" ? "target" : baseline.run_created ? "new" : "existing";
  const text =
    state === "pending"
      ? t("baseline.pending")
      : state === "none"
        ? t("baseline.noCourses")
        : state === "skip"
          ? t("baseline.skipped", { n: n(baseline?.entries ?? 0) })
          : state === "target"
            ? t("baseline.intoRun", { id: baseline?.run_id ?? 0, term })
            : state === "new"
              ? t("baseline.intoNew", { term })
              : t("baseline.intoExisting", { id: baseline?.run_id ?? 0, term });
  return (
    <section aria-labelledby={`baseline-${job.id}`} className="grid gap-1.5 rounded-lg bg-fill-3 p-3 edge-hairline" data-testid="onboarding-baseline-preview" data-state={state}>
      <h3 id={`baseline-${job.id}`} className="flex items-center gap-2 type-headline text-label-1">
        <Layers className="size-4 text-label-3" aria-hidden />
        {t("baseline.title")}
      </h3>
      <p className="type-callout text-label-1">{text}</p>
      {baseline && !baseline.skipped ? (
        <>
          <Counts baseline={baseline} />
          <p className="type-footnote text-label-2">{t("baseline.keeps")}</p>
        </>
      ) : null}
      {baseline && !baseline.skipped && baseline.run_id ? (
        <Link href={`/runs/${baseline.run_id}`} className="type-footnote font-medium text-tint-text underline-offset-4 hover:underline" data-testid="onboarding-baseline-existing">
          {t("baseline.openRun", { id: baseline.run_id })}
        </Link>
      ) : null}
    </section>
  );
}

const EXTRA = ["clipped_outside_term", "entries_unplaceable", "exam_entries_skipped", "duplicates_in_commit"] as const;

/** Kaydet: the commit's `baseline_run` counts, the run and a re-solve that keeps it. */
export function BaselineResult({ baseline }: { baseline: BaselineRunResult }) {
  const { t, n } = useI18n();
  if (baseline.skipped || baseline.run_id === null) {
    return (
      <section className="grid gap-1 rounded-lg p-3 edge-hairline" data-testid="onboarding-baseline-result" data-state="skip">
        <h3 className="flex items-center gap-2 type-headline text-label-1">
          <Layers className="size-4 text-label-3" aria-hidden />
          {t("baseline.resultSkipped")}
        </h3>
        <p className="type-footnote text-label-2">{t("baseline.skipped", { n: n(baseline.entries) })}</p>
      </section>
    );
  }
  const extra = EXTRA.map((k) => ({ k, v: Number(baseline[k] ?? 0) })).filter((x) => x.v > 0);
  const runId = baseline.run_id;
  const title = baseline.mode === "run" ? t("baseline.resultInto", { id: runId }) : baseline.run_created ? t("baseline.resultNew", { id: runId }) : t("baseline.resultUpdated", { id: runId });
  return (
    <section aria-labelledby="baseline-result" className="grid gap-2 rounded-lg p-3 edge-hairline" data-testid="onboarding-baseline-result" data-state={baseline.mode}>
      <h3 id="baseline-result" className="flex items-center gap-2 type-headline text-label-1">
        <Layers className="size-4 text-label-3" aria-hidden />
        {title}
      </h3>
      <Counts baseline={baseline} />
      <p className="type-footnote text-label-2">{t("baseline.linkedHint")}</p>
      {extra.length ? (
        <ul className="grid gap-0.5 type-footnote text-status-warning-fg" data-testid="onboarding-baseline-skipped">
          {extra.map((x) => (
            <li key={x.k}>{t(`baseline.skip.${x.k}`, { n: n(x.v) })}</li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" nativeButton={false} render={<Link href={`/runs/${runId}`} data-testid="onboarding-baseline-open" />}>
          {t("baseline.openRun", { id: runId })}
        </Button>
        <Button size="sm" nativeButton={false} render={<Link href={`/runs/${runId}?resolve=1`} data-testid="onboarding-baseline-resolve" />}>
          {t("baseline.resolve")}
          <ArrowRight aria-hidden />
        </Button>
      </div>
    </section>
  );
}
