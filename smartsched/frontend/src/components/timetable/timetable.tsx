"use client";
/**
 * Embedded calendar for one run (run report "Çizelge" tab). Same lenses and interactions as /timetable,
 * without URL sync and with the sidebar closed by default.
 */
import { CalendarView } from "./calendar-view";

export interface TimetableProps {
  runId: number;
  week?: number;
  className?: string;
}

export function Timetable({ runId, week, className }: TimetableProps) {
  return <CalendarView embedded runId={runId} initialWeek={week} className={className} />;
}
