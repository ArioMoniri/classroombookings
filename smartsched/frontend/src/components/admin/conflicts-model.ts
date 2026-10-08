/**
 * Booking conflicts after publishing (GET /bookings/conflicts): one row per active booking with every
 * timetable slot or block that now overlaps it. The backend returns one entry per (booking, holder) pair;
 * the planner wants one line per booking, in date then room order, so it can open and cancel each.
 */
import type { BookingConflict } from "@/lib/api/crbs";

export type ConflictHolder = BookingConflict["held"];

export interface ConflictRow {
  bookingId: number;
  roomId: number;
  date: string;
  holders: ConflictHolder[];
}

export interface ConflictSummary {
  bookings: number;
  rooms: number;
  days: number;
}

/** Collapse the backend pairs into one row per booking; holders sorted by period, rows by date then room label. */
export function groupConflicts(items: readonly BookingConflict[], roomLabel: (roomId: number) => string = String): ConflictRow[] {
  const byBooking = new Map<number, ConflictRow>();
  for (const c of items) {
    let row = byBooking.get(c.booking_id);
    if (!row) {
      row = { bookingId: c.booking_id, roomId: c.room_id, date: c.date, holders: [] };
      byBooking.set(c.booking_id, row);
    }
    if (!row.holders.some((h) => h.kind === c.held.kind && h.id === c.held.id)) row.holders.push(c.held);
  }
  const rows = [...byBooking.values()];
  for (const r of rows) r.holders.sort((a, b) => a.start_period - b.start_period || a.label.localeCompare(b.label));
  return rows.sort(
    (a, b) => a.date.localeCompare(b.date) || roomLabel(a.roomId).localeCompare(roomLabel(b.roomId), "tr") || a.bookingId - b.bookingId,
  );
}

export function summariseConflicts(rows: readonly ConflictRow[]): ConflictSummary {
  return {
    bookings: rows.length,
    rooms: new Set(rows.map((r) => r.roomId)).size,
    days: new Set(rows.map((r) => r.date)).size,
  };
}

/** "3" or "3–4": the slot numbers the holder occupies (CRBS period order). */
export function periodSpan(h: Pick<ConflictHolder, "start_period" | "end_period">): string {
  return h.start_period === h.end_period ? String(h.start_period) : `${h.start_period}–${h.end_period}`;
}
