"use client";

import { useMemo } from "react";
import { ChartCard } from "@/components/charts/chart-card";
import type { ChartColumn } from "@/components/charts/chart-csv";
import { useChartFormat } from "@/components/charts/chart-format";
import { LazyAreaChart } from "@/components/charts/chart-lazy";
import { chartSummary } from "@/components/charts/chart-summary";
import { singleConfig } from "@/components/charts/chart-tokens";
import { BarList } from "@/components/ui/bar-list";
import type { DashboardSummary } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS } from "@/lib/time";
import { cn } from "@/lib/utils";

/* Data marks use the sequential ramp, never the accent (G3: one tint for actions/selection only). The period chart
   sits in the shared ChartCard (CH-04, docs/design/v3/charts.md): no grow-in (A9), the table twin, CSV, keyboard. */

/** Weighted mean utilisation per period across buildings (rooms as weights). */
export function periodSeries(d: DashboardSummary): { period: string; index: number; util: number }[] {
  const rooms = new Map(d.utilisation_by_building.map((b) => [b.building, b.rooms]));
  return PERIODS.map((p) => {
    const cells = d.utilisation_building_period.filter((c) => c.period === p.index);
    const w = cells.reduce((s, c) => s + (rooms.get(c.building) ?? 1), 0);
    const v = w ? cells.reduce((s, c) => s + c.utilisation * (rooms.get(c.building) ?? 1), 0) / w : 0;
    return { period: p.start, index: p.index, util: Math.round(v * 100) };
  });
}

type PeriodRow = { period: string; util: number };

/** CH-04 (charts.md §4 row 8): one series on the shared ChartCard + EvilCharts ECharts area (`--seq-4`, SVG). */
export function PeriodArea({ data }: { data: DashboardSummary | undefined }) {
  const { t } = useI18n();
  const f = useChartFormat();
  const series = useMemo(() => (data ? periodSeries(data) : []), [data]);
  // the table and CSV hold ratios (%86 / 86); the plot keeps percent points 0…100
  const rows = useMemo<PeriodRow[]>(() => series.map((s) => ({ period: s.period, util: s.util / 100 })), [series]);
  const columns = useMemo<ChartColumn<PeriodRow>[]>(
    () => [
      { key: "period", label: t("common.period") },
      { key: "util", label: t("glass.dashboard.occupied"), kind: "percent" },
    ],
    [t],
  );
  const config = useMemo(() => singleConfig("util", t("glass.dashboard.occupied")), [t]);
  const empty = !series.some((s) => s.util > 0);
  const summary = empty ? "" : chartSummary({ t, f, points: rows.map((r) => ({ label: r.period, value: r.util })), kind: "slot", total: false, formatValue: f.pct });
  const pct = (v: number) => f.pct(v / 100);
  return (
    <ChartCard<PeriodRow>
      id="dashboard-periods"
      title={t("glass.dashboard.byPeriod")}
      hint={`${t("glass.dashboard.byPeriodHint")}.`}
      summary={summary}
      state={!data ? "loading" : empty ? "empty" : "ready"}
      empty={{ reason: t("common.noData") }}
      columns={columns}
      rows={rows}
      series={1}
      height={180}
    >
      {(ctx) => <LazyAreaChart {...ctx} valueFormatter={pct} tickFormatter={pct} data={series} config={config} xKey="period" series={SERIES} />}
    </ChartCard>
  );
}

const SERIES = ["util"] as const;

export function BuildingBars({ data, className }: { data: DashboardSummary; className?: string }) {
  const { t, n } = useI18n();
  const rows = useMemo(() => data.utilisation_by_building.map((b) => ({ building: b.building, util: Math.round(b.utilisation * 100), rooms: b.rooms })), [data]);
  if (!rows.length) return <p className={cn("type-callout text-label-2", className)}>{t("common.noData")}</p>;
  // values at the bar end, no axes (review 2026-10-15 §3 Dashboard: "building bars have no value labels")
  return (
    <BarList
      className={className}
      aria-label={t("glass.dashboard.buildings")}
      labelWidth="3rem"
      max={100}
      tone="var(--seq-4)"
      items={rows.map((r) => ({ key: r.building, label: <span title={t("glass.dashboard.buildingRow", { pct: r.util, rooms: r.rooms })}>{r.building}</span>, value: r.util, display: `${n(r.util)}%` }))}
    />
  )
}
