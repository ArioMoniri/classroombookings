/** Week/date helpers for titles, the mini-month, Month lens and scrubber (dates are ISO "YYYY-MM-DD", UTC). */
import type { IndexWeek } from "@/lib/api/calendar";

export function parseIso(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, (m || 1) - 1, d || 1));
}

export function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function addDays(isoDate: string, n: number): string {
  const d = parseIso(isoDate);
  d.setUTCDate(d.getUTCDate() + n);
  return iso(d);
}

/** Monday of the ISO week containing `isoDate`. */
export function mondayOf(isoDate: string): string {
  const d = parseIso(isoDate);
  const wd = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - wd);
  return iso(d);
}

/** Term week index → Monday; falls back to extrapolating from the first dated week. */
export function weekMonday(weeks: readonly IndexWeek[], week: number): string | null {
  const exact = weeks.find((w) => w.index === week && w.start_date);
  if (exact?.start_date) return mondayOf(exact.start_date);
  const first = weeks.find((w) => w.start_date);
  if (!first?.start_date) return null;
  return addDays(mondayOf(first.start_date), (week - first.index) * 7);
}

export function dateOf(weeks: readonly IndexWeek[], week: number, day: number): string | null {
  const mon = weekMonday(weeks, week);
  return mon ? addDays(mon, day - 1) : null;
}

/** Date → (term week, day) using the dated weeks; null outside the term. */
export function weekDayOf(weeks: readonly IndexWeek[], isoDate: string): { week: number; day: number } | null {
  for (const w of weeks) {
    const mon = weekMonday(weeks, w.index);
    if (!mon) continue;
    const diff = Math.round((parseIso(isoDate).getTime() - parseIso(mon).getTime()) / 86_400_000);
    if (diff >= 0 && diff < 7) return { week: w.index, day: diff + 1 };
  }
  return null;
}

/** "16–22 Mart 2026" / "30 Mar–5 Nis 2026" / "29 Ara 2025–4 Oca 2026". */
export function rangeTitle(startIso: string, endIso: string, locale: string): string {
  const a = parseIso(startIso);
  const b = parseIso(endIso);
  const fmt = (d: Date, o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(locale, { timeZone: "UTC", ...o }).format(d);
  if (a.getUTCFullYear() !== b.getUTCFullYear()) return `${fmt(a, { day: "numeric", month: "short", year: "numeric" })}–${fmt(b, { day: "numeric", month: "short", year: "numeric" })}`;
  if (a.getUTCMonth() !== b.getUTCMonth()) return `${fmt(a, { day: "numeric", month: "short" })}–${fmt(b, { day: "numeric", month: "short" })} ${b.getUTCFullYear()}`;
  return `${a.getUTCDate()}–${fmt(b, { day: "numeric", month: "long", year: "numeric" })}`;
}

export function dayTitle(isoDate: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { timeZone: "UTC", weekday: "long", day: "numeric", month: "long" }).format(parseIso(isoDate));
}

/** Month grid: Monday-start weeks covering the month (5 or 6 rows × 7). */
export function monthGrid(year: number, month1: number): string[] {
  const first = iso(new Date(Date.UTC(year, month1 - 1, 1)));
  const last = iso(new Date(Date.UTC(year, month1, 0)));
  const start = mondayOf(first);
  const out: string[] = [];
  let d = start;
  while (d <= last || out.length % 7 !== 0) {
    out.push(d);
    d = addDays(d, 1);
  }
  return out;
}

export function minutesNow(now: Date = new Date()): number {
  return now.getHours() * 60 + now.getMinutes();
}

export function todayIso(now: Date = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

/** Week type label key by kind (Ders / Final / Bütünleme / Tatil). */
export function weekTypeKey(kind: string): "lecture" | "final" | "makeup" | "holiday" {
  if (kind === "EXAM") return "final";
  if (kind === "MAKEUP") return "makeup";
  if (kind === "HOLIDAY") return "holiday";
  return "lecture";
}
