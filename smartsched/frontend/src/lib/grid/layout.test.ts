import { describe, expect, it } from "vitest";
import { checkPlacement, clampSpan, gridColumn, groupByRoom, layoutRow, spanRect, type GridSpanInput } from "./layout";

const ev = (id: string, roomId: number, day: number, s: number, e: number, status: GridSpanInput["status"] = "ok"): GridSpanInput => ({
  id,
  roomId,
  day,
  startPeriod: s,
  endPeriod: e,
  status,
});

describe("grid layout", () => {
  it("places non-overlapping spans in one lane with correct columns", () => {
    const rows = layoutRow([ev("a", 1, 1, 1, 3), ev("b", 1, 1, 4, 6), ev("other-room", 2, 1, 1, 2)], 1, 1);
    expect(rows.spans).toHaveLength(2);
    expect(rows.hasConflict).toBe(false);
    expect(rows.spans[0]).toMatchObject({ col: 0, colSpan: 3, lane: 0, lanes: 1 });
    expect(rows.spans[1]).toMatchObject({ col: 3, colSpan: 3, lane: 0, lanes: 1 });
  });

  it("stacks overlapping spans into lanes and flags the conflict", () => {
    const rows = layoutRow([ev("a", 1, 2, 7, 9), ev("b", 1, 2, 8, 10), ev("c", 1, 2, 11, 12)], 1, 2);
    expect(rows.hasConflict).toBe(true);
    const lanes = rows.spans.map((s) => s.lane);
    expect(lanes).toEqual([0, 1, 0]);
    expect(rows.spans.every((s) => s.lanes === 2)).toBe(true);
  });

  it("clamps spans into the 18-period range", () => {
    expect(clampSpan(0, 30)).toEqual([1, 18]);
    expect(clampSpan(5, 3)).toEqual([5, 5]);
  });

  it("detects conflicts for a proposed placement, ignoring the moving item", () => {
    const items = [ev("a", 1, 1, 1, 3), ev("blk", 1, 1, 10, 12, "block"), ev("m", 2, 1, 1, 2)];
    expect(checkPlacement(items, { id: "m" }, { roomId: 1, day: 1, startPeriod: 4, endPeriod: 6 })).toEqual({ ok: true, conflictIds: [] });
    expect(checkPlacement(items, { id: "m" }, { roomId: 1, day: 1, startPeriod: 3, endPeriod: 4 }).conflictIds).toEqual(["a"]);
    expect(checkPlacement(items, { id: "m" }, { roomId: 1, day: 1, startPeriod: 11, endPeriod: 13 }).conflictIds).toEqual(["blk"]);
    expect(checkPlacement(items, { id: "a" }, { roomId: 1, day: 1, startPeriod: 1, endPeriod: 3 }).ok).toBe(true);
    expect(checkPlacement(items, { id: "a" }, { roomId: 1, day: 1, startPeriod: 17, endPeriod: 19 }).ok).toBe(false);
  });

  it("groups by room and emits css helpers", () => {
    const g = groupByRoom([ev("a", 1, 1, 1, 1), ev("b", 1, 1, 2, 2), ev("c", 3, 1, 1, 1)]);
    expect(g.get(1)?.map((x) => x.id)).toEqual(["a", "b"]);
    expect(g.get(3)).toHaveLength(1);
    expect(gridColumn(6, 3)).toBe("7 / span 3");
    expect(spanRect(0, 18)).toEqual({ left: "0.0000%", width: "100.0000%" });
    expect(spanRect(9, 9).left).toBe("50.0000%");
  });
});
