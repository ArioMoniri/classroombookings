/**
 * The client-side calendar index (calendar.md §13): built once per run from `GET /runs/{id}/calendar-index`
 * and shared by every lens, the drag checks, the heat and compare. A lens or week switch is a lookup, never a
 * refetch. Week sets are 32-bit masks so overlap tests are a single AND.
 */
import type { CalendarIndex, IndexAssignment, IndexBlock, IndexBooking, IndexRoom, IndexUnplaced } from "@/lib/api/calendar";

export type WeekMask = number;

export function maskOf(weeks: readonly number[]): WeekMask {
  let m = 0;
  for (const w of weeks) if (w >= 1 && w <= 31) m |= 1 << (w - 1);
  return m >>> 0;
}

export function weeksOfMask(mask: WeekMask): number[] {
  const out: number[] = [];
  for (let w = 1; w <= 31; w++) if (mask & (1 << (w - 1))) out.push(w);
  return out;
}

export function hasWeek(mask: WeekMask, week: number): boolean {
  return week >= 1 && week <= 31 && (mask & (1 << (week - 1))) !== 0;
}

/** One chip: an assignment in one of its rooms (multi-room exams render one chip per room). */
export interface CalEvent {
  key: string;
  a: IndexAssignment;
  room: number;
  day: number;
  sp: number;
  ep: number;
  mask: WeekMask;
  /** cohort key "programme:year" when known */
  cohort: string | null;
  conflict: boolean;
  warning: boolean;
}

export interface CalBlock {
  key: string;
  b: IndexBlock;
  room: number;
  day: number;
  sp: number;
  ep: number;
  mask: WeekMask;
}

export interface CalBooking {
  key: string;
  bk: IndexBooking;
  room: number;
  day: number;
  sp: number;
  ep: number;
  mask: WeekMask;
}

export interface CalendarModel {
  index: CalendarIndex;
  exam: boolean;
  rooms: IndexRoom[];
  roomById: Map<number, IndexRoom>;
  buildings: string[];
  weeks: number[];
  allMask: WeekMask;
  events: CalEvent[];
  eventByAid: Map<number, CalEvent[]>;
  blocks: CalBlock[];
  bookings: CalBooking[];
  /** "room:day" → events / blocks / bookings over all weeks */
  byRoomDay: Map<string, CalEvent[]>;
  blocksByRoomDay: Map<string, CalBlock[]>;
  bookingsByRoomDay: Map<string, CalBooking[]>;
  /** "instructorId:day" and "cohort:day" → events (instructor / cohort clash checks) */
  byInstructorDay: Map<string, CalEvent[]>;
  byCohortDay: Map<string, CalEvent[]>;
  unplaced: IndexUnplaced[];
}

function push<K, V>(map: Map<K, V[]>, key: K, value: V) {
  const list = map.get(key);
  if (list) list.push(value);
  else map.set(key, [value]);
}

export function roomCap(model: Pick<CalendarModel, "exam">, room: IndexRoom | undefined): number {
  if (!room) return 0;
  return model.exam ? room.exam_capacity || room.capacity : room.capacity;
}

export function isConflictReason(r: string): boolean {
  return r.startsWith("room overlap") || r.startsWith("block") || r.startsWith("seats");
}

