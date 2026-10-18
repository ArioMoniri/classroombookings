"use client";
/**
 * Yönetim › Operasyon › "İstekler ve gecikme" (CH-06, docs/design/v3/charts.md §4 row 2): three small multiples on the
 * shared ChartCard (requests/min, 5xx/min, p95 ms), each on its own axis with a shared minute axis; never a dual axis.
 * One summary, one table twin and one CSV for the three measures; the keyboard scrub moves all three tooltips together.
 * Replaces the hand-drawn SVG (ops-model `chartGeometry`, retired). The range stays 30 / 60 / 180 dk: the backend caps
 * `/ops/requests?minutes=` at 180 (24 sa / 7 g need a coarser step server-side; open for W3-OPS).
 */
import { useMemo, useRef, useState } from "react";
import { ChartCard, type ChartPlotContext } from "@/components/charts/chart-card";
import type { ChartColumn } from "@/components/charts/chart-csv";
import { useChartFormat } from "@/components/charts/chart-format";
import type { ChartApi } from "@/components/charts/chart-form-types";
import { LazyLineChart } from "@/components/charts/chart-lazy";
import { singleConfig } from "@/components/charts/chart-tokens";
import { useOpsRequests } from "@/lib/api/ops";
import { useI18n } from "@/lib/i18n/provider";
import { requestsDigest, totals } from "./ops-model";

const RANGES = ["30", "60", "180"] as const;
type Range = (typeof RANGES)[number];
type Row = { time: string; requests: number; errors: number; p95?: number };
const MEASURES = [
  { key: "requests", label: "charts.ops.mRequests" },
  { key: "errors", label: "charts.ops.mErrors" },
  { key: "p95", label: "charts.ops.mP95" },
] as const;
const MINI_DESKTOP = 104;
const MINI_PHONE = 96;

export function RequestsChart() {
  const { t, locale } = useI18n();
  const f = useChartFormat();
  const [range, setRange] = useState<Range>("60");
  const q = useOpsRequests(Number(range));
  const points = useMemo(() => q.data?.points ?? [], [q.data]);
  const rows = useMemo<Row[]>(() => points.map((p) => ({ time: f.time(new Date(p.t * 1000)), requests: p.requests, errors: p.errors, p95: p.p95_ms ?? undefined })), [points, f]);
  const columns: ChartColumn<Row>[] = [
    { key: "time", label: t("charts.ops.time") },
    { key: "requests", label: t("charts.ops.requests"), kind: "number" },
    { key: "errors", label: t("charts.ops.errors"), kind: "number" },
    { key: "p95", label: t("charts.ops.p95"), kind: "number" },
  ];
  const tot = totals(points);
  const dig = requestsDigest(points);
  const nf = new Intl.NumberFormat(locale === "tr" ? "tr" : "en", { maximumFractionDigits: 1 });
  const summary = points.length
    ? `${t("ops.chart.summary", { requests: nf.format(tot.requests), errors: nf.format(tot.errors), pct: nf.format(tot.errorPct), p95: tot.p95 == null ? "–" : nf.format(tot.p95) })}. ` +
      `${t("charts.ops.avg", { n: f.num(dig.perMinute) })}${dig.spike ? `; ${t("charts.ops.spike", { time: f.time(new Date(dig.spike.t * 1000)), n: f.num(dig.spike.errors) })}` : ""}.`
    : "";
  const stale = q.isError && q.data ? { since: new Date(q.dataUpdatedAt), reason: t("charts.ops.staleReason") } : undefined;

  return (
    <section data-testid="ops-chart">
      <ChartCard<Row>
        id="ops-requests"
        title={t("ops.chart.title")}
        hint={q.data?.source === "prometheus" ? t("charts.ops.sourceProm") : t("charts.ops.sourceProcess")}
        summary={summary}
        summaryTestId="ops-chart-summary"
        state={q.isPending ? "loading" : q.isError && !q.data ? "error" : points.length ? "ready" : "empty"}
        onRetry={() => void q.refetch()}
        stale={stale}
        updatedAt={q.dataUpdatedAt ? new Date(q.dataUpdatedAt) : undefined}
        period={{
          value: range,
          label: t("ops.chart.range"),
          onChange: (v) => setRange(v as Range),
          options: RANGES.map((r) => ({ value: r, label: t("ops.chart.minutes", { n: Number(r) }), testId: `ops-range-${r}` })),
        }}
        columns={columns}
        rows={rows}
        series={1}
        height={MINI_DESKTOP * 3}
        phoneHeight={MINI_PHONE * 3}
        headingLevel={2}
      >
        {(ctx) => <Multiples ctx={ctx} rows={rows} />}
      </ChartCard>
    </section>
  );
}

/** Three stacked line charts; one combined API so the card's keyboard layer scrubs all three. */
function Multiples({ ctx, rows }: { ctx: ChartPlotContext; rows: Row[] }) {
  const { t } = useI18n();
  const apis = useRef<(ChartApi | null)[]>([null, null, null]);
  const ready = useMemo(
    () =>
      MEASURES.map((_, i) => (api: ChartApi) => {
        apis.current[i] = api;
        if (i !== 0) return;
        const each = (fn: (a: ChartApi) => void) => apis.current.forEach((a) => a && fn(a));
        ctx.onReady({
          getDataURL: (opts) => apis.current[0]?.getDataURL(opts) ?? null,
          dispatchAction: (action) => each((a) => a.dispatchAction(action)),
          showTip: (index) => each((a) => a.showTip(index)),
          hideTip: () => each((a) => a.hideTip()),
        });
      }),
    [ctx],
  );
  const mini = Math.floor(ctx.height / 3);
  return (
    <div className="flex flex-col">
      {MEASURES.map((m, i) => (
        <div key={m.key}>
          <p className="type-caption text-label-2">{t(m.label)}</p>
          <LazyLineChart {...ctx} height={mini - 18} onReady={ready[i]!} data={rows} config={singleConfig(m.key, t(m.label))} xKey="time" series={[m.key]} />
        </div>
      ))}
    </div>
  );
}
