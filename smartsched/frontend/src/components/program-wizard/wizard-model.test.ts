import { describe, expect, it } from "vitest";
import type { PasteRow } from "@/lib/api/program-drafts";
import {
  applyOps,
  cohortsFromYears,
  coursesFromPaste,
  diffOps,
  jointKey,
  jointTotal,
  neededCapacity,
  newCohortLabel,
  newCourse,
  newPayload,
  newSection,
  normalizeCode,
  parseNumber,
  parseStep,
  pasteDuplicates,
  patternHours,
  patternOptions,
  readPayload,
  samePerson,
  uncohorted,
  type Payload,
} from "./wizard-model";

/** the real Bahar rows of MBG Tezli YL (R182–R198) as the paste preview returns them */
const row = (line: number, code: string, name: string, t: number, ects = 9): PasteRow => ({ line, code, code_error: null, name, t, u: 0, l: 0, credits: t, ects, year: 1, enrolment: null });
const MBG: PasteRow[] = [row(2, "MBG 598", "Seminer", 0), row(3, "MBG 532", "Epigenetik", 3), row(4, "MBG 534", "Proteomiks", 3)];

function mbg(): Payload {
  const p = newPayload();
  p.program = { ...p.program, name: "Moleküler Biyoloji ve Genetik Tezli Yüksek Lisans", faculty_name: "Fen Bilimleri Enstitüsü", prefix: "MBG" };
  p.courses = coursesFromPaste(MBG);
  return p;
}

