import { describe, expect, it } from "vitest";
import type { Room } from "@/lib/api/schemas";
import { mergeIds } from "./use-wizard";
import {
  MBG_ENROLMENT,
  MBG_TSV,
  canGenerate,
  coursesFromPaste,
  fittingRooms,
  hashes,
  newCourse,
  newDraft,
  normalizeCode,
  parseNumber,
  parseStep,
  parseTsv,
  patternBody,
  patternHours,
  patternOptions,
  planSync,
  stepStatus,
  summary,
  validate,
  type Draft,
} from "./wizard-model";

/** room_master.csv shapes (spec §4.6): A 207 (120), C 201 (126), A 203 (148), A 204 (156), C 504 (40), D 106 (82), a lab */
const room = (code: string, capacity: number, tags: string[] = [], bookable = true): Room => ({ id: capacity * 10 + code.length, building_id: 1, building_code: code[0]!, code: code.replace(" ", ""), display_name: code, floor: 1, capacity, exam_capacity: capacity, tags: tags as Room["tags"], is_bookable: bookable });
const ROOMS = [room("A 207", 120), room("C 201", 126), room("A 203", 148), room("A 204", 156), room("C 504", 40), room("D 106", 82), room("B 501", 0, [], false), room("B 105", 30, ["LAB"])];

function mbg(): Draft {
  const d = newDraft("2026-10-15T00:00:00Z");
  d.termId = 7;
  d.termCode = "2026-GUZ";
  d.program = { ...d.program, name: "Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans", facultyName: "Fen Bilimleri Enstitüsü", prefix: "MBG" };
  d.courses = coursesFromPaste(parseTsv(MBG_TSV).rows, MBG_ENROLMENT);
  return d;
}

