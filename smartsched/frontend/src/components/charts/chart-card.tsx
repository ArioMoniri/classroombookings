"use client";
// SmartSched charts (CH-02, docs/design/v3/charts.md §5, wireframes charts-shell-1440 / charts-states / charts-390):
// the one shell every time-series chart sits in. It owns the frame, the title and the plain summary sentence, the
// period control, the legend, the states (loading / empty / error / stale / partial / too few points), the table
// twin, CSV and image download, and the renderer rule. It never fetches: the caller passes rows and a state. The
// plot is a render prop, usually a `Lazy*Chart` from ./chart-lazy, so ECharts loads only when a plot shows.
// Original work.
import { AlertTriangle, Ellipsis } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { cn } from "cn";
import { Button, IconButton } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { BELOW_MD, useMediaQuery } from "@/components/ui/use-media-query";
import { useI18n } from "@/lib/i18n/provider";
import { useReduce } from "@/lib/motion";
import { csvFilename, downloadText, downloadUrl, tableModel, toCsv, type ChartColumn } from "./chart-csv";
import { useChartFormat, type ChartFormat } from "./chart-format";
import type { ChartApi, ChartFormCommon } from "./chart-form-types";
import { useChartRenderer } from "./chart-renderer";
import { ChartSkeleton } from "./chart-skeleton";
import { bucketSentence, useChartKeyboard } from "./chart-keyboard";
import { ChartTable } from "./chart-table";
import { engineOptions, type LegendItem } from "./chart-tokens";
import { PeriodPicker, type PeriodOption } from "./period-picker";
import { useChartPatterns } from "./use-chart-patterns";
import "./chart-card.css";

export type ChartState = "loading" | "empty" | "error" | "ready";

/** what the plot render prop receives; spread it into a Lazy*Chart */
export interface ChartPlotContext extends ChartFormCommon {
  patterns: boolean;
  reduce: boolean;
  format: ChartFormat;
}

export interface ChartCardProps<R> {
  /** slug for the CSV name, test ids and element ids */
  id: string;
  title: string;
  /** one plain sentence from chart-summary.ts; the figure's description */
  summary: string;
  /** what the measure is, in a few words, under the title (read before the summary) */
  hint?: string;
  state: ChartState;
  /** drives the table twin and the CSV; the first column is the bucket */
  columns: readonly ChartColumn<R>[];
  rows: readonly R[];
  /** the measure, for the keyboard read-out ("token"); optional */
  unit?: string;
  /** number of series (marks = rows × series decides SVG vs canvas); default: the number columns */
  series?: number;
  legend?: readonly LegendItem[];
  period?: { value: string; options: readonly PeriodOption[]; onChange: (value: string) => void; label?: string };
  /** the last bucket is unfinished (hatched; "(eksik)" in the table) */
  partial?: boolean;
  /** the data is old: the chart stays with a text strip */
  stale?: { since: Date; reason?: string };
  updatedAt?: Date;
  /** the API's `message_tr` / `message_en` */
  error?: string;
  onRetry?: () => void;
  /** move focus to "Yeniden dene" (only when the user triggered the failed fetch) */
  focusRetry?: boolean;
  empty?: { reason?: string; action?: { label: string; onClick: () => void } };
  /** CSV file name range (ISO days) */
  range?: { from: string; to: string };
  /** plot height in px on desktop (default 240) */
  height?: number;
  /** plot height on phones (default 200, charts.md §7); small multiples need more */
  phoneHeight?: number;
  /** test id of the summary sentence (kept ids of a migrated surface) */
  summaryTestId?: string;
  /** fewer rows than this → the number instead of a chart (default 3) */
  minPoints?: number;
  /** the signed-in user, for the per-user "Grafiklerde desen" preference */
  userId?: string | number | null;
  headingLevel?: 2 | 3 | 4;
  className?: string;
  children: (ctx: ChartPlotContext) => ReactNode;
}

const PHONE_HEIGHT = 200;
const SWAP_BACK_MS = 2000;

