"use client";
// SmartSched charts (CH-02): the area form (charts.md §4: one series where the volume is the message). Loaded
// only through `LazyAreaChart` (chart-lazy.tsx). EvilCharts `EChartsAreaChart` with animation off, the shell's
// formatters and a dashed last segment for an unfinished bucket. Original work.
import { useRef } from "react";
import { useChartApi } from "./chart-api";
import type { AreaFormProps } from "./chart-form-types";
import { EChartsAreaChart } from "./evil/charts/echarts-area-chart";

export function AreaForm(p: AreaFormProps) {
  const ref = useRef<HTMLDivElement>(null);
  useChartApi(ref, p.onReady);
  return (
    <div ref={ref} className="w-full" style={{ height: p.height }}>
      <EChartsAreaChart
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
          <EChartsAreaChart.Area key={key} dataKey={key} enableBufferLine={p.partialLast} />
        ))}
        <EChartsAreaChart.XAxis dataKey={p.xKey} tickFormatter={p.xTickFormatter} />
        <EChartsAreaChart.YAxis tickFormatter={(v) => p.tickFormatter(Number(v))} />
        <EChartsAreaChart.Grid />
        <EChartsAreaChart.Tooltip
          variant="default"
          valueFormatter={p.valueFormatter}
          labelFormatter={p.labelFormatter}
          className={p.tooltipClassName}
        />
      </EChartsAreaChart>
    </div>
  );
}
