/**
 * Slot magnetism (calendar.md §9.2, motion pattern §7): the ghost's top-left edge snaps to the nearest
 * period boundary and column once within 16 px (full pull inside radius/3, linear falloff to the radius),
 * and an invalid target offers the nearest valid start within ±3 periods in the same room/day.
 */
import { PERIODS_PER_DAY } from "@/lib/time";
import { nearestPeriodStart, type RowTable } from "./geometry";

export const MAGNET_RADIUS = 16;

export interface SnapResult {
  /** 0-based column (room / day) under the ghost's left edge */
  col: number;
  /** 1-based start period the ghost's top edge snaps to */
  period: number;
  /** snapped content-space position of the slot's top-left */
  slotX: number;
  slotY: number;
  /** ghost position after the magnetic pull (content space) */
  x: number;
  y: number;
  /** 0..1 strength of the pull (1 = locked onto the slot) */
  pull: number;
}

/** Pull factor for a distance: 1 inside radius/3, linear to 0 at the radius, 0 beyond. */
export function pullFactor(d: number, radius = MAGNET_RADIUS): number {
  if (d >= radius) return 0;
  const inner = radius / 3;
  if (d <= inner) return 1;
  return 1 - (d - inner) / (radius - inner);
}

/**
 * Snap a ghost whose top-left is at (x, y) in content space (gutter excluded) onto a grid of uniform
 * columns (`colW`, `cols`) and variable rows (`rows`). The ghost never rests between periods: the
 * reported slot is always the nearest period start, the pull only affects the drawn position.
 */
export function snapGhost(x: number, y: number, colW: number, cols: number, rows: RowTable, span: number, radius = MAGNET_RADIUS): SnapResult {
  const col = Math.min(cols - 1, Math.max(0, Math.round(x / colW)));
  const maxStart = Math.max(1, PERIODS_PER_DAY - span + 1);
  const period = Math.min(maxStart, nearestPeriodStart(rows, y));
  const slotX = col * colW;
  const slotY = rows.tops[period - 1];
  const dx = slotX - x;
  const dy = slotY - y;
  const pull = pullFactor(Math.hypot(dx, dy), radius);
  return { col, period, slotX, slotY, x: x + dx * pull, y: y + dy * pull, pull };
}

/**
 * Nearest valid start period in the same room/day within ±range (ties prefer earlier), or null.
 * `isValid(start)` is the pure move check for that start.
 */
export function nearestValidStart(start: number, span: number, isValid: (start: number) => boolean, range = 3): number | null {
  for (let d = 1; d <= range; d++) {
    for (const s of [start - d, start + d]) {
      if (s < 1 || s + span - 1 > PERIODS_PER_DAY) continue;
      if (isValid(s)) return s;
    }
  }
  return null;
}
