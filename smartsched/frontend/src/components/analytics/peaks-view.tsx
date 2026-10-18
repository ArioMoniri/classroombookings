"use client";
/**
 * AS-16 "Yoğun saatler" (`/analytics/heatmap?tab=peaks`): the busy share of rooms per weekday × period × group from
 * the published history (backend `GET /analytics/peaks`, services/peaks.py). One sentence names the busiest hour, the
 * peak list gives each value with its 80 % range in text (never colour alone), the period profile sits in the shared
 * ChartCard, and the CSV is the backend's. An empty install shows the `needs` sentence, never a blank chart.
 */
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { ChartCard } from "@/components/charts/chart-card";
import type { ChartColumn } from "@/components/charts/chart-csv";
import { LazyBarChart } from "@/components/charts/chart-lazy";
import { singleConfig } from "@/components/charts/chart-tokens";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { adaptiveApi, PEAK_GROUPS, PEAK_KINDS, usePeaks, type PeakGroup, type PeakKind } from "@/lib/api/adaptive";
import { useI18n } from "@/lib/i18n/provider";
import { CsvButton } from "./csv-button";
import { ConfidenceNote, RangeText } from "./forecast-bits";

const SHOWN = 12;
const SERIES = ["value"] as const;

type ProfileRow = { period: string; value: number };

