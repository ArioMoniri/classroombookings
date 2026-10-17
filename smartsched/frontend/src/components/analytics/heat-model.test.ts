/** Heatmap helpers on the real Bahar 2026 week 3 live board (published run #5; trimmed to Mon–Wed, periods 1–4). */
import { describe, expect, it } from "vitest";
import type { InstructorHeatmap, RoomHeatmap } from "@/lib/api/analytics";
import fixture from "./__fixtures__/heat-bahar-w3.json";
import { columnHeader, detailCells, instructorMatrix, overviewRows, personMatrix, readHeatUrl } from "./heat-model";

const data = fixture as unknown as RoomHeatmap;

describe("heat model", () => {
  it("reads the URL state with safe defaults", () => {
    expect(readHeatUrl(new URLSearchParams(""))).toEqual({ tab: "rooms", source: "live", run: null, group: "building", scope: "week", week: null, bookings: true, blocks: true, g: "" });
    const s = readHeatUrl(new URLSearchParams("tab=instructors&source=run&run=6&group=room_type&scope=term&blocks=0&g=A"));
    expect(s).toMatchObject({ tab: "instructors", source: "run", run: 6, group: "room_type", scope: "term", blocks: false, g: "A" });
    // a run source without a run id falls back to the live board; an unknown grouping to building
    expect(readHeatUrl(new URLSearchParams("source=run&group=floor"))).toMatchObject({ source: "live", group: "building" });
  });

  it("puts every room first, then one row per building, with per-day totals", () => {
    const rows = overviewRows(data);
    expect(rows[0]!.key).toBe("");
    expect(rows[0]!.rooms).toBe(data.overall.rooms);
    expect(rows[1]!.key).toBe("A");
    expect(rows[1]!.byCol.get("d1")).toMatchObject({ col: "d1", capacity: 558 });
    expect(rows[1]!.total.pct).toBe(data.rows[0]!.total.pct);
  });

  it("drills down into a group's period × day cells (all rooms when no group)", () => {
    expect(detailCells(data, "A").get("d1|1")).toEqual(data.rows[0]!.cells.find((c) => c.col === "d1" && c.period === 1));
    expect(detailCells(data, "").get("d1|1")).toEqual(data.overall.cells.find((c) => c.col === "d1" && c.period === 1));
  });

  it("names weekday and exam-date columns in the UI language", () => {
    expect(columnHeader({ key: "d1", day: 1, label: { tr: "Pazartesi", en: "Monday" } }, "tr")).toEqual({ label: "Pzt", text: "Pazartesi" });
    const exam = columnHeader({ key: "w1d1", week: 1, day: 1, date: "2026-06-01", label: { tr: "Pzt 01.06.2026", en: "Mon 2026-06-01" } }, "tr");
    expect(exam.label).toBe("Pzt");
    expect(exam.sub).toBe("01.06");
    expect(exam.text).toContain("2026");
  });

  it("colours instructor slots relative to the busiest one and keeps the count", () => {
    const ins = { instructors_total: 340, matrix: [{ day: 1, period: 1, instructors: 10, pct: 2.9 }, { day: 1, period: 2, instructors: 52, pct: 15.3 }] } as unknown as InstructorHeatmap;
    const m = instructorMatrix(ins);
    expect(m.max).toBe(52);
    expect(m.cell(1, 2)).toMatchObject({ count: 52, pct: 100 });
    expect(m.cell(1, 1)!.pct).toBeCloseTo((10 / 52) * 100);
    expect(m.cell(2, 1)).toBeUndefined();
    const pm = personMatrix([{ day: 1, period: 2, weeks: 1, share: 1 }]);
    expect(pm(1, 2)!.pct).toBe(100);
    expect(pm(1, 3)!.pct).toBe(0);
  });
});
