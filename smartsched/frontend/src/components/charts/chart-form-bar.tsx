"use client";
// SmartSched charts (CH-02): the column form (charts.md §4: change over time, ≥ 3 points). Loaded only through
// `LazyBarChart` (chart-lazy.tsx). EvilCharts `EChartsBarChart` with animation off, the shell's formatters and a
// hatched last bar for an unfinished bucket. Original work.
import { useRef } from "react";
import { useChartApi } from "./chart-api";
import type { BarFormProps } from "./chart-form-types";
import { EChartsBarChart } from "./evil/charts/echarts-bar-chart";

export function BarForm(p: BarFormProps) {
  const ref = useRef<HTMLDivElement>(null);
  useChartApi(ref, p.onReady);
  return (
    <div ref={ref} className="w-full" style={{ height: p.height }}>
      <EChartsBarChart
        data={p.data as Record<string, unknown>[]}
        config={p.config}
        renderer={p.renderer}
        xDataKey={p.xKey}
        stackType={p.stackType ?? "default"}
        animation={false}
        animationType="none"
        chartOptions={p.engineOptions}
        className="h-full"
      >
        {p.series.map((key) => (
          <EChartsBarChart.Bar key={key} dataKey={key} bufferBar={p.partialLast} />
        ))}
        <EChartsBarChart.XAxis dataKey={p.xKey} tickFormatter={p.xTickFormatter} />
        <EChartsBarChart.YAxis tickFormatter={(v) => p.tickFormatter(Number(v))} />
        <EChartsBarChart.Grid />
        <EChartsBarChart.Tooltip
          variant="default"
          valueFormatter={p.valueFormatter}
          labelFormatter={p.labelFormatter}
          className={p.tooltipClassName}
        />
      </EChartsBarChart>
    </div>
  );
}
