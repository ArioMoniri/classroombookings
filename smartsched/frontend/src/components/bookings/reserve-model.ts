/**
 * Reservation panel model (pure, unit-tested): spans of consecutive free periods, the "Free slots" lens,
 * a room's day and next free slot, client-side "other available rooms" (until T1 `POST /rooms/find`
 * answers) and department colours. Everything reads the backend grid (`GET /bookings/grid`), which already
 * applies permissions, room ACLs, limits, holidays, blocks, non-bookable periods and the booking window:
 * a slot is reservable exactly when `isSelectable(slot)`.
 */
import type { Grid, GridPeriod, GridRoom, GridSlot, RoomInfo } from "@/lib/api/crbs";
import { isSelectable, slotKey } from "./grid-model";

/** period id → position in the grid's period order */
export function periodOrder(grid: Grid): Map<number, number> {
  return new Map(grid.periods.map((p, i) => [p.id, i]));
}

export function slotIndex(grid: Grid): Map<string, GridSlot> {
  const out = new Map<string, GridSlot>();
  for (const s of grid.slots) out.set(slotKey(s), s);
  return out;
}

/** the slots of one room on one date, in period order */
export function roomDay(grid: Grid, roomId: number, date: string): GridSlot[] {
  const order = periodOrder(grid);
  return grid.slots.filter((s) => s.room_id === roomId && s.date === date).sort((a, b) => (order.get(a.period_id) ?? 0) - (order.get(b.period_id) ?? 0));
}

/**
 * Consecutive reservable periods between two slots of the same room and date (either order), or null when
 * they are in different rooms / dates or anything in between cannot be booked.
 */
export function spanBetween(grid: Grid, a: GridSlot, b: GridSlot): GridSlot[] | null {
  if (a.room_id !== b.room_id || a.date !== b.date) return null;
  const day = roomDay(grid, a.room_id, a.date);
  const i = day.findIndex((s) => s.period_id === a.period_id);
  const j = day.findIndex((s) => s.period_id === b.period_id);
  if (i < 0 || j < 0) return null;
  const run = day.slice(Math.min(i, j), Math.max(i, j) + 1);
  return run.every(isSelectable) ? run : null;
}

/** The longest stretch of reservable periods from `anchor` towards `target` (drag clamps to it). */
export function clampSpan(grid: Grid, anchor: GridSlot, target: GridSlot): GridSlot[] {
  if (anchor.room_id !== target.room_id || anchor.date !== target.date || !isSelectable(anchor)) return [anchor];
  const day = roomDay(grid, anchor.room_id, anchor.date);
  const i = day.findIndex((s) => s.period_id === anchor.period_id);
  const j = day.findIndex((s) => s.period_id === target.period_id);
  if (i < 0 || j < 0) return [anchor];
  const step = j >= i ? 1 : -1;
  const out = [day[i]!];
  for (let k = i + step; step > 0 ? k <= j : k >= j; k += step) {
    const s = day[k]!;
    if (!isSelectable(s)) break;
    out.push(s);
  }
  return step > 0 ? out : out.reverse();
}

/** The whole run of consecutive reservable periods that contains `slot` (the sheet's period chips). */
export function freeRun(grid: Grid, slot: GridSlot): GridSlot[] {
  const day = roomDay(grid, slot.room_id, slot.date);
  const i = day.findIndex((s) => s.period_id === slot.period_id);
  if (i < 0 || !isSelectable(day[i])) return [slot];
  let lo = i;
  let hi = i;
  while (lo > 0 && isSelectable(day[lo - 1])) lo--;
  while (hi < day.length - 1 && isSelectable(day[hi + 1])) hi++;
  return day.slice(lo, hi + 1);
}

/**
 * Toggle a period chip in a contiguous range [lo, hi] (indices into a free run): outside grows the range,
 * an end shrinks it, an inner chip truncates to it. The range never becomes empty.
 */
export function toggleRange(range: { lo: number; hi: number }, i: number): { lo: number; hi: number } {
  const { lo, hi } = range;
  if (i < lo) return { lo: i, hi };
  if (i > hi) return { lo, hi: i };
  if (lo === hi) return range;
  if (i === lo) return { lo: lo + 1, hi };
  if (i === hi) return { lo, hi: hi - 1 };
  return { lo, hi: i };
}

/** "now" for hiding periods that are over: the backend's booking date plus the local clock time */
export interface Now {
  date: string;
  /** HH:MM */
  time: string;
}

