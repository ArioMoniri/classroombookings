"use client";

import { useI18n } from "@/lib/i18n/provider";
import { dayName } from "@/lib/time";

export interface DayOccupancy {
  day: number;
  /** occupied lecture periods (P1–P12) */
  day_periods: number;
  /** occupied evening periods (P13–P18) */
  evening_periods: number;
  blocked: number;
}

/** 7-bar weekday sparkline (inline SVG, no chart lib). Evening share stacked lighter; blocked hatched. */
export function SparklineBars({ data, selectedDay, height = 28, className }: { data: DayOccupancy[]; selectedDay?: number; height?: number; className?: string }) {
  const { locale } = useI18n();
  const bw = 8;
  const gap = 3;
  const width = data.length * (bw + gap) - gap;
  const label = data.map((d) => `${dayName(d.day, locale, "short")} ${Math.round(((d.day_periods + d.evening_periods + d.blocked) / 18) * 100)}%`).join(", ");
  return (
    <svg role="img" aria-label={label} viewBox={`0 0 ${width} ${height}`} width={width} height={height} className={className}>
      <defs>
        <pattern id="spark-hatch" width="3" height="3" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="1.5" height="3" fill="var(--status-preoccupied-hatch)" />
        </pattern>
      </defs>
      {data.map((d, i) => {
        const x = i * (bw + gap);
        const unit = height / 18;
        const dayH = d.day_periods * unit;
        const eveH = d.evening_periods * unit;
        const blkH = d.blocked * unit;
        const active = d.day === selectedDay;
        const colour = active ? "var(--primary)" : "var(--fg-subtle)";
        return (
          <g key={d.day}>
            <title>{`${dayName(d.day, locale)} · ${d.day_periods + d.evening_periods}/18 · ${d.blocked} blocked`}</title>
            <rect x={x} y={0} width={bw} height={height} fill="var(--surface-2)" rx={1} />
            <rect x={x} y={height - blkH} width={bw} height={blkH} fill="url(#spark-hatch)" />
            <rect x={x} y={height - blkH - dayH} width={bw} height={dayH} fill={colour} opacity={active ? 1 : 0.6} />
            <rect x={x} y={height - blkH - dayH - eveH} width={bw} height={eveH} fill={colour} opacity={active ? 0.5 : 0.3} />
          </g>
        );
      })}
    </svg>
  );
}
