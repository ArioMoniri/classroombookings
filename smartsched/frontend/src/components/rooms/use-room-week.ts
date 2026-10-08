"use client";
/** Today's place in the run (week, day, period) and the week the rooms views open on. */
import { useEffect, useState } from "react";
import { minutesNow, weekDayOf } from "@/components/timetable/model/dates";
import { periodAtMinute } from "@/components/timetable/model/geometry";
import type { CalendarModel } from "@/components/timetable/model/index-model";
import { weekInRun } from "@/components/timetable/model/view-state";

export interface RunNow {
  week: number;
  day: number;
  period: number | null;
}

/** null until mounted (no server/client mismatch) and when today is outside the run's dated weeks. */
export function useRunNow(model: CalendarModel | null): RunNow | null {
  const [minutes, setMinutes] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setMinutes(minutesNow());
    tick();
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, []);
  if (!model || minutes === null) return null;
  const today = model.index.today ?? null;
  const wd = today ? weekDayOf(model.index.weeks, today) : null;
  if (!wd) return null;
  return { week: wd.week, day: wd.day, period: periodAtMinute(minutes) };
}

export function defaultWeek(model: CalendarModel | null, now: RunNow | null, requested: number | null): number | null {
  if (!model) return requested;
  return weekInRun(model.index.run.weeks ?? [], model.weeks, requested ?? now?.week ?? null);
}