function over(slot: GridSlot, period: GridPeriod | undefined, now: Now | undefined): boolean {
  if (!now || !period) return false;
  return slot.date < now.date || (slot.date === now.date && period.time_end <= now.time);
}

export interface FreeDay {
  date: string;
  /** runs of consecutive reservable periods, each in period order */
  runs: GridSlot[][];
}

export interface FreeRoom {
  room: GridRoom;
  grid: Grid;
  days: FreeDay[];
  count: number;
}

/**
 * The "Free slots" lens: every reservable slot of the given grids (one day grid, or a week of day grids),
 * grouped by room, then date, merged into runs of consecutive periods; periods already over are left out.
 * Rooms keep the grid's configured order; `firstRooms` (e.g. the department's rooms) come first.
 */
export function freeSlotsByRoom(grids: Grid[], opts: { now?: Now; firstRooms?: ReadonlySet<number> } = {}): FreeRoom[] {
  const byRoom = new Map<number, FreeRoom>();
  const order: number[] = [];
  for (const grid of grids) {
    const periods = new Map(grid.periods.map((p) => [p.id, p]));
    const porder = periodOrder(grid);
    for (const room of grid.rooms) {
      let entry = byRoom.get(room.id);
      const dates = [...new Set(grid.slots.filter((s) => s.room_id === room.id).map((s) => s.date))].sort();
      for (const date of dates) {
        const day = grid.slots.filter((s) => s.room_id === room.id && s.date === date).sort((a, b) => (porder.get(a.period_id) ?? 0) - (porder.get(b.period_id) ?? 0));
        const runs: GridSlot[][] = [];
        let cur: GridSlot[] = [];
        for (const s of day) {
          if (isSelectable(s) && !over(s, periods.get(s.period_id), opts.now)) cur.push(s);
          else if (cur.length) {
            runs.push(cur);
            cur = [];
          }
        }
        if (cur.length) runs.push(cur);
        if (!runs.length) continue;
        if (!entry) {
          entry = { room, grid, days: [], count: 0 };
          byRoom.set(room.id, entry);
          order.push(room.id);
        }
        entry.days.push({ date, runs });
        entry.count += runs.reduce((n, r) => n + r.length, 0);
      }
    }
  }
  const first = opts.firstRooms;
  const rooms = order.map((id) => byRoom.get(id)!);
  for (const r of rooms) r.days.sort((a, b) => a.date.localeCompare(b.date));
  if (!first?.size) return rooms;
  return [...rooms.filter((r) => first.has(r.room.id)), ...rooms.filter((r) => !first.has(r.room.id))];
}

/** First reservable slot of a room in the grid at or after `now` (and after `after`, when given). */
export function nextFreeSlot(grid: Grid, roomId: number, now?: Now): GridSlot | null {
  const periods = new Map(grid.periods.map((p) => [p.id, p]));
  const porder = periodOrder(grid);
  const slots = grid.slots
    .filter((s) => s.room_id === roomId && isSelectable(s) && !over(s, periods.get(s.period_id), now))
    .sort((a, b) => a.date.localeCompare(b.date) || (porder.get(a.period_id) ?? 0) - (porder.get(b.period_id) ?? 0));
  return slots[0] ?? null;
}

/** Same time in another grid: the period with the same solver periods, else the same clock times. */
export function matchPeriod(grid: Grid, period: Pick<GridPeriod, "start_period" | "end_period" | "time_start" | "time_end">): GridPeriod | undefined {
  return (
    grid.periods.find((p) => p.start_period === period.start_period && p.end_period === period.end_period) ??
    grid.periods.find((p) => p.time_start === period.time_start && p.time_end === period.time_end)
  );
}

export interface AltQuery {
  date: string;
  /** the periods asked for (from the grid the user was looking at) */
  periods: Pick<GridPeriod, "start_period" | "end_period" | "time_start" | "time_end">[];
  excludeRoomId?: number;
  /** 0 = any size */
  minSeats: number;
  /** room tags every alternative must carry (PC, LAB, TIP …) */
  tags: string[];
}

export interface Alternative {
  room: GridRoom;
  grid: Grid;
  /** the reservable slots for the asked periods, in order */
  slots: GridSlot[];
  info?: RoomInfo;
  /** empty seats over the asked size (smaller = better fit); null when the size is unknown */
  spare: number | null;
}

