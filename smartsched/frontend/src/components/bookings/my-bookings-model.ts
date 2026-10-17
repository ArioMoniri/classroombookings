/**
 * /my-bookings rows (T-R2-13, R2-A-10 / R2-S-10, A-12): the periods of one submission (`group_id`, the
 * multi-booking) on one day in one room are one row, "C 303 · P7–P8 (13:30–15:00)", with one status; a period whose
 * status differs (one of them cancelled) stays its own row, so a cancelled list never hides a live period.
 */
import type { BookingOut } from "@/lib/api/crbs";

export interface BookingRow {
  /** the first period's id: the row's key, detail target and selection anchor */
  id: number;
  ids: number[];
  /** in period order */
  bookings: BookingOut[];
  first: BookingOut;
  last: BookingOut;
  /** "P7" or "P7–P8" */
  periodLabel: string;
}

const key = (b: BookingOut) => (b.group_id && b.type === "single" && !b.series_id ? `${b.group_id}|${b.date}|${b.room_id}|${b.status}` : `b${b.id}`);

export function groupBookings(rows: readonly BookingOut[]): BookingRow[] {
  const groups = new Map<string, BookingOut[]>();
  for (const b of rows) {
    const k = key(b);
    const g = groups.get(k);
    if (g) g.push(b);
    else groups.set(k, [b]);
  }
  return [...groups.values()].map((g) => {
    const bookings = [...g].sort((a, b) => a.start_period - b.start_period || a.id - b.id);
    const first = bookings[0]!;
    const last = bookings[bookings.length - 1]!;
    const p0 = first.period_name ?? `P${first.start_period}`;
    const p1 = last.period_name ?? `P${last.end_period}`;
    return { id: first.id, ids: bookings.map((b) => b.id), bookings, first, last, periodLabel: bookings.length > 1 ? `${p0}–${p1}` : p0 };
  });
}

/**
 * W3-SLOT (round-3 academician): the totals line counts live bookings only (GET /bookings/dashboard `totals`); open
 * requests are named apart. One submission (A-12: several periods share `group_id`) is one request.
 */
export function openRequestCount(requests: readonly { id: number; status: string; group_id?: number | null }[] | undefined): number {
  return new Set((requests ?? []).filter((r) => r.status === "PENDING").map((r) => (r.group_id != null ? `g${r.group_id}` : `r${r.id}`))).size;
}

const LIST = '[data-testid="booking-list"]';

/** R3-S-05: the index of the row that shows `bookingId` (rows carry every period's id in `data-booking-ids`), or -1. */
export function rowIndexOf(bookingId: number): number {
  const rows = [...document.querySelectorAll<HTMLElement>(`${LIST} > li`)];
  return rows.findIndex((li) => (li.dataset.bookingIds ?? "").split(",").includes(String(bookingId)));
}

/**
 * R3-S-05: after the row at `index` was cancelled and the list re-rendered without it, focus the row that took its
 * place, else the one before it, else the list heading. Never <body>. Returns the focused element.
 */
export function focusRowAfterRemoval(index: number): HTMLElement | null {
  const rows = [...document.querySelectorAll<HTMLElement>(`${LIST} > li [data-row-open]`)];
  const target = rows[Math.max(0, index)] ?? rows[index - 1] ?? rows[rows.length - 1] ?? document.getElementById("mine-list");
  target?.focus();
  return target;
}

/** R3-S-05: the same targets as selectors, for focusAfter's watch (a closing sheet hands focus back to a row that is gone). */
export function rowSelectorsAfterRemoval(index: number): string[] {
  const row = (n: number) => `${LIST} > li:nth-child(${n}) [data-row-open]`;
  return [row(Math.max(0, index) + 1), ...(index > 0 ? [row(index)] : []), `${LIST} > li:last-child [data-row-open]`, "#mine-list"];
}
