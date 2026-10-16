"use client";
/**
 * /rooms/[id] on phones (< 640 px; dense grids on phones, 2026-10-16): the 7 × 18 week grid becomes ONE day at a
 * time. A SegmentedControl picks the day (Pzt … Cmt, Paz when the room is used on Sunday; today preselected by the
 * caller) and the periods are full-width rows of at least 44 px (MOBILE.md M-02): a held span (class, pre-occupied
 * block, booking) is one row with its period range, each free period is its own row and picks the slot for
 * booking exactly like a free cell of the week grid. The classes of the week become a list of 44 px links instead
 * of a 560 px table, so nothing scrolls sideways (M-01). Tablet and desktop keep the week grid (room-detail.tsx).
 */
import Link from "next/link";
import { useId } from "react";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { spanText } from "@/components/timetable/model/check";
import { chipVars } from "@/components/timetable/event-chip";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS_PER_DAY, dayName } from "@/lib/time";
import { cn } from "@/lib/utils";
import { BareButton } from "@/components/shell/bare-button";
import { rowSegments, type FreeRun, type RoomCell, type weekClasses } from "./room-occupancy";

/** The day a phone opens on: today when the room's week shows it, else the first shown day. */
export function initialDay(days: readonly number[], today: number | null | undefined): number {
  return today && days.includes(today) ? today : (days[0] ?? 1);
}

function heldClass(c: Exclude<RoomCell, { kind: "free" }>): string {
  if (c.kind === "class") return "cal-chip !relative";
  if (c.kind === "block") return "cal-block !relative";
  return "cal-chip cal-booking !relative";
}

export function RoomDayView({
  grid,
  days,
  day,
  onDay,
  picked,
  onPick,
  now,
}: {
  grid: RoomCell[][];
  days: readonly number[];
  day: number;
  onDay: (day: number) => void;
  picked: FreeRun | null;
  onPick?: (f: FreeRun) => void;
  now: { day: number; period: number | null } | null;
}) {
  const { t, locale } = useI18n();
  const panel = useId();
  const row = grid[day - 1] ?? [];
  return (
    <div className="flex flex-col gap-3" data-testid="room-day-view">
      {/* tight segments (6 px side padding): six or seven day names stay a segmented control down to a 360 px phone
          instead of folding into the select fallback; every segment stays >= 44 px wide */}
      <SegmentedControl
        fill
        className="[&_[role=tab]]:px-1.5"
        aria-label={t("common.day")}
        value={String(day)}
        onValueChange={(v) => onDay(Number(v))}
        options={days.map((d) => ({ value: String(d), label: dayName(d, locale, "short"), controls: panel, testId: `room-day-${d}` }))}
        data-testid="room-day-picker"
      />
      <ol id={panel} role="tabpanel" aria-label={dayName(day, locale)} className="flex flex-col gap-1">
        {rowSegments(row).map((seg) => {
          if (seg.kind === "free") {
            const p = seg.p;
            const isPicked = !!picked && picked.day === day && p >= picked.sp && p <= picked.ep;
            const isNow = !!now && now.day === day && now.period === p;
            const body = (
              <>
                <span className="w-12 shrink-0 type-footnote font-semibold text-label-2 tabular-nums">P{p}</span>
                <span className="flex-1 type-callout tabular-nums">{spanText(p, p)}</span>
                <span className="type-footnote text-label-2">{t("roomsV2.legendFree")}</span>
              </>
            );
            const look = cn("flex min-h-11 w-full items-center gap-3 rounded-lg px-3 text-left", isPicked ? "bg-tint-soft text-tint-text edge-tint" : "bg-fill-3", isNow && "shadow-[inset_3px_0_0_var(--now)]");
            return (
              <li key={p} data-period={p}>
                {onPick ? (
                  <BareButton
                    aria-label={t("roomsV2.cellFree", { day: dayName(day, locale), p })}
                    aria-pressed={isPicked}
                    onClick={() => {
                      // two periods from here (one when the next period is taken), as in the week grid
                      const ep = p < PERIODS_PER_DAY && row[p]?.kind === "free" ? p + 1 : p;
                      onPick({ day, sp: p, ep, length: ep - p + 1 });
                    }}
                    className={cn(look, !isPicked && "hover:bg-fill-2")}
                  >
                    {body}
                  </BareButton>
                ) : (
                  <div className={look} aria-label={t("roomsV2.cellFree", { day: dayName(day, locale), p })} role="group">
                    {body}
                  </div>
                )}
              </li>
            );
          }
          const { cell: c, sp, ep } = seg;
          const range = `${sp}${ep > sp ? `–${ep}` : ""}`;
          const isNow = !!now && now.day === day && now.period !== null && now.period >= sp && now.period <= ep;
          return (
            <li
              key={sp}
              data-period={sp}
              aria-label={t("roomsV2.cellHeld", { day: dayName(day, locale), p: range, label: c.label })}
              data-conflict={c.kind === "class" && c.conflict ? "true" : undefined}
              className={cn("flex min-h-11 !flex-row items-center gap-3 rounded-lg py-1.5 pr-3 pl-3", heldClass(c), c.kind === "class" && "pl-4", isNow && "outline-2 outline-offset-1 outline-(--now)")}
              style={c.kind === "class" ? chipVars(c.fac) : undefined}
            >
              <span className="w-12 shrink-0 type-footnote font-semibold tabular-nums">P{range}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate type-callout font-semibold">{c.label}</span>
                <span className="block type-footnote tabular-nums opacity-80">{spanText(sp, ep)}</span>
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export type RoomClassRow = ReturnType<typeof weekClasses>[number];

/** The week's classes as 44 px link rows (phones); same links and facts as the desktop table. */
export function RoomClassesList({ classes, capacity, hrefOf }: { classes: readonly RoomClassRow[]; capacity: number; hrefOf: (e: RoomClassRow) => string }) {
  const { t, locale } = useI18n();
  return (
    <ul className="flex flex-col" data-testid="room-classes-list">
      {classes.map((e) => (
        <li key={e.key} className="not-last:hairline-b">
          <Link href={hrefOf(e)} className="flex min-h-11 items-center gap-3 px-4 py-2 hover:bg-fill-3 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)">
            <span aria-hidden className="h-8 w-[3px] shrink-0 rounded-full" style={{ background: `var(--fac-${e.a.slot}-bar)` }} />
            <span className="min-w-0 flex-1">
              <span className="block truncate type-callout font-semibold text-label-1">{e.a.label}</span>
              <span className="block truncate type-footnote text-label-2">{e.a.prog ?? "—"}</span>
            </span>
            <span className="shrink-0 text-right">
              <span className="block type-footnote text-label-1 tabular-nums">{dayName(e.day, locale, "short")} {spanText(e.sp, e.ep)}</span>
              <span className={cn("block type-footnote tabular-nums", e.a.size > capacity ? "text-status-warning-fg" : "text-label-2")}>{t("roomsV2.people", { size: e.a.size, cap: capacity })}</span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