export function buildModel(index: CalendarIndex): CalendarModel {
  const exam = index.run.kind === "EXAM";
  const weeks = index.weeks.length ? index.weeks.map((w) => w.index) : Array.from({ length: 14 }, (_, i) => i + 1);
  const allMask = maskOf(weeks);
  const roomById = new Map(index.rooms.map((r) => [r.id, r]));
  const buildings = [...new Set(index.rooms.map((r) => r.building))].sort((a, b) => a.localeCompare(b, "tr"));
  const events: CalEvent[] = [];
  const eventByAid = new Map<number, CalEvent[]>();
  const byRoomDay = new Map<string, CalEvent[]>();
  const byInstructorDay = new Map<string, CalEvent[]>();
  const byCohortDay = new Map<string, CalEvent[]>();
  for (const a of index.assignments) {
    const mask = a.weeks.length ? maskOf(a.weeks) : allMask;
    const cohort = a.prog_id && a.year ? `${a.prog_id}:${a.year}` : null;
    const conflict = a.reasons.some(isConflictReason);
    const warning = !conflict && a.reasons.some((r) => r.startsWith("capacity"));
    for (const room of a.rooms.length ? a.rooms : [0]) {
      const ev: CalEvent = { key: `${a.id}:${room}`, a, room, day: a.day, sp: a.sp, ep: a.ep, mask, cohort, conflict, warning };
      events.push(ev);
      push(eventByAid, a.id, ev);
      push(byRoomDay, `${room}:${a.day}`, ev);
    }
    const first = eventByAid.get(a.id)?.[0];
    if (!first) continue;
    for (const i of a.instr_ids) push(byInstructorDay, `${i}:${a.day}`, first);
    if (cohort) push(byCohortDay, `${cohort}:${a.day}`, first);
  }
  const blocks: CalBlock[] = index.blocks.map((b) => ({ key: `b${b.id}`, b, room: b.room, day: b.day, sp: b.sp, ep: b.ep, mask: b.weeks.length ? maskOf(b.weeks) : allMask }));
  const blocksByRoomDay = new Map<string, CalBlock[]>();
  for (const b of blocks) push(blocksByRoomDay, `${b.room}:${b.day}`, b);
  const bookings: CalBooking[] = index.bookings.map((bk) => ({ key: `k${bk.id}`, bk, room: bk.room, day: bk.day, sp: bk.sp, ep: bk.ep, mask: bk.week ? maskOf([bk.week]) : 0 }));
  const bookingsByRoomDay = new Map<string, CalBooking[]>();
  for (const b of bookings) push(bookingsByRoomDay, `${b.room}:${b.day}`, b);
  return {
    index,
    exam,
    rooms: index.rooms,
    roomById,
    buildings,
    weeks,
    allMask,
    events,
    eventByAid,
    blocks,
    bookings,
    byRoomDay,
    blocksByRoomDay,
    bookingsByRoomDay,
    byInstructorDay,
    byCohortDay,
    unplaced: index.unplaced,
  };
}

/** Events of one week (and optional day) after filters: the per-lens visible set. */
export function eventsOf(model: CalendarModel, week: number, day?: number, keep?: (e: CalEvent) => boolean): CalEvent[] {
  const bit = week >= 1 && week <= 31 ? 1 << (week - 1) : 0;
  return model.events.filter((e) => (e.mask & bit) !== 0 && (day === undefined || e.day === day) && (!keep || keep(e)));
}

export function blocksOf(model: CalendarModel, week: number, day?: number): CalBlock[] {
  const bit = week >= 1 && week <= 31 ? 1 << (week - 1) : 0;
  return model.blocks.filter((b) => (b.mask & bit) !== 0 && (day === undefined || b.day === day));
}

export function bookingsOf(model: CalendarModel, week: number, day?: number): CalBooking[] {
  const bit = week >= 1 && week <= 31 ? 1 << (week - 1) : 0;
  return model.bookings.filter((b) => (b.mask & bit) !== 0 && (day === undefined || b.day === day));
}

/** Term-long blocks (same room/day/span in ≥ 10 weeks) summarised once for the all-day band (§7.5). */
export function termLongBlocks(model: CalendarModel, day: number): { room: number; label: string; sp: number; ep: number; weeks: number }[] {
  const out = new Map<string, { room: number; label: string; sp: number; ep: number; weeks: number }>();
  for (const b of model.blocks) {
    if (b.day !== day) continue;
    const n = weeksOfMask(b.mask).length;
    if (n < 10) continue;
    const k = `${b.room}:${b.b.label}:${b.sp}:${b.ep}`;
    if (!out.has(k)) out.set(k, { room: b.room, label: b.b.label, sp: b.sp, ep: b.ep, weeks: n });
  }
  return [...out.values()];
}
