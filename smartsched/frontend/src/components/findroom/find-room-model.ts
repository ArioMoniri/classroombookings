/**
 * Find a room (T1): the form state, its `POST /rooms/find` body, recent searches and the booking-sheet target
 * of a result. Pure functions (no React), unit-tested in find-room-model.test.ts.
 */
import type { Grid, GridSlot } from "@/lib/api/crbs";
import type { FeatureFilter, FindQuery, FindRow } from "@/lib/api/wave1";
import { isSelectable } from "@/components/bookings/grid-model";

export type WhenMode = "date" | "weekday" | "range";
export type TimeMode = "clock" | "periods" | "duration";

export interface FindForm {
  when: WhenMode;
  date: string;
  weekday: number;
  /** "3-5, 7" (empty = every lecture week) */
  weeks: string;
  dateFrom: string;
  dateTo: string;
  /** ISO weekdays for the range (empty = every day) */
  weekdays: number[];
  time: TimeMode;
  start: string;
  end: string;
  startPeriod: number;
  endPeriod: number;
  durationPeriods: number;
  /** duration mode: the window the block may slide in */
  windowStart: string;
  windowEnd: string;
  headcount: string;
  purpose: "teaching" | "exam";
  /** feature id → filter value: true (yes/no), a number (≥), option ids */
  features: Record<string, true | number | number[]>;
  buildings: string[];
  text: string;
  showBusy: boolean;
  otherDays: boolean;
}

export function emptyForm(today: string): FindForm {
  return {
    when: "date",
    date: today,
    weekday: isoWeekdayOf(today),
    weeks: "",
    dateFrom: today,
    dateTo: today,
    weekdays: [],
    time: "clock",
    start: "10:10",
    end: "12:30",
    startPeriod: 3,
    endPeriod: 5,
    durationPeriods: 2,
    windowStart: "08:30",
    windowEnd: "17:00",
    headcount: "",
    purpose: "teaching",
    features: {},
    buildings: [],
    text: "",
    showBusy: false,
    otherDays: false,
  };
}

export function isoWeekdayOf(day: string): number {
  const [y, m, d] = day.split("-").map(Number);
  const wd = new Date(Date.UTC(y ?? 2026, (m ?? 1) - 1, d ?? 1)).getUTCDay();
  return wd === 0 ? 7 : wd;
}

