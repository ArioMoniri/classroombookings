import { describe, expect, it } from "vitest";
import { assignment, fixtureIndex } from "@/components/timetable/model/fixtures";
import { buildModel } from "@/components/timetable/model/index-model";
import { dayShare, freeRuns, heldAt, roomWeek, rowSegments, weekClasses, weekShare } from "./room-occupancy";

const model = buildModel(
  fixtureIndex([
    assignment({ id: 9, label: "MAT 101 §2", day: 3, sp: 1, ep: 2, rooms: [1], weeks: [1, 2, 3, 4, 5, 6, 7] }),
    assignment({ id: 10, label: "FIZ 101 §1", day: 1, sp: 10, ep: 12, rooms: [1], weeks: [8, 9, 10, 11, 12, 13, 14] }),
  ]),
);

describe("room occupancy", () => {
  it("lays the room's classes, blocks and bookings on a 7 × 18 grid for the week", () => {
    const g = roomWeek(model, 1, 7);
    expect(g).toHaveLength(7);
    expect(g[2][6]).toMatchObject({ kind: "class", label: "BME 419 §1" });
    expect(g[2][0]).toMatchObject({ kind: "class", label: "MAT 101 §2" });
    expect(g[0][9].kind).toBe("free"); // FIZ 101 runs in weeks 8–14 only
    expect(roomWeek(model, 1, 9)[0][9]).toMatchObject({ kind: "class", label: "FIZ 101 §1" });
    expect(roomWeek(model, 5, 7)[2][7]).toMatchObject({ kind: "block", label: "HAZIRLIK" });
  });
  it("shares: per day over 18 periods, per week over Mon–Fri", () => {
    const g = roomWeek(model, 1, 7);
    expect(dayShare(g, 3)).toBeCloseTo(5 / 18);
    expect(weekShare(g)).toBeCloseTo(5 / 18 / 5);
    expect(weekShare(roomWeek(model, 4, 7))).toBe(0);
  });
  it("free runs respect the minimum length and the evening cut", () => {
    const g = roomWeek(model, 1, 7);
    const wed = freeRuns(g, 2, [3]);
    expect(wed).toEqual([
      { day: 3, sp: 3, ep: 6, length: 4 },
      { day: 3, sp: 10, ep: 18, length: 9 },
    ]);
    expect(freeRuns(g, 5, [3])).toEqual([{ day: 3, sp: 10, ep: 18, length: 9 }]);
    expect(freeRuns(g, 2, [3], 11)).toEqual([
      { day: 3, sp: 3, ep: 6, length: 4 },
      { day: 3, sp: 10, ep: 11, length: 2 },
    ]);
  });
  it("busy-now and the weekly class list", () => {
    const g = roomWeek(model, 1, 7);
    expect(heldAt(g, 3, 8)).toMatchObject({ label: "BME 419 §1" });
    expect(heldAt(g, 3, 4)).toBeNull();
    expect(heldAt(g, 3, null)).toBeNull();
    expect(weekClasses(model, 1, 7).map((e) => e.a.label)).toEqual(["MAT 101 §2", "BME 419 §1"]);
  });
  it("row segments merge a held item over its periods and keep free periods single", () => {
    const row = roomWeek(model, 1, 7)[2];
    const segs = rowSegments(row);
    expect(segs[0]).toMatchObject({ kind: "held", sp: 1, ep: 2, cell: { label: "MAT 101 §2" } });
    expect(segs[1]).toEqual({ kind: "free", p: 3 });
    const covered = segs.reduce((n, s) => n + (s.kind === "free" ? 1 : s.ep - s.sp + 1), 0);
    expect(covered).toBe(18);
  });
});
