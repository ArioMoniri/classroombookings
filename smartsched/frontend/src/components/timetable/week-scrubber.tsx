"use client";
/**
 * Week scrubber (calendar.md §5.4, §9.6): a floating chrome capsule with one tick per week whose vertical
 * fill is that week's occupancy (holiday weeks hatched, exam weeks hollow), a raised thumb that travels with
 * springs.snappy, press-and-drag scrubbing (data is already in the index, so the canvas swaps live), arrow
 * keys / Home / End as a slider, and "Bugün".
 */
import { ChevronLeft, ChevronRight } from "lucide-react";
import { LayoutGroup, motion } from "motion/react";
import { useId, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Button } from "@/components/ui/button";
import { springs, useReduce } from "@/lib/motion";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";
import type { IndexWeek } from "@/lib/api/calendar";
import { addDays } from "./model/dates";

export interface WeekScrubberProps {
  weeks: IndexWeek[];
  week: number;
  occupancy: (week: number) => number;
  onWeek: (week: number) => void;
  onToday: () => void;
  todayWeek: number | null;
  runWeeks: readonly number[];
}

export function WeekScrubber({ weeks, week, occupancy, onWeek, onToday, todayWeek, runWeeks }: WeekScrubberProps) {
  const { t, locale } = useI18n();
  const reduce = useReduce();
  const group = useId();
  const track = useRef<HTMLDivElement>(null);
  const [scrub, setScrub] = useState<number | null>(null);
  const idx = weeks.findIndex((w) => w.index === week);
  const first = weeks[0]?.index ?? 1;
  const last = weeks[weeks.length - 1]?.index ?? 14;
  const range = (w: IndexWeek | undefined) => (w?.start_date ? `${formatDate(w.start_date, locale)}–${formatDate(addDays(w.start_date, 6), locale)}` : "");

  const weekAt = (clientX: number) => {
    const el = track.current;
    if (!el || !weeks.length) return week;
    const r = el.getBoundingClientRect();
    const i = Math.min(weeks.length - 1, Math.max(0, Math.floor(((clientX - r.left) / r.width) * weeks.length)));
    return weeks[i].index;
  };
  const onDown = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    const w = weekAt(e.clientX);
    setScrub(w);
    if (w !== week) onWeek(w);
  };
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    if (scrub === null) return;
    const w = weekAt(e.clientX);
    if (w !== scrub) {
      setScrub(w);
      onWeek(w);
    }
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowUp" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowDown" ? -1 : 0;
    if (step) {
      e.preventDefault();
      onWeek(Math.min(last, Math.max(first, week + step)));
    } else if (e.key === "Home") {
      e.preventDefault();
      onWeek(first);
    } else if (e.key === "End") {
      e.preventDefault();
      onWeek(last);
    }
  };

  return (
    <div className="glass-chrome pointer-events-auto flex h-11 max-w-[calc(100%-1.5rem)] items-center gap-1 rounded-full px-1.5" data-glass="chrome" data-testid="week-scrubber">
      <Button variant="ghost" size="icon-sm" aria-label={t("calendar.nav.prev")} onClick={() => onWeek(Math.max(first, week - 1))} disabled={week <= first}><ChevronLeft /></Button>
      <LayoutGroup id={group}>
        <div
          ref={track}
          role="slider"
          tabIndex={0}
          aria-label={t("calendar.scrubber")}
          aria-valuemin={first}
          aria-valuemax={last}
          aria-valuenow={week}
          aria-valuetext={t("calendar.scrubberValue", { n: week, range: range(weeks[idx]) })}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={() => setScrub(null)}
          onPointerCancel={() => setScrub(null)}
          onKeyDown={onKey}
          className="relative flex h-9 touch-none items-end gap-[3px] overflow-x-auto px-1 pb-1.5 outline-none focus-visible:outline-2 focus-visible:outline-(--focus) [scrollbar-width:none]"
        >
          {weeks.map((w) => {
            const occ = occupancy(w.index);
            const active = w.index === week;
            const exam = w.kind === "EXAM" || w.kind === "MAKEUP";
            const holiday = w.kind === "HOLIDAY";
            const outside = runWeeks.length > 0 && !runWeeks.includes(w.index);
            return (
              <div key={w.index} className="relative flex h-6 w-5 shrink-0 items-end justify-center" title={`${t("calendar.nav.weekShort", { n: w.index })} · ${range(w)} · ${t("calendar.heat.cellShort", { p: Math.round(occ * 100) })}`}>
                {active ? (
                  <motion.span
                    layoutId="scrubber-thumb"
                    transition={reduce ? { duration: 0 } : springs.snappy}
                    aria-hidden
                    className="pointer-events-none absolute -inset-x-0.5 -top-0.5 -bottom-0.5 rounded-[7px] bg-(--mat-thick) shadow-[inset_0_1px_0_0_var(--specular),0_0_0_1px_var(--hairline-strong),0_1px_3px_rgba(0,0,0,0.12)]"
                    style={{ borderRadius: 7 }}
                  />
                ) : null}
                <span
                  aria-hidden
                  className={cn("relative h-5 w-3 overflow-hidden rounded-[3px]", exam ? "shadow-[inset_0_0_0_1px_var(--label-3)]" : "bg-fill-2", outside && "opacity-40")}
                  style={holiday ? { background: "repeating-linear-gradient(45deg, transparent 0 3px, var(--cal-line-strong) 3px 4px)" } : undefined}
                >
                  {!holiday ? <span className="absolute inset-x-0 bottom-0 h-full origin-bottom bg-[var(--seq-3)]" style={{ transform: `scaleY(${Math.max(0.06, Math.min(1, occ))})`, opacity: exam ? 0.5 : 0.85 }} /> : null}
                </span>
                {active ? <span className="absolute -top-4 text-[10px] leading-3 font-semibold text-label-1 tabular-nums">{t("calendar.nav.weekShort", { n: w.index })}</span> : null}
                {todayWeek === w.index && !active ? <span aria-hidden className="absolute -bottom-1 size-1 rounded-full bg-[var(--now)]" /> : null}
              </div>
            );
          })}
        </div>
      </LayoutGroup>
      <Button variant="ghost" size="icon-sm" aria-label={t("calendar.nav.next")} onClick={() => onWeek(Math.min(last, week + 1))} disabled={week >= last}><ChevronRight /></Button>
      <Button variant="ghost" size="sm" onClick={onToday}>{t("calendar.nav.today")}</Button>
      {scrub !== null ? (
        <span role="status" className="glass-thick absolute -top-9 left-1/2 -translate-x-1/2 rounded-full px-3 py-1 text-[12px] font-medium whitespace-nowrap">
          {t("calendar.scrubberValue", { n: scrub, range: range(weeks.find((w) => w.index === scrub)) })}
        </span>
      ) : null}
    </div>
  );
}
