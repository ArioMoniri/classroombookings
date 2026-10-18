/**
 * HX-01 (helper.md §4.5): the deterministic shortcuts ("Kısayollar"). A small TR / EN reader for the phrasings people
 * type most: days (bugün, yarın, perşembe, 12 Kasım), clock times and periods (10:00, "3. saat", öğleden sonra), room
 * codes (A 204), headcounts (12 kişilik), a building (B blok) and a few features (projeksiyon). It maps them to one
 * action of the server registry with **partial arguments the server accepts** (`GET /helper/schema`, extra=forbid);
 * what the server cannot take (a clock time for a booking, "3. saat") stays a client hint that the card runner
 * resolves against the room's own periods. No AI, no network: the result is shown in the palette, and selecting it
 * asks `POST /helper/actions/{name}/card`, which answers confirm / form / list with the same confirm rules.
 */

export type IntentAction =
  | "create_booking"
  | "find_free_rooms"
  | "room_day_schedule"
  | "my_bookings"
  | "cancel_my_booking"
  | "my_requests_status"
  | "approvals_inbox"
  | "my_ai_usage"
  | "undo_last_helper_action"
  | "open_feature";

export interface IntentHints {
  /** a clock time the booking period should start at ("10:00") */
  time?: string;
  /** the Nth period of the day ("3. saat") */
  period?: number;
}

export interface Intent {
  action: IntentAction;
  args: Record<string, string | number>;
  hints?: IntentHints;
}