describe("program wizard model", () => {
  it("parses the step with term as the default", () => {
    expect(parseStep("patterns")).toBe("patterns");
    expect(parseStep("x")).toBe("term");
  });

  it("normalises course codes on blur and refuses Turkish letters", () => {
    expect(normalizeCode("MBG532")).toEqual({ code: "MBG 532", info: true, error: null });
    expect(normalizeCode("mbg 532")).toEqual({ code: "MBG 532", info: true, error: null });
    expect(normalizeCode("MBG 532")).toEqual({ code: "MBG 532", info: false, error: null });
    expect(normalizeCode("MBĞ 532").error).toBe("turkish");
    expect(normalizeCode("").error).toBe("empty");
    expect(normalizeCode("Seminer").error).toBe("shape");
  });

  it("reads comma decimals and flags non-numbers", () => {
    expect(parseNumber("4,5")).toBe(4.5);
    expect(parseNumber("")).toBeNull();
    expect(Number.isNaN(parseNumber("abc"))).toBe(true);
  });

  it("parses the MBG Tezli YL TSV paste: header skipped, 7 courses, MBG532 corrected", () => {
    const out = parseTsv(MBG_TSV);
    expect(out.rows).toHaveLength(7);
    expect(out.ignored).toEqual([1]);
    expect(out.rows[1]).toMatchObject({ code: "MBG532", name: "Epigenetik", t: 3, u: 0, l: 0, ects: 9, year: 1 });
    const courses = coursesFromPaste(out.rows, MBG_ENROLMENT);
    expect(courses.map((c) => c.code)).toEqual(["MBG 598", "MBG 532", "MBG 534", "MBG 546", "MBG 502", "MBG 541", "MBG 549"]);
    // the seminar is entered as 0+0+0 in the source and meets 1 period a week (Bahar R182)
    expect(courses[0]).toMatchObject({ t: 0, pattern: { weeklyHours: 1 } });
    expect(courses[0]!.sections[0]!.enrolment).toBe(120);
    expect(courses[1]!.pattern.theoryBlocks).toEqual([3]);
  });

  it("parses a headerless paste with empty lines", () => {
    const out = parseTsv("BIO 101\tBiyoloji\t2\t2\t0\t3\t5\t1\n\nBIO 102\tKimya\t3\t0\t2\t4\t6\t1\n");
    expect(out.rows.map((r) => [r.code, r.t, r.u, r.l])).toEqual([["BIO 101", 2, 2, 0], ["BIO 102", 3, 0, 2]]);
    expect(out.ignored).toEqual([2]);
  });

  it("offers theory splits derived from T", () => {
    expect(patternOptions(3)).toEqual([[3], [2, 1], [1, 1, 1]]);
    expect(patternOptions(2)).toEqual([[2], [1, 1]]);
    expect(patternOptions(4)).toEqual([[4], [3, 1], [2, 2], [1, 1, 1, 1]]);
    expect(patternOptions(0)).toEqual([]);
  });

  it("checks that a pattern places every hour (MBG 541: 3-hour course, 2 placed is an error)", () => {
    const d = mbg();
    const c = d.courses.find((x) => x.code === "MBG 541")!;
    c.pattern = { ...c.pattern, theoryBlocks: [2], start: "09:20" };
    expect(patternHours(c)).toBe(2);
    const issues = validate(d, ROOMS);
    expect(issues).toContainEqual(expect.objectContaining({ code: "patternTotal", level: "error", vars: expect.objectContaining({ code: "MBG 541", hours: 3, placed: 2 }) }));
  });

  it("explains the room fit live: A 207 fits 120 exactly, C 504 is too small for 80, B 501 is not bookable", () => {
    expect(fittingRooms(ROOMS, 120, []).map((r) => r.display_name)).toEqual(["A 207", "C 201", "A 203", "A 204"]);
    const d = mbg();
    for (const c of d.courses) c.pattern.start = "09:20";
    d.courses[1]!.room.preferred = "C 504";
    d.courses[4]!.room.preferred = "B 501";
    const issues = validate(d, ROOMS);
    expect(issues).toContainEqual(expect.objectContaining({ code: "exactFit", level: "warning", vars: expect.objectContaining({ room: "A 207", n: 120 }) }));
    expect(issues).toContainEqual(expect.objectContaining({ code: "preferredSmall", vars: expect.objectContaining({ room: "C 504", seats: 40, n: 80 }) }));
    expect(issues).toContainEqual(expect.objectContaining({ code: "preferredUnknown", vars: expect.objectContaining({ room: "B 501" }) }));
    expect(issues).toContainEqual(expect.objectContaining({ code: "fits", level: "info", vars: expect.objectContaining({ code: "MBG 598", count: 4 }) }));
  });

  it("a lab with no laboratory room big enough is an error", () => {
    const d = mbg();
    const c = d.courses[2]!;
    c.room.tags = ["LAB"];
    c.sections[0]!.enrolment = 40;
    c.pattern.start = "09:20";
    expect(validate(d, ROOMS)).toContainEqual(expect.objectContaining({ code: "noLabRoom", level: "error" }));
  });

  it("only errors block the final write; warnings never do", () => {
    const d = mbg();
    for (const c of d.courses) c.pattern.start = "09:20";
    const issues = validate(d, ROOMS);
    expect(issues.filter((i) => i.level === "error")).toEqual([]);
    // warnings: the seminar's 0+0+0 hours, missing instructors, A 207 exactly full
    expect(issues.some((i) => i.level === "warning")).toBe(true);
    expect(canGenerate(issues)).toBe(true);
    const st = stepStatus(d, issues);
    expect(st.find((s) => s.step === "patterns")).toMatchObject({ errors: 0 });
    expect(st.find((s) => s.step === "sections")!.warnings).toBe(7);
    d.courses.push(newCourse({ code: "MBG 532" }));
    expect(canGenerate(validate(d, ROOMS))).toBe(false);
  });

  it("builds the POST /sections/{id}/pattern body from T/U/L, the split and the room need", () => {
    const d = mbg();
    const seminar = { ...d.courses[0]!, pattern: { ...d.courses[0]!.pattern, start: "14:20", days: [5] } };
    expect(patternBody(seminar, 120)).toEqual({ theory: 1, practice: 0, lab: 0, days: [5], start: "14:20", weeks: "1-14", room_needs: { capacity: 120 }, replace: true });
    const epi = { ...d.courses[1]!, pattern: { ...d.courses[1]!.pattern, theoryBlocks: [2, 1], start: "09:20" }, room: { capacity: null, tags: [], building: "A", preferred: "" } };
    expect(patternBody(epi, 80)).toMatchObject({ theory: 3, block_size: [2, 1], room_needs: { building: "A", capacity: 80 } });
  });

  it("plans the autosave in dependency order and only writes what changed", () => {
    const d = mbg();
    expect(planSync({ ...d, termId: null })).toEqual([]);
    let ops = planSync(d);
    expect(ops[0]).toEqual({ kind: "faculty" });
    expect(ops[1]).toEqual({ kind: "program" });
    expect(ops.filter((o) => o.kind === "course")).toHaveLength(7);
    // no start time yet: no pattern writes
    expect(ops.some((o) => o.kind === "pattern")).toBe(false);
    // after a save: ids and hashes recorded, nothing left to write
    const saved: Draft = { ...d, program: { ...d.program, id: 1, facultyId: 2 } };
    saved.courses = saved.courses.map((c, i) => ({ ...c, id: 100 + i, own: true, sections: c.sections.map((s, j) => ({ ...s, id: 200 + i * 10 + j })) }));
    saved.synced = { program: hashes.program(saved) };
    for (const c of saved.courses) {
      saved.synced[c.key] = hashes.course(c);
      for (const s of c.sections) saved.synced[s.key] = hashes.section(saved, c, s);
    }
    expect(planSync(saved)).toEqual([]);
    // a new start time → only that course's pattern; a typed instructor → create it first
    saved.courses[1]!.pattern.start = "09:20";
    saved.courses[1]!.sections[0]!.instructors = [{ id: null, name: "Dr. Öğr. Üyesi A. B." }, null];
    ops = planSync(saved);
    expect(ops.map((o) => o.kind)).toEqual(["instructor", "section", "pattern"]);
    // a duplicate code is never written
    saved.courses.push(newCourse({ code: "MBG 532", sections: [] }));
    expect(planSync(saved).filter((o) => o.kind === "course")).toEqual([]);
  });

  it("keeps the user's newest edits and takes only the server ids from a finished write", () => {
    const d = mbg();
    const done: Draft = { ...d, program: { ...d.program, id: 9, facultyId: 3 }, courses: d.courses.map((c) => ({ ...c, id: 50, own: true })), synced: { program: "x" } };
    const cur: Draft = { ...d, program: { ...d.program, name: "MBG YL (yeni ad)" }, courses: d.courses.map((c, i) => (i === 0 ? { ...c, name: "Seminer (güncel)" } : c)) };
    const m = mergeIds(cur, done);
    expect(m.program).toMatchObject({ id: 9, facultyId: 3, name: "MBG YL (yeni ad)" });
    expect(m.courses[0]).toMatchObject({ id: 50, name: "Seminer (güncel)" });
    expect(m.synced.program).toBe("x");
  });

  it("summarises the draft for the rail and the preview card", () => {
    const d = mbg();
    d.courses[1]!.sections[0]!.instructors = [{ id: null, name: "Yeni Kişi" }, null];
    expect(summary(d)).toMatchObject({ courses: 7, ects: 63, sections: 7, people: 1, newPeople: 1, weeklyHours: 19 });
  });
});
