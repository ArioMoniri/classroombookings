"use client";

import { useMemo } from "react";
import { checkPlacement, groupByRoom, type EventStatus, type GridSpanInput } from "@/lib/grid/layout";
import type { Assignment, Block, GridResponse, Program, Room } from "@/lib/api/schemas";
import { PERIODS_PER_DAY } from "@/lib/time";

export interface GridEvent extends GridSpanInput {
  kind: "assignment" | "block";
  assignment: Assignment | null;
  block: Block | null;
  label: string;
  size: number;
  capacity: number;
  facultySlot: number;
  locked: boolean;
}

export type StatusKindOfEvent = "feasible" | "infeasible" | "warning" | "locked" | "preoccupied" | "tip" | "pclab";

export const STATUS_TO_KIND: Record<EventStatus, StatusKindOfEvent> = {
  ok: "feasible",
  conflict: "infeasible",
  warning: "warning",
  locked: "locked",
  block: "preoccupied",
  tip: "tip",
  pc: "pclab",
};

export function statusOf(a: Assignment, room: Room | undefined): EventStatus {
  if (a.conflict) return "conflict";
  if (a.is_locked) return "locked";
  if (room && a.size > room.capacity) return "warning";
  if (room?.tags.includes("TIP")) return "tip";
  if (room?.tags.includes("PC")) return "pc";
  return "ok";
}

export function facultySlotFor(programName: string | null, programs: readonly Program[]): number {
  const p = programs.find((x) => x.name === programName);
  const id = p?.faculty_id ?? 8;
  return id >= 1 && id <= 8 ? id : 8;
}

export interface GridModel {
  rooms: Room[];
  roomById: Map<number, Room>;
  events: GridEvent[];
  byRoom: Map<number, GridEvent[]>;
  conflicts: number;
  warnings: number;
}

export function buildModel(grid: GridResponse | undefined, programs: readonly Program[], rooms: Room[]): GridModel {
  const roomById = new Map(rooms.map((r) => [r.id, r]));
  const events: GridEvent[] = [];
  if (grid) {
    for (const a of grid.assignments) {
      for (const rid of a.room_ids) {
        const room = roomById.get(rid);
        const status = statusOf(a, room);
        events.push({
          id: `a${a.id}:${rid}`,
          roomId: rid,
          day: a.day,
          startPeriod: a.start_period,
          endPeriod: a.end_period,
          status,
          kind: "assignment",
          assignment: a,
          block: null,
          label: a.label,
          size: a.size,
          capacity: room?.capacity ?? 0,
          facultySlot: facultySlotFor(a.program_name, programs),
          locked: a.is_locked,
        });
      }
    }
    for (const b of grid.blocks) {
      events.push({ id: `b${b.id}`, roomId: b.room_id, day: b.day, startPeriod: b.start_period, endPeriod: b.end_period, status: "block", kind: "block", assignment: null, block: b, label: b.label, size: 0, capacity: 0, facultySlot: 8, locked: true });
    }
  }
  return {
    rooms,
    roomById,
    events,
    byRoom: groupByRoom(events),
    conflicts: events.filter((e) => e.status === "conflict").length,
    warnings: events.filter((e) => e.status === "warning").length,
  };
}

export function useGridModel(grid: GridResponse | undefined, programs: readonly Program[], rooms: Room[]): GridModel {
  return useMemo(() => buildModel(grid, programs, rooms), [grid, programs, rooms]);
}

export interface MoveCheck {
  ok: boolean;
  reasons: string[];
  conflictIds: string[];
  /** soft issues (warn, do not block) */
  warnings: string[];
}

/** Pure client-side validity preview for a drag target (mirrors the server's hard checks). */
export function checkMove(model: GridModel, moving: GridEvent, target: { roomId: number; day: number; startPeriod: number }): MoveCheck {
  const duration = moving.endPeriod - moving.startPeriod + 1;
  const endPeriod = target.startPeriod + duration - 1;
  const reasons: string[] = [];
  const warnings: string[] = [];
  const room = model.roomById.get(target.roomId);
  if (moving.locked) reasons.push("locked");
  if (endPeriod > PERIODS_PER_DAY || target.startPeriod < 1) reasons.push("out_of_range");
  if (!room) reasons.push("unknown_room");
  else {
    if (!room.is_bookable) reasons.push("not_bookable");
    if (room.capacity < moving.size) reasons.push("capacity");
    const isMedicine = moving.assignment?.program_name === "Tıp";
    if (room.tags.includes("TIP") && !isMedicine) reasons.push("tip");
    if (target.startPeriod <= 12 && endPeriod >= 12 && duration > 1) warnings.push("p12");
  }
  const placement = checkPlacement(model.events, moving, { roomId: target.roomId, day: target.day, startPeriod: target.startPeriod, endPeriod });
  if (!placement.ok) reasons.push("overlap");
  return { ok: reasons.length === 0, reasons, conflictIds: placement.conflictIds.filter((id) => id !== "out-of-range"), warnings };
}
