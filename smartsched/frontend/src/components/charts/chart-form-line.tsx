"use client";
// SmartSched charts (CH-02): the line form (charts.md §4: many points or continuous change). Loaded
// only through `LazyLineChart` (chart-lazy.tsx). EvilCharts `EChartsLineChart` with animation off, the shell's
// formatters and a dashed last segment for an unfinished bucket. Original work.
import { useRef } from "react";
import { useChartApi } from "./chart-api";
import type { LineFormProps } from "./chart-form-types";
import { EChartsLineChart } from "./evil/charts/echarts-line-chart";

export function LineForm(p: LineFormProps) {
  const ref = useRef<HTMLDivElement>(null);
  useChartApi(ref, p.onReady);
  return (
    <div ref={ref} className="w-full" style={{ height: p.height }}>
      <EChartsLineChart
        data={p.data as Record<string, unknown>[]}
        config={p.config}
        renderer={p.renderer}
        xDataKey={p.xKey}
        animation={false}
        animationType="none"
        chartOptions={p.engineOptions}
        className="h-full"
      >
        {p.series.map((key) => (
          <EChartsLineChart.Line key={key} dataKey={key} enableBufferLine={p.partialLast} />
        ))}
        <EChartsLineChart.XAxis dataKey={p.xKey} tickFormatter={p.xTickFormatter} />
        <EChartsLineChart.YAxis tickFormatter={(v) => p.tickFormatter(Number(v))} />
        <EChartsLineChart.Grid />
        <EChartsLineChart.Tooltip
          variant="default"
          valueFormatter={p.valueFormatter}
          labelFormatter={p.labelFormatter}
          className={p.tooltipClassName}
        />
      </EChartsLineChart>
    </div>
  );
}
