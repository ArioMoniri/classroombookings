"use client";
// SmartSched charts (CH-02, docs/design/v3/charts.md §5.1, §10): the only doors to ECharts. Each form is its own
// `next/dynamic` chunk (`ssr: false`), so a route pays for the engine only when a ChartCard renders a plot, and a
// route without a chart pays 0 kB. Never import ./chart-form-* or ./evil/** directly from app code. Original work.
import dynamic from "next/dynamic";
import { ChartSkeleton } from "./chart-skeleton";
import type { AreaFormProps, BarFormProps, LineFormProps } from "./chart-form-types";

export const LazyBarChart = dynamic<BarFormProps>(() => import("./chart-form-bar").then((m) => m.BarForm), {
  ssr: false,
  loading: () => <ChartSkeleton testId="chart-skeleton-lazy" />,
});

export const LazyLineChart = dynamic<LineFormProps>(() => import("./chart-form-line").then((m) => m.LineForm), {
  ssr: false,
  loading: () => <ChartSkeleton testId="chart-skeleton-lazy" />,
});

export const LazyAreaChart = dynamic<AreaFormProps>(() => import("./chart-form-area").then((m) => m.AreaForm), {
  ssr: false,
  loading: () => <ChartSkeleton testId="chart-skeleton-lazy" />,
});
