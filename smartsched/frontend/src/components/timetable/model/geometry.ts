/**
 * Layout math for the calendar lenses (calendar.md §6, §7.6, §9.7, §13). Pure functions, no DOM.
 * Period rows have variable height (P12 is a 30-minute transition at 0.6×), so positions come from a
 * prefix-sum table instead of `p * rowH`.
 */
import { PERIODS, PERIODS_PER_DAY, parseClock } from "@/lib/time";

export type Density = "compact" | "standard" | "comfortable";

/** Zoom steps 1..5 (calendar.md §7.6: row height 24/32/40/52/64, independent of density). */
export const ROW_STEPS = [24, 32, 40, 52, 64] as const;
export const DEFAULT_ZOOM = 3;
/** Week-strip slot widths per zoom step (calendar.md §6.2: 6, 10, 14, 20 (default), 28). */
export const STRIP_SLOT_STEPS = [6, 10, 14, 20, 28] as const;
/** Day-timeline pixels per minute per zoom step (1.4 px/min standard → 860 min ≈ 1,204 px). */
export const MINUTE_PX_STEPS = [0.8, 1.1, 1.4, 1.8, 2.3] as const;

export const ROOM_COL: Record<Density, number> = { compact: 96, standard: 120, comfortable: 152 };
export const GUTTER_W = 56;
export const ROOM_HEADER_H = 48;
export const BAND_H = 24;
export const P12 = 12;
export const P12_SCALE = 0.6;
export const DAY_START_MIN = parseClock(PERIODS[0].start) ?? 510;
export const DAY_END_MIN = parseClock(PERIODS[PERIODS_PER_DAY - 1].end) ?? 1370;

export function clampZoom(z: number): number {
  return Math.min(ROW_STEPS.length, Math.max(1, Math.round(z)));
}

export function rowHeightFor(zoom: number): number {
  return ROW_STEPS[clampZoom(zoom) - 1];
}

export interface RowTable {
  /** top offset of period p (1-based) at index p-1; tops[18] = total height */
  tops: number[];
  heights: number[];
  total: number;
}

/** Prefix-sum table of period rows for a base row height (P12 at 0.6×, rounded to whole px). */
export function rowTable(rowH: number): RowTable {
  const heights = PERIODS.map((p) => (p.index === P12 ? Math.round(rowH * P12_SCALE) : rowH));
  const tops = [0];
  for (const h of heights) tops.push(tops[tops.length - 1] + h);
  return { tops, heights, total: tops[tops.length - 1] };
}

export function periodTop(t: RowTable, p: number): number {
  return t.tops[Math.min(PERIODS_PER_DAY, Math.max(1, p)) - 1];
}

/** Height of an inclusive period span minus the 1 px gap between stacked chips. */
export function spanHeight(t: RowTable, sp: number, ep: number): number {
  return t.tops[Math.min(PERIODS_PER_DAY, ep)] - t.tops[Math.max(1, sp) - 1] - 1;
}

/** Period under a y offset (binary search; clamps to 1..18). */
export function periodAt(t: RowTable, y: number): number {
  if (y <= 0) return 1;
  if (y >= t.total) return PERIODS_PER_DAY;
  let lo = 0;
  let hi = PERIODS_PER_DAY - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (t.tops[mid] <= y) lo = mid;
    else hi = mid - 1;
  }
  return lo + 1;
}

/** Nearest period boundary (start of a period) to y, as a 1-based period index. */
export function nearestPeriodStart(t: RowTable, y: number): number {
  let best = 1;
  let dist = Number.POSITIVE_INFINITY;
  for (let p = 1; p <= PERIODS_PER_DAY; p++) {
    const d = Math.abs(t.tops[p - 1] - y);
    if (d < dist) {
      dist = d;
      best = p;
    }
  }
  return best;
}

/* ----------------------------------------------------------------- day timeline (minutes → x) */

export function minuteX(min: number, pxPerMin: number): number {
  return (Math.min(DAY_END_MIN, Math.max(DAY_START_MIN, min)) - DAY_START_MIN) * pxPerMin;
}

export function periodStartMin(p: number): number {
  return parseClock(PERIODS[Math.min(PERIODS_PER_DAY, Math.max(1, p)) - 1].start) ?? DAY_START_MIN;
}

export function periodEndMin(p: number): number {
  return parseClock(PERIODS[Math.min(PERIODS_PER_DAY, Math.max(1, p)) - 1].end) ?? DAY_END_MIN;
}

