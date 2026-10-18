"use client";
/**
 * AS-16 `/analytics/forecast` "Tahmin ve senaryo": next-term room demand per group with calibrated 80 % ranges
 * ("düşük güven" while the backend says low), the hours where suitable rooms may run short, and the what-if
 * (+N % enrolment for the institution, a faculty or a programme) with an optional draft run. Every block says how
 * sure it is and, on an empty install, what it needs; nothing is a chart of unexplained numbers.
 */
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/common/page-header";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { FORECAST_GROUPS, useDemandForecast, useShortfall, type ForecastCell, type ForecastGroup, type ShortfallCell } from "@/lib/api/adaptive";
import { intlLocale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { usePermissions } from "@/lib/permissions";
import { ConfidenceNote, NoTerms, RangeText } from "./forecast-bits";
import { WhatIfForm } from "./forecast-whatif";

const SHOWN = 10;

/** ISO weekday names (16 Feb 2026 is a Monday) */
export function useDayNames(): string[] {
  const { locale } = useI18n();
  return useMemo(() => Array.from({ length: 7 }, (_, i) => new Intl.DateTimeFormat(intlLocale(locale), { weekday: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2026, 1, 16 + i)))), [locale]);
}

export function ForecastView() {
  const { t } = useI18n();
  const { term, terms } = useActiveTerm();
  const [picked, setPicked] = useState<number | null>(null);
  const termId = picked ?? term?.id ?? null;
  const name = terms.find((x) => x.id === termId)?.name;
  const { can } = usePermissions();
  return (
    <div className="flex min-w-0 flex-col gap-5" data-testid="forecast-page">
      <PageHeader title={t("adaptive.forecast.title")} subtitle={name ? `${name} · ${t("adaptive.forecast.subtitle")}` : t("adaptive.forecast.subtitle")} />
      {terms.length === 0 ? (
        <NoTerms />
      ) : (
        <label className="flex max-w-xs flex-col gap-1">
          <span className="type-footnote font-medium text-label-2">{t("adaptive.peaks.term")}</span>
          <NativeSelect value={termId ?? ""} onChange={(e) => setPicked(e.target.value ? Number(e.target.value) : null)} data-testid="forecast-term">
            {terms.map((x) => (
              <option key={x.id} value={x.id}>{x.name}</option>
            ))}
          </NativeSelect>
        </label>
      )}
      {terms.length === 0 ? null : termId === null ? (
        <p className="type-callout text-label-2">{t("analytics.noTerm")}</p>
      ) : (
        <>
          <DemandBlock termId={termId} />
          <ShortfallBlock termId={termId} />
          {can("planning.edit") ? <WhatIfForm termId={termId} /> : null}
          <Card className="flex flex-row flex-wrap items-center justify-between gap-3 p-4">
            <div className="min-w-0">
              <h2 className="type-headline text-label-1">{t("adaptive.exams.title")}</h2>
              <p className="type-footnote text-label-2">{t("adaptive.exams.linkHint")}</p>
            </div>
            <Button variant="outline" nativeButton={false} render={<Link href={`/exams/advisor?term=${termId}`} />} data-testid="forecast-exams-link">
              {t("adaptive.exams.open")} <ArrowRight aria-hidden />
            </Button>
          </Card>
        </>
      )}
    </div>
  );
}

function cellLabel(c: ForecastCell, lang: "tr" | "en"): string {
  if (typeof c.label === "string") return c.label;
  return c.label?.[lang] || c.key;
}

