/**
 * Client-side heat (calendar.md §6.5, §6.6): occupancy = occupied room-periods ÷ (bookable rooms × 18) per
 * (week, day), computed from the index so it respects the sidebar filters. Same definition as the server
 * aggregate `GET /runs/{id}/heat` (pre-occupied blocks count as occupied).
 */
import { PERIODS_PER_DAY } from "@/lib/time";
import type { CalEvent, CalendarModel } from "./index-model";

export type HeatMetric = "occupancy" | "conflicts" | "unplaced" | "changes";

export interface HeatValue {
  week: number;
  day: number;
  occupied: number;
  blocked: number;
  capacity: number;
  occupancy: number;
  conflicts: number;
  changes: number;
  byBuilding: Record<string, number>;
}

export interface HeatOptions {
  rooms?: ReadonlySet<number>;
  keep?: (e: CalEvent) => boolean;
  /** compare diff: assignment ids that moved vs the compare run, per week */
  changed?: (e: CalEvent, week: number) => boolean;
}

export function computeHeat(model: CalendarModel, opts: HeatOptions = {}): Map<string, HeatValue> {
  const rooms = model.rooms.filter((r) => r.bookable && (!opts.rooms || opts.rooms.has(r.id)));
  const roomSet = new Set(rooms.map((r) => r.id));
  const buildingRooms = new Map<string, Set<number>>();
  for (const r of rooms) {
    const s = buildingRooms.get(r.building) ?? new Set<number>();
    s.add(r.id);
    buildingRooms.set(r.building, s);
  }
  const capacity = Math.max(1, rooms.length * PERIODS_PER_DAY);
  const occ = new Map<string, Set<number>>();
  const blk = new Map<string, Set<number>>();
  const conflicts = new Map<string, number>();
  const changes = new Map<string, number>();
  const cell = (m: Map<string, Set<number>>, k: string) => {
    let s = m.get(k);
    if (!s) {
      s = new Set();
      m.set(k, s);
    }
    return s;
  };
  for (const e of model.events) {
    if (!roomSet.has(e.room) || (opts.keep && !opts.keep(e))) continue;
    for (const w of model.weeks) {
      if (!(e.mask & (1 << (w - 1)))) continue;
      const k = `${w}:${e.day}`;
      const s = cell(occ, k);
      for (let p = e.sp; p <= e.ep; p++) s.add(e.room * 32 + p);
      if (e.conflict) conflicts.set(k, (conflicts.get(k) ?? 0) + 1);
      if (opts.changed?.(e, w)) changes.set(k, (changes.get(k) ?? 0) + 1);
    }
  }
  for (const b of model.blocks) {
    if (!roomSet.has(b.room)) continue;
    for (const w of model.weeks) {
      if (!(b.mask & (1 << (w - 1)))) continue;
      const s = cell(blk, `${w}:${b.day}`);
      for (let p = b.sp; p <= b.ep; p++) s.add(b.room * 32 + p);
    }
  }
  const out = new Map<string, HeatValue>();
  for (const w of model.weeks) {
    for (let d = 1; d <= 7; d++) {
      const k = `${w}:${d}`;
      const o = occ.get(k) ?? new Set<number>();
      const b = blk.get(k) ?? new Set<number>();
      const both = new Set([...o, ...b]);
      const byBuilding: Record<string, number> = {};
      for (const [bld, ids] of buildingRooms) {
        let n = 0;
        for (const x of both) if (ids.has(Math.floor(x / 32))) n++;
        byBuilding[bld] = n / Math.max(1, ids.size * PERIODS_PER_DAY);
      }
      let blockedOnly = 0;
      for (const x of b) if (!o.has(x)) blockedOnly++;
      out.set(k, { week: w, day: d, occupied: o.size, blocked: blockedOnly, capacity, occupancy: both.size / capacity, conflicts: conflicts.get(k) ?? 0, changes: changes.get(k) ?? 0, byBuilding });
    }
  }
  return out;
}

/** Sequential heat step 0..5 for a 0..1 occupancy (legend "%0 · 1–25 · 26–50 · 51–75 · 76–100"). */
export function heatStep(v: number): number {
  if (v <= 0) return 0;
  if (v <= 0.25) return 1;
  if (v <= 0.5) return 2;
  if (v <= 0.75) return 3;
  return 4 + (v > 0.9 ? 1 : 0);
}

/** Count-based metrics (conflicts, unplaced, changes) map onto the same 6 steps relative to the max. */
export function countStep(v: number, max: number): number {
  if (v <= 0 || max <= 0) return 0;
  return Math.min(5, Math.max(1, Math.ceil((v / max) * 5)));
}

/** Weekly mean of the 7 day cells (Term lens right column, scrubber ticks). */
export function weeklyMean(heat: Map<string, HeatValue>, week: number, days = 7): number {
  let s = 0;
  for (let d = 1; d <= days; d++) s += heat.get(`${week}:${d}`)?.occupancy ?? 0;
  return s / days;
}
