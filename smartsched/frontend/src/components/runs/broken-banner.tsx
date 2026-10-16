"use client";
/**
 * Round-1 R1-M-05: a run (published or not) whose stored timetable breaks a hard rule says so wherever it is shown
 * - the run report's verdict, the Studio card and this banner on the timetable - with every broken rule and the
 * forced move's reason that explains it. Never silent: the numbers come from the backend's `stats.truth`.
 */
import { XOctagon } from "lucide-react";
import Link from "next/link";
import { useRun } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { BROKEN_RULE_TR, truthOf } from "./run-truth";

export function BrokenRulesBanner({ runId, className }: { runId: number | null; className?: string }) {
  const { n, locale } = useI18n();
  const run = useRun(runId);
  const truth = truthOf(run.data?.stats?.truth);
  if (!run.data || !truth || truth.verdict !== "broken") return null;
  const tr = locale === "tr";
  const published = run.data.is_active;
  return (
    <div role="alert" className={className ?? "mb-2 grid gap-1 rounded-xl bg-status-infeasible px-3 py-2 type-callout text-status-infeasible-fg"} data-testid="run-broken-banner">
      <p className="flex items-center gap-1.5 font-medium">
        <XOctagon aria-hidden className="size-4 shrink-0" />
        {tr
          ? `${published ? "Yayımdaki program" : `Çalıştırma #${run.data.id}`} ${n(truth.broken_count)} kesin kuralı bozuyor (katı puan ${truth.hard_score ?? "—"})`
          : `${published ? "The published timetable" : `Run #${run.data.id}`} breaks ${n(truth.broken_count)} hard rule(s) (hard score ${truth.hard_score ?? "—"})`}
      </p>
      <ul className="list-disc pl-5 type-footnote text-label-1">
        {truth.broken.slice(0, 3).map((b, i) => (
          <li key={`${b.rule}-${i}`}>
            {(tr ? BROKEN_RULE_TR[b.rule] : null) ?? b.rule.replace(/_/g, " ")}: {b.message}
            {b.explained && b.reason ? ` · ${tr ? "gerekçe" : "reason"}: “${b.reason}”${b.by_name ? ` (${b.by_name})` : ""}` : tr ? " · açıklanmamış" : " · not explained"}
          </li>
        ))}
      </ul>
      <Link href={`/runs/${run.data.id}`} className="type-footnote font-medium underline underline-offset-2">
        {tr ? "Raporda hepsini gör" : "See all in the report"}
      </Link>
    </div>
  );
}
