import { describe, expect, it } from "vitest";
import type { ClassRow } from "@/lib/api/classes";
import { EMPTY, activeFields, aggregate, applyFilters, clearField, defaultView, facetCounts, normalizeView, parsePastedColumn, parseTimeWindow, parseTokens, sameView, systemPredicate, type ClassFilters } from "./classes-model";

function row(p: Partial<ClassRow> & { id: number; course_code: string }): ClassRow {
  return {
    kind: "meeting",
    course_name: null,
    section: "1",
    faculty_id: 1,
    faculty_name: "Mühendislik ve Doğa Bilimleri Fakültesi",
    faculty_slot: 1,
    program_id: 10,
    program_name: "Bilgisayar Mühendisliği",
    is_evening: false,
    class_years: [2],
    instructors: [{ id: 1, name: "Ayşe Kaya" }],
    enrolment: 50,
    mode: "F2F",
    needs_room: true,
    merge_key: null,
    req: { day: 3, days: [3], date: null, start_period: 7, end_period: 9, weeks: [1, 2], room_text: null, room_ids: [], room_codes: [], building: null, tags: [], capacity: null, flexible_day: false, status: "LOCKED", warnings: [], notes: null, room_count: null },
    definitive: { text: null, room_ids: [], room_codes: [] },
    placement: { assignment_ids: [p.id * 10], day: 3, date: null, start_period: 7, end_period: 9, room_ids: [1], room_codes: ["A 204"], capacity: 156, weeks_placed: [1, 2], locked: false, origin: "SOLVER", matched: "request" },
    placement_status: "placed",
    issues: [],
    changed: [],
    provenance: { kind: "planning-list", row: p.id },
    updated_at: null,
    ...p,
  } as ClassRow;
}

const rows: ClassRow[] = [
  row({ id: 1, course_code: "BME 419" }),
  row({ id: 2, course_code: "ECZ 112", faculty_id: 5, faculty_name: "Eczacılık Fakültesi", program_id: 20, program_name: "Eczacılık (İÖ)", is_evening: true, class_years: [1], instructors: [{ id: 2, name: "Selin Arslan" }], placement: { assignment_ids: [20], day: 1, date: null, start_period: 13, end_period: 14, room_ids: [2], room_codes: ["B 204"], capacity: 64, weeks_placed: [1, 2], locked: true, origin: "MANUAL", matched: "request" } }),
  row({ id: 3, course_code: "ECZ 118", faculty_id: 5, faculty_name: "Eczacılık Fakültesi", program_id: 20, class_years: [1], placement: null, placement_status: "unplaced", issues: [{ code: "unplaced", severity: "hard", text: { tr: "Yerleşmedi", en: "Unplaced" }, weeks: [] }], req: { ...row({ id: 0, course_code: "x" }).req, day: 1, start_period: 13, end_period: 14, status: "NEEDS_REVIEW" } }),
  row({ id: 4, course_code: "PHAR 240", changed: [{ field: "room", source: "run", from: ["A 206"], to: ["D 106"] }], placement: { assignment_ids: [40], day: 2, date: null, start_period: 1, end_period: 3, room_ids: [9], room_codes: ["D 106"], capacity: 82, weeks_placed: [1], locked: false, origin: "IMPORT", matched: "board" }, issues: [{ code: "capacity", severity: "soft", text: { tr: "x", en: "x" }, weeks: [] }] }),
  row({ id: 5, course_code: "UZM 101", mode: "ONLINE", placement: null, placement_status: "no_room_needed" }),
];

const ctx = { faculties: [{ id: 1, name: "Mühendislik ve Doğa Bilimleri Fakültesi" }, { id: 5, name: "Eczacılık Fakültesi" }], programs: [{ id: 10, name: "Bilgisayar Mühendisliği" }, { id: 20, name: "Eczacılık (İÖ)" }], modes: ["F2F", "ONLINE", "HYBRID"] };