/** "3-5, 7" / "3–5 7" → [3, 4, 5, 7]; `null` when a piece is not a week number. */
export function parseWeeks(text: string): number[] | null {
  const out = new Set<number>();
  const parts = text.split(/[,;\s]+/).map((p) => p.trim()).filter(Boolean);
  for (const p of parts) {
    const m = /^(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?$/.exec(p);
    if (!m) return null;
    const a = Number(m[1]);
    const b = m[2] ? Number(m[2]) : a;
    if (a < 1 || b < a || b > 60) return null;
    for (let w = a; w <= b; w++) out.add(w);
  }
  return [...out].sort((x, y) => x - y);
}

/**
 * Clock text as the planners type it: "10:10", "10.10", "1010", "9:5" is refused; NBSP and spaces are
 * tolerated. Returns "HH:MM" or `null`.
 */
export function normaliseClock(text: string): string | null {
  const s = text.replace(/[\s ]/g, "");
  const m = /^(\d{1,2})[:.]?(\d{2})$/.exec(s);
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h > 23 || min > 59) return null;
  return `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
}

export type FormError = "date" | "weeks" | "range" | "start" | "end" | "order" | "window";

/** The request body, or the first field that is wrong (the form shows it next to the field). */
export function buildQuery(f: FindForm, termId?: number, kinds: Readonly<Record<string, string>> = {}): { query: FindQuery } | { error: FormError } {
  const q: FindQuery = { start: "", term_id: termId };
  if (f.when === "date") {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(f.date)) return { error: "date" };
    q.date = f.date;
  } else if (f.when === "weekday") {
    const weeks = parseWeeks(f.weeks);
    if (weeks === null) return { error: "weeks" };
    q.weekday = f.weekday;
    q.weeks = weeks;
  } else {
    if (!f.dateFrom || !f.dateTo || f.dateTo < f.dateFrom) return { error: "range" };
    q.date_from = f.dateFrom;
    q.date_to = f.dateTo;
    if (f.weekdays.length) q.weekdays = [...f.weekdays].sort((a, b) => a - b);
  }
  if (f.time === "clock") {
    const start = normaliseClock(f.start);
    const end = normaliseClock(f.end);
    if (!start) return { error: "start" };
    if (!end) return { error: "end" };
    if (end <= start) return { error: "order" };
    q.start = start;
    q.end = end;
  } else if (f.time === "periods") {
    if (f.endPeriod < f.startPeriod) return { error: "order" };
    q.start = f.startPeriod;
    q.end = f.endPeriod;
  } else {
    const start = normaliseClock(f.windowStart);
    const end = normaliseClock(f.windowEnd);
    if (!start) return { error: "start" };
    if (!end || end <= start) return { error: "window" };
    q.start = start;
    q.duration_periods = Math.max(1, Math.min(18, f.durationPeriods));
    q.window_end = end;
  }
  const head = Number(f.headcount.replace(/\D/g, "") || "0");
  if (head > 0) q.headcount = head;
  if (f.purpose === "exam") q.purpose = "exam";
  const features: FeatureFilter[] = Object.entries(f.features).filter(([, v]) => !(Array.isArray(v) && v.length === 0)).map(([id, v]) =>
    v === true ? { field: Number(id) } : typeof v === "number" ? { field: Number(id), op: "gte", value: v } : { field: Number(id), op: kinds[id] === "SELECT" ? "in" : "has", value: v },
  );
  if (features.length) q.features = features;
  if (f.buildings.length) q.buildings = [...f.buildings];
  if (f.text.trim()) q.text = f.text.trim();
  q.include_busy = f.showBusy;
  q.flex = { periods: 2, other_days: f.otherDays };
  q.limit = 60;
  return { query: q };
}

/** A recent search body (GET /rooms/find/recent) back into the form, so one click re-runs it. */
export function formFromRecent(body: Record<string, unknown>, base: FindForm): FindForm {
  const f: FindForm = { ...base, features: {}, buildings: [], text: "", headcount: "" };
  const str = (k: string) => (typeof body[k] === "string" ? (body[k] as string) : undefined);
  const num = (k: string) => (typeof body[k] === "number" ? (body[k] as number) : undefined);
  const arr = (k: string) => (Array.isArray(body[k]) ? (body[k] as unknown[]) : []);
  if (str("date")) Object.assign(f, { when: "date", date: str("date") });
  else if (arr("dates").length) Object.assign(f, { when: "date", date: String(arr("dates")[0]) });
  else if (num("weekday")) Object.assign(f, { when: "weekday", weekday: num("weekday"), weeks: compactWeeks(arr("weeks").map(Number)) });
  else if (str("date_from")) Object.assign(f, { when: "range", dateFrom: str("date_from"), dateTo: str("date_to") ?? str("date_from"), weekdays: arr("weekdays").map(Number) });
  const start = body.start;
  const end = body.end;
  if (body.duration_periods || body.window_end) {
    Object.assign(f, { time: "duration", windowStart: String(start ?? f.windowStart), windowEnd: String(body.window_end ?? f.windowEnd), durationPeriods: Number(body.duration_periods ?? 2) });
  } else if (typeof start === "number") {
    Object.assign(f, { time: "periods", startPeriod: start, endPeriod: typeof end === "number" ? end : start });
  } else if (typeof start === "string") {
    Object.assign(f, { time: "clock", start, end: typeof end === "string" ? end : f.end });
  }
  if (num("headcount")) f.headcount = String(num("headcount"));
  if (str("purpose") === "exam") f.purpose = "exam";
  if (str("text")) f.text = str("text")!;
  f.buildings = arr("buildings").map(String);
  for (const x of arr("features")) {
    if (!x || typeof x !== "object") continue;
    const ff = x as { field?: unknown; op?: unknown; value?: unknown };
    if (typeof ff.field !== "number") continue;
    if (ff.op === "gte" && ff.value != null) f.features[String(ff.field)] = Number(ff.value);
    else if (Array.isArray(ff.value)) f.features[String(ff.field)] = ff.value.map(Number);
    else f.features[String(ff.field)] = true;
  }
  f.showBusy = body.include_busy === true;
  const flex = body.flex as { other_days?: unknown } | undefined;
  f.otherDays = flex?.other_days === true;
  return f;
}

/** [3, 4, 5, 7] → "3-5, 7" */
export function compactWeeks(weeks: number[]): string {
  const w = [...new Set(weeks)].sort((a, b) => a - b);
  const out: string[] = [];
  for (let i = 0; i < w.length; i++) {
    let j = i;
    while (j + 1 < w.length && w[j + 1] === w[j]! + 1) j++;
    out.push(j > i ? `${w[i]}-${w[j]}` : String(w[i]));
    i = j;
  }
  return out.join(", ");
}

/** Parts of a short label for a recent search ("18.02.2026 · 10:10–12:30 · 90+"); the view formats dates. */
export function recentParts(body: Record<string, unknown>): { date?: string; weekday?: number; range?: [string, string]; time?: string; headcount?: number; text?: string } {
  const out: ReturnType<typeof recentParts> = {};
  if (typeof body.date === "string") out.date = body.date;
  else if (Array.isArray(body.dates) && body.dates.length) out.date = String(body.dates[0]);
  else if (typeof body.weekday === "number") out.weekday = body.weekday;
  else if (typeof body.date_from === "string") out.range = [body.date_from, typeof body.date_to === "string" ? body.date_to : body.date_from];
  const s = body.start;
  const e = body.end ?? body.window_end;
  if (s !== undefined) out.time = typeof s === "number" ? `P${s}${typeof e === "number" ? `–P${e}` : ""}` : `${String(s)}${e !== undefined ? `–${String(e)}` : ""}`;
  if (typeof body.headcount === "number" && body.headcount > 0) out.headcount = body.headcount;
  if (typeof body.text === "string" && body.text) out.text = body.text;
  return out;
}

/* --------------------------------------------------------------------------------- reserve target */

/** Grid slots of `roomId` on `date` whose periods fall in start..end (grid period numbers), in order. */
export function slotsFor(grid: Grid, roomId: number, date: string, start: number, end: number): GridSlot[] {
  const periods = grid.periods.filter((p) => p.start_period >= start && p.end_period <= end).sort((a, b) => a.start_period - b.start_period);
  const ids = new Set(periods.map((p) => p.id));
  const order = new Map(periods.map((p, i) => [p.id, i]));
  return grid.slots.filter((s) => s.room_id === roomId && s.date === date && ids.has(s.period_id)).sort((a, b) => (order.get(a.period_id) ?? 0) - (order.get(b.period_id) ?? 0));
}

/**
 * What the booking sheet opens with: the longest leading run of reservable slots (all of them when the room
 * is free for the whole span). `null` when none of them can be booked from the grid (taken meanwhile, or no
 * right in that room).
 */
export function reserveSpan(slots: GridSlot[]): GridSlot[] | null {
  const run: GridSlot[] = [];
  for (const s of slots) {
    if (!isSelectable(s)) {
      if (run.length) break;
      continue;
    }
    run.push(s);
  }
  return run.length ? run : null;
}

/** The first date a result is free on (multi-date searches report per date). */
export function firstFreeDate(row: Pick<FindRow, "per_date">, slots: { date: string }[]): string | null {
  const free = row.per_date?.find((d) => d.status === "free" || d.status === "requestable");
  if (free) return free.date;
  return slots[0]?.date ?? null;
}

/** Statuses a person can act on (book directly or send a request). */
export const ACTIONABLE = new Set(["free", "requestable", "partial"]);