describe("program wizard model", () => {
  it("parses the server steps and the old aliases", () => {
    expect(parseStep("rooms")).toBe("rooms");
    expect(parseStep("patterns")).toBe("rooms");
    expect(parseStep("term")).toBe("program");
    expect(parseStep("precheck")).toBe("constraints");
    expect(parseStep("x")).toBe("program");
  });

  it("normalises course codes and refuses Turkish letters", () => {
    expect(normalizeCode("MBG532")).toEqual({ code: "MBG 532", info: true, error: null });
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

  it("turns pasted rows into courses; a 0+0+0 seminar gets weekly hours", () => {
    const p = mbg();
    expect(p.courses.map((c) => c.code)).toEqual(["MBG 598", "MBG 532", "MBG 534"]);
    expect(p.courses[0]!.pattern.weekly_hours).toBe(1);
    expect(p.courses[1]!.pattern.theory_blocks).toEqual([3]);
    expect(p.courses.every((c) => c.compulsory && c.sections.length === 1)).toBe(true);
  });

  it("flags pasted rows that repeat a draft course or an earlier row", () => {
    const p = mbg();
    const dup = pasteDuplicates(p.courses, [row(1, "MBG 532", "Epigenetik", 3), row(2, "MBG 951", "X", 3), row(3, "MBG 951", "X", 3)]);
    expect([...dup]).toEqual([1, 3]);
  });

  it("offers the theory splits and checks the placed total", () => {
    expect(patternOptions(3)).toEqual([[3], [2, 1], [1, 1, 1]]);
    const c = newCourse({ t: 3, pattern: { theory_blocks: [2], weekly_hours: null, days: [1], start: "08:30", weeks: "1-14" } });
    expect(patternHours(c)).toBe(2);
  });

  it("sizes the room from the joint total (MBG 598 + its joint seminars = 120)", () => {
    const s = { ...newSection("1", 15), joint_section_ids: [11, 12], joint_labels: { [jointKey(11)]: { label: "MBG 408", enrolment: 60, periods: 1 }, [jointKey(12)]: { label: "MBG 416", enrolment: 45, periods: 1 } } };
    expect(jointTotal(s)).toBe(120);
    expect(neededCapacity(newCourse({ sections: [s] }))).toBe(120);
    expect(neededCapacity(newCourse({ sections: [s], room: { capacity: 130, tags: [], building: "", preferred: "" } }))).toBe(130);
  });

  it("builds cohorts from the years, electives in one group", () => {
    const p = mbg();
    p.courses[2]!.compulsory = false;
    const cohorts = cohortsFromYears(p, (y) => newCohortLabel("MBG", y, "tr"));
    expect(cohorts).toHaveLength(1);
    expect(cohorts[0]!.label).toBe("MBG 1. sınıf");
    expect(cohorts[0]!.compulsory).toEqual([p.courses[0]!.key, p.courses[1]!.key]);
    expect(cohorts[0]!.elective_groups).toEqual([[p.courses[2]!.key]]);
    expect(uncohorted({ ...p, cohorts })).toEqual([]);
    expect(uncohorted({ ...p, cohorts: [{ ...cohorts[0]!, compulsory: [] }] }).map((c) => c.code)).toEqual(["MBG 598", "MBG 532"]);
  });

  it("reads a sparse or camelCase payload with every default", () => {
    const p = readPayload({ program: { name: "X", facultyName: "Fen" }, courses: [{ key: "c1", code: "MBG 532", pattern: { theoryBlocks: [3] }, sections: [{ key: "s1", instructors: [null, { id: 4 }] }] }] });
    expect(p.program.faculty_name).toBe("Fen");
    expect(p.courses[0]!.pattern.theory_blocks).toEqual([3]);
    expect(p.courses[0]!.sections[0]!.instructors).toEqual([{ id: 4 }]);
    expect(p.rules.window.enabled).toBe(true);
    expect(readPayload({}).cohorts).toEqual([]);
  });
});

describe("autosave ops", () => {
  it("sends only the changed fields, list items by key", () => {
    const a = mbg();
    const b = structuredClone(a);
    b.program.name = "MBG Tezsiz YL";
    b.courses[1]!.sections[0]!.enrolment = 80;
    b.courses[1]!.pattern.days = [2];
    const ops = diffOps(a, b);
    const k = a.courses[1]!.key;
    const s = a.courses[1]!.sections[0]!.key;
    expect(ops).toEqual([
      { path: "program.name", value: "MBG Tezsiz YL", op: "set" },
      { path: `courses.${k}.sections.${s}.enrolment`, value: 80, op: "set" },
      { path: `courses.${k}.pattern.days`, value: [2], op: "set" },
    ]);
    expect(applyOps(a, ops)).toEqual(b);
  });

  it("sets a whole list when items are added, removed or reordered", () => {
    const a = mbg();
    const b = structuredClone(a);
    b.courses.push(newCourse({ code: "MBG 546" }));
    expect(diffOps(a, b)).toEqual([{ path: "courses", value: b.courses, op: "set" }]);
    const c = structuredClone(a);
    c.courses.reverse();
    expect(diffOps(a, c)).toEqual([{ path: "courses", value: c.courses, op: "set" }]);
  });

  it("removes keys that disappeared and adds new ones", () => {
    const a = mbg();
    const b = structuredClone(a);
    const s = b.courses[1]!.sections[0]!;
    s.joint_section_ids = [345];
    s.joint_labels = { [jointKey(345)]: { label: "MBG 014 §1", enrolment: 75, periods: 3 } };
    const ops = diffOps(a, b);
    expect(ops.map((o) => o.path)).toEqual([`courses.${a.courses[1]!.key}.sections.${s.key}.joint_section_ids`, `courses.${a.courses[1]!.key}.sections.${s.key}.joint_labels`]);
    const c = structuredClone(b);
    delete c.courses[1]!.sections[0]!.joint_labels;
    expect(diffOps(b, c)).toEqual([{ path: `courses.${a.courses[1]!.key}.sections.${s.key}.joint_labels`, op: "remove" }]);
    expect(applyOps(b, diffOps(b, c))).toEqual(c);
  });

  it("rebases our unsaved edit onto someone else's save", () => {
    const base = mbg();
    const theirs = structuredClone(base);
    theirs.program.prefix = "MBY";
    const ours = structuredClone(base);
    ours.courses[0]!.name = "Seminer I";
    const rebased = applyOps(theirs, diffOps(base, ours));
    expect(rebased.program.prefix).toBe("MBY");
    expect(rebased.courses[0]!.name).toBe("Seminer I");
  });

  it("drops an edit whose item someone else removed", () => {
    const base = mbg();
    const theirs = structuredClone(base);
    theirs.courses = theirs.courses.slice(1);
    const ours = structuredClone(base);
    ours.courses[0]!.name = "Seminer I";
    expect(applyOps(theirs, diffOps(base, ours)).courses.map((c) => c.code)).toEqual(["MBG 532", "MBG 534"]);
  });
});

describe("samePerson (R2-M-07: one person once per section)", () => {
  it("matches ids, and new names up to case, titles, dots, NBSP and Turkish letters", () => {
    expect(samePerson({ id: 491, name: "T. E." }, { id: 491 })).toBe(true);
    expect(samePerson({ id: 491 }, { id: 7 })).toBe(false);
    expect(samePerson({ id: 491, name: "Tolga Emre" }, { name: "Tolga Emre" })).toBe(false); // an id against a new name: the server decides
    expect(samePerson({ name: "Tolga Emre" }, { name: "TOLGA\u00a0EMRE" })).toBe(true);
    expect(samePerson({ name: "Dr. Öğr. Üyesi Elçim Elgün Kırımlı" }, { name: "elçim elgün kırımlı" })).toBe(true);
    expect(samePerson({ name: "İpek Yılmaz" }, { name: "ipek yılmaz" })).toBe(true);
    expect(samePerson({ name: "Tolga Emre" }, { name: "Tolga Emir" })).toBe(false);
    expect(samePerson({ name: "" }, { name: "" })).toBe(false);
  });
});