/** Lower case (Turkish rules), dotless ı → i, no diacritics, single spaces; apostrophes kept ("a 204'u"). */
export function foldText(text: string): string {
  return text
    .toLocaleLowerCase("tr-TR")
    .replace(/ı/g, "i")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[’`´]/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

const pad = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);

function validDate(y: number, m: number, d: number): Date | null {
  const out = new Date(y, m - 1, d);
  return out.getFullYear() === y && out.getMonth() === m - 1 && out.getDate() === d ? out : null;
}

const MONTHS: Record<string, number> = {
  ocak: 1, subat: 2, mart: 3, nisan: 4, mayis: 5, haziran: 6, temmuz: 7, agustos: 8, eylul: 9, ekim: 10, kasim: 11, aralik: 12,
  january: 1, february: 2, march: 3, april: 4, may: 5, june: 6, july: 7, august: 8, september: 9, october: 10, november: 11, december: 12,
  jan: 1, feb: 2, mar: 3, apr: 4, jun: 6, jul: 7, aug: 8, sep: 9, sept: 9, oct: 10, nov: 11, dec: 12,
};
const MONTH_RE = Object.keys(MONTHS).sort((a, b) => b.length - a.length).join("|");

/** Sunday = 0, as Date.getDay(); longer names first so "cumartesi" is not read as "cuma". */
const WEEKDAYS: [string, number][] = [
  ["pazartesi", 1], ["cumartesi", 6], ["carsamba", 3], ["persembe", 4], ["pazar", 0], ["sali", 2], ["cuma", 5],
  ["monday", 1], ["tuesday", 2], ["wednesday", 3], ["thursday", 4], ["friday", 5], ["saturday", 6], ["sunday", 0],
];
const WEEKDAY_RE = new RegExp(`(?:\\b(gelecek|haftaya|next)\\s+)?\\b(${WEEKDAYS.map(([w]) => w).join("|")})`);

interface Found<T> {
  value: T;
  rest: string;
}

/** Replace the matched span with a space so later readers do not see it again. */
const cut = (s: string, m: RegExpExecArray) => s.slice(0, m.index) + " " + s.slice(m.index + m[0].length);

function readDate(s: string, now: Date): Found<string> | null {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  let m: RegExpExecArray | null;
  if ((m = /\b(\d{4})-(\d{2})-(\d{2})\b/.exec(s))) {
    const d = validDate(+m[1]!, +m[2]!, +m[3]!);
    if (d) return { value: iso(d), rest: cut(s, m) };
  }
  if ((m = /\b(yarindan sonra|obur gun|day after tomorrow)\b/.exec(s))) return { value: iso(addDays(today, 2)), rest: cut(s, m) };
  if ((m = /\b(bugun|today)\w*/.exec(s))) return { value: iso(today), rest: cut(s, m) };
  if ((m = /\b(yarin|tomorrow)\w*/.exec(s))) return { value: iso(addDays(today, 1)), rest: cut(s, m) };
  const withYear = (day: number, month: number, year?: number): string | null => {
    if (year !== undefined) {
      const d = validDate(year < 100 ? 2000 + year : year, month, day);
      return d ? iso(d) : null;
    }
    const d = validDate(today.getFullYear(), month, day);
    if (!d) return null;
    return iso(d < today ? (validDate(today.getFullYear() + 1, month, day) ?? d) : d);
  };
  if ((m = new RegExp(`\\b(\\d{1,2})\\s*(?:'|\\.)?\\s*(${MONTH_RE})\\w*(?:\\s+(\\d{4}))?`).exec(s))) {
    const v = withYear(+m[1]!, MONTHS[m[2]!]!, m[3] ? +m[3] : undefined);
    return v ? { value: v, rest: cut(s, m) } : null;
  }
  if ((m = new RegExp(`\\b(${MONTH_RE})\\s+(\\d{1,2})(?:st|nd|rd|th)?\\b(?:,?\\s+(\\d{4}))?`).exec(s))) {
    const v = withYear(+m[2]!, MONTHS[m[1]!]!, m[3] ? +m[3] : undefined);
    if (v) return { value: v, rest: cut(s, m) };
  }
  // day.month or day/month (Turkish order); "15.30" (month 30) is a time, not a date
  if ((m = /(?<![\d:])\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b(?![:.]\d)/.exec(s))) {
    const day = +m[1]!;
    const month = +m[2]!;
    if (month >= 1 && month <= 12 && day >= 1) {
      const v = withYear(day, month, m[3] ? +m[3] : undefined);
      if (v) return { value: v, rest: cut(s, m) };
    }
  }
  if ((m = WEEKDAY_RE.exec(s))) {
    const want = WEEKDAYS.find(([w]) => w === m![2])![1];
    let ahead = (want - today.getDay() + 7) % 7;
    if (m[1]) ahead += 7;
    return { value: iso(addDays(today, ahead)), rest: cut(s, m) };
  }
  return null;
}

/** A day on its own ("yarın", "perşembe", "12 Kasım") → YYYY-MM-DD, or null. */
export function parseDate(text: string, now: Date): string | null {
  return readDate(foldText(text), now)?.value ?? null;
}

const hhmm = (h: number, min = 0): string | null => (h >= 0 && h <= 23 && min >= 0 && min <= 59 ? `${pad(h)}:${pad(min)}` : null);

interface TimeFound {
  time?: string;
  until?: string;
}

function readTime(s: string, afternoon: boolean): Found<TimeFound> | null {
  let m: RegExpExecArray | null;
  const pm = (h: number, flag?: string) => (flag === "pm" || (afternoon && h < 12 && h >= 1) ? (h === 12 ? 12 : h + 12) : flag === "am" && h === 12 ? 0 : h);
  // a range "14:00-16:00", "14-16 arası"
  if ((m = /\b(\d{1,2})(?:[:.](\d{2}))?\s*[-–]\s*(\d{1,2})(?:[:.](\d{2}))?\b/.exec(s))) {
    const a = hhmm(+m[1]!, m[2] ? +m[2] : 0);
    const b = hhmm(+m[3]!, m[4] ? +m[4] : 0);
    if (a && b && a < b) return { value: { time: a, until: b }, rest: cut(s, m) };
  }
  if ((m = /\b(\d{1,2})[:.](\d{2})\s*(am|pm)?(?:'\w+)?/.exec(s))) {
    const t = hhmm(pm(+m[1]!, m[3]), +m[2]!);
    return t ? { value: { time: t }, rest: cut(s, m) } : { value: {}, rest: cut(s, m) };
  }
  if ((m = /\b(?:saat|at)\s+(\d{1,2})\s*(am|pm)?(?:'\w+)?\b/.exec(s)) || (m = /\b(\d{1,2})\s*(am|pm)\b/.exec(s)) || (m = /\b(\d{1,2})'(?:da|de|ta|te|a|e|ya|ye)\b/.exec(s))) {
    const t = hhmm(pm(+m[1]!, m[2]));
    return t ? { value: { time: t }, rest: cut(s, m) } : null;
  }
  return null;
}

/** A clock time on its own ("saat 9", "14:30", "2 pm") → {time}; nothing for an impossible time. */
export function parseTime(text: string): TimeFound {
  return readTime(foldText(text), false)?.value ?? {};
}

/** Short words that look like the letters of a room code ("at 10", "on 12"): never a room. */
const NOT_ROOM = new Set(["at", "on", "in", "of", "by", "to", "da", "de", "te", "ta", "ve", "or", "is", "am", "pm", "no", "ne", "mi", "mu", "bu", "su", "o", "ya", "ye"]);

function readRoom(s: string): Found<string> | null {
  const re = /(^|[\s,(])([a-z]{1,2})\s?-?\s?(\d{2,4})(?:'[a-z]*|[a-z]{0,3})?(?=$|[\s,.?!)])/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    if (NOT_ROOM.has(m[2]!)) continue;
    const at = m.index + m[1]!.length;
    return { value: `${m[2]!.toLocaleUpperCase("tr-TR")} ${m[3]}`, rest: s.slice(0, at) + " " + s.slice(m.index + m[0].length) };
  }
  return null;
}

/** "a204'te", "C-12" → "A 204", "C 12"; course-like codes (3+ letters, "BME 419") are not rooms. */
export function parseRoom(text: string): string | null {
  return readRoom(foldText(text))?.value ?? null;
}

function readHeadcount(s: string): Found<number> | null {
  const m = /\b(\d{1,4})\s*(?:kisilik|kisi|people|persons|person|seats|students|ogrenci)\w*/.exec(s) ?? /\bfor\s+(\d{1,4})\b(?!\s*(?:am|pm|[:.]\d))/.exec(s);
  return m && +m[1]! > 0 ? { value: +m[1]!, rest: cut(s, m) } : null;
}

function readPeriod(s: string): Found<number> | null {
  const m = /\b(\d{1,2})\.\s?(?:ders\s)?saat\w*/.exec(s) ?? /\b(\d{1,2})(?:st|nd|rd|th)\s+period\b/.exec(s) ?? /\bperiod\s+(\d{1,2})\b/.exec(s) ?? /\b(\d{1,2})\.\s?ders\b/.exec(s);
  return m && +m[1]! >= 1 && +m[1]! <= 16 ? { value: +m[1]!, rest: cut(s, m) } : null;
}

function readBuilding(s: string): Found<string> | null {
  const m = /\b([a-z])\s?blok\w*/.exec(s) ?? /\b(?:block|building)\s+([a-z])\b/.exec(s) ?? /\b([a-z])\s+binasi\w*/.exec(s);
  return m ? { value: m[1]!.toLocaleUpperCase("tr-TR"), rest: cut(s, m) } : null;
}

const FEATURES: [RegExp, string][] = [
  [/projeksiyon|projektor|projector|beamer/, "projeksiyon"],
  [/bilgisayar|computer/, "bilgisayar"],
  [/akilli tahta|smart ?board/, "akıllı tahta"],
];

const DAY_PARTS: [RegExp, string, string][] = [
  [/\b(ogleden sonra|afternoon)\b/, "13:00", "17:00"],
  [/\b(sabah|morning)\b/, "08:00", "12:00"],
  [/\b(aksam|evening)\b/, "17:00", "21:00"],
];

const has = (s: string, re: RegExp) => re.test(s);

/**
 * One phrase → an action with partial arguments, or null (questions, unknown text: the search and the helper take
 * those). `now` is the reader's local time.
 */
export function parseIntent(text: string, now: Date = new Date()): Intent | null {
  const f = foldText(text);
  if (!f) return null;

  // actions with no arguments, and the hand-overs
  if (has(f, /\bgeri al\w*|\bundo\b/)) return { action: "undo_last_helper_action", args: {} };
  if (has(f, /\btakvim\w*|\bcalendar\b/)) return { action: "open_feature", args: { feature_id: "profile.calendar" } };
  if (has(f, /\bdavet\w*|\binvite\b/)) return { action: "open_feature", args: { feature_id: "admin.users.invite" } };
  if (has(f, /yapay zeka (hakk|kullan|kota|pay)|\bai usage\b|\bai (allowance|quota)\b|\btoken\w*|\bkotam\b/)) return { action: "my_ai_usage", args: {} };
  if (has(f, /\bbekleyen talep|\bonay bekleyen|\bonaylanacak|\bpending (approvals|requests)\b|\bapprovals? inbox\b|\bto approve\b/)) return { action: "approvals_inbox", args: {} };
  if (has(f, /\btaleplerim\w*|\btalebim\w*|\bmy requests?\b/)) return { action: "my_requests_status", args: {} };
  if (has(f, /\biptal\w*|\bcancel\b/) && has(f, /rezervasyon|booking/)) return { action: "cancel_my_booking", args: {} };
  if (has(f, /\brezervasyonlarim\w*|\bmy bookings\b/)) return { action: "my_bookings", args: { days: has(f, /\bbu hafta|\bthis week\b/) ? 7 : 0 } };

  // the slot readers, most specific first; each removes what it read
  let rest = ` ${f} `;
  const room = readRoom(rest);
  if (room) rest = room.rest;
  const head = readHeadcount(rest);
  if (head) rest = head.rest;
  const period = readPeriod(rest);
  if (period) rest = period.rest;
  const day = readDate(rest, now);
  if (day) rest = day.rest;
  const part = DAY_PARTS.find(([re]) => re.test(rest));
  const time = readTime(rest, part?.[1] === "13:00" || part?.[1] === "17:00");
  if (time) rest = time.rest;
  const building = readBuilding(rest);
  if (building) rest = building.rest;
  const feature = FEATURES.find(([re]) => re.test(f))?.[1];

  const booking = has(f, /\bayir\w*|\brezerv\w*|\bbook\b|\breserve\b|\blazim\b|\brezervasyon yap/);
  const finding = has(f, /\bbos\b|\bfree\b|\buygun\b|\bmusait\b|\bavailable\b|\bsalon bul|\bfind (a )?(free )?room|\broom for\b/) || !!head || !!feature || !!building;
  const roomDay = has(f, /\bdolu mu\b|\bbos mu\b|\bprogrami\b|\bschedule\b|\bis\b.*\bfree\b|\bne zaman bos/);

  // a bare hour ("yarın 10 a 204"), only with a day or a booking word and no other time
  let clock = time?.value.time;
  if (!clock && (day || booking)) {
    const m = /(?:^|\s)(\d{1,2})(?=\s|$)/.exec(rest);
    if (m && +m[1]! >= 7 && +m[1]! <= 21) clock = hhmm(+m[1]!) ?? undefined;
  }
  const hints: IntentHints = {};
  if (period) hints.period = period.value;

  if (room && roomDay) return { action: "room_day_schedule", args: { room: room.value, ...(day ? { date: day.value } : {}) } };
  if (room && (booking || day)) {
    if (clock) hints.time = clock;
    return { action: "create_booking", args: { room: room.value, ...(day ? { date: day.value } : {}) }, hints };
  }
  if (booking || finding) {
    const args: Record<string, string | number> = {};
    if (day) args.date = day.value;
    if (clock) args.start = clock;
    if (time?.value.until) args.end = time.value.until;
    else if (!clock && part) {
      args.start = part[1];
      args.end = part[2];
    }
    if (head) args.headcount = head.value;
    if (building) args.building = building.value;
    if (feature) args.text = feature;
    return { action: "find_free_rooms", args, hints };
  }
  return null;
}
