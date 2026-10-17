// SmartSched charts (CH-02, docs/design/v3/charts.md §5.3.2): the one plain sentence that answers a chart's
// question with its numbers ("Son 30 günde 1,2 milyon token; en yoğun gün 14 Eki (82 bin). Bugün henüz
// bitmedi."). Pure builders over the `charts.summary.*` messages; no adjectives. Original work.
import type { MessageKey, Vars } from "@/lib/i18n";
import type { ChartFormat } from "./chart-format";

export type Translate = (key: MessageKey, vars?: Vars) => string;
export type ChartPeriod = "7d" | "30d" | "term" | "1h" | "24h";
export type BucketKind = "day" | "week" | "hour" | "slot" | "run";

export interface SummaryPoint {
  /** the bucket key (an ISO day, "10:30", a run name) */
  label: string;
  value: number;
}

export interface SummaryInput {
  t: Translate;
  f: ChartFormat;
  points: readonly SummaryPoint[];
  kind: BucketKind;
  /** the period the points cover; omitted → no total phrase */
  period?: ChartPeriod;
  /** the measure after the total ("token"); optional */
  unit?: string;
  /** include the total (default true when a period is given) */
  total?: boolean;
  /** formats the total and the peak value (default `f.compactLong`) */
  formatValue?: (value: number) => string;
  /** formats the peak bucket (default: the label as is) */
  peakLabel?: (label: string) => string;
  /** the last bucket is unfinished */
  partial?: boolean;
  /** buckets were folded to weekly sums on a phone */
  weekly?: boolean;
}

/** the first bucket with the largest value */
export function peakOf(points: readonly SummaryPoint[]): SummaryPoint | null {
  let best: SummaryPoint | null = null;
  for (const p of points) if (!best || p.value > best.value) best = p;
  return best;
}

const tidy = (text: string) => text.replace(/\s+/g, " ").replace(/\s+([;.,:])/g, "$1").trim();

export function chartSummary(input: SummaryInput): string {
  const { t, f, points, kind, period } = input;
  if (!points.length) return "";
  const fmt = input.formatValue ?? f.compactLong;
  const label = input.peakLabel ?? ((s: string) => s);
  const peak = peakOf(points)!;
  const vars = {
    kind: t(`charts.kind.${kind}` as MessageKey),
    peak: label(peak.label),
    peakValue: fmt(peak.value),
    unit: input.unit ?? "",
    period: period ? t(`charts.periodPhrase.${period}` as MessageKey) : "",
    total: fmt(points.reduce((s, p) => s + p.value, 0)),
  };
  const withTotal = (input.total ?? true) && !!period;
  const parts = [tidy(t(withTotal ? "charts.summary.totalPeak" : "charts.summary.peak", vars))];
  if (input.partial) parts.push(t(`charts.summary.partial.${kind}` as MessageKey));
  if (input.weekly) parts.push(t("charts.summary.weekly"));
  return parts.join(" ");
}

/** "Önceki döneme göre %25 artış." (|change| < 0,5 % is "no change"); "" without a base */
export function trendSentence(t: Translate, f: ChartFormat, previous: number, current: number): string {
  if (!previous) return "";
  const change = (current - previous) / previous;
  if (Math.abs(change) < 0.005) return t("charts.summary.trendFlat");
  const pct = f.num(Math.round(Math.abs(change) * 100));
  return t(change > 0 ? "charts.summary.trendUp" : "charts.summary.trendDown", { pct });
}
