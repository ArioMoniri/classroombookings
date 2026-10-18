// SmartSched charts (CH-02, docs/design/v3/charts.md §6): series colours for the EvilCharts `ChartConfig`, and the
// engine options every chart shares (animation off, hover emphasis timing, hatch patterns). Type-only import of the
// vendored module, so this file never pulls ECharts into a route. Original work.
import type { ChartConfig } from "./evil/ui/echarts-chart";

/** categorical identity colours, fixed order, never cycled; a 6th+ series folds into "Diğer" */
export const CAT = ["var(--cat-1)", "var(--cat-2)", "var(--cat-3)", "var(--cat-4)", "var(--cat-5)"] as const;
export const OTHER = "var(--label-3)";
/** single-series magnitude; the emphasised bar (exam week) uses SEQ_EMPHASIS. Never the accent. */
export const SEQ = "var(--seq-4)";
export const SEQ_EMPHASIS = "var(--seq-5)";

export interface SeriesSpec {
  key: string;
  label: string;
  /** a fixed colour (the entity's colour, e.g. AI `SERIES_COLOR`); default: CAT by position, OTHER after 5 */
  color?: string;
}

const both = (c: string) => ({ light: [c], dark: [c] });

export function seriesColor(index: number): string {
  return CAT[index] ?? OTHER;
}

/** `ChartConfig` for several series: the colour follows the series, not its position in a filtered list. */
export function categoricalConfig(series: readonly SeriesSpec[]): ChartConfig {
  return Object.fromEntries(series.map((s, i) => [s.key, { label: s.label, colors: both(s.color ?? seriesColor(i)) }]));
}

/** `ChartConfig` for one series (`--seq-4`). */
export function singleConfig(key: string, label: string, color: string = SEQ): ChartConfig {
  return { [key]: { label, colors: both(color) } };
}

export interface LegendItem {
  key: string;
  label: string;
  color: string;
}

export function legendItems(series: readonly SeriesSpec[]): LegendItem[] {
  return series.map((s, i) => ({ key: s.key, label: s.label, color: s.color ?? seriesColor(i) }));
}

/** hover emphasis on a series: `--dur-fast`; 0 under reduced motion (charts.md §8) */
export const EMPHASIS_MS = 120;

export interface EngineOptions {
  animation: false;
  stateAnimation: { duration: number };
  aria: { enabled: boolean; label: { enabled: false }; decal: { show: boolean } };
  [key: string]: unknown;
}

/**
 * Merged over every EvilCharts option (`chartOptions`): no grow-in (A9), short hover emphasis, and the hatch
 * patterns when the user wants them. `aria.label` stays off: screen readers get the shell's title, summary and
 * table instead of ECharts' generated English description (the plot is aria-hidden).
 */
export function engineOptions({ reduce, patterns }: { reduce: boolean; patterns: boolean }): EngineOptions {
  return {
    animation: false,
    stateAnimation: { duration: reduce ? 0 : EMPHASIS_MS },
    aria: { enabled: patterns, label: { enabled: false }, decal: { show: patterns } },
  };
}
