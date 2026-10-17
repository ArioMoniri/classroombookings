// SmartSched charts (CH-02): the props every lazy chart form takes. Types only (no ECharts at runtime), so the
// shell and the callers can import them without paying for the engine. Original work.
import type { ChartRenderer } from "./chart-renderer";
import type { EngineOptions } from "./chart-tokens";
import type { ChartConfig } from "./evil/ui/echarts-chart";

/** the live chart, for the ⋯ menu's image download and the CH-03 keyboard layer */
export interface ChartApi {
  getDataURL: (opts: { type: "svg" | "png"; pixelRatio?: number; backgroundColor?: string }) => string | null;
  dispatchAction: (action: Record<string, unknown>) => void;
}

/** what `ChartCard` hands its plot (spread it into a Lazy*Chart) */
export interface ChartFormCommon {
  renderer: ChartRenderer;
  engineOptions: EngineOptions;
  /** tooltip values, full precision: 82.300 */
  valueFormatter: (value: number) => string;
  /** tooltip heading: 14 Ekim Çarşamba */
  labelFormatter: (label: string) => string;
  /** value-axis ticks, compact: 82 B */
  tickFormatter: (value: number) => string;
  /** category-axis ticks: 14 Eki */
  xTickFormatter: (label: string) => string;
  /** class on the tooltip root (free `tooltip` recipe) */
  tooltipClassName: string;
  /** the last bucket is unfinished → hatched bar / dashed last segment */
  partialLast: boolean;
  height: number;
  onReady: (api: ChartApi) => void;
}

export interface ChartFormProps extends ChartFormCommon {
  data: readonly Record<string, unknown>[];
  config: ChartConfig;
  /** the category (bucket) key */
  xKey: string;
  /** series keys in legend order */
  series: readonly string[];
}

export interface BarFormProps extends ChartFormProps {
  stackType?: "default" | "stacked";
}

export type LineFormProps = ChartFormProps;
export type AreaFormProps = ChartFormProps;