describe("filters", () => {
  it("faculty, day (placed vs requested), time window and flags combine", () => {
    const f: ClassFilters = { ...EMPTY, faculty: [5], day: [1] };
    expect(applyFilters(rows, f).map((r) => r.id)).toEqual([2]);
    expect(applyFilters(rows, { ...f, dayWhere: "requested" }).map((r) => r.id)).toEqual([3]); // ECZ 112 was requested on Wednesday
    expect(applyFilters(rows, { ...EMPTY, time: { from: 13, to: 18, mode: "overlap" } }).map((r) => r.id)).toEqual([2, 3]); // unplaced rows fall back to the requested time
    expect(applyFilters(rows, { ...EMPTY, time: { from: 7, to: 8, mode: "within" } }).map((r) => r.id)).toEqual([]);
    expect(applyFilters(rows, { ...EMPTY, locked: true }).map((r) => r.id)).toEqual([2]);
    expect(applyFilters(rows, { ...EMPTY, changed: true }).map((r) => r.id)).toEqual([4]);
    expect(applyFilters(rows, { ...EMPTY, issue: "hard" }).map((r) => r.id)).toEqual([3]);
    expect(applyFilters(rows, { ...EMPTY, building: ["D"] }).map((r) => r.id)).toEqual([4]);
  });
  it("free text is Turkish-aware and matches instructor and room", () => {
    expect(applyFilters(rows, { ...EMPTY, text: "phar240" }).map((r) => r.id)).toEqual([4]);
    expect(applyFilters(rows, { ...EMPTY, text: "selin" }).map((r) => r.id)).toEqual([2]);
    expect(applyFilters(rows, { ...EMPTY, text: "d106" }).map((r) => r.id)).toEqual([4]);
  });
  it("facet counts ignore their own field but respect the others", () => {
    const f: ClassFilters = { ...EMPTY, faculty: [5], day: [1] };
    expect(Object.fromEntries(facetCounts(rows, f, "day"))).toEqual({ "1": 1 });
    expect(Object.fromEntries(facetCounts(rows, f, "faculty"))).toEqual({ "5": 1 });
    expect(facetCounts(rows, EMPTY, "status").get("pl:unplaced")).toBe(1);
  });
  it("active fields and clearing one field", () => {
    const f: ClassFilters = { ...EMPTY, faculty: [5], placement: ["unplaced"], locked: false };
    expect(activeFields(f)).toEqual(["faculty", "status", "locked"]);
    expect(activeFields(clearField(f, "status"))).toEqual(["faculty", "locked"]);
  });
});

describe("token search", () => {
  it("turns tokens into filters and keeps the rest as text", () => {
    const r = parseTokens("fak:ecz gün:pzt saat:13:30-17:30 yerleşmedi kaya", EMPTY, ctx);
    expect(r.filters.faculty).toEqual([5]);
    expect(r.filters.day).toEqual([1]);
    expect(r.filters.time).toEqual({ from: 7, to: 11, mode: "overlap" });
    expect(r.filters.placement).toEqual(["unplaced"]);
    expect(r.rest).toBe("kaya");
    expect(r.consumed).toHaveLength(4);
  });
  it("English aliases and unknown values stay as text", () => {
    const r = parseTokens("fac:xyz day:wed locked sınıf:1,2 mode:onl", EMPTY, ctx);
    expect(r.filters.day).toEqual([3]);
    expect(r.filters.locked).toBe(true);
    expect(r.filters.year).toEqual([1, 2]);
    expect(r.filters.mode).toEqual(["ONLINE"]);
    expect(r.rest).toBe("fac:xyz");
  });
  it("time windows snap to period starts / ends", () => {
    expect(parseTimeWindow("17:30-")).toEqual({ from: 12, to: 18 });
    expect(parseTimeWindow("abc")).toBeNull();
  });
});

describe("system views", () => {
  const tip = new Set(["A 201"]);
  it("each view selects the right rows", () => {
    const pick = (v: Parameters<typeof systemPredicate>[0]) => rows.filter(systemPredicate(v, tip)).map((r) => r.id);
    expect(pick("all")).toEqual([1, 2, 3, 4, 5]);
    expect(pick("unplaced")).toEqual([3]);
    expect(pick("issues")).toEqual([3, 4]);
    expect(pick("changed")).toEqual([4]);
    expect(pick("evening")).toEqual([2, 3]); // unplaced 18:00 request counts as evening
    expect(pick("noRoom")).toEqual([5]);
    expect(pick("review")).toEqual([3]);
    expect(pick("tip")).toEqual([]);
  });
  it("aggregates count placed among rows that need a room", () => {
    expect(aggregate(rows)).toEqual({ n: 5, students: 250, placedPct: 75, issues: 2 });
  });
});

describe("saved views", () => {
  it("modified detection is key-order independent", () => {
    const a = defaultView();
    const b = JSON.parse(JSON.stringify({ ...a, filters: { ...a.filters } }));
    expect(sameView(a, b)).toBe(true);
    expect(sameView(a, { ...a, density: "compact" })).toBe(false);
  });
  it("normalises partial / old server state onto the defaults", () => {
    const v = normalizeView({ filters: { faculty: [5] }, columns: ["course", "bogus"] } as never);
    expect(v.filters.faculty).toEqual([5]);
    expect(v.filters.day).toEqual([]);
    expect(v.columns).toEqual(["course"]);
    expect(v.group).toBe("faculty");
  });
  it("parses a pasted Excel column (Turkish thousands, blanks)", () => {
    expect(parsePastedColumn("102\n1.204\n\n58\r\n")).toEqual([102, 1204, null, 58]);
  });
});
