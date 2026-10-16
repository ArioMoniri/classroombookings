"use client";
/**
 * The run report of the term's baseline import run (`params.source = COUNCIL_BASELINE`, app/council/baseline.py):
 * which files the schedule map came from (each once, by sha256) and how the last commit wrote it
 * (`stats.baseline`: created / updated / unchanged entries, linked to a meeting request or not).
 */
import { FileSpreadsheet } from "lucide-react";
import type { ScheduleRun } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";

const COUNTS = ["created", "updated", "unchanged", "linked", "unlinked"] as const;

export function BaselineRunCard({ r }: { r: ScheduleRun }) {
  const { t, n } = useI18n();
  const sources = r.params.sources ?? [];
  const raw = r.stats_detail?.baseline;
  const counts = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return (
    <section aria-labelledby="baseline-run-title" className="mt-4 grid gap-2 rounded-lg bg-fill-3 px-3 py-3" data-testid="baseline-run-card">
      <h3 id="baseline-run-title" className="type-headline text-label-1">{t("baseline.runTitle")}</h3>
      <p className="type-callout text-label-2">{t("baseline.runLead")}</p>
      {sources.length ? (
        <ul className="grid gap-1 type-callout" aria-label={t("baseline.sources")}>
          {sources.map((s, i) => (
            <li key={s.sha256 ?? i} className="flex min-w-0 items-center gap-2 text-label-1">
              <FileSpreadsheet className="size-4 shrink-0 text-label-3" aria-hidden />
              <span className="truncate">{s.file ?? "—"}</span>
              {s.sha256 ? (
                <span className="shrink-0 font-mono type-footnote text-label-3" title={s.sha256}>
                  {s.sha256.slice(0, 8)}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-5">
        {COUNTS.map((k) => (
          <div key={k} className="min-w-0">
            <dt className="type-footnote text-label-2">{t(`baseline.${k}`)}</dt>
            <dd className="type-callout font-medium text-label-1" data-numeric>{n(Number(counts[k] ?? 0))}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
