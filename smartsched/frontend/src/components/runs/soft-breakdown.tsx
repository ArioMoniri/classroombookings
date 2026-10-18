"use client";

import { useMemo, useState } from "react";
import { BarList } from "@/components/ui/bar-list";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const KNOWN = ["room_preference", "building_preference", "min_capacity_waste", "same_room_across_weeks", "stability", "exam_gap"] as const;
type Known = (typeof KNOWN)[number];
const isKnown = (k: string): k is Known => (KNOWN as readonly string[]).includes(k);

/** Soft score with the points lost per soft-rule family: bars with the value at the bar end (review 2026-10-15),
 *  and a table twin that adds the weights. Penalty points are data marks (categorical colour, never the accent). */
export function SoftBreakdown({ score, breakdown, weights, className }: { score: number | null; breakdown: Record<string, number>; weights?: Record<string, number>; className?: string }) {
  const { t, n } = useI18n();
  const [table, setTable] = useState(false);
  const rows = useMemo(
    () =>
      Object.entries(breakdown)
        .sort((a, b) => b[1] - a[1])
        .map(([kind, points]) => ({ kind, label: isKnown(kind) ? t(`generate.weight.${kind}`) : t("glass.report.otherRule"), points })),
    [breakdown, t],
  );
  return (
    <div className={cn("min-w-0", className)}>
      <p className="type-callout text-label-2">{t("runs.softScore")}</p>
      <p className="flex items-baseline type-kpi text-label-1">
        {/* a static report: a plain number (the rolling digits exposed "0 1 2 … 9" to assistive tech, round-1 R1-M-27) */}
        {score === null ? "—" : <span className="tabular-nums" data-testid="soft-score">{n(score)}</span>}
        <span className="ml-1 type-callout font-normal text-label-2">/ 100</span>
      </p>
      <p className="type-footnote text-label-2">{t("glass.report.softHint")}</p>
      {rows.length === 0 ? (
        <p className="mt-3 type-callout text-label-2">{t("glass.report.noSoftLoss")}</p>
      ) : table ? (
        <table className="mt-3 w-full type-footnote">
          <thead className="text-label-3">
            <tr>
              <th scope="col" className="pb-1 text-left font-medium">{t("glass.report.ruleCol")}</th>
              <th scope="col" className="pb-1 text-right font-medium">{t("glass.report.points")}</th>
              <th scope="col" className="pb-1 text-right font-medium">{t("glass.report.weight")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.kind} className="hairline-t">
                <th scope="row" className="py-1 text-left font-normal text-label-1">{r.label}</th>
                <td className="text-right tabular-nums">{n(r.points)}</td>
                <td className="text-right tabular-nums">{weights?.[r.kind] ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <BarList className="mt-3" aria-label={t("glass.report.points")} items={rows.map((r) => ({ key: r.kind, label: r.label, value: r.points, display: t("glass.report.pointsN", { n: n(r.points) }) }))} />
      )}
      {rows.length ? (
        <Button variant="ghost" size="xs" aria-pressed={table} className="mt-1 text-tint-text" onClick={() => setTable((v) => !v)}>
          {table ? t("glass.report.asChart") : t("glass.dashboard.asTable")}
        </Button>
      ) : null}
    </div>
  );
}
