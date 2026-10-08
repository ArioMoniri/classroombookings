/**
 * Dates in the organisation's patterns (CRBS `settings/General`: `pattern_long` "EEEE d MMMM yyyy",
 * `pattern_weekday` "EEE d MMM", `pattern_time` "HH:mm"), in any of the 14 languages: Turkish and English are
 * SmartSched's own tables, the 12 other CRBS languages use CRBS's day and month names (`calendar_lang.php`, via
 * `lib/i18n/locale-data.json`, the file the backend reads too) and English AM/PM (CRBS has none).
 *
 * Supported tokens (the ICU subset of the CRBS option lists): `EEEE` `EEE` (weekday long/short), `d` `dd`,
 * `M` `MM` `MMM` `MMMM`, `yy` `yyyy`, `H` `HH`, `h` `hh`, `m` `mm`, `a` (ÖÖ/ÖS, AM/PM); text in single quotes is
 * literal ('' = a quote). Names come from the same tables as the backend, so screens and e-mails agree.
 * Booking dates are plain calendar dates ("2026-02-16"), so they are parsed as local dates: no time-zone
 * shift can move a booking to the previous day.
 */
import type { CrbsLocale, Locale } from "@/lib/i18n";
import localeData from "@/lib/i18n/locale-data.json";

const CRBS = localeData.languages as Record<CrbsLocale, (typeof localeData)["languages"][CrbsLocale]>;
const CRBS_CODES = Object.keys(CRBS) as CrbsLocale[];
/** one table per locale: Turkish and English as written here, the CRBS languages from the generated data */
function withCrbs<T>(own: Record<"tr" | "en", T>, pick: (d: (typeof CRBS)[CrbsLocale]) => T): Record<Locale, T> {
  return { ...own, ...(Object.fromEntries(CRBS_CODES.map((c) => [c, pick(CRBS[c])])) as Record<CrbsLocale, T>) };
}

export const DEFAULT_PATTERNS = { long: "EEEE d MMMM yyyy", weekday: "EEE d MMM", time: "HH:mm" } as const;

export interface PatternDefaults {
  long: string;
  weekday: string;
  time: string;
}

/** An empty org pattern is CRBS "(Default)": the locale's FULL / MEDIUM / SHORT format. Same table as the
 *  backend (`bookings_i18n.DEFAULT_PATTERNS`, served as `GET /org/i18n` → `date_defaults`). */
export const LOCALE_DEFAULTS: Record<Locale, PatternDefaults> = withCrbs(
  {
    tr: { long: "d MMMM yyyy EEEE", weekday: "d MMM yyyy", time: "HH:mm" },
    en: { long: "EEEE, d MMMM yyyy", weekday: "d MMM yyyy", time: "HH:mm" },
  },
  (d) => d.date_defaults,
);
/** numeric day-month-year of each locale (tables, error messages): ICU's order and separators */
const SHORT: Record<Locale, string> = withCrbs({ tr: "dd.MM.yyyy", en: "dd/MM/yyyy" }, (d) => d.short);

/* Month and day names: the backend's tables, so the grid and the e-mails read the same ("Sep", not Intl's "Sept"). */
const MONTHS: Record<Locale, readonly string[]> = withCrbs(
  {
    tr: ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"],
    en: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
  },
  (d) => d.months,
);
const MONTHS_SHORT: Record<Locale, readonly string[]> = withCrbs(
  {
    tr: ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"],
    en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
  },
  (d) => d.months_short,
);
/** Monday first, like Python's `date.weekday()` */
const WEEKDAYS: Record<Locale, readonly string[]> = withCrbs(
  {
    tr: ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"],
    en: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
  },
  (d) => d.weekdays,
);
const WEEKDAYS_SHORT: Record<Locale, readonly string[]> = withCrbs(
  {
    tr: ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"],
    en: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
  },
  (d) => d.weekdays_short,
);
const AM_PM: Record<Locale, readonly [string, string]> = withCrbs<readonly [string, string]>({ tr: ["ÖÖ", "ÖS"], en: ["AM", "PM"] }, () => ["AM", "PM"]);

export interface DatePatterns {
  pattern_long?: string | null;
  pattern_weekday?: string | null;
  pattern_time?: string | null;
}

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
    if (/[EdMyHhmsa]/.test(ch)) {
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

function field(d: Date, letter: string, count: number, locale: Locale): string {
  const pad = (n: number, w = 2) => String(n).padStart(w, "0");
  switch (letter) {
    case "E":
      return (count >= 4 ? WEEKDAYS : WEEKDAYS_SHORT)[locale][(d.getDay() + 6) % 7]!;
    case "d":
      return count >= 2 ? pad(d.getDate()) : String(d.getDate());
    case "M":
      if (count >= 4) return MONTHS[locale][d.getMonth()]!;
      if (count === 3) return MONTHS_SHORT[locale][d.getMonth()]!;
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
    case "a":
      return AM_PM[locale][d.getHours() >= 12 ? 1 : 0];
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
  /** "08:30" stays as is unless the pattern says otherwise ("h:mm a" → "8:30 AM") */
  time: (hhmm: string) => string;
  /** numeric, for tables: 16.02.2026 (tr, de) / 16/02/2026 (en, fr) / 2026-02-16 (sv) */
  short: (day: string) => string;
  /** a backend timestamp (UTC, with or without "Z") in local time: weekday pattern + time pattern */
  dateTime: (iso: string | null | undefined) => string;
}

/** Backend timestamps are naive UTC ("2026-02-16T08:00:00"); read them as UTC, show them in local time. */
export function parseTimestamp(iso: string): Date {
  return new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`);
}

/**
 * Formatter over the organisation's patterns. An empty pattern is CRBS "(Default)" = `defaults` (from
 * `GET /org/i18n` → `date_defaults`, else the same table shipped here) for the language.
 */
export function dateFormatter(patterns: DatePatterns | undefined | null, locale: Locale, defaults?: PatternDefaults | null): DateFormatter {
  const base = defaults ?? LOCALE_DEFAULTS[locale] ?? DEFAULT_PATTERNS;
  const long = patterns?.pattern_long || base.long;
  const weekday = patterns?.pattern_weekday || base.weekday;
  const time = patterns?.pattern_time || base.time;
  const clock = (d: Date) => formatPattern(d, time, locale);
  return {
    long: (day) => formatPattern(day, long, locale),
    weekday: (day) => formatPattern(day, weekday, locale),
    time: (hhmm) => {
      const m = /^(\d{1,2}):(\d{2})/.exec(hhmm);
      if (!m) return hhmm;
      return clock(new Date(2000, 0, 1, Number(m[1]), Number(m[2])));
    },
    short: (day) => formatPattern(day, SHORT[locale] ?? SHORT.en, locale),
    dateTime: (iso) => {
      if (!iso) return "";
      const d = parseTimestamp(iso);
      if (Number.isNaN(d.getTime())) return iso;
      return `${formatPattern(d, weekday, locale)} ${clock(d)}`;
    },
  };
}
