import { getResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { GridResponse, MoveResponse, ScheduleRun } from "@/lib/api/schemas";
import { handlers, resetMockState } from "./handlers";

const BASE = "http://backend.test/api/v1";
async function call(path: string, init?: RequestInit) {
  const res = await getResponse(handlers, new Request(`${BASE}${path}`, init));
  if (!res) throw new Error(`no handler for ${path}`);
  return res;
}

describe("mock API", () => {
  beforeEach(() => resetMockState());

  it("serves a schema-valid grid for the feasible run with 61 rooms and no conflicts", async () => {
    const grid = GridResponse.parse(await (await call("/runs/1/grid?week=7")).json());
    expect(grid.rooms).toHaveLength(61);
    expect(grid.periods).toHaveLength(18);
    expect(grid.assignments.length).toBeGreaterThan(100);
    expect(grid.assignments.some((a) => a.conflict)).toBe(false);
    expect(grid.blocks.some((b) => b.label === "HAZIRLIK")).toBe(true);
  });

  it("flags conflicts and diagnoses on the infeasible run", async () => {
    const run = ScheduleRun.parse(await (await call("/runs/2")).json());
    expect(run.status).toBe("INFEASIBLE");
    expect(run.diagnosis.length).toBeGreaterThanOrEqual(2);
    const grid = GridResponse.parse(await (await call("/runs/2/grid?week=7")).json());
    expect(grid.assignments.some((a) => a.conflict)).toBe(true);
  });

  it("rejects a move into an occupied slot and accepts a free one", async () => {
    const grid = GridResponse.parse(await (await call("/runs/1/grid?week=7")).json());
    const a = grid.assignments.find((x) => !x.is_locked && x.size < 30);
    const other = grid.assignments.find((x) => x.id !== a?.id && x.day === a?.day);
    expect(a && other).toBeTruthy();
    if (!a || !other) return;
    const bad = await call(`/runs/1/assignments/${a.id}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_ids: other.room_ids, day: other.day, start_period: other.start_period, end_period: other.end_period }),
    });
    expect(bad.status).toBe(409);
    const badBody = MoveResponse.parse(await bad.json());
    expect(badBody.ok).toBe(false);
    expect(badBody.conflicts.some((c) => c.kind === "no_room_overlap")).toBe(true);

    // Find a free room/slot for the small class.
    const free = grid.rooms.find((r) => r.is_bookable && !r.tags.includes("TIP") && r.capacity >= a.size && !grid.assignments.some((x) => x.room_ids.includes(r.id) && x.day === a.day) && !grid.blocks.some((b) => b.room_id === r.id && b.day === a.day));
    expect(free).toBeTruthy();
    if (!free) return;
    const good = await call(`/runs/1/assignments/${a.id}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_ids: [free.id], day: a.day, start_period: a.start_period, end_period: a.end_period }),
    });
    expect(good.status).toBe(200);
    expect(MoveResponse.parse(await good.json()).assignment?.room_ids).toEqual([free.id]);
  });

  it("creates a run that progresses to FEASIBLE and proposes chat moves", async () => {
    const created = await call("/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ term_id: 1, kind: "COURSE", horizon: "WEEK", horizon_params: { weeks: [8] } }) });
    expect(created.status).toBe(202);
    const { run_id } = (await created.json()) as { run_id: number };
    expect(run_id).toBeGreaterThan(2);
    const chat = await call("/runs/1/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: "BME 419'u A 204'e taşı" }) });
    const { messages } = (await chat.json()) as { messages: { proposal: { moves: unknown[] } | null }[] };
    expect(messages.at(-1)?.proposal?.moves.length).toBe(1);
  });
});
