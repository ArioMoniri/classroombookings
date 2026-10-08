/**
 * Session calendar painter (CRBS `Sessions::view` + `Dates_model::set_weeks`): assign a timetable week to
 * each date of a term by painting with a brush (a week id, or `null` = no week).
 *
 * Interaction model (pure, so the component stays thin and the logic is tested):
 * - pointer down on a date starts a stroke; moving over other dates extends it as a *range in date order*
 *   from the anchor (like selecting text), so a drag across rows paints whole weeks;
 * - shift+click paints the range from the last painted date;
 * - clicking a week number paints Monday–Sunday of that week;
 * - nothing is sent until "Save": `changes()` is the minimal `PUT /dates` body.
 */
import { addDays, isoWeekday, mondayOf } from "@/components/bookings/date-format";

export type Brush = number | null;

export interface PainterState {
  /** term dates in order, as returned by the backend */
  days: string[];
  original: Record<string, number | null>;
  pending: Record<string, number | null>;
  brush: Brush;
  stroke: { anchor: string; base: Record<string, number | null> } | null;
  last: string | null;
}

export type PainterAction =
  | { type: "load"; dates: { date: string; timetable_week_id?: number | null }[] }
  | { type: "brush"; brush: Brush }
  | { type: "down"; date: string; shift?: boolean }
  | { type: "enter"; date: string }
  | { type: "up" }
  | { type: "week"; monday: string }
  | { type: "fill"; brush: Brush }
  | { type: "revert" };

export function initialPainter(brush: Brush = null): PainterState {
  return { days: [], original: {}, pending: {}, brush, stroke: null, last: null };
}

/** Dates of `days` between a and b inclusive, in date order whatever the direction. */
export function rangeBetween(days: readonly string[], a: string, b: string): string[] {
  const [lo, hi] = a <= b ? [a, b] : [b, a];
  return days.filter((d) => d >= lo && d <= hi);
}

function paint(target: Record<string, number | null>, dates: readonly string[], brush: Brush): Record<string, number | null> {
  const next = { ...target };
  for (const d of dates) if (d in next) next[d] = brush;
  return next;
}

export function painterReducer(state: PainterState, action: PainterAction): PainterState {
  switch (action.type) {
    case "load": {
      const original: Record<string, number | null> = {};
      for (const d of action.dates) original[d.date] = d.timetable_week_id ?? null;
      return { ...state, days: action.dates.map((d) => d.date), original, pending: { ...original }, stroke: null, last: null };
    }
    case "brush":
      return { ...state, brush: action.brush };
    case "down": {
      if (!(action.date in state.pending)) return state;
      if (action.shift && state.last) {
        return { ...state, pending: paint(state.pending, rangeBetween(state.days, state.last, action.date), state.brush), last: action.date, stroke: null };
      }
      return { ...state, stroke: { anchor: action.date, base: state.pending }, pending: paint(state.pending, [action.date], state.brush), last: action.date };
    }
    case "enter": {
      if (!state.stroke || !(action.date in state.pending)) return state;
      // repaint from the stroke's base so shrinking the range restores the dates it no longer covers
      return { ...state, pending: paint(state.stroke.base, rangeBetween(state.days, state.stroke.anchor, action.date), state.brush), last: action.date };
    }
    case "up":
      return state.stroke ? { ...state, stroke: null } : state;
    case "week": {
      const week = Array.from({ length: 7 }, (_, i) => addDays(action.monday, i));
      return { ...state, pending: paint(state.pending, week, state.brush), last: week[6] ?? state.last };
    }
    case "fill":
      return { ...state, pending: paint(state.pending, state.days, action.brush) };
    case "revert":
      return { ...state, pending: { ...state.original }, stroke: null };
  }
}

/** Minimal `PUT /booking-admin/sessions/{id}/dates` body: only dates whose week changed. */
export function changes(state: PainterState): Record<string, number | null> {
  const out: Record<string, number | null> = {};
  for (const d of state.days) if (state.pending[d] !== state.original[d]) out[d] = state.pending[d] ?? null;
  return out;
}

export function changeCount(state: PainterState): number {
  return Object.keys(changes(state)).length;
}

export interface MonthGrid {
  /** "2026-02" */
  key: string;
  year: number;
  month: number; // 1..12
  /** Monday-first weeks; null = a day outside the month */
  weeks: { monday: string; days: (string | null)[] }[];
}

/** Calendar months covering [start, end], Monday-first (Türkiye and ISO 8601). */
export function monthsBetween(start: string, end: string): MonthGrid[] {
  const out: MonthGrid[] = [];
  let y = Number(start.slice(0, 4));
  let m = Number(start.slice(5, 7));
  const endKey = end.slice(0, 7);
  for (let guard = 0; guard < 36; guard++) {
    const key = `${y}-${String(m).padStart(2, "0")}`;
    if (key > endKey) break;
    const first = `${key}-01`;
    const daysInMonth = new Date(y, m, 0).getDate();
    const weeks: MonthGrid["weeks"] = [];
    let monday = mondayOf(first);
    while (monday <= `${key}-${String(daysInMonth).padStart(2, "0")}`) {
      const days = Array.from({ length: 7 }, (_, i) => {
        const d = addDays(monday, i);
        return d.slice(0, 7) === key ? d : null;
      });
      weeks.push({ monday, days });
      monday = addDays(monday, 7);
    }
    out.push({ key, year: y, month: m, weeks });
    m += 1;
    if (m > 12) {
      m = 1;
      y += 1;
    }
  }
  return out;
}

export { isoWeekday };