/**
 * Client-side "other available rooms" from day grids of the date (one per room group): rooms where every
 * asked period is reservable, that seat at least `minSeats` and carry every asked tag. Best fit first
 * (fewest spare seats), then the grid's room order.
 */
export function alternativesFromGrids(grids: Grid[], q: AltQuery, infos: ReadonlyMap<number, RoomInfo>): Alternative[] {
  const out: Alternative[] = [];
  const seen = new Set<number>();
  let pos = 0;
  const order = new Map<number, number>();
  for (const grid of grids) {
    const idx = slotIndex(grid);
    const periods = q.periods.map((p) => matchPeriod(grid, p));
    if (!periods.length || periods.some((p) => !p)) continue;
    for (const room of grid.rooms) {
      order.set(room.id, pos++);
      if (room.id === q.excludeRoomId || seen.has(room.id)) continue;
      const slots = periods.map((p) => idx.get(slotKey({ date: q.date, period_id: p!.id, room_id: room.id })));
      if (slots.some((s) => !isSelectable(s))) continue;
      const info = infos.get(room.id);
      const seats = room.capacity ?? info?.capacity ?? null;
      if (q.minSeats > 0 && (seats === null || seats < q.minSeats)) continue;
      const tags = new Set((info?.tags ?? []).map((t) => t.toUpperCase()));
      if (q.tags.some((t) => !tags.has(t.toUpperCase()))) continue;
      seen.add(room.id);
      out.push({ room, grid, slots: slots as GridSlot[], info, spare: seats === null ? null : seats - q.minSeats });
    }
  }
  return out.sort((a, b) => (a.spare ?? Infinity) - (b.spare ?? Infinity) || (order.get(a.room.id) ?? 0) - (order.get(b.room.id) ?? 0));
}

/* ----------------------------------------------------------------------------------- departments */

const CATS = 8;

/** A stable category colour per department (`--cat-1` … `--cat-8`), the same on every day and view. */
export function departmentColor(id: number | null | undefined): string | null {
  if (id === null || id === undefined) return null;
  return `var(--cat-${(((id - 1) % CATS) + CATS) % CATS + 1})`;
}

export interface DepartmentTally {
  id: number;
  name: string;
  count: number;
}

/** Departments of the bookings in the grid with their counts: the user's department first, then by count. */
export function departmentTally(grid: Grid | undefined, mine: number | null | undefined, collator?: Intl.Collator): DepartmentTally[] {
  if (!grid) return [];
  const map = new Map<number, DepartmentTally>();
  for (const s of grid.slots) {
    const b = s.booking;
    if (s.status !== "booked" || !b?.department_id) continue;
    const e = map.get(b.department_id) ?? { id: b.department_id, name: b.department_name ?? `#${b.department_id}`, count: 0 };
    e.count++;
    map.set(b.department_id, e);
  }
  const cmp = collator ?? new Intl.Collator("tr");
  return [...map.values()].sort((a, b) => Number(b.id === mine) - Number(a.id === mine) || b.count - a.count || cmp.compare(a.name, b.name));
}

/** `"all"` or a department id, remembered per user (localStorage). */
export type DepartmentLens = "all" | number;

export const deptStorageKey = (userId: number) => `smartsched.reserve.department.${userId}`;

export function parseDepartmentLens(raw: string | null | undefined): DepartmentLens | null {
  if (raw === "all") return "all";
  const n = Number(raw);
  return raw && Number.isInteger(n) && n > 0 ? n : null;
}

/* ----------------------------------------------------------------------------------- calendar URLs */

/** `https://host/x.ics` → `webcal://host/x.ics` (Apple Calendar, Outlook desktop and most apps subscribe). */
export function webcalUrl(https: string): string {
  return https.replace(/^https?:\/\//i, "webcal://");
}

/** Google Calendar "add by URL" (it wants the webcal form in `cid`). */
export function googleSubscribeUrl(https: string): string {
  return `https://calendar.google.com/calendar/r?cid=${encodeURIComponent(webcalUrl(https))}`;
}

/** Outlook on the web "subscribe from web" (personal and Microsoft 365). */
export function outlookSubscribeUrl(https: string, name: string, work = false): string {
  const host = work ? "https://outlook.office.com" : "https://outlook.live.com";
  return `${host}/calendar/0/addfromweb?url=${encodeURIComponent(https)}&name=${encodeURIComponent(name)}`;
}
