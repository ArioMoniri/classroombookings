"use client";
// SmartSched charts (CH-02, docs/design/v3/charts.md §5.1): every number and date a chart shows, through `Intl`
// in the user's language (tr-TR first) and the campus time zone. Original work.
import { useMemo } from "react";
import { intlLocale, type Locale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";

export const CHART_TIME_ZONE = "Europe/Istanbul";

export interface ChartFormat {
  locale: Locale;
  /** 82.300 · 82,3 (≤ 1 decimal) */
  num: (value: number) => string;
  /** a ratio 0…1 → %86 */
  pct: (ratio: number) => string;
  /** axis ticks: 82 B · 1,2 Mn */
  compact: (value: number) => string;
  /** sentences: 82 bin · 1,2 milyon */
  compactLong: (value: number) => string;
  /** 14 Eki */
  day: (value: string | Date) => string;
  /** 14 Ekim Çarşamba (tooltip heading, table) */
  dayLong: (value: string | Date) => string;
  /** Çar */
  weekday: (value: string | Date) => string;
  /** 19:42, 24-hour in both languages */
  time: (value: Date) => string;
  /** the calendar day in Istanbul as 2026-10-14 */
  isoDay: (value: Date) => string;
  /** 2 saat önce */
  ago: (value: Date, now?: Date) => string;
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** An ISO day is a calendar day, not an instant: read it at noon UTC, which is the same day in Istanbul. */
export function toDate(value: string | Date): Date {
  if (value instanceof Date) return value;
  return new Date(ISO_DAY.test(value) ? `${value}T12:00:00Z` : value);
}

const RELATIVE: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400_000],
  ["hour", 3_600_000],
  ["minute", 60_000],
];

export function makeChartFormat(locale: Locale): ChartFormat {
  const tag = intlLocale(locale);
  const tz = CHART_TIME_ZONE;
  const num = new Intl.NumberFormat(tag, { maximumFractionDigits: 1 });
  const pct = new Intl.NumberFormat(tag, { style: "percent", maximumFractionDigits: 0 });
  const compact = new Intl.NumberFormat(tag, { notation: "compact", maximumFractionDigits: 1 });
  const compactLong = new Intl.NumberFormat(tag, { notation: "compact", compactDisplay: "long", maximumFractionDigits: 1 });
  const day = new Intl.DateTimeFormat(tag, { day: "numeric", month: "short", timeZone: tz });
  const dayLong = new Intl.DateTimeFormat(tag, { day: "numeric", month: "long", weekday: "long", timeZone: tz });
  const weekday = new Intl.DateTimeFormat(tag, { weekday: "short", timeZone: tz });
  const time = new Intl.DateTimeFormat(tag, { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: tz });
  const iso = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: tz });
  const rel = new Intl.RelativeTimeFormat(tag, { numeric: "auto" });
  return {
    locale,
    num: (v) => num.format(v),
    pct: (r) => pct.format(r),
    compact: (v) => compact.format(v),
    compactLong: (v) => compactLong.format(v),
    day: (v) => day.format(toDate(v)),
    dayLong: (v) => dayLong.format(toDate(v)),
    weekday: (v) => weekday.format(toDate(v)),
    time: (v) => time.format(v),
    isoDay: (v) => iso.format(v),
    ago: (v, now = new Date()) => {
      const diff = v.getTime() - now.getTime();
      for (const [unit, ms] of RELATIVE) {
        if (Math.abs(diff) >= ms || unit === "minute") return rel.format(Math.round(diff / ms), unit);
      }
      return rel.format(0, "minute");
    },
  };
}

/** `makeChartFormat` for the active language (`useI18n().locale`). */
export function useChartFormat(): ChartFormat {
  const { locale } = useI18n();
  return useMemo(() => makeChartFormat(locale), [locale]);
}
