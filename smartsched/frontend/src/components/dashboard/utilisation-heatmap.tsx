"use client";
// Dashboard utilisation heatmap (building × day / period). Phones (< 640 px; dense grids on phones 2026-10-16): the
// 40 × 32 px cells become ONE column at a time — a SegmentedControl picks the day (today preselected) or the period
// (the current one) and the buildings are a ranked BarList with the value printed, each row a 44 px link to the same
// timetable view as its cell (MOBILE.md M-02). From 640 px up the heatmap (and its table toggle) is unchanged.

import Link from "next/link";
import { useState } from "react";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { DashboardSummary } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS, dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { BarList } from "@/components/ui/bar-list";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { minutesNow } from "@/components/timetable/model/dates";
import { periodAtMinute } from "@/components/timetable/model/geometry";

/** Buildings ranked by value (highest first; ties by name), the order of the phone list. */
export function rankRows<T extends { building: string }>(rows: readonly T[], value: (row: T) => number): { row: T; value: number }[] {
  return rows.map((row) => ({ row, value: value(row) })).sort((a, b) => b.value - a.value || a.row.building.localeCompare(b.row.building, "tr"));
}

/** Sequential 5-step scale from tokens §2.5; text colour flips at step 4. 0 % / no data is NOT step 1: it is
 *  drawn as `--fill-3` with a dot pattern and a label-3 numeral, so empty days stop weighing like data
 *  (review 2026-10-15 §3 Dashboard; tokens.md §2.5 "No data"). */
export function seqStep(v: number): { bg: string; fg: string; step: number } {
  const step = v <= 0 ? 1 : v <= 0.25 ? 2 : v <= 0.5 ? 3 : v <= 0.75 ? 4 : 5;
  return { bg: `var(--seq-${step})`, fg: step >= 4 ? "var(--primary-fg)" : "var(--fg)", step };
}