export function PeaksView() {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const { term, terms } = useActiveTerm();
  const [termId, setTermId] = useState<number | null>(null);
  const [group, setGroup] = useState<PeakGroup>("building");
  const [kind, setKind] = useState<PeakKind>("LECTURE");
  const [all, setAll] = useState(false);
  const query = { term_id: termId ?? term?.id ?? null, group_by: group, period_kind: kind };
  const q = usePeaks(query, query.term_id !== null || terms.length === 0);
  const d = q.data;
  const peaks = useMemo(() => [...(d?.peaks ?? [])].sort((a, b) => b.value - a.value), [d]);
  const rows = useMemo<ProfileRow[]>(() => (d?.period_profile ?? []).map((p) => ({ period: t("adaptive.peaks.periodN", { n: p.period }), value: p.value / 100 })), [d, t]);
  const columns = useMemo<ChartColumn<ProfileRow>[]>(() => [{ key: "period", label: t("adaptive.peaks.col.period") }, { key: "value", label: t("adaptive.peaks.col.value"), kind: "percent" }], [t]);
  const config = useMemo(() => singleConfig("value", t("adaptive.peaks.col.value")), [t]);
  const top = peaks[0];
  const groupText = (g: string) => (g === "*" ? t("adaptive.peaks.allRooms") : g);
  const pct = (v: number) => `%${n(Math.round(v))}`;

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="peaks-view">
      <section aria-label={t("analytics.controls")} className="flex flex-wrap items-end gap-x-4 gap-y-3 rounded-xl bg-card p-3 edge-hairline">
        <label className="flex min-w-0 flex-col gap-1 max-sm:w-full">
          <span className="type-footnote font-medium text-label-2">{t("adaptive.peaks.term")}</span>
          <NativeSelect size="sm" className="w-56 max-sm:w-full" value={query.term_id ?? ""} onChange={(e) => setTermId(e.target.value ? Number(e.target.value) : null)} data-testid="peaks-term">
            {terms.map((x) => (
              <option key={x.id} value={x.id}>{x.name}</option>
            ))}
          </NativeSelect>
        </label>
        <label className="flex min-w-0 flex-col gap-1 max-sm:w-full">
          <span className="type-footnote font-medium text-label-2">{t("analytics.groupBy")}</span>
          <NativeSelect size="sm" className="w-44 max-sm:w-full" value={group} onChange={(e) => setGroup(e.target.value as PeakGroup)} data-testid="peaks-group">
            {PEAK_GROUPS.map((g) => (
              <option key={g} value={g}>{t(`adaptive.peaks.group.${g}`)}</option>
            ))}
          </NativeSelect>
        </label>
        <label className="flex min-w-0 flex-col gap-1 max-sm:w-full">
          <span className="type-footnote font-medium text-label-2">{t("adaptive.peaks.kind")}</span>
          <NativeSelect size="sm" className="w-44 max-sm:w-full" value={kind} onChange={(e) => setKind(e.target.value as PeakKind)} data-testid="peaks-kind">
            {PEAK_KINDS.map((k) => (
              <option key={k} value={k}>{t(`adaptive.kind.${k}`)}</option>
            ))}
          </NativeSelect>
        </label>
        <div className="flex flex-wrap gap-2 sm:ml-auto">
          <CsvButton href={adaptiveApi.peaksCsvUrl(query)} label={t("analytics.csv")} testId="peaks-csv" />
          <Button size="sm" variant="ghost" nativeButton={false} render={<Link href="/analytics/forecast" />}>
            {t("adaptive.forecast.link")} <ArrowRight aria-hidden />
          </Button>
        </div>
      </section>

      {q.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : q.isError ? (
        <p role="alert" className="type-callout text-label-2">{t("adaptive.loadError")}</p>
      ) : !d || d.confidence === "none" || d.cells.length === 0 ? (
        <div className="rounded-xl bg-fill-3 px-4 py-5" data-testid="peaks-needs">
          <p className="type-callout text-label-1">{d?.needs?.[lang] || t("adaptive.peaks.empty")}</p>
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-1">
            <p className="type-title-3 text-label-1" data-testid="peaks-summary">
              {top ? t("adaptive.peaks.summary", { cell: top.label?.[lang] ?? "", group: groupText(top.group), pct: pct(top.value), n: n(peaks.length), threshold: pct(d.threshold_pct) }) : t("adaptive.peaks.noPeak", { threshold: pct(d.threshold_pct) })}
            </p>
            <ConfidenceNote confidence={d.confidence} label={d.confidence_label?.[lang]} basis={d.basis?.[lang]} needs={d.needs?.[lang]} />
          </div>
          {peaks.length ? (
            <div className="overflow-x-auto rounded-xl bg-card edge-hairline">
              <table className="w-full type-callout" data-testid="peaks-table">
                <caption className="sr-only">{t("adaptive.peaks.tableCaption", { threshold: pct(d.threshold_pct) })}</caption>
                <thead>
                  <tr className="text-left type-footnote text-label-2">
                    <th scope="col" className="px-3 py-2 font-medium">{t("adaptive.peaks.col.when")}</th>
                    <th scope="col" className="px-3 py-2 font-medium">{t("adaptive.peaks.col.group")}</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">{t("adaptive.peaks.col.value")}</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">{t("adaptive.peaks.col.range")}</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium max-sm:hidden">{t("adaptive.peaks.col.weeks")}</th>
                  </tr>
                </thead>
                <tbody>
                  {peaks.slice(0, all ? peaks.length : SHOWN).map((c) => (
                    <tr key={`${c.day}-${c.period}-${c.group}`} className="not-last:edge-hairline-b" data-testid="peak-row">
                      <th scope="row" className="px-3 py-2 text-left font-normal">{c.label?.[lang]}</th>
                      <td className="px-3 py-2">{groupText(c.group)}</td>
                      <td className="px-3 py-2 text-right font-semibold tabular-nums">{pct(c.value)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-label-2">
                        <RangeText lo={c.lo80} hi={c.hi80} format={pct} confidence={d.confidence} method={d.method} />
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-label-2 max-sm:hidden">{n(c.n_weeks)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {peaks.length > SHOWN && !all ? (
                <div className="p-2">
                  <Button size="sm" variant="secondary" onClick={() => setAll(true)}>{t("adaptive.showAll", { n: peaks.length })}</Button>
                </div>
              ) : null}
            </div>
          ) : null}
          <ChartCard<ProfileRow>
            id="peaks-period-profile"
            title={t("adaptive.peaks.profileTitle")}
            hint={t("adaptive.peaks.profileHint")}
            summary={d.period_profile.some((p) => p.value > 0) ? t("adaptive.peaks.profileSummary", { period: t("adaptive.peaks.periodN", { n: maxPeriod(d.period_profile) }) }) : ""}
            state={rows.length ? "ready" : "empty"}
            empty={{ reason: t("adaptive.peaks.empty") }}
            columns={columns}
            rows={rows}
            series={1}
            height={180}
          >
            {(ctx) => <LazyBarChart {...ctx} valueFormatter={pct} tickFormatter={pct} data={rows.map((r) => ({ period: r.period, value: Math.round(r.value * 100) }))} config={config} xKey="period" series={SERIES} />}
          </ChartCard>
        </>
      )}
    </div>
  );
}

function maxPeriod(profile: readonly { period: number; value: number }[]): number {
  return profile.reduce((best, p) => (p.value > best.value ? p : best), profile[0] ?? { period: 0, value: -1 }).period;
}