function DemandBlock({ termId }: { termId: number }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const [group, setGroup] = useState<ForecastGroup>("building");
  const [all, setAll] = useState(false);
  const q = useDemandForecast(termId, group);
  const d = q.data;
  const cells = useMemo(() => [...(d?.cells ?? [])].sort((a, b) => b.value - a.value), [d]);
  const max = cells[0]?.value ?? 0;
  const num = (v: number) => n(Math.round(v * 10) / 10);
  return (
    <section aria-labelledby="fc-demand" className="flex flex-col gap-3" data-testid="forecast-demand">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 id="fc-demand" className="type-title-3 text-label-1">{t("adaptive.forecast.demandTitle")}</h2>
          <p className="type-footnote text-label-2">{d?.unit?.[lang] ? t("adaptive.forecast.unit", { unit: d.unit[lang] }) : t("adaptive.forecast.demandHint")}</p>
        </div>
        <label className="flex flex-col gap-1 max-sm:w-full">
          <span className="type-footnote font-medium text-label-2">{t("analytics.groupBy")}</span>
          <NativeSelect size="sm" className="w-44 max-sm:w-full" value={group} onChange={(e) => setGroup(e.target.value as ForecastGroup)} data-testid="forecast-group">
            {FORECAST_GROUPS.map((g) => (
              <option key={g} value={g}>{t(`adaptive.forecast.group.${g}`)}</option>
            ))}
          </NativeSelect>
        </label>
      </div>
      {q.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : q.isError ? (
        <p role="alert" className="type-callout text-label-2">{t("adaptive.loadError")}</p>
      ) : !d || d.confidence === "none" || cells.length === 0 ? (
        <div className="rounded-xl bg-fill-3 px-4 py-5" data-testid="forecast-needs">
          <p className="type-callout text-label-1">{d?.needs?.[lang] || t("adaptive.forecast.empty")}</p>
        </div>
      ) : (
        <>
          <ConfidenceNote confidence={d.confidence} basis={d.basis?.[lang]} needs={d.needs?.[lang]} />
          <Card className="gap-0 overflow-hidden py-0">
            <ul data-testid="forecast-cells">
              {cells.slice(0, all ? cells.length : SHOWN).map((c) => (
                <li key={c.key} className="grid grid-cols-[minmax(6rem,30%)_1fr_auto] items-center gap-3 px-4 py-2 type-callout not-last:edge-hairline-b max-sm:grid-cols-[1fr_auto]" data-testid="forecast-cell">
                  <span className="min-w-0 truncate text-label-1">{cellLabel(c, lang)}</span>
                  {/* the bar repeats the number (never the only channel) */}
                  <span className="h-2 rounded-full bg-fill-2 max-sm:hidden" aria-hidden>
                    <span className="block h-2 rounded-full bg-(--seq-4)" style={{ width: `${max ? Math.max(2, (c.value / max) * 100) : 0}%` }} />
                  </span>
                  <span className="flex flex-col items-end text-right">
                    <span className="font-semibold tabular-nums">{num(c.value)}</span>
                    <span className="type-footnote tabular-nums text-label-2">
                      <RangeText lo={c.lo80} hi={c.hi80} format={num} confidence={c.confidence} method={c.method} />
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            {cells.length > SHOWN && !all ? (
              <div className="p-2">
                <Button size="sm" variant="secondary" onClick={() => setAll(true)}>{t("adaptive.showAll", { n: cells.length })}</Button>
              </div>
            ) : null}
          </Card>
        </>
      )}
    </section>
  );
}

export function shortfallText(c: ShortfallCell, days: readonly string[], t: (k: "adaptive.shortfall.row" | "adaptive.shortfall.all", v?: Record<string, string | number>) => string): string {
  return t("adaptive.shortfall.row", { day: days[c.day - 1] ?? String(c.day), period: c.period, group: c.group === "*" ? t("adaptive.shortfall.all") : c.group, demand: c.demand, supply: c.supply, short: c.shortfall });
}

function ShortfallBlock({ termId }: { termId: number }) {
  const { t, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const days = useDayNames();
  const q = useShortfall(termId);
  const d = q.data;
  const rows = useMemo(() => (d?.cells ?? []).filter((c) => c.shortfall > 0).sort((a, b) => b.shortfall - a.shortfall), [d]);
  return (
    <section aria-labelledby="fc-short" className="flex flex-col gap-3" data-testid="forecast-shortfall">
      <div>
        <h2 id="fc-short" className="type-title-3 text-label-1">{t("adaptive.shortfall.title")}</h2>
        <p className="type-footnote text-label-2">{t("adaptive.shortfall.hint")}</p>
      </div>
      {q.isLoading ? (
        <Skeleton className="h-20 w-full" />
      ) : q.isError ? (
        <p role="alert" className="type-callout text-label-2">{t("adaptive.loadError")}</p>
      ) : !d || d.confidence === "none" ? (
        <div className="rounded-xl bg-fill-3 px-4 py-5"><p className="type-callout text-label-1">{d?.needs?.[lang] || t("adaptive.forecast.empty")}</p></div>
      ) : rows.length === 0 ? (
        <p className="type-callout text-label-1" data-testid="shortfall-none">{t("adaptive.shortfall.none")}</p>
      ) : (
        <ul className="flex flex-col gap-1" data-testid="shortfall-list">
          {rows.slice(0, SHOWN).map((c) => (
            <li key={`${c.day}-${c.period}-${c.group}`} className="type-callout text-label-1">
              {shortfallText(c, days, t)}
              {c.competing.length ? <span className="block type-footnote text-label-2">{t("adaptive.shortfall.competing", { list: c.competing.slice(0, 4).join(", ") })}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
