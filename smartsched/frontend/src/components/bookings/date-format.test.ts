import { describe, expect, it } from "vitest";
import { addDays, dateFormatter, formatPattern, isoWeekday, mondayOf, parseDay, tokenize } from "./date-format";

describe("org date patterns", () => {
  it("formats the CRBS defaults in Turkish and English", () => {
    expect(formatPattern("2026-04-23", "EEEE d MMMM yyyy", "tr")).toBe("Perşembe 23 Nisan 2026");
    expect(formatPattern("2026-04-23", "EEEE d MMMM yyyy", "en")).toBe("Thursday 23 April 2026");
    expect(formatPattern("2026-02-16", "EEE d MMM", "tr")).toBe("Pzt 16 Şub");
    expect(formatPattern("2026-02-16", "EEE d MMM", "en")).toBe("Mon 16 Feb");
  });
  it("supports numeric fields and quoted literals", () => {
    expect(formatPattern("2026-02-05", "dd.MM.yy", "tr")).toBe("05.02.26");
    expect(formatPattern("2026-02-05", "d/M/yyyy", "en")).toBe("5/2/2026");
    expect(formatPattern("2026-02-05", "'Hafta' d", "tr")).toBe("Hafta 5");
    expect(tokenize("HH:mm")).toEqual([
      { kind: "field", letter: "H", count: 2 },
      { kind: "text", value: ":" },
      { kind: "field", letter: "m", count: 2 },
    ]);
  });
  it("formats times with the time pattern", () => {
    const f = dateFormatter({ pattern_time: "h:mm" }, "en");
    expect(f.time("08:30")).toBe("8:30");
    expect(f.time("22:50")).toBe("10:50");
    expect(dateFormatter(null, "tr").time("08:30")).toBe("08:30");
    expect(dateFormatter(null, "tr").short("2026-04-23")).toBe("23.04.2026");
  });
  it("parses calendar dates as local dates (no time-zone shift)", () => {
    const d = parseDay("2026-02-16");
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 1, 16]);
    expect(isoWeekday("2026-02-16")).toBe(1);
    expect(isoWeekday("2026-02-22")).toBe(7);
    expect(mondayOf("2026-02-19")).toBe("2026-02-16");
    expect(addDays("2026-02-28", 1)).toBe("2026-03-01");
  });
});
