"use client";

import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { ReadinessMeter, useEstimateText } from "./check-step";
import { GenerateButton, KeepSmallToggle, useHumanSummary } from "./generate-step";
import { RunCard } from "./run-cards";
import { useStudio, useStudioStore } from "./studio-context";

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
      <h2 className="text-sm font-semibold">{t("studio.summary.title")}</h2>
      {active ? <RunCard compact /> : null}
      <p className="text-sm leading-relaxed" aria-live="polite">
        {human}
      </p>
      <dl className="grid grid-cols-3 gap-2">
        {stats.map((s) => (
          <div key={s.label} className="rounded-md border bg-card px-2 py-1.5">
            <dt className="truncate text-[11px] text-muted-foreground" title={s.label}>
              {s.label}
            </dt>
            <dd className="text-base font-semibold tabular-nums" data-testid={s.testId}>
              {s.value}
            </dd>
          </div>
        ))}
      </dl>
      <div className="space-y-2 rounded-lg border bg-card p-3">
        <ReadinessMeter readiness={summary.readiness} compact />
        {summary.topIssues.length ? (
          <ul className="space-y-1 text-xs">
            {summary.topIssues.map((i) => (
              <li key={i.id}>
                <button type="button" className="text-left text-muted-foreground hover:text-foreground hover:underline" onClick={() => goStep("check")}>
                  · {i.title[locale] || i.title.en}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <p className="text-xs text-muted-foreground">{t("studio.check.estimate", { words: est(summary.estimate) })}</p>
      </div>
      {showGenerate ? (
        <div className="space-y-3">
          <GenerateButton className="w-full" testId="summary-generate" />
          <p className="text-center text-[11px] text-muted-foreground">{t("studio.summary.shortcut")}</p>
          <KeepSmallToggle />
        </div>
      ) : null}
    </aside>
  );
}
