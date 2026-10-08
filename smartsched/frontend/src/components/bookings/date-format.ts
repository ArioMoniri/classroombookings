/**
 * Dates in the organisation's patterns (CRBS `settings/General`: `pattern_long` "EEEE d MMMM yyyy",
 * `pattern_weekday` "EEE d MMM", `pattern_time` "HH:mm"), in Turkish or English.
 *
 * Supported tokens (ICU / date-fns subset that CRBS documents): `EEEE` `EEE` (weekday long/short), `d` `dd`,
 * `M` `MM` `MMM` `MMMM`, `yy` `yyyy`, `H` `HH`, `m` `mm`; text in single quotes is literal ('' = a quote).
 * Booking dates are plain calendar dates ("2026-02-16"), so they are parsed as local dates: no time-zone
 * shift can move a booking to the previous day.
 */
import type { Locale } from "@/lib/i18n";

export const DEFAULT_PATTERNS = { long: "EEEE d MMMM yyyy", weekday: "EEE d MMM", time: "HH:mm" } as const;

export interface DatePatterns {
  pattern_long?: string | null;
  pattern_weekday?: string | null;
  pattern_time?: string | null;
}

const intlTag = (locale: Locale) => (locale === "tr" ? "tr-TR" : "en-GB");

/** "2026-02-16" → local Date at midnight; also accepts full ISO timestamps. */
export function parseDay(value: string | Date): Date {
  if (value instanceof Date) return value;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return new Date(value);
}

/** Local Date → "YYYY-MM-DD". */
export function isoDay(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function addDays(day: string, n: number): string {
  const d = parseDay(day);
  d.setDate(d.getDate() + n);
  return isoDay(d);
}

/** ISO weekday 1 (Monday) … 7 (Sunday). */
export function isoWeekday(day: string): number {
  const wd = parseDay(day).getDay();
  return wd === 0 ? 7 : wd;
}

export function mondayOf(day: string): string {
  return addDays(day, 1 - isoWeekday(day));
}

type Token = { kind: "field"; letter: string; count: number } | { kind: "text"; value: string };

export function tokenize(pattern: string): Token[] {
  const out: Token[] = [];
  let i = 0;
  while (i < pattern.length) {
    const ch = pattern[i]!;
    if (ch === "'") {
      if (pattern[i + 1] === "'") {
        out.push({ kind: "text", value: "'" });
        i += 2;
        continue;
      }
      const end = pattern.indexOf("'", i + 1);
      const stop = end === -1 ? pattern.length : end;
      out.push({ kind: "text", value: pattern.slice(i + 1, stop) });
      i = stop + 1;
      continue;
    }
    if (/[EdMyHhms]/.test(ch)) {
      let j = i;
      while (pattern[j] === ch) j++;
      out.push({ kind: "field", letter: ch, count: j - i });
      i = j;
      continue;
    }
    const last = out[out.length - 1];
    if (last && last.kind === "text") last.value += ch;
    else out.push({ kind: "text", value: ch });
    i++;
  }
  return out;
}

function part(d: Date, locale: Locale, opts: Intl.DateTimeFormatOptions, type: Intl.DateTimeFormatPartTypes): string {
  return new Intl.DateTimeFormat(intlTag(locale), opts).formatToParts(d).find((p) => p.type === type)?.value ?? "";
}

function field(d: Date, letter: string, count: number, locale: Locale): string {
  const pad = (n: number, w = 2) => String(n).padStart(w, "0");
  switch (letter) {
    case "E":
      return part(d, locale, { weekday: count >= 4 ? "long" : "short" }, "weekday").replace(/\.$/, "");
    case "d":
      return count >= 2 ? pad(d.getDate()) : String(d.getDate());
    case "M":
      if (count >= 4) return part(d, locale, { month: "long", day: "numeric" }, "month");
      if (count === 3) return part(d, locale, { month: "short", day: "numeric" }, "month").replace(/\.$/, "");
      return count === 2 ? pad(d.getMonth() + 1) : String(d.getMonth() + 1);
    case "y":
      return count === 2 ? pad(d.getFullYear() % 100) : String(d.getFullYear());
    case "H":
      return count >= 2 ? pad(d.getHours()) : String(d.getHours());
    case "h": {
      const h = d.getHours() % 12 || 12;
      return count >= 2 ? pad(h) : String(h);
    }
    case "m":
      return count >= 2 ? pad(d.getMinutes()) : String(d.getMinutes());
    case "s":
      return count >= 2 ? pad(d.getSeconds()) : String(d.getSeconds());
    default:
      return letter.repeat(count);
  }
}

export function formatPattern(value: string | Date, pattern: string, locale: Locale): string {
  const d = parseDay(value);
  if (Number.isNaN(d.getTime())) return typeof value === "string" ? value : "";
  return tokenize(pattern)
    .map((t) => (t.kind === "text" ? t.value : field(d, t.letter, t.count, locale)))
    .join("");
}

export interface DateFormatter {
  long: (day: string) => string;
  weekday: (day: string) => string;
  /** "08:30" stays as is unless the pattern says otherwise ("h:mm" → "8:30") */
  time: (hhmm: string) => string;
  /** numeric, for tables: 16.02.2026 (tr) / 16/02/2026 (en) */
  short: (day: string) => string;
}

export function dateFormatter(patterns: DatePatterns | undefined | null, locale: Locale): DateFormatter {
  const long = patterns?.pattern_long || DEFAULT_PATTERNS.long;
  const weekday = patterns?.pattern_weekday || DEFAULT_PATTERNS.weekday;
  const time = patterns?.pattern_time || DEFAULT_PATTERNS.time;
  return {
    long: (day) => formatPattern(day, long, locale),
    weekday: (day) => formatPattern(day, weekday, locale),
    time: (hhmm) => {
      const m = /^(\d{1,2}):(\d{2})/.exec(hhmm);
      if (!m) return hhmm;
      const d = new Date(2000, 0, 1, Number(m[1]), Number(m[2]));
      return formatPattern(d, time, locale);
    },
    short: (day) => formatPattern(day, locale === "tr" ? "dd.MM.yyyy" : "dd/MM/yyyy", locale),
  };
}
