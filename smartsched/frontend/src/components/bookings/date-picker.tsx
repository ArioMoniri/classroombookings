"use client";
/**
 * Date picker for the booking grid (CRBS `Bookings::filter('date')`): one month at a time inside the
 * session, each day with its timetable-week colour (a bar under the number, plus the week name in the
 * label), holidays struck through with their name, closed dates dimmed. Keyboard: arrows move by day/week,
 * PageUp/PageDown by month, Enter picks.
 */
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { DateInfo, TimetableWeek } from "@/lib/api/crbs";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/provider";
import { monthsBetween } from "@/components/admin/date-painter";
import { EntityIcon } from "@/components/admin/icons";
import { addDays, formatPattern, type DateFormatter } from "./date-format";

interface Props {
  value: string;
  onChange: (day: string) => void;
  dates: readonly DateInfo[];
  weeks: readonly TimetableWeek[];
  termStart: string;
  termEnd: string;
  today?: string;
  fmt: DateFormatter;
}

export function DatePicker({ value, onChange, dates, weeks, termStart, termEnd, today, fmt }: Props) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(value.slice(0, 7));
  const [cursor, setCursor] = useState(value);
  const info = useMemo(() => new Map(dates.map((d) => [d.date, d])), [dates]);
  const weekById = useMemo(() => new Map(weeks.map((w) => [w.id, w])), [weeks]);
  const months = useMemo(() => monthsBetween(termStart, termEnd), [termStart, termEnd]);
  const idx = Math.max(0, months.findIndex((m) => m.key === month));
  const grid = months[idx];
  const weekdays = useMemo(() => Array.from({ length: 7 }, (_, i) => formatPattern(addDays("2026-02-16", i), "EEE", locale)), [locale]);

  const pick = (day: string) => {
    if (day < termStart || day > termEnd) return;
    onChange(day);
    setOpen(false);
  };
  const move = (day: string) => {
    if (day < termStart || day > termEnd) return;
    setCursor(day);
    setMonth(day.slice(0, 7));
    requestAnimationFrame(() => document.querySelector<HTMLButtonElement>(`[data-day="${day}"]`)?.focus());
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, PageUp: -28, PageDown: 28 };
    const n = step[e.key];
    if (n === undefined) return;
    e.preventDefault();
    move(addDays(cursor, n));
  };

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) {
          setMonth(value.slice(0, 7));
          setCursor(value);
        }
      }}
    >
      <PopoverTrigger render={<Button variant="outline" className="min-w-0 justify-start" data-testid="date-picker-trigger" />}>
        <CalendarDays aria-hidden />
        <span className="truncate">{fmt.long(value)}</span>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[19.5rem] p-3">
        <div className="mb-2 flex items-center justify-between">
          <Button variant="ghost" size="icon-sm" aria-label={t("crbs.picker.prevMonth")} disabled={idx <= 0} onClick={() => setMonth(months[idx - 1]?.key ?? month)}>
            <ChevronLeft />
          </Button>
          <p className="type-headline text-label-1" aria-live="polite">
            {grid ? formatPattern(`${grid.key}-01`, "MMMM yyyy", locale) : ""}
          </p>
          <Button variant="ghost" size="icon-sm" aria-label={t("crbs.picker.nextMonth")} disabled={idx >= months.length - 1} onClick={() => setMonth(months[idx + 1]?.key ?? month)}>
            <ChevronRight />
          </Button>
        </div>
        <div role="grid" aria-label={t("crbs.picker.label")} onKeyDown={onKey}>
          <div role="row" className="grid grid-cols-7 gap-0.5 pb-1">
            {weekdays.map((w) => (
              <span role="columnheader" key={w} className="text-center type-caption text-label-3">
                {w}
              </span>
            ))}
          </div>
          {grid?.weeks.map((wk) => (
            <div role="row" key={wk.monday} className="grid grid-cols-7 gap-0.5">
              {wk.days.map((day, i) => {
                if (!day) return <span key={i} role="gridcell" />;
                const d = info.get(day);
                const inTerm = day >= termStart && day <= termEnd;
                const week = d?.timetable_week_id != null ? weekById.get(d.timetable_week_id) : undefined;
                const selected = day === value;
                const desc = [fmt.long(day), week ? t("crbs.picker.week", { name: week.name }) : null, d?.holiday ? t("crbs.picker.holiday", { name: d.holiday }) : null, d && !d.open && !d.holiday ? t("crbs.picker.closed") : null]
                  .filter(Boolean)
                  .join(", ");
                return (
                  <span role="gridcell" key={day} aria-selected={selected}>
                    <button
                      type="button"
                      data-day={day}
                      tabIndex={day === cursor ? 0 : -1}
                      disabled={!inTerm}
                      aria-label={desc}
                      title={d?.holiday ?? week?.name ?? undefined}
                      onClick={() => pick(day)}
                      onFocus={() => setCursor(day)}
                      className={cn(
                        "relative flex h-9 w-full flex-col items-center justify-center rounded-md type-callout tabular-nums outline-none focus-visible:outline-2 focus-visible:outline-(--focus) disabled:opacity-30",
                        selected ? "bg-tint text-tint-foreground" : "text-label-1 hover:bg-fill-2",
                        !selected && d && !d.open && "text-label-3",
                        d?.holiday && "line-through decoration-1",
                        day === today && !selected && "shadow-[inset_0_0_0_1.5px_var(--accent)]",
                      )}
                    >
                      {Number(day.slice(8))}
                      {week ? <span aria-hidden className="absolute inset-x-2 bottom-1 h-[3px] rounded-full" style={{ background: week.bgcol }} /> : null}
                    </button>
                  </span>
                );
              })}
            </div>
          ))}
        </div>
        {weeks.length || dates.some((d) => d.holiday) ? (
          <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 border-t border-hairline pt-2 type-footnote text-label-2">
            {weeks.map((w) => (
              <li key={w.id} className="flex items-center gap-1.5">
                <span aria-hidden className="h-[3px] w-4 rounded-full" style={{ background: w.bgcol }} />
                <EntityIcon name={w.icon} />
                {w.name}
              </li>
            ))}
            {dates.some((d) => d.holiday) ? <li className="line-through">{t("crbs.picker.holidayLegend")}</li> : null}
          </ul>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
