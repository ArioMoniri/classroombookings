/**
 * HX-01 (helper.md §4.5): the deterministic shortcuts. Common TR / EN phrasings → one registry action with partial
 * arguments the server accepts (`GET /helper/schema` args), plus hints the client resolves itself (a clock time or
 * an "N. saat" → the booking period). No AI.
 */
import { describe, expect, it } from "vitest";
import { foldText, parseDate, parseIntent, parseRoom, parseTime, type Intent } from "./intents";

// Sunday 18 October 2026, 09:00 local
const NOW = new Date(2026, 9, 18, 9, 0);
const p = (text: string) => parseIntent(text, NOW);
const stable = (o: object) => JSON.stringify(Object.entries(o).sort(([a], [b]) => a.localeCompare(b)));

type Case = [string, Partial<Intent> & { action: Intent["action"] }];

const CASES: Case[] = [
  // create_booking (room + day, optional time)
  ["yarın 10 a 204", { action: "create_booking", args: { room: "A 204", date: "2026-10-19" }, hints: { time: "10:00" } }],
  ["Yarın 10:00 için A 204'ü ayır", { action: "create_booking", args: { room: "A 204", date: "2026-10-19" }, hints: { time: "10:00" } }],
  ["A204'ü yarın saat 14'te rezerve et", { action: "create_booking", args: { room: "A 204", date: "2026-10-19" }, hints: { time: "14:00" } }],
  ["bu odayı yarın 10:00 için rezerve et", { action: "find_free_rooms", args: { date: "2026-10-19", start: "10:00" } }],
  ["perşembe 3. saat B 105 ayır", { action: "create_booking", args: { room: "B 105", date: "2026-10-22" }, hints: { period: 3 } }],
  ["PERŞEMBE 3. DERS SAATİ B105 REZERVE ET", { action: "create_booking", args: { room: "B 105", date: "2026-10-22" }, hints: { period: 3 } }],
  ["book A 204 tomorrow at 10am", { action: "create_booking", args: { room: "A 204", date: "2026-10-19" }, hints: { time: "10:00" } }],
  ["Book room C-12 on Friday at 2 pm", { action: "create_booking", args: { room: "C 12", date: "2026-10-23" }, hints: { time: "14:00" } }],
  ["reserve A 204 on 12 November", { action: "create_booking", args: { room: "A 204", date: "2026-11-12" } }],
  ["12 Kasım'da A 204'ü ayır", { action: "create_booking", args: { room: "A 204", date: "2026-11-12" } }],
  ["A 204 bugün 15.30 ayır", { action: "create_booking", args: { room: "A 204", date: "2026-10-18" }, hints: { time: "15:30" } }],
  ["salı A 204 rezervasyon yap", { action: "create_booking", args: { room: "A 204", date: "2026-10-20" } }],
  ["A 204 ayır", { action: "create_booking", args: { room: "A 204" } }],
  ["yarından sonra a 204 ayır", { action: "create_booking", args: { room: "A 204", date: "2026-10-20" } }],
  ["öbür gün A 204 rezerve", { action: "create_booking", args: { room: "A 204", date: "2026-10-20" } }],
  ["book A 204 the day after tomorrow", { action: "create_booking", args: { room: "A 204", date: "2026-10-20" } }],
  ["A 204'ü 2026-11-03 tarihinde ayır", { action: "create_booking", args: { room: "A 204", date: "2026-11-03" } }],
  ["A 204 3/11 ayır", { action: "create_booking", args: { room: "A 204", date: "2026-11-03" } }],
  ["A 204 3.11 ayır", { action: "create_booking", args: { room: "A 204", date: "2026-11-03" } }],
  ["gelecek pazartesi A 204 ayır", { action: "create_booking", args: { room: "A 204", date: "2026-10-26" } }],
  ["next monday book A 204", { action: "create_booking", args: { room: "A 204", date: "2026-10-26" } }],
  ["haftaya çarşamba a 204 ayır", { action: "create_booking", args: { room: "A 204", date: "2026-10-28" } }],
  ["A 204 period 4 tomorrow book", { action: "create_booking", args: { room: "A 204", date: "2026-10-19" }, hints: { period: 4 } }],
  ["book A 204 3rd period on Thursday", { action: "create_booking", args: { room: "A 204", date: "2026-10-22" }, hints: { period: 3 } }],
  ["yarın 10'da A 204 lazım", { action: "create_booking", args: { room: "A 204", date: "2026-10-19" }, hints: { time: "10:00" } }],
  ["İNGİLİZCE SINAVI İÇİN YARIN A 204 AYIR", { action: "create_booking", args: { room: "A 204", date: "2026-10-19" } }],
  // find_free_rooms
  ["perşembe öğleden sonra 12 kişilik", { action: "find_free_rooms", args: { date: "2026-10-22", start: "13:00", end: "17:00", headcount: 12 } }],
  ["boş salon 12 kişi", { action: "find_free_rooms", args: { headcount: 12 } }],
  ["yarın 10'da boş bir salon var mı?", { action: "find_free_rooms", args: { date: "2026-10-19", start: "10:00" } }],
  ["Yarın için boş bir salon bul", { action: "find_free_rooms", args: { date: "2026-10-19" } }],
  ["Perşembe 14:00'te 12 kişilik projeksiyonlu salon", { action: "find_free_rooms", args: { date: "2026-10-22", start: "14:00", headcount: 12, text: "projeksiyon" } }],
  ["12 kişilik projeksiyonlu salon, perşembe öğleden sonra", { action: "find_free_rooms", args: { date: "2026-10-22", start: "13:00", end: "17:00", headcount: 12, text: "projeksiyon" } }],
  ["free room tomorrow at 10", { action: "find_free_rooms", args: { date: "2026-10-19", start: "10:00" } }],
  ["find a free room for 30 people on Friday afternoon", { action: "find_free_rooms", args: { date: "2026-10-23", start: "13:00", end: "17:00", headcount: 30 } }],
  ["room for 20 with a projector tomorrow morning", { action: "find_free_rooms", args: { date: "2026-10-19", start: "08:00", end: "12:00", headcount: 20, text: "projeksiyon" } }],
  ["müsait derslik bugün 3. saat", { action: "find_free_rooms", args: { date: "2026-10-18" }, hints: { period: 3 } }],
  ["B blokta boş amfi yarın", { action: "find_free_rooms", args: { date: "2026-10-19", building: "B" } }],
  ["uygun salon var mı cuma sabah 40 kişi", { action: "find_free_rooms", args: { date: "2026-10-23", start: "08:00", end: "12:00", headcount: 40 } }],
  ["bilgisayarlı lab yarın 25 kişilik", { action: "find_free_rooms", args: { date: "2026-10-19", headcount: 25, text: "bilgisayar" } }],
  ["salon ayır yarın 10", { action: "find_free_rooms", args: { date: "2026-10-19", start: "10:00" } }],
  ["available rooms in block C today", { action: "find_free_rooms", args: { date: "2026-10-18", building: "C" } }],
  ["14:00-16:00 arası boş salon", { action: "find_free_rooms", args: { start: "14:00", end: "16:00" } }],
  // room_day_schedule
  ["A 204 yarın dolu mu?", { action: "room_day_schedule", args: { room: "A 204", date: "2026-10-19" } }],
  ["A 204 bugün boş mu", { action: "room_day_schedule", args: { room: "A 204", date: "2026-10-18" } }],
  ["is A 204 free tomorrow?", { action: "room_day_schedule", args: { room: "A 204", date: "2026-10-19" } }],
  ["A 204 programı perşembe", { action: "room_day_schedule", args: { room: "A 204", date: "2026-10-22" } }],
  ["schedule of room B 12 on monday", { action: "room_day_schedule", args: { room: "B 12", date: "2026-10-19" } }],
  // my_bookings / cancel
  ["Bu haftaki rezervasyonlarım", { action: "my_bookings", args: { days: 7 } }],
  ["rezervasyonlarım", { action: "my_bookings", args: { days: 0 } }],
  ["my bookings", { action: "my_bookings", args: { days: 0 } }],
  ["Perşembe rezervasyonumu iptal et", { action: "cancel_my_booking", args: {} }],
  ["cancel my booking", { action: "cancel_my_booking", args: {} }],
  // requests / approvals
  ["Taleplerim ne durumda?", { action: "my_requests_status", args: {} }],
  ["my requests", { action: "my_requests_status", args: {} }],
  ["Bekleyen taleplerim", { action: "approvals_inbox", args: {} }],
  ["Bana bekleyen talep var mı?", { action: "approvals_inbox", args: {} }],
  ["pending approvals", { action: "approvals_inbox", args: {} }],
  // usage / undo
  ["Ne kadar yapay zekâ hakkım kaldı?", { action: "my_ai_usage", args: {} }],
  ["my ai usage", { action: "my_ai_usage", args: {} }],
  ["Son yaptığımı geri al", { action: "undo_last_helper_action", args: {} }],
  ["undo my last action", { action: "undo_last_helper_action", args: {} }],
  // hand-overs (nav)
  ["takvim", { action: "open_feature", args: { feature_id: "profile.calendar" } }],
  ["Derslerimi takvimime ekle", { action: "open_feature", args: { feature_id: "profile.calendar" } }],
  ["add to my calendar", { action: "open_feature", args: { feature_id: "profile.calendar" } }],
  ["davet", { action: "open_feature", args: { feature_id: "admin.users.invite" } }],
  ["Ayşe'yi öğretim elemanı olarak davet et", { action: "open_feature", args: { feature_id: "admin.users.invite" } }],
  ["invite a user", { action: "open_feature", args: { feature_id: "admin.users.invite" } }],
];

