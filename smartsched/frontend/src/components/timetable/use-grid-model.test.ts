import { describe, expect, it } from "vitest";
import { GridResponse } from "@/lib/api/schemas";
import { PERIODS } from "@/lib/time";
import { assignmentsByRun, blocks, programs, rooms, weeks } from "@/mocks/data";
import { buildModel, checkMove } from "./use-grid-model";

const grid = GridResponse.parse({
  run_id: 1,
  week: 7,
  week_start: "2026-03-16",
  weeks: weeks.filter((w) => w.term_id === 1),
  periods: PERIODS,
  rooms,
  assignments: (assignmentsByRun.get(1) ?? []).filter((a) => a.week === null),
  blocks: blocks.filter((b) => b.weeks.includes(7)),
});

describe("grid model", () => {
  const model = buildModel(grid, programs, rooms);

  it("maps assignments and blocks to spans with statuses", () => {
    expect(model.events.length).toBe(grid.assignments.length + grid.blocks.length);
    expect(model.events.some((e) => e.status === "block")).toBe(true);
    expect(model.conflicts).toBe(0);
    const tip = model.events.find((e) => model.roomById.get(e.roomId)?.tags.includes("TIP") && e.kind === "assignment");
    if (tip) expect(["tip", "locked"]).toContain(tip.status);
  });

  it("previews moves: overlap, capacity, TIP and range are hard; P12 is a warning", () => {
    const small = model.events.find((e) => e.kind === "assignment" && !e.locked && e.size <= 30 && e.endPeriod - e.startPeriod >= 1);
    expect(small).toBeDefined();
    if (!small) return;
    const other = model.events.find((e) => e.id !== small.id && e.kind === "assignment" && e.day === small.day);
    expect(other).toBeDefined();
    if (!other) return;
    expect(checkMove(model, small, { roomId: other.roomId, day: other.day, startPeriod: other.startPeriod }).reasons).toContain("overlap");
    const tipRoom = rooms.find((r) => r.tags.includes("TIP"))!;
    const tipCheck = checkMove(model, small, { roomId: tipRoom.id, day: 7, startPeriod: 1 });
    expect(tipCheck.reasons).toContain("tip");
    expect(checkMove(model, small, { roomId: rooms[0].id, day: 7, startPeriod: 18 }).reasons).toContain("out_of_range");
    const tiny = rooms.find((r) => r.capacity === 10)!;
    expect(checkMove(model, small, { roomId: tiny.id, day: 7, startPeriod: 1 }).reasons).toContain("capacity");
    const free = rooms.find((r) => r.is_bookable && !r.tags.includes("TIP") && r.capacity >= small.size && !model.byRoom.get(r.id)?.some((e) => e.day === 7))!;
    const ok = checkMove(model, small, { roomId: free.id, day: 7, startPeriod: 11 });
    expect(ok.ok).toBe(true);
    expect(ok.warnings).toContain("p12");
  });
});
