// CH-11 (docs/design/v3/charts.md §4 rows 17 and 19, wireframe charts-user-390.svg): the user's three numbers and
// quota sentence, and the academician's weekly load by weekday. No chart library: tiles and a BarList. Pure.
// Original work.
import type { Translate } from "@/components/charts/chart-summary";
import { intlLocale, type Locale } from "@/lib/i18n";
import type { MyLoad } from "@/lib/api/stats";

export interface DashLike {
  totals: { active: number; session: number; all: number; active_periods?: number };
  limits?: { max_active_bookings?: number | null };
}

export type TileKey = "active" | "term" | "open";

export function myTiles(dash: Pick<DashLike, "totals">, openRequests: number): { key: TileKey; value: number }[] {
  return [
    { key: "active", value: dash.totals.active },
    { key: "term", value: dash.totals.session },
    { key: "open", value: openRequests },
  ];
}

/** "3 / 5 aktif rezervasyon hakkı kullanıldı"; the limit counts periods when the server sends them (T-R2-13) */
export function quotaSentence(dash: DashLike, t: Translate): string | null {
  const limit = dash.limits?.max_active_bookings;
  if (limit == null) return null;
  return t("charts.mine.quota", { used: dash.totals.active_periods ?? dash.totals.active, limit });
}

export interface LoadRow {
  day: number;
  label: string;
  periods: number;
  display: string;
}

// 2026-10-12 is a Monday: ISO weekday d is that date + (d − 1)
const weekdayName = (day: number, tag: string) => new Intl.DateTimeFormat(tag, { weekday: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2026, 9, 11 + day, 12)));

/** Monday–Friday always; Saturday and Sunday only when they have classes. 0 periods reads "ders yok". */
export function loadRows(load: Pick<MyLoad, "days">, locale: Locale, t: Translate): LoadRow[] {
  const by = new Map<number, number>();
  for (const d of load.days) by.set(d.day, (by.get(d.day) ?? 0) + d.periods);
  const days = [1, 2, 3, 4, 5, 6, 7].filter((d) => d <= 5 || (by.get(d) ?? 0) > 0);
  const tag = intlLocale(locale);
  return days.map((d) => {
    const periods = by.get(d) ?? 0;
    return { day: d, label: weekdayName(d, tag), periods, display: periods ? t("charts.load.periods", { n: periods }) : t("charts.load.none") };
  });
}

/** that weekday of the timetable, for the linked instructor (and the published run when known) */
export function timetableDayHref(day: number, instructorId: number, runId: number | null): string {
  const p = new URLSearchParams({ lens: "day", day: String(day), subject: `instructor:${instructorId}` });
  if (runId != null) p.set("run", String(runId));
  return `/timetable?${p.toString()}`;
}
