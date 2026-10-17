"use client";
/**
 * Yapay zekâ › Kullanım: KPI tiles, the org budget meter, "Günlük token kullanımı" (stacked columns by feature, fixed
 * colour per feature, one axis, a table twin that is always in the DOM), a by-feature list and the per-user table
 * with search and a meter against each user's limit. Metadata only: no prompt or answer text exists to show.
 */
import { useMemo, useState } from "react";
import { Alert, Loading } from "@/components/admin/kit";
import { BarList } from "@/components/ui/bar-list";
import { Card } from "@/components/ui/card";
import { EvilBarChart } from "@/components/ui/evilcharts/charts/recharts-bar-chart";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useAiSummary, useAiUsage, type UsageRow } from "@/lib/api/ai-admin";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { Meter, StatTile, Tokens, useAiLabels } from "./ai-kit";
import { activeSeries, compactTokens, dayChartData, errorMessage, meterState, pctText, resetDate, SERIES_COLOR, sortUsers, usd, userPct, type ChartSeries } from "./ai-model";

type Period = "7d" | "30d" | "month";

function startFor(period: Period): string | undefined {
  if (period === "month") return undefined;
  const d = new Date(Date.now() - (period === "7d" ? 6 : 29) * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Istanbul", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

export function UsageTab() {
  const { t, locale } = useI18n();
  const [period, setPeriod] = useState<Period>("month");
  const start = startFor(period);
  const summary = useAiSummary();
  const days = useAiUsage("day", { start });
  const features = useAiUsage("feature", { start });
  if (summary.isLoading) return <Loading />;
  if (summary.isError || !summary.data) return <Alert tone="error">{errorMessage(summary.error, locale, t("aiAdmin.error.load"))}</Alert>;
  const org = summary.data.org;
  const blocked = (features.data?.rows ?? []).reduce((a, r) => a + r.refused, 0);
  const calls = (features.data?.rows ?? []).reduce((a, r) => a + r.calls, 0);
  const tokens = (features.data?.rows ?? []).reduce((a, r) => a + r.tokens, 0);
  const cost = (features.data?.rows ?? []).reduce((a, r) => a + r.cost_usd, 0);
  return (
    <div className="flex flex-col gap-5" data-testid="ai-usage">
      <SegmentedControl<Period>
        aria-label={t("aiAdmin.usage.period")}
        value={period}
        onValueChange={setPeriod}
        options={[
          { value: "7d", label: t("aiAdmin.usage.period7d"), testId: "ai-period-7d" },
          { value: "30d", label: t("aiAdmin.usage.period30d"), testId: "ai-period-30d" },
          { value: "month", label: t("aiAdmin.usage.periodMonth"), testId: "ai-period-month" },
        ]}
        semantics="radiogroup"
        className="self-start"
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile testId="ai-kpi-tokens" label={t("aiAdmin.kpi.tokens")} value={<Tokens n={tokens} />} />
        <StatTile testId="ai-kpi-cost" label={t("aiAdmin.kpi.cost")} value={usd(cost, locale)} note={t("aiAdmin.kpi.costNote")} />
        <StatTile testId="ai-kpi-requests" label={t("aiAdmin.kpi.requests")} value={new Intl.NumberFormat(locale === "tr" ? "tr-TR" : "en-GB").format(calls)} />
        <StatTile testId="ai-kpi-blocked" label={t("aiAdmin.kpi.blocked")} value={new Intl.NumberFormat(locale === "tr" ? "tr-TR" : "en-GB").format(blocked)} />
      </div>
      <Card className="px-4 py-4">
        {org.budget_tokens || org.budget_cost_usd ? (
          <Meter
            testId="ai-org-meter"
            pct={org.pct}
            state={meterState(org.pct, org.soft_pct)}
            label={
              org.budget_tokens
                ? t("aiAdmin.budget.line", { used: compactTokens(org.month_tokens, locale), limit: compactTokens(org.budget_tokens, locale), date: resetDate("month", locale) })
                : t("aiAdmin.budget.lineCost", { used: usd(org.month_cost_usd, locale), limit: usd(org.budget_cost_usd, locale), date: resetDate("month", locale) })
            }
          />
        ) : (
          <p className="type-callout text-label-2" data-testid="ai-org-meter">
            {t("aiAdmin.budget.none")}
          </p>
        )}
      </Card>
      <DailyChart rows={days.data?.rows ?? []} loading={days.isLoading} lastDays={period === "7d" ? 7 : undefined} />
      <ByFeature rows={features.data?.rows ?? []} />
      <UsersTable start={start} />
    </div>
  );
}

function DailyChart({ rows, loading, lastDays }: { rows: UsageRow[]; loading: boolean; lastDays?: number }) {
  const { t, locale } = useI18n();
  const labels = useAiLabels();
  const [view, setView] = useState<"chart" | "table">("chart");
  const points = useMemo(() => dayChartData(rows, locale, lastDays), [rows, locale, lastDays]);
  const series = activeSeries(points);
  const label = (s: ChartSeries) => (s === "other" ? t("aiAdmin.feature.other") : labels.feature(s));
  const key = series.join(",");
  const config = useMemo(
    () => Object.fromEntries(key.split(",").filter(Boolean).map((s) => [s, { label: s === "other" ? t("aiAdmin.feature.other") : labels.feature(s), colors: { light: [SERIES_COLOR[s as ChartSeries]], dark: [SERIES_COLOR[s as ChartSeries]] } }])),
    [key, t, labels],
  );
  const total = points.reduce((a, p) => a + p.total, 0);
  const top = series.map((s) => ({ s, v: points.reduce((a, p) => a + p[s], 0) })).sort((a, b) => b.v - a.v)[0];
  return (
    <Card className="gap-3 px-4 py-4" data-testid="ai-daily-chart">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="type-headline text-label-1">{t("aiAdmin.usage.chart")}</h3>
        <SegmentedControl<"chart" | "table">
          size="sm"
          aria-label={t("aiAdmin.usage.view")}
          value={view}
          onValueChange={setView}
          options={[
            { value: "chart", label: t("aiAdmin.usage.chartView"), testId: "ai-view-chart" },
            { value: "table", label: t("aiAdmin.usage.table"), testId: "ai-view-table" },
          ]}
        />
      </div>
      {loading ? <Loading /> : null}
      {!loading && !total ? <p className="type-callout text-label-2">{t("aiAdmin.usage.empty")}</p> : null}
      {total ? (
        <p className="type-footnote text-label-2" data-testid="ai-chart-summary">
          {t("aiAdmin.usage.summary", { total: compactTokens(total, locale), top: top ? label(top.s) : "", pct: top ? pctText(Math.round((100 * top.v) / total), locale) : "" })}
        </p>
      ) : null}
      {total && view === "chart" ? (
        <div aria-hidden className="h-56 w-full overflow-x-auto">
          <div className="h-full min-w-[480px]">
            <EvilBarChart config={config as never} data={points as never[]} stackType="stacked" animationType="none" className="aspect-auto size-full">
              <EvilBarChart.Grid vertical={false} />
              <EvilBarChart.XAxis dataKey="label" />
              <EvilBarChart.YAxis width={48} tickFormatter={(v: number) => compactTokens(v, locale)} />
              <EvilBarChart.Tooltip variant="frosted-glass" />
              <EvilBarChart.Legend />
              {series.map((s) => (
                <EvilBarChart.Bar key={s} dataKey={s} />
              ))}
            </EvilBarChart>
          </div>
        </div>
      ) : null}
      {total ? (
        <div className={view === "table" ? "overflow-x-auto" : "sr-only"} data-testid="ai-chart-table">
          <table className="w-full type-footnote">
            <thead>
              <tr className="text-left text-label-2">
                <th scope="col" className="py-1 pr-3">
                  {t("aiAdmin.usage.day")}
                </th>
                {series.map((s) => (
                  <th key={s} scope="col" className="py-1 pr-3 text-right">
                    {label(s)}
                  </th>
                ))}
                <th scope="col" className="py-1 text-right">
                  {t("aiAdmin.usage.total")}
                </th>
              </tr>
            </thead>
            <tbody>
              {points
                .filter((p) => p.total > 0 || view === "table")
                .map((p) => (
                  <tr key={p.day} className="border-t border-hairline">
                    <th scope="row" className="py-1 pr-3 text-left font-normal text-label-1">
                      {p.label}
                    </th>
                    {series.map((s) => (
                      <td key={s} className="py-1 pr-3 text-right tabular-nums">
                        {compactTokens(p[s], locale)}
                      </td>
                    ))}
                    <td className="py-1 text-right font-medium tabular-nums">{compactTokens(p.total, locale)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  );
}

function ByFeature({ rows }: { rows: UsageRow[] }) {
  const { t, locale } = useI18n();
  const labels = useAiLabels();
  if (!rows.length) return null;
  return (
    <Card className="gap-3 px-4 py-4" data-testid="ai-by-feature">
      <h3 className="type-headline text-label-1">{t("aiAdmin.usage.byFeature")}</h3>
      <BarList aria-label={t("aiAdmin.usage.byFeature")} items={rows.map((r) => ({ key: String(r.key), label: labels.feature(String(r.key)), value: r.tokens, display: compactTokens(r.tokens, locale) }))} />
    </Card>
  );
}

function UsersTable({ start }: { start?: string }) {
  const { t, locale } = useI18n();
  const labels = useAiLabels();
  const [q, setQ] = useState("");
  const users = useAiUsage("user", { start });
  const summary = useAiSummary();
  const soft = summary.data?.org.soft_pct ?? 80;
  const rows = useMemo(() => sortUsers(users.data?.rows ?? [], q), [users.data, q]);
  return (
    <Card className="gap-3 px-4 py-4" data-testid="ai-users">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h3 className="type-headline text-label-1">{t("aiAdmin.users.title")}</h3>
        <div className="flex w-full max-w-xs flex-col gap-1.5">
          <Label htmlFor="ai-user-search" className="type-footnote font-medium text-label-2">
            {t("aiAdmin.users.search")}
          </Label>
          <Input id="ai-user-search" type="search" value={q} placeholder={t("aiAdmin.users.searchPh")} onChange={(e) => setQ(e.target.value)} data-testid="ai-user-search" />
        </div>
      </div>
      {users.isLoading ? <Loading /> : null}
      {!users.isLoading && !rows.length ? <p className="type-callout text-label-2">{t("aiAdmin.users.empty")}</p> : null}
      <ul className="flex flex-col divide-y divide-hairline">
        {rows.map((r) => {
          const pct = userPct(r);
          const limit = r.limits?.monthly || r.limits?.daily || 0;
          return (
            <li key={String(r.key)} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:gap-4" data-testid={`ai-user-row-${r.key ?? "none"}`}>
              <div className="min-w-0 sm:w-56">
                <p className="truncate type-callout font-medium text-label-1">{r.label ?? t("aiAdmin.users.system")}</p>
                <p className="truncate type-footnote text-label-2">{[r.email, r.role ? t(`aiAdmin.role.${["ADMIN", "PLANNER", "VIEWER", "TEACHER"].includes(r.role) ? r.role : "CUSTOM"}` as MessageKey) : null].filter(Boolean).join(" · ")}</p>
              </div>
              <div className="flex-1">
                <Meter
                  pct={pct}
                  state={meterState(pct, soft)}
                  label={
                    <>
                      <Tokens n={r.tokens} /> {limit ? t("aiAdmin.users.ofLimit", { limit: compactTokens(limit, locale) }) : t("aiAdmin.users.noLimit")}
                    </>
                  }
                />
              </div>
              <p className="type-footnote text-label-2 sm:w-48 sm:text-right">
                {t("aiAdmin.users.calls", { n: r.calls })} · {t("aiAdmin.users.blocked", { n: r.refused })} · {usd(r.cost_usd, locale)}
              </p>
              <span className="sr-only">{labels.state(meterState(pct, soft))}</span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
