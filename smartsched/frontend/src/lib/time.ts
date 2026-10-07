/**
 * Period / time helpers for the 18-period daily grid (docs/DATA_ANALYSIS.md "Time grid").
 * All helpers are pure and locale-neutral; day names are resolved via Intl in the UI.
 */

export interface Period {
  /** 1-based index */
  index: number;
  /** "HH:MM" */
  start: string;
  /** "HH:MM" */
  end: string;
}

export const PERIODS_PER_DAY = 18;

const PERIOD_STARTS = [
  "08:30", "09:20", "10:10", "11:00", "11:50", "12:40",
  "13:30", "14:20", "15:10", "16:00", "16:50", "17:30",
  "18:00", "18:50", "19:40", "20:30", "21:20", "22:10",
] as const;

const PERIOD_ENDS = [
  "09:10", "10:00", "10:50", "11:40", "12:30", "13:20",
  "14:10", "15:00", "15:50", "16:40", "17:30", "18:00",
  "18:40", "19:30", "20:20", "21:10", "22:00", "22:50",
] as const;

export const PERIODS: readonly Period[] = PERIOD_STARTS.map((start, i) => ({
  index: i + 1,
  start,
  end: PERIOD_ENDS[i],
}));

/** Minutes since midnight for "HH:MM" / "HH.MM" / "H:MM". Returns null when unparsable. */
export function parseClock(text: string): number | null {
  const m = /^\s*(\d{1,2})[:.](\d{2})\s*$/.exec(text);
  if (!m) return null;
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h > 23 || min > 59) return null;
  return h * 60 + min;
}

export function formatClock(minutes: number): string {
  const h = Math.floor(minutes / 60) % 24;
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** Period whose start is closest to the given time (snap). Returns index 1..18. */
export function snapToPeriod(clock: string): { index: number; exact: boolean } | null {
  const minutes = parseClock(clock);
  if (minutes === null) return null;
  let best = 1;
  let bestDist = Number.POSITIVE_INFINITY;
  for (const p of PERIODS) {
    const d = Math.abs((parseClock(p.start) ?? 0) - minutes);
    if (d < bestDist) {
      bestDist = d;
      best = p.index;
    }
  }
  return { index: best, exact: bestDist === 0 };
}

/** The last period whose end is <= the given end time (inclusive range end). */
export function periodEndingAt(clock: string): number | null {
  const minutes = parseClock(clock);
  if (minutes === null) return null;
  let last: number | null = null;
  for (const p of PERIODS) {
    if ((parseClock(p.end) ?? 0) <= minutes + 10) last = p.index;
  }
  return last;
}

/** Inclusive period range → "08:30–10:50" label. */
export function periodRangeLabel(start: number, end: number): string {
  const a = PERIODS[clampPeriod(start) - 1];
  const b = PERIODS[clampPeriod(end) - 1];
  return `${a.start}–${b.end}`;
}

export function periodLabel(index: number): string {
  const p = PERIODS[clampPeriod(index) - 1];
  return `P${p.index} ${p.start}`;
}

export function clampPeriod(index: number): number {
  return Math.min(PERIODS_PER_DAY, Math.max(1, Math.round(index)));
}

/** Number of periods in an inclusive range. */
export function spanLength(start: number, end: number): number {
  return Math.max(0, end - start + 1);
}

/** Inclusive ranges overlap? */
export function rangesOverlap(aStart: number, aEnd: number, bStart: number, bEnd: number): boolean {
  return aStart <= bEnd && bStart <= aEnd;
}

/** Evening (İÖ) programmes start at P13 (18:00). */
export function isEveningPeriod(index: number): boolean {
  return index >= 13;
}

export const DAY_INDEXES = [1, 2, 3, 4, 5, 6, 7] as const;
export type DayIndex = (typeof DAY_INDEXES)[number];

/** Localised weekday name for ISO day 1..7 (1 = Monday). */
export function dayName(day: number, locale: string, width: "long" | "short" = "long"): string {
  // 2024-01-01 is a Monday.
  const d = new Date(Date.UTC(2024, 0, 1 + (clampDay(day) - 1)));
  return new Intl.DateTimeFormat(locale, { weekday: width, timeZone: "UTC" }).format(d);
}

export function clampDay(day: number): number {
  return Math.min(7, Math.max(1, Math.round(day)));
}

/** ISO date for week start + day offset (week start is a "YYYY-MM-DD"). */
export function dateForWeekDay(weekStart: string, day: number): string {
  const [y, m, d] = weekStart.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d + (clampDay(day) - 1)));
  return date.toISOString().slice(0, 10);
}

export function formatDate(iso: string, locale: string, opts?: Intl.DateTimeFormatOptions): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return new Intl.DateTimeFormat(locale, { timeZone: "UTC", day: "numeric", month: "short", ...opts }).format(date);
}
