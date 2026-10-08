/**
 * Room occupancy from the calendar index (one fetch per run, shared with /timetable): a 7 × 18 grid per
 * room and week, day shares, the weekly share used on the room cards, free runs for the free-slot finder
 * and the "busy now / free now" line. Pure functions; tested in rooms.test.ts.
 */
import { PERIODS_PER_DAY } from "@/lib/time";
import type { CalendarModel } from "@/components/timetable/model/index-model";

export type RoomCell =
  | { kind: "free" }
  | { kind: "class"; label: string; aid: number; fac: number; conflict: boolean; sp: number; ep: number }
  | { kind: "block"; label: string; sp: number; ep: number }
  | { kind: "booking"; label: string; sp: number; ep: number };

/** grid[day - 1][period - 1] */
export type RoomWeek = RoomCell[][];

export const TEACHING_DAYS = [1, 2, 3, 4, 5] as const;

export function roomWeek(model: CalendarModel, roomId: number, week: number): RoomWeek {
  const bit = week >= 1 && week <= 31 ? 1 << (week - 1) : 0;
  const grid: RoomWeek = Array.from({ length: 7 }, () => Array.from({ length: PERIODS_PER_DAY }, () => ({ kind: "free" }) as RoomCell));
  const put = (day: number, sp: number, ep: number, cell: RoomCell) => {
    if (day < 1 || day > 7) return;
    for (let p = Math.max(1, sp); p <= Math.min(PERIODS_PER_DAY, ep); p++) {
      // classes win over bookings and blocks in the same period (they are what the planner acts on)
      const cur = grid[day - 1][p - 1];
      if (cur.kind === "class") continue;
      grid[day - 1][p - 1] = cell;
    }
  };
  for (let day = 1; day <= 7; day++) {
    const key = `${roomId}:${day}`;
    for (const b of model.blocksByRoomDay.get(key) ?? []) if (b.mask & bit) put(day, b.sp, b.ep, { kind: "block", label: b.b.label, sp: b.sp, ep: b.ep });
    for (const b of model.bookingsByRoomDay.get(key) ?? []) if (b.mask & bit) put(day, b.sp, b.ep, { kind: "booking", label: b.bk.title, sp: b.sp, ep: b.ep });
    for (const e of model.byRoomDay.get(key) ?? []) if (e.mask & bit) put(day, e.sp, e.ep, { kind: "class", label: e.a.label, aid: e.a.id, fac: e.a.slot, conflict: e.conflict, sp: e.sp, ep: e.ep });
  }
  return grid;
}

/** Share of the day's 18 periods held by classes, bookings or pre-occupied blocks (same as the heat lenses). */
export function dayShare(grid: RoomWeek, day: number): number {
  const row = grid[day - 1] ?? [];
  return row.filter((c) => c.kind !== "free").length / PERIODS_PER_DAY;
}

/** Mean share over the teaching days (Mon–Fri): the percentage on a room card. */
export function weekShare(grid: RoomWeek, days: readonly number[] = TEACHING_DAYS): number {
  if (!days.length) return 0;
  return days.reduce((s, d) => s + dayShare(grid, d), 0) / days.length;
}

export interface FreeRun {
  day: number;
  sp: number;
  ep: number;
  length: number;
}

/** Free runs of at least `minLen` periods, by day then start; `maxPeriod` cuts the evening off when wanted. */
export function freeRuns(grid: RoomWeek, minLen: number, days: readonly number[] = [1, 2, 3, 4, 5, 6], maxPeriod = PERIODS_PER_DAY): FreeRun[] {
  const out: FreeRun[] = [];
  for (const day of days) {
    const row = grid[day - 1] ?? [];
    let start: number | null = null;
    for (let p = 1; p <= maxPeriod + 1; p++) {
      const free = p <= maxPeriod && row[p - 1]?.kind === "free";
      if (free && start === null) start = p;
      if (!free && start !== null) {
        const len = p - start;
        if (len >= minLen) out.push({ day, sp: start, ep: p - 1, length: len });
        start = null;
      }
    }
  }
  return out;
}

/** What holds the room at (day, period) in this week, or null when it is free. */
export function heldAt(grid: RoomWeek, day: number, period: number | null): Exclude<RoomCell, { kind: "free" }> | null {
  if (period === null || day < 1 || day > 7) return null;
  const c = grid[day - 1]?.[period - 1];
  return c && c.kind !== "free" ? c : null;
}

/** Distinct classes of the week, sorted by day and start (the list under the occupancy grid). */
export function weekClasses(model: CalendarModel, roomId: number, week: number) {
  const bit = week >= 1 && week <= 31 ? 1 << (week - 1) : 0;
  const out = [];
  for (let day = 1; day <= 7; day++) {
    for (const e of model.byRoomDay.get(`${roomId}:${day}`) ?? []) if (e.mask & bit) out.push(e);
  }
  return out.sort((a, b) => a.day - b.day || a.sp - b.sp || a.a.label.localeCompare(b.a.label, "tr"));
}
