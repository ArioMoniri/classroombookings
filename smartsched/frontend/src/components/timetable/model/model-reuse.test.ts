import { describe, expect, it } from "vitest";
import { patchIndex } from "@/lib/api/calendar";
import { assignment, fixtureIndex } from "@/test/fixtures/calendar-index";
import { buildModel } from "./index-model";

describe("buildModel keeps unchanged events (motion audit T3: a move re-rendered every chip, 380-482 ms)", () => {
  it("after a move only the moved class gets new event objects", () => {
    const idx = fixtureIndex([assignment({ id: 9, label: "MAT 101 §2", day: 1, sp: 7, ep: 9, rooms: [3] }), assignment({ id: 10, label: "FIZ 101 §1", day: 2, sp: 1, ep: 2, rooms: [4] })]);
    const before = buildModel(idx);
    const moved = { ...idx.assignments.find((a) => a.id === 9)!, day: 4 };
    const after = buildModel(patchIndex(idx, [moved]), before);
    expect(after.eventByAid.get(10)?.[0]).toBe(before.eventByAid.get(10)?.[0]);
    expect(after.eventByAid.get(9)?.[0]).not.toBe(before.eventByAid.get(9)?.[0]);
    expect(after.eventByAid.get(9)?.[0].day).toBe(4);
    expect(after.byRoomDay.get("3:4")?.map((e) => e.a.id)).toContain(9);
    expect(after.byRoomDay.get("3:1")?.map((e) => e.a.id) ?? []).not.toContain(9);
  });

  it("a different week list rebuilds everything (masks depend on it)", () => {
    const idx = fixtureIndex([assignment({ id: 10, label: "FIZ 101 §1", day: 2, sp: 1, ep: 2, rooms: [4], weeks: [] })]);
    const before = buildModel(idx);
    const after = buildModel({ ...idx, weeks: idx.weeks.slice(0, 7) }, before);
    expect(after.eventByAid.get(10)?.[0]).not.toBe(before.eventByAid.get(10)?.[0]);
  });
});

describe("EventChip memo", () => {
  it("equal rects by value and identical props skip the re-render; any other change does not", async () => {
    const { sameChipProps } = await import("../event-chip");
    type Props = Parameters<typeof sameChipProps>[0];
    const model = buildModel(fixtureIndex([assignment({ id: 9, label: "MAT 101 §2", day: 1, sp: 7, ep: 9, rooms: [3] })]));
    const ev = model.eventByAid.get(9)![0];
    const base: Props = { ev, rect: { left: 0, top: 0, width: 100, height: 40 }, lines: 2, line2: "A", ariaLabel: "MAT", selected: false };
    expect(sameChipProps(base, { ...base, rect: { left: 0, top: 0, width: 100, height: 40 } })).toBe(true);
    expect(sameChipProps(base, { ...base, rect: { left: 0, top: 0, width: 100, height: 41 } })).toBe(false);
    expect(sameChipProps(base, { ...base, selected: true })).toBe(false);
  });
});