/** The free `text-states-swap` recipe: new text rises in; the first render and reduced motion do not animate. */
function SwapText({ text, reduce }: { text: string; reduce: boolean }) {
  const [initial] = useState(text);
  const [changed, setChanged] = useState(false);
  if (text !== initial && !changed) setChanged(true);
  const animate = !reduce && changed;
  return (
    <span key={text} className="ch-swap" data-swap={animate ? "true" : "false"}>
      {text}
    </span>
  );
}

/** Off-screen cards mount their plot on intersection (charts.md §10, ≤ 4 live instances per route). */
function useInView(rootMargin = "200px") {
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  const [inView, setInView] = useState(() => typeof IntersectionObserver === "undefined");
  useEffect(() => {
    if (inView || !el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setInView(true);
        io.disconnect();
      }
    }, { rootMargin });
    io.observe(el);
    return () => io.disconnect();
  }, [el, inView, rootMargin]);
  return { setEl, inView };
}

export function ChartCard<R>(props: ChartCardProps<R>) {
  const { id, title, summary, hint, state, columns, rows, unit, legend, period, partial, stale, updatedAt, error, onRetry, focusRetry, empty, range, minPoints = 3, userId, headingLevel = 3, className, children } = props;
  const { t } = useI18n();
  const f = useChartFormat();
  const reduce = useReduce();
  const phone = useMediaQuery(BELOW_MD);
  const patterns = useChartPatterns(userId);
  const uid = useId();
  const titleId = `${uid}-title`;
  const summaryId = `${uid}-summary`;
  const hintId = `${uid}-hint`;
  // phones always get the 200 px plot (charts.md §7); `height` is the desktop plot
  const height = phone ? (props.phoneHeight ?? PHONE_HEIGHT) : (props.height ?? 240);

  const numberColumns = columns.filter((c) => c.kind === "number" || c.kind === "percent");
  const marks = rows.length * (props.series ?? Math.max(1, numberColumns.length));
  const renderer = useChartRenderer(marks);

  const [tableMode, setTableMode] = useState(false);
  const [downloaded, setDownloaded] = useState(false);
  const [live, setLive] = useState("");
  const [api, setApi] = useState<ChartApi | null>(null);
  const onReady = setApi;

  // the plot fades in (skeleton-reveal) only when it replaces a loading state
  const wasLoading = useRef(state === "loading");
  const [reveal, setReveal] = useState(false);
  useEffect(() => {
    if (state === "loading") wasLoading.current = true;
    else if (state === "ready" && wasLoading.current) {
      wasLoading.current = false;
      setReveal(true);
    }
  }, [state]);

  useEffect(() => {
    if (!downloaded) return;
    const timer = setTimeout(() => setDownloaded(false), SWAP_BACK_MS);
    return () => clearTimeout(timer);
  }, [downloaded]);

  const retryRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (state === "error" && focusRetry) retryRef.current?.focus();
  }, [state, focusRetry]);

  const { setEl: plotRef, inView } = useInView();

  const partialText = partial ? t("charts.partialRow") : undefined;
  const describeBucket = useCallback(
    (i: number) => (rows[i] ? bucketSentence({ row: rows[i], columns, f, t, unit, partial: partialText && i === rows.length - 1 ? partialText : undefined }) : ""),
    [rows, columns, f, t, unit, partialText],
  );
  const kb = useChartKeyboard({ count: rows.length, api, describe: describeBucket, announce: setLive });

  const ready = state === "ready" && rows.length > 0;
  const tooFew = ready && rows.length < minPoints;
  const shownState: ChartState = state === "ready" && rows.length === 0 ? "empty" : state;
  const periodLabel = period ? (period.options.find((o) => o.value === period.value)?.label ?? "") : "";
  const caption = periodLabel ? `${title} · ${periodLabel}` : title;

  const model = useMemo(() => tableModel(rows, columns, f, { partialLast: partial ? t("charts.partialRow") : undefined }), [rows, columns, f, partial, t]);

  const first = columns[0];
  const ctx: ChartPlotContext = useMemo(() => {
    const isDate = first?.kind === "date";
    return {
      renderer,
      engineOptions: engineOptions({ reduce, patterns }),
      valueFormatter: f.num,
      labelFormatter: isDate ? (s: string) => f.dayLong(s) : (s: string) => s,
      tickFormatter: f.compact,
      xTickFormatter: isDate ? (s: string) => f.day(s) : (s: string) => s,
      tooltipClassName: "ch-tt",
      partialLast: !!partial,
      height,
      onReady,
      patterns,
      reduce,
      format: f,
    };
  }, [renderer, reduce, patterns, f, first?.kind, partial, height, onReady]);

  // The plot element is memoised: keyboard focus, the live text and the CSV label re-render the card, and a re-rendered
  // EvilCharts chart re-pushes its option (`notMerge`), which would drop a keyboard-shown tooltip.
  const plot = useMemo(() => children(ctx), [children, ctx]);

  const downloadCsv = () => {
    downloadText(csvFilename(id, range?.from, range?.to), toCsv(rows, columns, f.locale, f));
    setDownloaded(true);
    setLive(t("charts.downloadedLive"));
  };
  const downloadImage = () => {
    const type = renderer === "svg" ? "svg" : "png";
    const background = typeof window !== "undefined" ? getComputedStyle(document.body).backgroundColor : undefined;
    const url = api?.getDataURL({ type, pixelRatio: 2, backgroundColor: background });
    if (!url) return;
    downloadUrl(csvFilename(id, range?.from, range?.to).replace(/\.csv$/, `.${type}`), url);
    setLive(t("charts.imageDownloadedLive"));
  };

  const Heading = `h${headingLevel}` as "h3";
  const showPlot = ready && !tooFew && !tableMode;

  return (
    <figure
      aria-labelledby={titleId}
      aria-describedby={hint ? `${hintId} ${summaryId}` : summaryId}
      aria-busy={state === "loading" ? true : undefined}
      data-chart-card={id}
      data-state={shownState}
      className={cn("m-0 flex min-w-0 flex-col gap-3", className)}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <div className="min-w-0 flex-1 basis-64">
          <Heading id={titleId} className="type-headline text-label-1">
            {title}
          </Heading>
          {hint ? (
            <p id={hintId} className="type-footnote text-label-3">
              {hint}
            </p>
          ) : null}
          <p id={summaryId} className="mt-1 type-subheadline text-label-2" data-testid={props.summaryTestId}>
            {state === "loading" ? <Skeleton className="inline-block h-[1lh] w-3/4 align-middle" /> : <SwapText text={summary} reduce={reduce} />}
          </p>
        </div>
        {period || ready ? (
          <div className="flex items-center gap-2 max-md:w-full">
            {period ? (
              <div data-chart-period className="max-md:flex-1">
                <PeriodPicker id={id} value={period.value} options={period.options} onChange={period.onChange} label={period.label ?? t("charts.period.label")} />
              </div>
            ) : null}
            {ready ? (
              <div data-chart-menu>
                <DropdownMenu>
                  <DropdownMenuTrigger render={<IconButton size="md" label={t("charts.menu")} data-testid={`chart-menu-${id}`} />}>
                    <Ellipsis aria-hidden />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="min-w-48">
                    {showPlot ? <DropdownMenuItem onClick={downloadImage}>{t("charts.downloadImage")}</DropdownMenuItem> : null}
                    <DropdownMenuItem onClick={() => window.print()}>{t("charts.print")}</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      {stale && ready ? (
        <p data-testid={`chart-stale-${id}`} className="flex items-center gap-2 rounded-lg bg-status-warning px-3 py-2 type-footnote text-status-warning-fg">
          <AlertTriangle aria-hidden className="size-4 shrink-0" />
          {stale.reason ? t("charts.staleReason", { ago: f.ago(stale.since), reason: stale.reason }) : t("charts.stale", { ago: f.ago(stale.since) })}
        </p>
      ) : null}

      {showPlot && legend && legend.length >= 2 ? (
        <ul aria-hidden className="flex flex-wrap gap-x-4 gap-y-1 type-footnote text-label-1" data-testid={`chart-legend-${id}`}>
          {legend.map((item) => (
            <li key={item.key} className="flex items-center gap-1.5">
              <span className="size-2.5 shrink-0 rounded-[2px]" style={{ background: item.color }} />
              {item.label}
            </li>
          ))}
        </ul>
      ) : null}

      {tableMode && ready ? null : (
        <div data-testid={`chart-body-${id}`} style={{ minHeight: height }} className="flex min-w-0 flex-col justify-center">
          {shownState === "loading" ? <ChartSkeleton height={height} /> : null}
          {shownState === "empty" ? (
            <div className="flex flex-col items-start gap-2 px-1">
              <p className="type-callout font-medium text-label-1">{t("charts.empty.title")}</p>
              <p className="type-footnote text-label-2">{empty?.reason ?? t("charts.empty.period")}</p>
              {empty?.action ? (
                <Button variant="secondary" size="md" onClick={empty.action.onClick}>
                  {empty.action.label}
                </Button>
              ) : null}
            </div>
          ) : null}
          {shownState === "error" ? (
            <div role="status" className="flex flex-col items-start gap-2 px-1">
              <p className="type-callout font-medium text-label-1">{t("charts.error.title")}</p>
              {error ? <p className="type-footnote text-label-2">{error}</p> : null}
              {onRetry ? (
                <Button ref={retryRef} variant="secondary" size="md" onClick={onRetry}>
                  {t("charts.error.retry")}
                </Button>
              ) : null}
            </div>
          ) : null}
          {tooFew ? (
            <div data-testid={`chart-few-${id}`} className="flex flex-col gap-3">
              <dl className="flex flex-wrap gap-6">
                {numberColumns.slice(0, 3).map((c) => {
                  const total = rows.reduce((s, r) => s + (typeof r[c.key] === "number" ? (r[c.key] as number) : 0), 0);
                  return (
                    <div key={c.key}>
                      <dt className="type-footnote text-label-2">{c.label}</dt>
                      <dd className="type-title-2 font-semibold text-label-1 tabular-nums">{c.kind === "percent" ? f.pct(total / rows.length) : f.num(total)}</dd>
                    </div>
                  );
                })}
              </dl>
              <p className="type-footnote text-label-3">{t("charts.tooFew")}</p>
            </div>
          ) : null}
          {showPlot ? (
            <div
              ref={plotRef}
              role="group"
              tabIndex={0}
              aria-label={t("charts.kb.label")}
              onKeyDown={kb.onKeyDown}
              onBlur={kb.onBlur}
              className="ch-plot min-w-0 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus)"
              data-reveal={reveal ? "true" : "false"}
              data-renderer={renderer}
              data-testid={`chart-plot-${id}`}
            >
              <div aria-hidden="true">{inView ? plot : <ChartSkeleton height={height} />}</div>
            </div>
          ) : null}
        </div>
      )}

      {ready ? <ChartTable id={id} caption={caption} model={model} visible={tableMode || tooFew} /> : null}

      {ready ? (
        <div data-chart-footer className="flex flex-wrap items-center gap-2 max-md:[&>[data-slot=button]]:flex-1">
          {!tooFew ? (
            <Button variant="secondary" size="md" onClick={() => setTableMode((v) => !v)} data-testid={`chart-table-toggle-${id}`}>
              {tableMode ? t("charts.showChart") : t("charts.showTable")}
            </Button>
          ) : null}
          <Button variant="secondary" size="md" onClick={downloadCsv} data-testid={`chart-csv-${id}`}>
            <SwapText text={downloaded ? t("charts.downloaded") : t("charts.download")} reduce={reduce} />
          </Button>
          {updatedAt ? (
            <span className="ms-auto type-caption text-label-3 max-md:w-full" title={f.ago(updatedAt)}>
              {t("charts.updated", { time: f.time(updatedAt) })}
            </span>
          ) : null}
        </div>
      ) : null}

      <div aria-live="polite" className="sr-only" data-testid={`chart-live-${id}`}>
        {live}
      </div>
    </figure>
  );
}
