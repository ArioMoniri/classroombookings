/**
 * Ghost overlay compare (calendar.md §9.9): match run A and run B by request id (or label for board rows)
 * plus week; categorise Same / Moved / Only in A / Only in B. Ghosts are drawn only where they differ.
 */
import type { IndexAssignment } from "@/lib/api/calendar";

export interface GhostPlacement {
  key: string;
  label: string;
  room: number;
  day: number;
  sp: number;
  ep: number;
  week: number;
  /** "moved" ghosts point at the A-side assignment id */
  aid: number | null;
  kind: "moved" | "onlyB";
}

export interface CompareResult {
  moved: number;
  onlyA: number;
  onlyB: number;
  movedAids: Set<number>;
  onlyAAids: Set<number>;
  /** week → ghosts of run B that differ from A */
  ghosts: Map<number, GhostPlacement[]>;
  movedWeeks: Map<number, Set<number>>;
}

const matchKey = (a: IndexAssignment) => (a.mr ? `m${a.mr}` : a.ex ? `e${a.ex}` : `l${a.label}`);

function explode(rows: readonly IndexAssignment[], allWeeks: readonly number[]): Map<string, IndexAssignment> {
  const out = new Map<string, IndexAssignment>();
  for (const a of rows) for (const w of a.weeks.length ? a.weeks : allWeeks) out.set(`${matchKey(a)}#${w}`, a);
  return out;
}

const samePlace = (a: IndexAssignment, b: IndexAssignment) => a.day === b.day && a.sp === b.sp && a.ep === b.ep && a.rooms.join(",") === b.rooms.join(",");

export function compareRuns(a: readonly IndexAssignment[], b: readonly IndexAssignment[], allWeeks: readonly number[]): CompareResult {
  const A = explode(a, allWeeks);
  const B = explode(b, allWeeks);
  const res: CompareResult = { moved: 0, onlyA: 0, onlyB: 0, movedAids: new Set(), onlyAAids: new Set(), ghosts: new Map(), movedWeeks: new Map() };
  const addGhost = (week: number, g: GhostPlacement) => {
    const list = res.ghosts.get(week) ?? [];
    list.push(g);
    res.ghosts.set(week, list);
  };
  for (const [k, x] of A) {
    const week = Number(k.split("#")[1]);
    const y = B.get(k);
    if (!y) {
      res.onlyA++;
      res.onlyAAids.add(x.id);
      continue;
    }
    if (!samePlace(x, y)) {
      res.moved++;
      res.movedAids.add(x.id);
      const s = res.movedWeeks.get(x.id) ?? new Set<number>();
      s.add(week);
      res.movedWeeks.set(x.id, s);
      for (const room of y.rooms) addGhost(week, { key: `g${y.id}:${room}:${week}`, label: y.label, room, day: y.day, sp: y.sp, ep: y.ep, week, aid: x.id, kind: "moved" });
    }
  }
  for (const [k, y] of B) {
    if (A.has(k)) continue;
    const week = Number(k.split("#")[1]);
    res.onlyB++;
    for (const room of y.rooms) addGhost(week, { key: `g${y.id}:${room}:${week}`, label: y.label, room, day: y.day, sp: y.sp, ep: y.ep, week, aid: null, kind: "onlyB" });
  }
  return res;
}
