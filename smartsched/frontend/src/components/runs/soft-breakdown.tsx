"use client";

import { useMemo, useState } from "react";
import { KpiNumber } from "@/components/dashboard/kpi-number";
import { EvilBarChart } from "@/components/ui/evilcharts/charts/recharts-bar-chart";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

const KNOWN = ["room_preference", "building_preference", "min_capacity_waste", "same_room_across_weeks", "stability", "exam_gap"] as const;
type Known = (typeof KNOWN)[number];
const isKnown = (k: string): k is Known => (KNOWN as readonly string[]).includes(k);

/* Penalty points are data marks: the categorical ramp, never the accent (G3); no grow-in on load (A9). */
const CAT = { light: ["var(--cat-1)"], dark: ["var(--cat-1)"] };

/** Soft score with the points lost per soft-rule family (evilcharts bar chart) and its text/table twin. */
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
  const config = useMemo(() => ({ points: { label: t("glass.report.points"), colors: CAT } }), [t]);
  return (
    <div className={cn("min-w-0", className)}>
      <p className="text-[13px] text-label-2">{t("runs.softScore")}</p>
      <p className="type-title-1 text-label-1">
        {score === null ? "—" : <KpiNumber value={score} />}
        <span className="ml-1 text-[13px] font-normal text-label-3">/ 100</span>
      </p>
      <p className="text-[12px] text-label-3">{t("glass.report.softHint")}</p>
      {rows.length === 0 ? (
        <p className="mt-3 text-[13px] text-label-2">{t("glass.report.noSoftLoss")}</p>
      ) : table ? (
        <table className="mt-3 w-full text-[12px]">
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
        <figure className="mt-2" style={{ height: Math.max(72, rows.length * 34 + 28) }}>
          <div aria-hidden className="size-full">
            <EvilBarChart config={config} data={rows} layout="horizontal" animationType="none" barRadius={5} className="aspect-auto size-full">
              <EvilBarChart.XAxis type="number" hide />
              <EvilBarChart.YAxis dataKey="label" width={150} />
              <EvilBarChart.Tooltip variant="frosted-glass" />
              <EvilBarChart.Bar dataKey="points" />
            </EvilBarChart>
          </div>
          <figcaption className="sr-only">{rows.map((r) => `${r.label}: ${n(r.points)}`).join(", ")}</figcaption>
        </figure>
      )}
      {rows.length ? (
        <button type="button" aria-pressed={table} className="mt-1 rounded-full px-2 py-0.5 text-[12px] font-medium text-tint-text outline-none hover:bg-fill-2 focus-visible:outline-2 focus-visible:outline-(--focus)" onClick={() => setTable((v) => !v)}>
          {table ? t("glass.report.asChart") : t("glass.dashboard.asTable")}
        </button>
      ) : null}
    </div>
  );
}
