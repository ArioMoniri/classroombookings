/**
 * Live conflict preview (calendar.md §9.2): a pure, < 1 ms check of one target slot against the index,
 * mirroring the server's rules in app/services/calendar_views.py `check_candidate` (same codes, same
 * TR/EN sentences), so the preview and the committed result agree.
 */
import { PERIODS, PERIODS_PER_DAY } from "@/lib/time";
import type { Text2 } from "@/lib/api/calendar";
import { roomCap, type CalEvent, type CalendarModel, type WeekMask } from "./index-model";

export type Severity = "hard" | "soft";
export interface CheckIssue {
  code: string;
  severity: Severity;
  text: Text2;
  withKey?: string;
  withAid?: number;
}

export interface MoveTarget {
  room: number;
  day: number;
  sp: number;
  ep: number;
  /** weeks the move applies to (mask); defaults to the moving event's weeks */
  mask?: WeekMask;
}

export interface CheckResult {
  ok: boolean;
  hard: CheckIssue[];
  soft: CheckIssue[];
  /** chip keys to ring red while hovering (culprits) */
  culprits: string[];
}

const DAY_TR = ["", "Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];
const DAY_EN = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function spanText(sp: number, ep: number): string {
  const a = PERIODS[Math.min(PERIODS_PER_DAY, Math.max(1, sp)) - 1];
  const b = PERIODS[Math.min(PERIODS_PER_DAY, Math.max(1, ep)) - 1];
  return `${a.start}–${b.end}`;
}

export function whenText(day: number, sp: number, ep: number): Text2 {
  return { tr: `${DAY_TR[day] ?? day} ${spanText(sp, ep)}`, en: `${DAY_EN[day] ?? day} ${spanText(sp, ep)}` };
}

const overlap = (a0: number, a1: number, b0: number, b1: number) => a0 <= b1 && b0 <= a1;

/**
 * Check placing the assignment(s) of `moving` (all rooms of one assignment move together to `target.room`
 * for single-room classes) at `target`. `ignore` = assignment ids that move in the same gesture.
 */
export function checkMove(model: CalendarModel, moving: CalEvent, target: MoveTarget, ignore: ReadonlySet<number> = new Set()): CheckResult {
  const hard: CheckIssue[] = [];
  const soft: CheckIssue[] = [];
  const culprits: string[] = [];
  const a = moving.a;
  const mask = target.mask ?? moving.mask;
  const self = new Set<number>([a.id, ...ignore]);
  if (target.sp < 1 || target.ep > PERIODS_PER_DAY || target.sp > target.ep || target.day < 1 || target.day > 7) {
    hard.push({ code: "out_of_range", severity: "hard", text: { tr: "Ders saati 08:30–22:50 aralığının dışına taşıyor", en: "The span leaves the 08:30–22:50 day" } });
    return { ok: false, hard, soft, culprits };
  }
  const room = model.roomById.get(target.room);
  if (!room) {
    hard.push({ code: "unknown_room", severity: "hard", text: { tr: "Bilinmeyen derslik", en: "Unknown room" } });
    return { ok: false, hard, soft, culprits };
  }
  const code = room.name;
  if (!room.bookable) hard.push({ code: "not_bookable", severity: "hard", text: { tr: `${code} kullanıma kapalı`, en: `${code} is not bookable` } });
  if (room.tags.includes("TIP") && !a.rooms.includes(room.id) && !a.tags.includes("TIP")) {
    soft.push({ code: "tip", severity: "soft", text: { tr: `${code} TIP dersliği (tıp eğitimine ayrılmış)`, en: `${code} is a TIP room (reserved for medical teaching)` } });
  }
  if (a.needs_pc && !room.tags.includes("PC")) {
    hard.push({ code: "pc", severity: "hard", text: { tr: `Bu ders bilgisayar laboratuvarı istiyor; ${code} PC dersliği değil`, en: `This class needs a computer lab; ${code} is not a PC room` } });
  }
  for (const b of model.blocksByRoomDay.get(`${room.id}:${target.day}`) ?? []) {
    if ((b.mask & mask) === 0 || !overlap(target.sp, target.ep, b.sp, b.ep)) continue;
    const w = whenText(target.day, b.sp, b.ep);
    hard.push({ code: "block", severity: "hard", withKey: b.key, text: { tr: `${code} önceden dolu: ${b.b.label} (${w.tr})`, en: `${code} is pre-occupied: ${b.b.label} (${w.en})` } });
    culprits.push(b.key);
    break;
  }
  for (const bk of model.bookingsByRoomDay.get(`${room.id}:${target.day}`) ?? []) {
    if ((bk.mask & mask) === 0 || !overlap(target.sp, target.ep, bk.sp, bk.ep)) continue;
    hard.push({ code: "booking", severity: "hard", withKey: bk.key, text: { tr: `${code} rezerve edilmiş: ${bk.bk.title}`, en: `${code} is booked: ${bk.bk.title}` } });
    culprits.push(bk.key);
    break;
  }
  const cap = roomCap(model, room);
  if (a.size && cap < a.size) {
    soft.push({
      code: "capacity",
      severity: "soft",
      text: model.exam
        ? { tr: `${code}: ${cap} sınav koltuğu, bu sınav ${a.size} öğrenci`, en: `${code}: ${cap} exam seats, this exam has ${a.size} students` }
        : { tr: `${code}: ${cap} koltuk, bu ders ${a.size} öğrenci`, en: `${code}: ${cap} seats, this class has ${a.size} students` },
    });
  }
  let seatLoad = 0;
  for (const o of model.byRoomDay.get(`${room.id}:${target.day}`) ?? []) {
    if (self.has(o.a.id) || (o.mask & mask) === 0 || !overlap(target.sp, target.ep, o.sp, o.ep)) continue;
    if (model.exam) {
      seatLoad += o.a.size;
      continue;
    }
    const w = whenText(o.day, o.sp, o.ep);
    hard.push({ code: "room_overlap", severity: "hard", withKey: o.key, withAid: o.a.id, text: { tr: `${o.a.label} ile çakışıyor (${code} ${w.tr})`, en: `Clashes with ${o.a.label} (${code} ${w.en})` } });
    culprits.push(o.key);
  }
  if (model.exam && seatLoad && seatLoad + a.size > cap) {
    hard.push({ code: "seats", severity: "hard", text: { tr: `${code} sınav kapasitesi aşılıyor: ${seatLoad + a.size} > ${cap}`, en: `${code} exam seats exceeded: ${seatLoad + a.size} > ${cap}` } });
  }
  const seen = new Set<number>();
  a.instr_ids.forEach((iid, i) => {
    for (const o of model.byInstructorDay.get(`${iid}:${target.day}`) ?? []) {
      if (self.has(o.a.id) || seen.has(o.a.id) || (o.mask & mask) === 0 || !overlap(target.sp, target.ep, o.sp, o.ep)) continue;
      seen.add(o.a.id);
      const name = a.instr[i] ?? "?";
      const w = whenText(o.day, o.sp, o.ep);
      hard.push({ code: "instructor", severity: "hard", withKey: o.key, withAid: o.a.id, text: { tr: `${name} aynı saatte ${o.a.label} dersinde (${w.tr})`, en: `${name} teaches ${o.a.label} at the same time (${w.en})` } });
      culprits.push(o.key);
    }
  });
  if (moving.cohort) {
    for (const o of model.byCohortDay.get(`${moving.cohort}:${target.day}`) ?? []) {
      if (self.has(o.a.id) || seen.has(o.a.id) || (o.mask & mask) === 0 || !overlap(target.sp, target.ep, o.sp, o.ep)) continue;
      if (o.a.code && o.a.code === a.code) continue; // parallel sections of one course are different student groups
      seen.add(o.a.id);
      hard.push({ code: "cohort", severity: "hard", withKey: o.key, withAid: o.a.id, text: { tr: `${a.prog ?? ""} ${a.year}. sınıf aynı saatte ${o.a.label} dersinde`, en: `${a.prog ?? ""} year ${a.year} has ${o.a.label} at the same time` } });
      culprits.push(o.key);
    }
  }
  if (a.locked) soft.push({ code: "locked", severity: "soft", text: { tr: "Kilitli ders: taşıma kilidi korur", en: "Locked class: the move keeps it locked" } });
  if (target.sp <= 12 && target.ep >= 12 && target.ep > target.sp) {
    soft.push({ code: "p12", severity: "soft", text: { tr: "Aralık 17:30–18:00 geçiş saatini içeriyor", en: "The span includes the 17:30–18:00 transition (P12)" } });
  }
  return { ok: hard.length === 0, hard, soft, culprits };
}

/** Summary capsule for a multi-move: "6 ders · 5 uygun · 1 çakışma". */
export function multiSummary(results: CheckResult[]): { total: number; ok: number; bad: number } {
  const ok = results.filter((r) => r.ok).length;
  return { total: results.length, ok, bad: results.length - ok };
}

/** Is a slot free for quick-create (no event, block or booking in the given weeks)? */
export function slotFree(model: CalendarModel, room: number, day: number, sp: number, ep: number, mask: WeekMask): boolean {
  const key = `${room}:${day}`;
  const hit = <T extends { sp: number; ep: number; mask: WeekMask }>(list: T[] | undefined) => (list ?? []).some((x) => (x.mask & mask) !== 0 && overlap(sp, ep, x.sp, x.ep));
  return !hit(model.byRoomDay.get(key)) && !hit(model.blocksByRoomDay.get(key)) && !hit(model.bookingsByRoomDay.get(key));
}
