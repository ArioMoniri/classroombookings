"use client";

import { useMemo } from "react";
import { useGrid, useRuns } from "@/lib/api/hooks";
import type { Assignment, Block } from "@/lib/api/schemas";
import type { DayOccupancy } from "./sparkline-bars";

/** Latest finished run — the default "context" for occupancy visuals. */
export function useContextRun(): number | null {
  const runs = useRuns();
  return runs.data?.find((r) => r.status === "FEASIBLE" || r.status === "OPTIMAL")?.id ?? runs.data?.[0]?.id ?? null;
}

export interface RoomOccupancy {
  byRoom: Map<number, DayOccupancy[]>;
  assignments: Assignment[];
  blocks: Block[];
  week: number;
}

export function useRoomOccupancy(week: number): { data: RoomOccupancy | null; runId: number | null; isLoading: boolean } {
  const runId = useContextRun();
  const grid = useGrid(runId, week);
  const data = useMemo<RoomOccupancy | null>(() => {
    if (!grid.data) return null;
    const byRoom = new Map<number, DayOccupancy[]>();
    const ensure = (roomId: number) => {
      let rows = byRoom.get(roomId);
      if (!rows) {
        rows = Array.from({ length: 7 }, (_, i) => ({ day: i + 1, day_periods: 0, evening_periods: 0, blocked: 0 }));
        byRoom.set(roomId, rows);
      }
      return rows;
    };
    for (const r of grid.data.rooms) ensure(r.id);
    for (const a of grid.data.assignments) {
      for (const rid of a.room_ids) {
        const row = ensure(rid)[a.day - 1];
        if (!row) continue;
        for (let p = a.start_period; p <= a.end_period; p++) {
          if (p >= 13) row.evening_periods++;
          else row.day_periods++;
        }
      }
    }
    for (const b of grid.data.blocks) {
      const row = ensure(b.room_id)[b.day - 1];
      if (row) row.blocked += b.end_period - b.start_period + 1;
    }
    return { byRoom, assignments: grid.data.assignments, blocks: grid.data.blocks, week: grid.data.week };
  }, [grid.data]);
  return { data, runId, isLoading: grid.isLoading };
}
