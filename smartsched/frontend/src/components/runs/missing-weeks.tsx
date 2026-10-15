"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n/provider";

/**
 * Term runs place most classes in every week; a few miss exactly one week (Bahar: HAZIRLIK week 1 has no
 * room left once the rest is placed). The backend counts them per week (`stats.missing_only_week`,
 * `app/solver/weeksplit.py`); the report says so separately, with a link to that week.
 */
export function missingOnlyWeek(stats: Record<string, unknown>): { week: number; count: number }[] {
  const raw = stats.missing_only_week;
  if (!raw || typeof raw !== "object") return [];
  return Object.entries(raw as Record<string, unknown>)
    .map(([w, c]) => ({ week: Number(w), count: Number(c) }))
    .filter((x) => Number.isInteger(x.week) && x.week > 0 && Number.isFinite(x.count) && x.count > 0)
    .sort((a, b) => b.count - a.count || a.week - b.week);
}

export function MissingWeeks({ runId, stats }: { runId: number; stats: Record<string, unknown> }) {
  const { t, n } = useI18n();
  const rows = missingOnlyWeek(stats);
  if (!rows.length) return null;
  return (
    <ul className="mt-2 space-y-1 text-[13px] text-status-warning-fg" data-testid="missing-weeks">
      {rows.map((r) => (
        <li key={r.week} className="flex flex-wrap items-baseline gap-x-2">
          <span>{t("glass.report.missingOnlyWeek", { n: n(r.count), week: r.week })}</span>
          <Link href={`/timetable?run=${runId}&week=${r.week}`} className="font-medium text-tint-text hover:underline">
            {t("glass.report.openWeek", { week: r.week })}
          </Link>
        </li>
      ))}
    </ul>
  );
}