const NONE = ["Tatil nasıl eklenir?", "CRBS'teki 'Periods' nerede?", "merhaba", "", "   ", "MAT 112'yi salıya taşı", "periods", "ders saatleri", "Planı yayınla"];

describe("intents", () => {
  it(`reads ${CASES.length} TR/EN phrasings`, () => {
    expect(CASES.length).toBeGreaterThanOrEqual(60);
    const wrong: string[] = [];
    for (const [text, want] of CASES) {
      const got = p(text);
      const ok =
        got?.action === want.action &&
        stable(got.args) === stable(want.args ?? {}) &&
        stable(got.hints ?? {}) === stable(want.hints ?? {});
      if (!ok) wrong.push(`${text}\n   got  ${JSON.stringify(got)}\n   want ${JSON.stringify(want)}`);
    }
    expect(wrong).toEqual([]);
  });

  it("leaves questions and unknown text to the search and the helper", () => {
    for (const text of NONE) expect(p(text), text).toBeNull();
  });

  it("folds Turkish İ/ı and diacritics, keeping word breaks", () => {
    expect(foldText("İPTAL ŞUBE Işık")).toBe("iptal sube isik");
    expect(foldText("PERŞEMBE  öğleden")).toBe("persembe ogleden");
  });

  it("parses dates, times and room codes on their own", () => {
    expect(parseDate("yarın", NOW)).toBe("2026-10-19");
    expect(parseDate("pazar", NOW)).toBe("2026-10-18");
    expect(parseDate("31 aralık", NOW)).toBe("2026-12-31");
    expect(parseDate("5 ocak", NOW)).toBe("2027-01-05");
    expect(parseDate("31 şubat", NOW)).toBeNull();
    expect(parseTime("saat 9")).toEqual({ time: "09:00" });
    expect(parseTime("09:15")).toEqual({ time: "09:15" });
    expect(parseTime("25:00")).toEqual({});
    expect(parseRoom("a204'te")).toBe("A 204");
    expect(parseRoom("BME 419")).toBeNull();
  });

  it("only produces argument names the server accepts (extra=forbid)", () => {
    const allowed: Record<string, string[]> = {
      create_booking: ["room", "date", "period_id", "notes"],
      find_free_rooms: ["date", "start", "end", "headcount", "building", "text"],
      room_day_schedule: ["room", "date"],
      my_bookings: ["days"],
      open_feature: ["feature_id"],
    };
    for (const [text] of CASES) {
      const got = p(text)!;
      for (const k of Object.keys(got.args)) expect(allowed[got.action] ?? [], `${text}: ${k}`).toContain(k);
    }
  });
});
