import { describe, expect, it } from "vitest";
import { addDays, dateFormatter, formatPattern, isoWeekday, LOCALE_DEFAULTS, mondayOf, parseDay, tokenize } from "./date-format";

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
  it("uses the backend's name tables (e-mails and screens agree) and every CRBS time pattern", () => {
    expect(formatPattern("2026-09-03", "d MMM yyyy", "en")).toBe("3 Sep 2026");
    expect(formatPattern("2026-09-03", "EEE d MMM", "tr")).toBe("Per 3 Eyl");
    expect(formatPattern("2026-02-22", "EEEE", "tr")).toBe("Pazar");
    const at = (p: string, l: "tr" | "en", hhmm: string) => dateFormatter({ pattern_time: p }, l).time(hhmm);
    expect(at("hh:mma", "en", "09:30")).toBe("09:30AM");
    expect(at("h:mm a", "en", "21:05")).toBe("9:05 PM");
    expect(at("h:mm a", "tr", "12:00")).toBe("12:00 ÖS");
    expect(at("hh:mm a", "tr", "00:15")).toBe("12:15 ÖÖ");
  });
  it("an empty pattern is CRBS '(Default)' for the language, or the defaults the backend sends", () => {
    expect(dateFormatter({ pattern_long: "" }, "tr").long("2026-04-23")).toBe("23 Nisan 2026 Perşembe");
    expect(dateFormatter(null, "en").long("2026-04-23")).toBe("Thursday, 23 April 2026");
    expect(dateFormatter(null, "en").weekday("2026-04-23")).toBe("23 Apr 2026");
    expect(dateFormatter(null, "tr", { ...LOCALE_DEFAULTS.tr, long: "dd.MM.yyyy" }).long("2026-04-23")).toBe("23.04.2026");
    expect(dateFormatter({ pattern_long: "EEEE d MMMM yyyy" }, "tr").long("2026-04-23")).toBe("Perşembe 23 Nisan 2026");
  });
  it("formats backend timestamps (naive UTC) in local time with the weekday and time patterns", () => {
    const f = dateFormatter({ pattern_weekday: "dd.MM.yyyy", pattern_time: "HH:mm" }, "tr");
    const local = new Date(Date.UTC(2026, 1, 16, 8, 5));
    const hh = String(local.getHours()).padStart(2, "0");
    const dd = String(local.getDate()).padStart(2, "0");
    expect(f.dateTime("2026-02-16T08:05:00")).toBe(`${dd}.02.2026 ${hh}:05`);
    expect(f.dateTime("2026-02-16T08:05:00Z")).toBe(`${dd}.02.2026 ${hh}:05`);
    expect(f.dateTime(null)).toBe("");
    expect(f.dateTime("not a date")).toBe("not a date");
  });
});
