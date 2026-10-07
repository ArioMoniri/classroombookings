/**
 * Pure layout utilities for the timetable grid (rooms × periods).
 * Events are inclusive period spans; the grid places them as absolutely
 * positioned blocks inside a room row so the DOM never reflows on load.
 */
import { PERIODS_PER_DAY, rangesOverlap } from "@/lib/time";

export type EventStatus = "ok" | "locked" | "conflict" | "block" | "tip" | "pc" | "warning";

export interface GridSpanInput {
  id: string;
  roomId: number;
  day: number;
  startPeriod: number;
  endPeriod: number;
  status: EventStatus;
}

export interface PlacedSpan<T extends GridSpanInput = GridSpanInput> {
  item: T;
  /** 0-based column index inside the row */
  col: number;
  /** number of period columns covered */
  colSpan: number;
  /** lane index when overlapping spans must stack (conflicts) */
  lane: number;
  /** total lanes in this row for the day */
  lanes: number;
}

export interface RowLayout<T extends GridSpanInput = GridSpanInput> {
  roomId: number;
  day: number;
  spans: PlacedSpan<T>[];
  /** true when two or more spans overlap in this row */
  hasConflict: boolean;
}

export function clampSpan(start: number, end: number): [number, number] {
  const s = Math.max(1, Math.min(PERIODS_PER_DAY, start));
  const e = Math.max(s, Math.min(PERIODS_PER_DAY, end));
  return [s, e];
}

/**
 * Lay out all spans for one room & day. Overlapping spans are assigned to lanes
 * (greedy interval partitioning) so conflicts are visible instead of hidden.
 */
export function layoutRow<T extends GridSpanInput>(items: readonly T[], roomId: number, day: number): RowLayout<T> {
  const relevant = items
    .filter((i) => i.roomId === roomId && i.day === day)
    .slice()
    .sort((a, b) => a.startPeriod - b.startPeriod || b.endPeriod - a.endPeriod);

  const laneEnds: number[] = [];
  const placed: PlacedSpan<T>[] = [];
  let hasConflict = false;

  for (const item of relevant) {
    const [s, e] = clampSpan(item.startPeriod, item.endPeriod);
    let lane = laneEnds.findIndex((end) => end < s);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(e);
      if (lane > 0) hasConflict = true;
    } else {
      laneEnds[lane] = e;
    }
    placed.push({ item, col: s - 1, colSpan: e - s + 1, lane, lanes: 1 });
  }
  const lanes = Math.max(1, laneEnds.length);
  for (const p of placed) p.lanes = lanes;
  return { roomId, day, spans: placed, hasConflict };
}

/** Index spans by room so each virtualised row can be laid out in O(k). */
export function groupByRoom<T extends GridSpanInput>(items: readonly T[]): Map<number, T[]> {
  const map = new Map<number, T[]>();
  for (const item of items) {
    const list = map.get(item.roomId);
    if (list) list.push(item);
    else map.set(item.roomId, [item]);
  }
  return map;
}

export interface ConflictCheck {
  ok: boolean;
  conflictIds: string[];
}

/**
 * Would placing `moving` at (roomId, day, start, end) overlap anything else?
 * Blocks (pre-occupied slots) and other events count; the moving item itself is ignored.
 */
export function checkPlacement<T extends GridSpanInput>(
  items: readonly T[],
  moving: Pick<T, "id">,
  target: { roomId: number; day: number; startPeriod: number; endPeriod: number },
): ConflictCheck {
  const [s, e] = clampSpan(target.startPeriod, target.endPeriod);
  if (target.endPeriod > PERIODS_PER_DAY || target.startPeriod < 1) {
    return { ok: false, conflictIds: ["out-of-range"] };
  }
  const conflictIds = items
    .filter((i) => i.id !== moving.id && i.roomId === target.roomId && i.day === target.day)
    .filter((i) => rangesOverlap(i.startPeriod, i.endPeriod, s, e))
    .map((i) => i.id);
  return { ok: conflictIds.length === 0, conflictIds };
}

/** CSS grid-column value for a 0-based col and span (1-based grid lines). */
export function gridColumn(col: number, colSpan: number): string {
  return `${col + 1} / span ${colSpan}`;
}

/** Percentage-based left/width for absolute positioning fallbacks. */
export function spanRect(col: number, colSpan: number, columns = PERIODS_PER_DAY): { left: string; width: string } {
  const unit = 100 / columns;
  return { left: `${(col * unit).toFixed(4)}%`, width: `${(colSpan * unit).toFixed(4)}%` };
}
