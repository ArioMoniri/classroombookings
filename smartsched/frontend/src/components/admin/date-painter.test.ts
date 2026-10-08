import { describe, expect, it } from "vitest";
import { changeCount, changes, initialPainter, monthsBetween, painterReducer, rangeBetween, type PainterState } from "./date-painter";

const days = Array.from({ length: 21 }, (_, i) => `2026-02-${String(i + 2).padStart(2, "0")}`); // Mon 2 → Sun 22 Feb
const A = 1;
const B = 2;
const loaded = (): PainterState =>
  painterReducer(initialPainter(A), { type: "load", dates: days.map((date) => ({ date, timetable_week_id: date === "2026-02-02" ? B : null })) });

describe("session date painter", () => {
  it("loads the term's mapping and has no changes", () => {
    const s = loaded();
    expect(s.days).toHaveLength(21);
    expect(s.pending["2026-02-02"]).toBe(B);
    expect(changeCount(s)).toBe(0);
  });
  it("a drag paints the range in date order and can shrink back", () => {
    let s = loaded();
    s = painterReducer(s, { type: "down", date: "2026-02-04" });
    s = painterReducer(s, { type: "enter", date: "2026-02-10" });
    expect(Object.keys(changes(s))).toEqual(["2026-02-04", "2026-02-05", "2026-02-06", "2026-02-07", "2026-02-08", "2026-02-09", "2026-02-10"]);
    s = painterReducer(s, { type: "enter", date: "2026-02-05" }); // pointer comes back: dates 06–10 restored
    expect(changes(s)).toEqual({ "2026-02-04": A, "2026-02-05": A });
    s = painterReducer(s, { type: "enter", date: "2026-02-02" }); // backwards past the anchor
    expect(changes(s)).toEqual({ "2026-02-02": A, "2026-02-03": A, "2026-02-04": A });
    s = painterReducer(s, { type: "up" });
    expect(s.stroke).toBeNull();
    s = painterReducer(s, { type: "enter", date: "2026-02-20" }); // hovering after release paints nothing
    expect(changeCount(s)).toBe(3);
  });
  it("shift+click paints from the last painted date; the eraser clears", () => {
    let s = painterReducer(loaded(), { type: "down", date: "2026-02-09" });
    s = painterReducer(s, { type: "up" });
    s = painterReducer(s, { type: "down", date: "2026-02-15", shift: true });
    expect(Object.keys(changes(s))).toHaveLength(7);
    s = painterReducer(s, { type: "brush", brush: null });
    s = painterReducer(s, { type: "down", date: "2026-02-02" });
    s = painterReducer(s, { type: "up" });
    expect(changes(s)["2026-02-02"]).toBeNull();
  });
  it("paints a whole week, fills the term, reverts", () => {
    let s = painterReducer(loaded(), { type: "brush", brush: B });
    s = painterReducer(s, { type: "week", monday: "2026-02-16" });
    expect(Object.keys(changes(s))).toEqual(["2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-21", "2026-02-22"]);
    s = painterReducer(s, { type: "fill", brush: A });
    expect(changeCount(s)).toBe(21);
    s = painterReducer(s, { type: "revert" });
    expect(changeCount(s)).toBe(0);
  });
  it("ignores dates outside the term", () => {
    const s = painterReducer(loaded(), { type: "down", date: "2026-03-01" });
    expect(s.stroke).toBeNull();
    expect(rangeBetween(days, "2026-02-21", "2026-03-05")).toEqual(["2026-02-21", "2026-02-22"]);
  });
  it("lays months out Monday-first", () => {
    const months = monthsBetween("2026-02-02", "2026-03-10");
    expect(months.map((m) => m.key)).toEqual(["2026-02", "2026-03"]);
    const feb = months[0]!;
    expect(feb.weeks[0]!.monday).toBe("2026-01-26");
    expect(feb.weeks[0]!.days[0]).toBeNull(); // 26 Jan belongs to January
    expect(feb.weeks[0]!.days[6]).toBe("2026-02-01");
    expect(feb.weeks).toHaveLength(5);
  });
});
