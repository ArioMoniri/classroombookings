"use client";

import { useMemo } from "react";
import { EvilAreaChart } from "@/components/ui/evilcharts/charts/recharts-area-chart";
import { EvilBarChart } from "@/components/ui/evilcharts/charts/recharts-bar-chart";
import type { DashboardSummary } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS } from "@/lib/time";
import { cn } from "@/lib/utils";

/* Data marks use the sequential ramp, never the accent (G3: one tint for actions/selection only).
   No grow-in or stagger on load (A9, motion.md §0.3): animationType="none". Every chart has a text twin
   (sr-only table) because a chart is not accessible on its own. */
const SEQ = { light: ["var(--seq-4)"], dark: ["var(--seq-4)"] };

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

export function PeriodArea({ data, className }: { data: DashboardSummary; className?: string }) {
  const { t } = useI18n();
  const series = useMemo(() => periodSeries(data), [data]);
  const config = useMemo(() => ({ util: { label: t("glass.dashboard.occupied"), colors: SEQ } }), [t]);
  const peak = series.reduce((a, b) => (b.util > a.util ? b : a), series[0] ?? { period: "", index: 0, util: 0 });
  return (
    <figure className={cn("relative", className)}>
      <div aria-hidden className="size-full">
        <EvilAreaChart config={config} data={series} curveType="monotone" animationType="none" className="aspect-auto size-full">
          <EvilAreaChart.Grid />
          <EvilAreaChart.XAxis dataKey="period" interval={2} />
          <EvilAreaChart.YAxis width={32} tickFormatter={(v: number) => `${v}`} domain={[0, 100]} ticks={[0, 50, 100]} />
          <EvilAreaChart.Tooltip variant="frosted-glass" />
          <EvilAreaChart.Area dataKey="util" variant="gradient" strokeVariant="solid" strokeWidth={2} />
        </EvilAreaChart>
      </div>
      <figcaption className="sr-only">
        {t("glass.dashboard.peakAt", { time: peak.period, pct: peak.util })}
        <table>
          <tbody>
            {series.map((s) => (
              <tr key={s.index}>
                <th scope="row">{s.period}</th>
                <td>{s.util}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}

export function BuildingBars({ data, className }: { data: DashboardSummary; className?: string }) {
  const { t } = useI18n();
  const rows = useMemo(() => data.utilisation_by_building.map((b) => ({ building: b.building, util: Math.round(b.utilisation * 100), rooms: b.rooms })), [data]);
  const config = useMemo(() => ({ util: { label: t("glass.dashboard.occupied"), colors: SEQ } }), [t]);
  return (
    <figure className={cn("relative", className)}>
      <div aria-hidden className="size-full">
        <EvilBarChart config={config} data={rows} layout="horizontal" animationType="none" barRadius={6} className="aspect-auto size-full">
          <EvilBarChart.XAxis type="number" domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} />
          <EvilBarChart.YAxis dataKey="building" width={28} />
          <EvilBarChart.Tooltip variant="frosted-glass" />
          <EvilBarChart.Bar dataKey="util" />
        </EvilBarChart>
      </div>
      <figcaption className="sr-only">
        <table>
          <tbody>
            {rows.map((r) => (
              <tr key={r.building}>
                <th scope="row">{r.building}</th>
                <td>{t("glass.dashboard.buildingRow", { pct: r.util, rooms: r.rooms })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}
