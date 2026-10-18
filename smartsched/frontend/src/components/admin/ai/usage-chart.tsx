"use client";
/**
 * Yapay zekâ › Kullanım › "Günlük token kullanımı" (CH-05, docs/design/v3/charts.md §4 row 1): stacked columns by
 * feature on the shared ChartCard + EvilCharts ECharts bar. Colours stay `SERIES_COLOR` (fixed order, "Diğer" =
 * `--label-3`), today is hatched while it is not over, and phones show weekly sums (≤ 5 columns for 30 days). The
 * period control stays the page's (it drives the KPI tiles too). Moved out of usage-tab.tsx so the chart has its own
 * file and test.
 */
import { useMemo } from "react";
import { ChartCard } from "@/components/charts/chart-card";
import type { ChartColumn } from "@/components/charts/chart-csv";
import { useChartFormat } from "@/components/charts/chart-format";
import { LazyBarChart } from "@/components/charts/chart-lazy";
import { categoricalConfig } from "@/components/charts/chart-tokens";
import { Card } from "@/components/ui/card";
import { BELOW_MD, useMediaQuery } from "@/components/ui/use-media-query";
import type { UsageRow } from "@/lib/api/ai-admin";
import { useI18n } from "@/lib/i18n/provider";
import { useAiLabels } from "./ai-kit";
import { activeSeries, compactTokens, dailyLegend, dayChartData, foldWeeks, lastIsToday, pctText, type ChartSeries, type DayPoint } from "./ai-model";

const WEEKLY_ABOVE = 7;

export function DailyChart({ rows, loading, lastDays }: { rows: UsageRow[]; loading: boolean; lastDays?: number }) {
  const { t, locale } = useI18n();
  const f = useChartFormat();
  const labels = useAiLabels();
  const phone = useMediaQuery(BELOW_MD);
  const days = useMemo(() => dayChartData(rows, locale, lastDays), [rows, locale, lastDays]);
  const weekly = phone && days.length > WEEKLY_ABOVE;
  const points = useMemo(() => (weekly ? foldWeeks(days, (from, to) => `${f.day(from)}–${f.day(to)}`) : days), [weekly, days, f]);
  const series = activeSeries(days);
  const label = (s: ChartSeries) => (s === "other" ? t("aiAdmin.feature.other") : labels.feature(s));
  const legend = dailyLegend(series, label);
  const config = categoricalConfig(legend);
  const partial = lastIsToday(days);

  const total = days.reduce((a, p) => a + p.total, 0);
  const top = series.map((s) => ({ s, v: days.reduce((a, p) => a + p[s], 0) })).sort((a, b) => b.v - a.v)[0];
  const summary = total
    ? [
        t("aiAdmin.usage.summary", { total: compactTokens(total, locale), top: top ? label(top.s) : "", pct: top ? pctText(Math.round((100 * top.v) / total), locale) : "" }),
        partial ? t("charts.summary.partial.day") : "",
        weekly ? t("charts.summary.weekly") : "",
      ]
        .filter(Boolean)
        .join(" ")
    : "";

  const columns: ChartColumn<DayPoint>[] = [
    weekly ? { key: "label", label: t("common.week") } : { key: "day", label: t("aiAdmin.usage.day"), kind: "date" },
    ...series.map((s) => ({ key: s, label: label(s), kind: "number" as const })),
    { key: "total", label: t("aiAdmin.usage.total"), kind: "number" },
  ];

  return (
    <Card className="px-4 py-4" data-testid="ai-daily-chart">
      <ChartCard<DayPoint>
        id="ai-daily-tokens"
        title={t("aiAdmin.usage.chart")}
        summary={summary}
        state={loading ? "loading" : total ? "ready" : "empty"}
        empty={{ reason: t("aiAdmin.usage.empty") }}
        columns={columns}
        rows={points}
        series={series.length}
        legend={legend}
        partial={partial}
        range={days.length ? { from: days[0]!.day, to: days.at(-1)!.day } : undefined}
        unit={t("charts.unit.tokens")}
      >
        {(ctx) => <LazyBarChart {...ctx} data={points} config={config} xKey={weekly ? "label" : "day"} series={series} stackType="stacked" />}
      </ChartCard>
    </Card>
  );
}
