/** Small, fully known calendar index for unit tests and component tests (mirrors tests/test_api_calendar.py). */
import type { CalendarIndex, IndexAssignment } from "@/lib/api/calendar";

const ALL = Array.from({ length: 14 }, (_, i) => i + 1);

export function assignment(p: Partial<IndexAssignment> & Pick<IndexAssignment, "id" | "label" | "day" | "sp" | "ep" | "rooms">): IndexAssignment {
  return {
    mr: p.id + 1000,
    ex: null,
    code: p.label.split(" §")[0],
    name: null,
    sec: "1",
    prog: "Bilgisayar Mühendisliği",
    prog_id: 1,
    fac: 1,
    slot: 1,
    year: 2,
    evening: false,
    instr: [],
    instr_ids: [],
    size: 50,
    cap: null,
    weeks: ALL,
    date: null,
    locked: false,
    origin: "SOLVER",
    reasons: [],
    tags: [],
    needs_pc: false,
    ...p,
  };
}

export function fixtureIndex(extra: IndexAssignment[] = []): CalendarIndex {
  return {
    run: { id: 42, term_id: 1, kind: "COURSE", status: "FEASIBLE", label: null, horizon: "TERM", weeks: [], is_active: false, origin_import: false },
    rooms: [
      { id: 1, code: "A204", name: "A 204", building: "A", capacity: 156, exam_capacity: 74, tags: [], bookable: true, photo_url: null },
      { id: 2, code: "A101", name: "A 101", building: "A", capacity: 58, exam_capacity: 30, tags: [], bookable: true, photo_url: null },
      { id: 3, code: "A104", name: "A 104", building: "A", capacity: 41, exam_capacity: 41, tags: ["PC"], bookable: true, photo_url: null },
      { id: 4, code: "C201", name: "C 201", building: "C", capacity: 126, exam_capacity: 60, tags: [], bookable: true, photo_url: null },
      { id: 5, code: "C202", name: "C 202", building: "C", capacity: 72, exam_capacity: 35, tags: [], bookable: true, photo_url: null },
    ],
    weeks: ALL.map((i) => ({ index: i, start_date: addWeeks("2026-02-02", i - 1), kind: "LECTURE", label: `H${i}` })),
    periods: [],
    faculties: [{ id: 1, name: "Mühendislik ve Doğa Bilimleri Fakültesi", slot: 1 }],
    assignments: [
      assignment({ id: 1, label: "BME 419 §1", day: 3, sp: 7, ep: 9, rooms: [1], size: 102, instr: ["Ayşe Kaya"], instr_ids: [10] }),
      assignment({ id: 2, label: "ENG 102 §1", day: 3, sp: 8, ep: 9, rooms: [2], size: 50, instr: ["Can Demir"], instr_ids: [11], year: 1 }),
      assignment({ id: 3, label: "CSE 225 §1", day: 2, sp: 3, ep: 4, rooms: [3], size: 40, instr: ["Can Demir"], instr_ids: [11], needs_pc: true, locked: true }),
      ...extra,
    ],
    blocks: [{ id: 7, room: 5, day: 3, sp: 7, ep: 9, weeks: ALL, label: "HAZIRLIK", source: "GRID_IMPORT" }],
    bookings: [],
    unplaced: [],
    bookings_enabled: true,
    today: "2026-03-18",
  };
}

function addWeeks(isoDate: string, n: number): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n * 7)).toISOString().slice(0, 10);
}
