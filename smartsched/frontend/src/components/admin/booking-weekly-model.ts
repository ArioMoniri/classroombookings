// CH-07 (docs/design/v3/charts.md §4 rows 5–6): rows and plain sentences for "Haftalık rezervasyonlar" and
// "Haftalık talep sonuçları" on /admin, read from `GET /bookings/stats/weekly` (lib/api/stats.ts). Pure; the
// numbers are the server's, never estimated here. Original work.
import type { ChartFormat } from "@/components/charts/chart-format";
import type { Translate } from "@/components/charts/chart-summary";
import type { WeeklyBookingStats } from "@/lib/api/stats";

export interface WeekRow {
  /** "7. hf": the bucket (x axis, table, CSV) */
  week: string;
  n: number;
  start: string;
  end: string;
  exam: boolean;
  /** "Sınav haftası" or "" (a text column, so the exam label is in the table and CSV too) */
  examText: string;
  partial: boolean;
  bookings: number;
  approved: number;
  rejected: number;
  pending: number;
  [key: string]: unknown;
}

export function weeklyRows(stats: WeeklyBookingStats, t: Translate): WeekRow[] {
  return [...stats.weeks]
    .sort((a, b) => a.week - b.week)
    .map((w) => ({
      week: t("charts.bookings.weekShort", { n: w.week }),
      n: w.week,
      start: w.start,
      end: w.end,
      exam: w.exam,
      examText: w.exam ? t("charts.bookings.exam") : "",
      partial: w.partial,
      bookings: w.bookings,
      approved: w.requests.approved,
      rejected: w.requests.rejected,
      pending: w.requests.pending,
    }));
}

/** the last row is the unfinished current week */
export const lastPartial = (rows: readonly WeekRow[]) => rows.at(-1)?.partial === true;

export function bookingsSummary(rows: readonly WeekRow[], t: Translate, f: ChartFormat): string {
  const total = rows.reduce((s, r) => s + r.bookings, 0);
  if (!total) return "";
  const peak = rows.reduce((best, r) => (r.bookings > best.bookings ? r : best), rows[0]!);
  return [
    t("charts.bookings.summary", { total: f.num(total), peak: t("charts.bookings.weekLong", { n: peak.n }), peakValue: f.num(peak.bookings) }),
    lastPartial(rows) ? t("charts.summary.partial.week") : "",
  ]
    .filter(Boolean)
    .join(" ");
}

export function requestTotals(rows: readonly WeekRow[]) {
  const approved = rows.reduce((s, r) => s + r.approved, 0);
  const rejected = rows.reduce((s, r) => s + r.rejected, 0);
  const pending = rows.reduce((s, r) => s + r.pending, 0);
  return { approved, rejected, pending, total: approved + rejected + pending };
}

export function requestsSummary(rows: readonly WeekRow[], t: Translate, f: ChartFormat): string {
  const s = requestTotals(rows);
  if (!s.total) return "";
  return t("charts.requests.summary", { total: f.num(s.total), approved: f.num(s.approved), rejected: f.num(s.rejected), pending: f.num(s.pending) });
}
