"use client";
/**
 * /admin › "Bu dönem" (CH-07, docs/design/v3/charts.md §4 rows 5–6): bookings per week and booking-request outcomes
 * per week for the current term, two ChartCards with the EvilCharts ECharts bar (lazy; the engine loads only when a
 * plot shows). Exam weeks carry a direct "Sınav haftası" label on the axis and a text column in the table; the
 * current week is hatched. Data: `GET /bookings/stats/weekly` (lib/api/stats.ts). While that route is missing the
 * section shows one honest "veri yok" card, never invented numbers. Shown to people who may export all bookings
 * (`system.export_bookings`), since the counts cover everyone's bookings. Original work.
 */
import { useMemo } from "react";
import { ChartCard, type ChartState } from "@/components/charts/chart-card";
import type { ChartColumn } from "@/components/charts/chart-csv";
import { useChartFormat } from "@/components/charts/chart-format";
import { LazyBarChart } from "@/components/charts/chart-lazy";
import { categoricalConfig, legendItems, singleConfig } from "@/components/charts/chart-tokens";
import { Card } from "@/components/ui/card";
import { useBookingContext } from "@/lib/api/crbs";
import { serverMessage } from "@/lib/api/error-text";
import { isMissingRoute, useWeeklyBookingStats } from "@/lib/api/stats";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";
import { SectionTitle } from "./kit";
import { bookingsSummary, lastPartial, requestsSummary, requestTotals, weeklyRows, type WeekRow } from "./booking-weekly-model";

const REQUEST_SERIES = ["approved", "rejected", "pending"] as const;

export function BookingWeekly() {
  const { can } = usePermissions();
  if (!can("system.export_bookings")) return null;
  return <BookingWeeklyCharts />;
}

function BookingWeeklyCharts() {
  const { t, locale } = useI18n();
  const f = useChartFormat();
  const ctx = useBookingContext();
  const term = ctx.data?.sessions.find((s) => s.is_current) ?? null;
  const q = useWeeklyBookingStats(term?.id ?? null, !!term);
  const missing = q.isError && isMissingRoute(q.error);
  const rows = useMemo(() => (q.data ? weeklyRows(q.data, t) : []), [q.data, t]);
  const partial = lastPartial(rows);
  const examWeeks = useMemo(() => new Set(rows.filter((r) => r.exam).map((r) => r.week)), [rows]);
  const xTick = useMemo(() => (s: string) => (examWeeks.has(s) ? `${s}\n${t("charts.bookings.exam")}` : s), [examWeeks, t]);

  const noTerm = ctx.isSuccess && !term;
  const loading = ctx.isLoading || (!!term && q.isLoading);
  const state: ChartState = loading ? "loading" : missing || noTerm ? "empty" : q.isError ? "error" : "ready";
  const error = q.isError && !missing ? (serverMessage(q.error, locale) ?? undefined) : undefined;
  const range = rows.length ? { from: rows[0]!.start, to: rows.at(-1)!.end } : undefined;

  const bookingsCols: ChartColumn<WeekRow>[] = [
    { key: "week", label: t("charts.bookings.week") },
    { key: "start", label: t("charts.bookings.start"), kind: "date" },
    { key: "bookings", label: t("charts.bookings.count"), kind: "number" },
    { key: "examText", label: t("charts.bookings.exam") },
  ];
  const bookingsConfig = useMemo(() => singleConfig("bookings", t("charts.bookings.count")), [t]);
  const bookingTotal = rows.reduce((s, r) => s + r.bookings, 0);

  const requestSpecs = REQUEST_SERIES.map((k) => ({ key: k, label: t(`charts.requests.${k}`) }));
  const requestConfig = useMemo(() => categoricalConfig(REQUEST_SERIES.map((k) => ({ key: k, label: t(`charts.requests.${k}`) }))), [t]);
  const requestCols: ChartColumn<WeekRow>[] = [
    { key: "week", label: t("charts.bookings.week") },
    { key: "start", label: t("charts.bookings.start"), kind: "date" },
    ...requestSpecs.map((s) => ({ key: s.key, label: s.label, kind: "number" as const })),
  ];
  const requestsTotal = requestTotals(rows).total;

  return (
    <section aria-labelledby="admin-term-charts" data-testid="admin-term-charts">
      <SectionTitle id="admin-term-charts">{term ? t("charts.bookings.section", { term: term.name }) : t("charts.bookings.sectionPlain")}</SectionTitle>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="px-4 py-4" data-testid="admin-bookings-weekly">
          <ChartCard<WeekRow>
            id="bookings-weekly"
            title={t("charts.bookings.title")}
            hint={t("charts.bookings.hint")}
            summary={bookingsSummary(rows, t, f)}
            state={state === "ready" && !bookingTotal ? "empty" : state}
            empty={{ reason: missing ? t("charts.bookings.missing") : noTerm ? t("charts.bookings.noTerm") : t("charts.bookings.empty") }}
            error={error}
            onRetry={() => void q.refetch()}
            columns={bookingsCols}
            rows={rows}
            series={1}
            partial={partial}
            range={range}
            unit={t("charts.bookings.count").toLocaleLowerCase(locale)}
          >
            {(c) => <LazyBarChart {...c} xTickFormatter={xTick} data={rows} config={bookingsConfig} xKey="week" series={["bookings"]} />}
          </ChartCard>
        </Card>
        {/* the route missing: one honest card is enough; the second would repeat the same sentence */}
        {missing || noTerm ? null : (
          <Card className="px-4 py-4" data-testid="admin-requests-weekly">
            <ChartCard<WeekRow>
              id="requests-weekly"
              title={t("charts.requests.title")}
              hint={t("charts.requests.hint")}
              summary={requestsSummary(rows, t, f)}
              state={state === "ready" && !requestsTotal ? "empty" : state}
              empty={{ reason: t("charts.requests.empty") }}
              error={error}
              onRetry={() => void q.refetch()}
              columns={requestCols}
              rows={rows}
              series={REQUEST_SERIES.length}
              legend={legendItems(requestSpecs)}
              partial={partial}
              range={range}
            >
              {(c) => <LazyBarChart {...c} xTickFormatter={xTick} data={rows} config={requestConfig} xKey="week" series={REQUEST_SERIES} stackType="stacked" />}
            </ChartCard>
          </Card>
        )}
      </div>
    </section>
  );
}
