// CH-10 (docs/design/v3/charts.md §4 row 15): audit events per day for the last 30 days, from
// `GET /audit/stats/daily` (lib/api/stats.ts). Days the server does not list are 0 (it lists only days with
// events); days outside its range are dropped. A column click narrows the list to that day. Pure. Original work.
import type { ChartFormat } from "@/components/charts/chart-format";
import type { Translate } from "@/components/charts/chart-summary";
import type { DailyAuditStats } from "@/lib/api/stats";
import type { AuditFilterForm } from "./audit-model";

export interface DayRow {
  day: string;
  events: number;
  [key: string]: unknown;
}

const DAY_MS = 86_400_000;
const iso = (ms: number) => new Date(ms).toISOString().slice(0, 10);

export function dailyRows(stats: Pick<DailyAuditStats, "from" | "to" | "days">): DayRow[] {
  const counts = new Map(stats.days.map((d) => [d.day, d.events]));
  const from = Date.parse(`${stats.from}T00:00:00Z`);
  const to = Date.parse(`${stats.to}T00:00:00Z`);
  const out: DayRow[] = [];
  for (let ms = from; ms <= to && out.length < 400; ms += DAY_MS) {
    const day = iso(ms);
    out.push({ day, events: counts.get(day) ?? 0 });
  }
  return out;
}

export function auditDailySummary(rows: readonly DayRow[], t: Translate, f: ChartFormat): string {
  const total = rows.reduce((s, r) => s + r.events, 0);
  if (!total) return "";
  const peak = rows.reduce((b, r) => (r.events > b.events ? r : b), rows[0]!);
  return t("charts.audit.summary", { total: f.num(total), peak: f.day(peak.day), peakValue: f.num(peak.events) });
}

/** the filters after a click on `day`: from = to = that day, every other filter kept */
export function filterToDay(filters: AuditFilterForm, day: string): AuditFilterForm {
  return { ...filters, from: day, to: day };
}
