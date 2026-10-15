/**
 * iCalendar (RFC 5545) export of the calendar's subject — a room, an instructor or a cohort — built from the
 * loaded run index (calendar follow-up ".ics export per subject"). One VEVENT per dated occurrence (week ×
 * day), so holidays and week-limited classes are exact without RRULE/EXDATE. Clock times are the periods' local
 * times in Istanbul, which has been UTC+3 all year since 2016, written as UTC.
 */
import { PERIODS } from "@/lib/time";
import { dateOf } from "./dates";
import { weeksOfMask, type CalEvent, type CalendarModel } from "./index-model";

const TZ_OFFSET_MIN = 180; // Europe/Istanbul, no DST

export function icsEscape(text: string): string {
  return text.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

/** Fold to ≤ 75 octets per line (continuation lines start with one space). */
function fold(line: string): string[] {
  const enc = new TextEncoder();
  if (enc.encode(line).length <= 75) return [line];
  const out: string[] = [];
  let cur = "";
  for (const ch of line) {
    const limit = out.length === 0 ? 75 : 74; // the leading space counts on continuation lines
    if (enc.encode(cur + ch).length > limit) {
      out.push(out.length === 0 ? cur : ` ${cur}`);
      cur = ch;
    } else cur += ch;
  }
  out.push(out.length === 0 ? cur : ` ${cur}`);
  return out;
}

/** "2026-02-04" + "13:30" (Istanbul) → "20260204T103000Z" */
function utcStamp(isoDate: string, hhmm: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  const [hh, mm] = hhmm.split(":").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d, hh, mm) - TZ_OFFSET_MIN * 60_000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${t.getUTCFullYear()}${p(t.getUTCMonth() + 1)}${p(t.getUTCDate())}T${p(t.getUTCHours())}${p(t.getUTCMinutes())}00Z`;
}

export function buildIcs(model: CalendarModel, keep: (e: CalEvent) => boolean, opts: { title: string; stamp: string }): string {
  const lines: string[] = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SmartSched//Timetable//TR", "CALSCALE:GREGORIAN", "METHOD:PUBLISH", `X-WR-CALNAME:${icsEscape(opts.title)}`, "X-WR-TIMEZONE:Europe/Istanbul"];
  const runId = model.index.run.id;
  for (const e of model.events) {
    if (!keep(e)) continue;
    const start = PERIODS[e.sp - 1]?.start;
    const end = PERIODS[e.ep - 1]?.end;
    if (!start || !end) continue;
    const room = model.roomById.get(e.room);
    for (const w of weeksOfMask(e.mask)) {
      const date = dateOf(model.index.weeks, w, e.day);
      if (!date) continue;
      lines.push(
        "BEGIN:VEVENT",
        `UID:smartsched-${runId}-${e.a.id}-${e.room}-${date.replace(/-/g, "")}@smartsched`,
        `DTSTAMP:${opts.stamp}`,
        `DTSTART:${utcStamp(date, start)}`,
        `DTEND:${utcStamp(date, end)}`,
        `SUMMARY:${icsEscape(e.a.label)}`,
        ...(room ? [`LOCATION:${icsEscape(room.name)}`] : []),
        ...(e.a.instr.length ? [`DESCRIPTION:${icsEscape(e.a.instr.join(", "))}`] : []),
        "END:VEVENT",
      );
    }
  }
  lines.push("END:VCALENDAR");
  return `${lines.flatMap(fold).join("\r\n")}\r\n`;
}

/** "20261015T120000Z" for DTSTAMP */
export function icsNow(d: Date = new Date()): string {
  return `${d.toISOString().slice(0, 19).replace(/[-:]/g, "")}Z`;
}
