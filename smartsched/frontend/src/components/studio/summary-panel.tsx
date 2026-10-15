"use client";

import { useI18n } from "@/lib/i18n/provider";
import { LoadingValue, Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { ReadinessMeter, useEstimateText } from "./check-step";
import { GenerateButton, KeepSmallToggle, useHumanSummary } from "./generate-step";
import { RunCard } from "./run-cards";
import { useStudio, useStudioStore } from "./studio-context";
import { pairLang } from "@/lib/i18n";

/** "What will happen": sentence summary, six mini stats, readiness + top issues, estimate, Generate. */
export function SummaryPanel({ className, showGenerate = true }: { className?: string; showGenerate?: boolean }) {
  const { t, n, locale } = useI18n();
  const { summary, goStep } = useStudio();
  const est = useEstimateText();
  const human = useHumanSummary();
  const active = useStudioStore((s) => s.activeRun);
  const stats: { label: string; value: string; testId: string }[] = [
    { label: t("studio.summary.in"), value: n(summary.classesIn), testId: "stat-in" },
    { label: t("studio.summary.out"), value: n(summary.classesOut), testId: "stat-out" },
    { label: t("studio.summary.pinned"), value: n(summary.pinned), testId: "stat-pinned" },
    { label: t("studio.summary.must"), value: n(summary.must), testId: "stat-must" },
    { label: t("studio.summary.try"), value: n(summary.tryTo), testId: "stat-try" },
    { label: t("studio.summary.weeks"), value: n(summary.weeks.length), testId: "stat-weeks" },
  ];
  return (
    <aside aria-label={t("studio.summary.title")} className={cn("space-y-4", className)} data-testid="summary-panel">
      <h2 className="type-headline text-label-1">{t("studio.summary.title")}</h2>
      {active ? <RunCard compact /> : null}
      <p className="type-body text-label-1" aria-live="polite">
        {human || <span className="grid gap-1.5" aria-label={t("common.loading")}><Skeleton className="h-3.5 w-full rounded-sm" /><Skeleton className="h-3.5 w-3/4 rounded-sm" /></span>}
      </p>
      {/* numbers in one quiet grid, not six bordered tiles (A2) */}
      <dl className="grid grid-cols-3 gap-x-3 gap-y-2 py-3 hairline-t hairline-b">
        {stats.map((s) => (
          <div key={s.label} className="min-w-0">
            <dt className="truncate type-caption text-label-2" title={s.label}>
              {s.label}
            </dt>
            <dd className="type-headline tnum" data-testid={s.testId}>
              <LoadingValue value={summary.ready ? s.value : undefined} chars={2} />
            </dd>
          </div>
        ))}
      </dl>
      <div className="space-y-2 rounded-xl bg-fill-3 p-3 edge-hairline">
        <ReadinessMeter readiness={summary.readiness} compact />
        {summary.topIssues.length ? (
          <ul className="grid gap-0.5 type-footnote">
            {summary.topIssues.map((i) => {
              // name the class(es) on each line: "Engel var" listed the same title 3× without saying which class
              // (review 2026-10-15 §3 Generate 1024)
              const names = i.classes.map((c) => (typeof c.label === "string" ? c.label : null)).filter((x): x is string => !!x);
              return (
                <li key={i.id}>
                  <button type="button" className="inline-flex min-h-6 w-full items-baseline gap-1 rounded-sm text-left text-label-2 hover:text-label-1 hover:underline focus-visible:outline-2 focus-visible:outline-(--focus)" onClick={() => goStep("check")}>
                    <span className="shrink-0">{i.title[pairLang(locale)] || i.title.en}</span>
                    {names.length ? <span className="min-w-0 truncate font-medium text-label-1">· {names.slice(0, 2).join(", ")}{names.length > 2 ? ` +${names.length - 2}` : ""}</span> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        ) : null}
        <p className="type-footnote text-label-2">{t("studio.check.estimate", { words: est(summary.estimate) })}</p>
      </div>
      {showGenerate ? (
        <div className="space-y-3">
          <GenerateButton className="w-full" testId="summary-generate" />
          <p className="text-center type-caption text-label-2">{t("studio.summary.shortcut")}</p>
          <KeepSmallToggle />
        </div>
      ) : null}
    </aside>
  );
}
