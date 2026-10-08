import { describe, expect, it } from "vitest";
import { ClassRow } from "@/lib/api/studio-schemas";
import { EMPTY_FILTERS, activeFilterCount, filterClasses, filterOptions, fold, quickCounts, type RowState } from "./class-filters";

const row = (over: Partial<ClassRow> & { id: number }): ClassRow =>
  ClassRow.parse({
    status: "PARSED",
    course_code: "MAT 112",
    course_name: "Matematik II",
    section_label: "1",
    program_id: 1,
    program_name: "İşletme",
    faculty_id: 6,
    faculty_name: "İİSBF",
    class_year: 1,
    day: 1,
    start_period: 2,
    end_period: 4,
    mode: "F2F",
    ...over,
  });

const rows: ClassRow[] = [
  row({ id: 1 }),
  row({ id: 2, course_code: "ECZ 101", course_name: "Farmasötik Kimya", program_id: 2, program_name: "Eczacılık", faculty_id: 2, faculty_name: "Eczacılık Fakültesi", class_year: 2, day: 3, requested_building: "C", requested_room_codes: ["C 301"] }),
  row({ id: 3, course_code: "HEM 334", program_id: 3, program_name: "Hemşirelik", faculty_id: 3, faculty_name: "Sağlık Bilimleri Fakültesi", class_years: [3, 4], class_year: 3, mode: "HYBRID", changed_fields: [{ field: "enrolment", imported: 58, current: 60 }], instructors: ["Doç. Dr. Pınar Güneş"] }),
  row({ id: 4, course_code: "ANS 101", program_id: 15, program_name: "Anestezi (İÖ)", is_evening: true, start_period: null, end_period: null, day: null, status: "NEEDS_REVIEW", definitive_room_codes: ["A 204"] }),
];
const state: RowState = { excluded: new Set([2]), pinned: new Set([3]) };

describe("class-table filters", () => {
  it("folds Turkish text (İ/ı, ş, ğ, ü …) for search", () => {
    expect(fold("İŞLETME")).toBe("isletme");
    expect(fold("Güneş")).toBe("gunes");
    expect(fold("ışık  Ç")).toBe("isik c");
  });

  it("filters by faculty, programme, year (incl. merged years), day, building and mode", () => {
    expect(filterClasses(rows, { ...EMPTY_FILTERS, faculty: 2 }, state).map((r) => r.id)).toEqual([2]);
    expect(filterClasses(rows, { ...EMPTY_FILTERS, program: 3 }, state).map((r) => r.id)).toEqual([3]);
    expect(filterClasses(rows, { ...EMPTY_FILTERS, year: 4 }, state).map((r) => r.id)).toEqual([3]);
    expect(filterClasses(rows, { ...EMPTY_FILTERS, day: 3 }, state).map((r) => r.id)).toEqual([2]);
    expect(filterClasses(rows, { ...EMPTY_FILTERS, building: "C" }, state).map((r) => r.id)).toEqual([2]);
    expect(filterClasses(rows, { ...EMPTY_FILTERS, building: "A" }, state).map((r) => r.id)).toEqual([4]);
    expect(filterClasses(rows, { ...EMPTY_FILTERS, mode: "hybrid" }, state).map((r) => r.id)).toEqual([3]);
  });

  it("filters changed rows and combines filters (all must match)", () => {
    expect(filterClasses(rows, { ...EMPTY_FILTERS, changed: true }, state).map((r) => r.id)).toEqual([3]);
    expect(filterClasses(rows, { ...EMPTY_FILTERS, changed: true, faculty: 2 }, state)).toHaveLength(0);
  });

  it("searches course, name, programme and instructor, diacritic-insensitive", () => {
    expect(filterClasses(rows, { ...EMPTY_FILTERS, q: "gunes" }, state).map((r) => r.id)).toEqual([3]);
    expect(filterClasses(rows, { ...EMPTY_FILTERS, q: "ECZACILIK kimya" }, state).map((r) => r.id)).toEqual([2]);
    expect(filterClasses(rows, { ...EMPTY_FILTERS, q: "isletme" }, state).map((r) => r.id)).toEqual([1]);
  });

  it("quick chips use the local draft (left out / pinned) and the row data", () => {
    expect(filterClasses(rows, { ...EMPTY_FILTERS, quick: "leftOut" }, state).map((r) => r.id)).toEqual([2]);
    expect(filterClasses(rows, { ...EMPTY_FILTERS, quick: "pinned" }, state).map((r) => r.id)).toEqual([3]);
    expect(filterClasses(rows, { ...EMPTY_FILTERS, quick: "noDayTime" }, state).map((r) => r.id)).toEqual([4]);
    expect(quickCounts(rows, state)).toEqual({ needsRoom: 4, changed: 1, pinned: 1, leftOut: 1, needsReview: 1, evening: 1, noDayTime: 1 });
  });

  it("filters classes matched by a rule (?rule=)", () => {
    const withRule = rows.map((r) => (r.id === 1 ? { ...r, rule_ids: [12] } : r));
    expect(filterClasses(withRule, { ...EMPTY_FILTERS, ruleId: 12 }, state).map((r) => r.id)).toEqual([1]);
  });

  it("counts active filters and lists only existing options", () => {
    expect(activeFilterCount(EMPTY_FILTERS)).toBe(0);
    expect(activeFilterCount({ ...EMPTY_FILTERS, q: " x ", day: 1, changed: true })).toBe(3);
    const o = filterOptions(rows);
    expect(o.years).toEqual([1, 2, 3, 4]);
    expect(o.buildings).toEqual(["A", "C"]);
    expect(o.modes).toEqual(["F2F", "HYBRID"]);
    expect(o.faculties.map((f) => f.id).sort()).toEqual([2, 3, 6]);
  });
});