export function UtilisationHeatmap({ data, week }: { data: DashboardSummary; week: number }) {
  const { t, locale } = useI18n();
  const [mode, setMode] = useState<"day" | "period">("day");
  const [table, setTable] = useState(false);
  const phone = useIsPhone();
  const [pickedCol, setPickedCol] = useState<number | null>(null);
  const days = [1, 2, 3, 4, 5, 6, 7];
  const buildingRows = data.utilisation_by_building;
  // Real matrices from `GET /dashboard` (occupied room-periods / available, per building); the composed
  // client-side fallback has none, so it derives an estimate from the peak hours instead.
  const realDay = data.utilisation_building_day;
  const realPeriod = data.utilisation_building_period;
  const dayValue = (building: string, buildingUtil: number, day: number): number => {
    if (realDay.length) return realDay.find((c) => c.building === building && c.day === day)?.utilisation ?? 0;
    const dayOcc = data.peak_hours.filter((p) => p.day === day);
    if (dayOcc.length === 0) return 0;
    const avg = dayOcc.reduce((s, p) => s + p.occupancy, 0) / dayOcc.length;
    return Math.min(1, buildingUtil * (avg / Math.max(0.01, data.utilisation)));
  };
  const periodValue = (building: string, period: number): number => {
    if (realPeriod.length) return realPeriod.find((c) => c.building === building && c.period === period)?.utilisation ?? 0;
    const list = data.peak_hours.filter((p) => p.period === period && p.day <= 5);
    return list.length ? list.reduce((s, p) => s + p.occupancy, 0) / list.length : 0;
  };
  const cols = mode === "day" ? days : Array.from({ length: 18 }, (_, i) => i + 1);
  const caption = `${t("dashboard.utilisation")}, ${t("common.week")} ${week}`;
  const rows = mode === "day" || realPeriod.length ? buildingRows : [{ building: t("common.all"), utilisation: data.utilisation, rooms: data.rooms_bookable }];
  const valueAt = (row: { building: string; utilisation: number }, c: number) => (mode === "day" ? dayValue(row.building, row.utilisation, c) : periodValue(row.building, c));
  const labelAt = (building: string, c: number, pct: number) => (mode === "day" ? `${building} · ${dayName(c, locale)} · ${pct}%` : `${building} · ${PERIODS[c - 1]?.start ?? c} · ${pct}%`);
  const hrefAt = (building: string, c: number) => (mode === "day" ? `/timetable?day=${c}&building=${building}` : `/timetable?period=${c}`);

  if (phone) {
    // Sunday only when some building is used on it; today / the current period preselected
    const phoneDays = days.filter((d) => d < 7 || buildingRows.some((r) => dayValue(r.building, r.utilisation, d) > 0));
    const phoneCols = mode === "day" ? phoneDays : cols;
    const fallback = mode === "day" ? ((new Date().getDay() + 6) % 7) + 1 : (periodAtMinute(minutesNow()) ?? 1);
    const col = pickedCol !== null && phoneCols.includes(pickedCol) ? pickedCol : phoneCols.includes(fallback) ? fallback : (phoneCols[0] ?? 1);
    const ranked = rankRows(rows, (row) => valueAt(row, col));
    const colName = mode === "day" ? dayName(col, locale) : `${t("common.period")} ${col} · ${PERIODS[col - 1]?.start ?? ""}`;
    return (
      <div className="flex flex-col gap-3" data-testid="heat-phone">
        <SegmentedControl
          fill
          aria-label={t("dashboard.heatmap")}
          value={mode}
          onValueChange={(v) => {
            setMode(v);
            setPickedCol(null);
          }}
          options={[
            { value: "day", label: t("common.day") },
            { value: "period", label: t("common.period") },
          ]}
        />
        <SegmentedControl
          fill
          aria-label={mode === "day" ? t("common.day") : t("common.period")}
          value={String(col)}
          onValueChange={(v) => setPickedCol(Number(v))}
          options={phoneCols.map((c) => ({
            value: String(c),
            label: mode === "day" ? dayName(c, locale, "short") : (PERIODS[c - 1]?.start ?? String(c)),
            // day names stay short (the long ones would size the control into its select fallback on a phone)
            text: mode === "day" ? undefined : `${t("common.period")} ${c} · ${PERIODS[c - 1]?.start ?? ""}`,
          }))}
          data-testid="heat-phone-col"
        />
        <BarList
          aria-label={`${caption} · ${colName}`}
          tone="var(--seq-4)"
          max={100}
          linkAs={Link}
          items={ranked.map(({ row, value }) => {
            const pct = Math.round(value * 100);
            return { key: row.building, label: row.building, value: pct, display: `${pct}%`, href: hrefAt(row.building, col), linkLabel: labelAt(row.building, col, pct) };
          })}
        />
      </div>
    );
  }

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <SegmentedControl
          size="sm"
          aria-label={t("dashboard.heatmap")}
          value={mode}
          onValueChange={(v) => setMode(v)}
          options={[
            { value: "day", label: t("common.day") },
            { value: "period", label: t("common.period") },
          ]}
        />
        <div className="flex flex-wrap items-center gap-2 type-caption text-label-3">
          {[1, 2, 3, 4, 5].map((s) => (
            <span key={s} className="inline-flex items-center gap-1"><span className="size-2.5 rounded-[3px] edge-hairline" style={s === 1 ? undefined : { background: `var(--seq-${s})` }} aria-hidden data-empty={s === 1 || undefined} />{[0, 25, 50, 75, 100][s - 1]}</span>
          ))}
          <Button variant="ghost" size="xs" aria-pressed={table} className="text-tint-text" onClick={() => setTable((v) => !v)}>{table ? t("glass.dashboard.asHeatmap") : t("glass.dashboard.asTable")}</Button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className={cn("border-separate border-spacing-[3px] text-xs", table && "border-spacing-0 [&_td]:px-1 [&_td]:hairline-b")}>
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              <th scope="col" className="w-10 text-left font-medium text-label-3"></th>
              {cols.map((c) => (
                <th key={c} scope="col" className="min-w-[18px] text-center type-caption font-medium text-label-3 sm:min-w-[36px]">
                  {mode === "day" ? dayName(c, locale, "short") : c % 3 === 1 ? PERIODS[c - 1]?.start ?? "" : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.building}>
                <th scope="row" className="pr-2 text-left type-callout font-medium text-label-1">{row.building}</th>
                {cols.map((c) => {
                  const v = valueAt(row, c);
                  const { bg, fg } = seqStep(v);
                  const pct = Math.round(v * 100);
                  const empty = pct === 0;
                  const label = labelAt(row.building, c, pct);
                  const href = hrefAt(row.building, c);
                  return (
                    <td key={c} className="p-0">
                      <Tooltip>
                        <TooltipTrigger
                          render={
                            <Link href={href} aria-label={label} data-empty={empty || undefined} className={cn("flex h-8 items-center justify-center rounded-[6px] type-caption font-medium tabular-nums focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)", mode === "day" ? "w-10" : "w-[18px] sm:w-6", empty && !table && "bg-fill-3 bg-[radial-gradient(var(--hairline-strong)_0.75px,transparent_0.75px)] bg-[length:5px_5px] font-normal text-label-3")} style={table || empty ? undefined : { background: bg, color: fg }}>
                              {mode === "day" || table ? pct : ""}
                            </Link>
                          }
                        />
                        <TooltipContent>{label}</TooltipContent>
                      </Tooltip>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
