import { describe, expect, it } from "vitest";
import { assignment, fixtureIndex } from "@/test/fixtures/calendar-index";
import { buildIcs, icsEscape } from "./ics";
import { buildModel } from "./index-model";

describe(".ics export per subject (calendar follow-up)", () => {
  const model = buildModel(fixtureIndex([assignment({ id: 9, label: "MAT 101 §2", day: 3, sp: 7, ep: 9, rooms: [4], weeks: [1, 2], instr: ["Dr. Kaya"], instr_ids: [77] })]));
  const ics = buildIcs(model, (e) => e.a.id === 9, { title: "MAT 101; A 204", stamp: "20261015T120000Z" });
  const lines = ics.split("\r\n");

  it("is a VCALENDAR with CRLF lines, one VEVENT per dated occurrence", () => {
    expect(lines[0]).toBe("BEGIN:VCALENDAR");
    expect(lines).toContain("VERSION:2.0");
    expect(lines.at(-2)).toBe("END:VCALENDAR");
    expect(lines.filter((l) => l === "BEGIN:VEVENT")).toHaveLength(2);
  });

  it("times are the periods' clock times in Istanbul (UTC+3) written as UTC", () => {
    // week 1 Monday 2026-02-02 → Wednesday 2026-02-04; P7 13:30 → 10:30Z, P9 ends 15:50 → 12:50Z
    expect(lines).toContain("DTSTART:20260204T103000Z");
    expect(lines).toContain("DTEND:20260204T125000Z");
    expect(lines).toContain("DTSTART:20260211T103000Z");
  });

  it("names the class, room and instructors, escapes text and keeps stable UIDs", () => {
    expect(lines).toContain("SUMMARY:MAT 101 §2");
    expect(lines.some((l) => l.startsWith("LOCATION:"))).toBe(true);
    expect(lines.some((l) => l.startsWith("DESCRIPTION:Dr. Kaya"))).toBe(true);
    expect(lines).toContain("X-WR-CALNAME:MAT 101\\; A 204");
    expect(lines.some((l) => /^UID:smartsched-42-9-4-20260204@/.test(l))).toBe(true);
    expect(icsEscape("a,b;c\\d\ne")).toBe("a\\,b\\;c\\\\d\\ne");
  });

  it("folds lines longer than 75 octets", () => {
    const long = buildIcs(model, (e) => e.a.id === 9, { title: "x".repeat(200), stamp: "20261015T120000Z" });
    expect(long.split("\r\n").every((l) => new TextEncoder().encode(l).length <= 75)).toBe(true);
  });
});
