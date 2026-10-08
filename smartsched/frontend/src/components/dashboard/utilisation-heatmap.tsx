"use client";

import Link from "next/link";
import { useState } from "react";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { DashboardSummary } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS, dayName } from "@/lib/time";
import { cn } from "@/lib/utils";

/** Sequential 5-step scale from tokens §2.5; text colour flips at step 4. */
export function seqStep(v: number): { bg: string; fg: string; step: number } {
  const step = v <= 0 ? 1 : v <= 0.25 ? 2 : v <= 0.5 ? 3 : v <= 0.75 ? 4 : 5;
  return { bg: `var(--seq-${step})`, fg: step >= 4 ? "var(--primary-fg)" : "var(--fg)", step };
}

export function UtilisationHeatmap({ data, week }: { data: DashboardSummary; week: number }) {
  const { t, locale } = useI18n();
  const [mode, setMode] = useState<"day" | "period">("day");
  const [table, setTable] = useState(false);
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
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <SegmentedGlass
          size="sm"
          aria-label={t("dashboard.heatmap")}
          value={mode}
          onValueChange={(v) => setMode(v)}
          options={[
            { value: "day", label: t("common.day") },
            { value: "period", label: t("common.period") },
          ]}
        />
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-label-3">
          {[1, 2, 3, 4, 5].map((s) => (
            <span key={s} className="inline-flex items-center gap-1"><span className="size-2.5 rounded-[3px] shadow-[inset_0_0_0_1px_var(--hairline)]" style={{ background: `var(--seq-${s})` }} aria-hidden />{[0, 25, 50, 75, 100][s - 1]}</span>
          ))}
          <button type="button" aria-pressed={table} className="rounded-full px-2 py-0.5 font-medium text-tint-text outline-none hover:bg-fill-2 focus-visible:outline-2 focus-visible:outline-(--focus)" onClick={() => setTable((v) => !v)}>{table ? t("glass.dashboard.asHeatmap") : t("glass.dashboard.asTable")}</button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className={cn("border-separate border-spacing-[3px] text-xs", table && "border-spacing-0 [&_td]:px-1 [&_td]:hairline-b")}>
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              <th scope="col" className="w-10 text-left font-medium text-label-3"></th>
              {cols.map((c) => (
                <th key={c} scope="col" className="min-w-[18px] text-center text-[11px] font-medium text-label-3 sm:min-w-[36px]">
                  {mode === "day" ? dayName(c, locale, "short") : c % 3 === 1 ? PERIODS[c - 1]?.start ?? "" : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(mode === "day" || realPeriod.length ? buildingRows : [{ building: t("common.all"), utilisation: data.utilisation, rooms: data.rooms_bookable }]).map((row) => (
              <tr key={row.building}>
                <th scope="row" className="pr-2 text-left text-[13px] font-medium text-label-1">{row.building}</th>
                {cols.map((c) => {
                  const v = mode === "day" ? dayValue(row.building, row.utilisation, c) : periodValue(row.building, c);
                  const { bg, fg } = seqStep(v);
                  const pct = Math.round(v * 100);
                  const label = mode === "day" ? `${row.building} · ${dayName(c, locale)} · ${pct}%` : `${row.building} · ${PERIODS[c - 1]?.start ?? c} · ${pct}%`;
                  const href = mode === "day" ? `/timetable?day=${c}&building=${row.building}` : `/timetable?period=${c}`;
                  return (
                    <td key={c} className="p-0">
                      <Tooltip>
                        <TooltipTrigger
                          render={
                            <Link href={href} aria-label={label} className={cn("flex h-8 items-center justify-center rounded-[6px] text-[11px] font-medium tabular-nums outline-none focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-(--focus)", mode === "day" ? "w-10" : "w-[18px] sm:w-6")} style={table ? undefined : { background: bg, color: fg }}>
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