/** Period containing (or, in a break, following) a minute of the day; null outside 08:30–22:50. */
export function periodAtMinute(min: number): number | null {
  if (min < DAY_START_MIN || min > DAY_END_MIN) return null;
  for (let p = 1; p <= PERIODS_PER_DAY; p++) {
    if (min < periodEndMin(p)) return p;
  }
  return PERIODS_PER_DAY;
}

/**
 * Now-line offset inside a period grid: interpolated within the period (13:47 is 17/40 of P7); during a
 * 10-minute break it sits on the boundary between the two rows (calendar.md §7.4).
 */
export function nowOffset(t: RowTable, min: number): number | null {
  if (min < DAY_START_MIN || min > DAY_END_MIN) return null;
  for (let p = 1; p <= PERIODS_PER_DAY; p++) {
    const s = periodStartMin(p);
    const e = periodEndMin(p);
    if (min < s) return t.tops[p - 1];
    if (min <= e) return t.tops[p - 1] + ((min - s) / Math.max(1, e - s)) * t.heights[p - 1];
  }
  return t.total;
}

/* ----------------------------------------------------------------- lanes (side-by-side overlaps) */

export interface LaneInput {
  id: string | number;
  sp: number;
  ep: number;
}

/**
 * Greedy interval partitioning inside clusters of mutually overlapping spans: each item gets a lane and the
 * lane count of its own cluster (so a lone event elsewhere in the column keeps the full width).
 */
export function layoutLanes<T extends LaneInput>(items: readonly T[]): Map<T["id"], { lane: number; lanes: number }> {
  const sorted = [...items].sort((a, b) => a.sp - b.sp || b.ep - a.ep);
  const out = new Map<T["id"], { lane: number; lanes: number }>();
  let cluster: { item: T; lane: number }[] = [];
  let clusterEnd = -1;
  let laneEnds: number[] = [];
  const flush = () => {
    const lanes = Math.max(1, laneEnds.length);
    for (const c of cluster) out.set(c.item.id, { lane: c.lane, lanes });
    cluster = [];
    laneEnds = [];
  };
  for (const it of sorted) {
    if (cluster.length && it.sp > clusterEnd) flush();
    let lane = laneEnds.findIndex((end) => end < it.sp);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(it.ep);
    } else laneEnds[lane] = it.ep;
    cluster.push({ item: it, lane });
    clusterEnd = Math.max(clusterEnd, it.ep);
  }
  flush();
  return out;
}

/* ----------------------------------------------------------------- virtualisation + zoom anchor */

/** Visible index window for a uniform list (overscan on both sides). */
export function visibleRange(scroll: number, viewport: number, itemSize: number, count: number, overscan = 4): [number, number] {
  if (count === 0 || itemSize <= 0) return [0, -1];
  const first = Math.max(0, Math.floor(scroll / itemSize) - overscan);
  const last = Math.min(count - 1, Math.ceil((scroll + viewport) / itemSize) + overscan);
  return [first, last];
}

/**
 * Instant anchored re-layout on zoom (motion.md §3.2: no row-height interpolation): returns the new
 * scrollTop that keeps the content point under the pointer at the same screen position.
 * `pointerY` is relative to the scroll viewport.
 */
export function anchoredScroll(oldT: RowTable, newT: RowTable, scrollTop: number, pointerY: number): number {
  const y = scrollTop + pointerY;
  const p = periodAt(oldT, y);
  const frac = (y - oldT.tops[p - 1]) / Math.max(1, oldT.heights[p - 1]);
  const newY = newT.tops[p - 1] + frac * newT.heights[p - 1];
  return Math.max(0, newY - pointerY);
}

/** Horizontal counterpart for column widths (week strip, timeline). */
export function anchoredScrollLinear(oldUnit: number, newUnit: number, scrollLeft: number, pointerX: number): number {
  const content = (scrollLeft + pointerX) / Math.max(0.0001, oldUnit);
  return Math.max(0, content * newUnit - pointerX);
}

/** Wheel / pinch gesture → zoom delta (macOS trackpad pinch arrives as wheel + ctrlKey). */
export function zoomDeltaFromWheel(deltaY: number, accumulated: number, threshold = 60): { step: number; rest: number } {
  const total = accumulated + deltaY;
  if (Math.abs(total) < threshold) return { step: 0, rest: total };
  return { step: total < 0 ? 1 : -1, rest: 0 };
}
