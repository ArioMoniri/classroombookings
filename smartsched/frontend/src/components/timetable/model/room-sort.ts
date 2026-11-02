/**
 * Room order in Çizelge (owner report 2026-11-02): the board columns, the day timeline and the strip board list the
 * rooms in one order the user picks. Code order is natural ("A101, A102, … A110", not "A101, A110, A102"): letters
 * compare as text (Turkish collation), digit runs as numbers, spaces and case are ignored ("A 101" = "a101").
 * Capacity orders use the seats the columns show (exam seats on an exam run), then the code.
 * The choice is per user in localStorage; storage that throws (private mode, quota, disabled) falls back to the default.
 */

export const ROOM_SORTS = ["code-asc", "code-desc", "cap-desc", "cap-asc"] as const;
export type RoomSort = (typeof ROOM_SORTS)[number];
export const DEFAULT_ROOM_SORT: RoomSort = "code-asc";

const collator = new Intl.Collator("tr", { sensitivity: "base", numeric: false });

/** "A 101" → ["A", 101]; "B-2a" → ["B-", 2, "A"]: text chunks upper-cased, digit runs as numbers, spaces dropped. */
export function codeChunks(code: string): (string | number)[] {
  const flat = code.replace(/\s+/g, "").toLocaleUpperCase("tr-TR");
  const out: (string | number)[] = [];
  for (const m of flat.matchAll(/(\d+)|(\D+)/g)) out.push(m[1] !== undefined ? Number(m[1]) : m[2]);
  return out;
}

/** Natural order of two room codes ("A101" < "A102" < "A110" < "B101"; "A 101" equals "A101"). */
export function compareRoomCodes(a: string, b: string): number {
  const x = codeChunks(a);
  const y = codeChunks(b);
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    const p = x[i];
    const q = y[i];
    if (typeof p === "number" && typeof q === "number") {
      if (p !== q) return p - q;
      continue;
    }
    // a number sorts before text at the same place ("A1" before "AB")
    if (typeof p === "number") return -1;
    if (typeof q === "number") return 1;
    const c = collator.compare(p, q);
    if (c !== 0) return c;
  }
  return x.length - y.length;
}

export interface SortableRoom {
  id: number;
  code: string;
  name: string;
  capacity: number;
  exam_capacity: number;
}

/** The seats a column shows: exam seats on an exam run (falling back to the room's own), else the room's own. */
export function seatsOf(r: SortableRoom, exam: boolean): number {
  return exam ? r.exam_capacity || r.capacity : r.capacity;
}

const codeOf = (r: SortableRoom) => r.code || r.name;

/** A new array in the chosen order; ties fall back to the natural code, then the id (stable across renders). */
export function sortRooms<T extends SortableRoom>(rooms: readonly T[], sort: RoomSort, exam = false): T[] {
  const byCode = (a: T, b: T) => compareRoomCodes(codeOf(a), codeOf(b)) || a.id - b.id;
  const list = [...rooms];
  switch (sort) {
    case "code-desc":
      return list.sort((a, b) => -byCode(a, b));
    case "cap-desc":
      return list.sort((a, b) => seatsOf(b, exam) - seatsOf(a, exam) || byCode(a, b));
    case "cap-asc":
      return list.sort((a, b) => seatsOf(a, exam) - seatsOf(b, exam) || byCode(a, b));
    default:
      return list.sort(byCode);
  }
}

export function isRoomSort(v: unknown): v is RoomSort {
  return typeof v === "string" && (ROOM_SORTS as readonly string[]).includes(v);
}

export const roomSortKey = (userKey: string) => `smartsched.calendar.roomSort.${userKey || "anon"}`;

export function readRoomSort(userKey: string, storage: Pick<Storage, "getItem"> | null = typeof window !== "undefined" ? window.localStorage : null): RoomSort {
  try {
    const v = storage?.getItem(roomSortKey(userKey));
    return isRoomSort(v) ? v : DEFAULT_ROOM_SORT;
  } catch {
    return DEFAULT_ROOM_SORT;
  }
}

export function writeRoomSort(userKey: string, sort: RoomSort, storage: Pick<Storage, "setItem" | "removeItem"> | null = typeof window !== "undefined" ? window.localStorage : null): void {
  try {
    if (sort === DEFAULT_ROOM_SORT) storage?.removeItem(roomSortKey(userKey));
    else storage?.setItem(roomSortKey(userKey), sort);
  } catch {
    /* storage refused (private mode, quota): the order still applies for this page */
  }
}
