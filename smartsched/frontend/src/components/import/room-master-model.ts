/**
 * Room master preview (ROADMAP P19-I7): the planner's room list (`code, capacity, exam_capacity, tags, building,
 * floor, bookable[, notes]`) read in the browser and compared with the rooms the backend has, before
 * `POST /imports/room-master` applies it. The rules mirror `app/importers/room_master.py`:
 *
 * - header row required, any column order, `;` `,` or tab separated, UTF-8 (BOM allowed); `#` lines are comments;
 * - an empty cell leaves the stored value unchanged; `tags` replaces the list (`-` clears it, `|` `;` `/` or
 *   spaces separate); `bookable` is 1/0, yes/no, true/false, evet/hayır, or empty = bookable when it has a capacity.
 *
 * The backend also reads alias spellings ("B Blok Bilg. Lab." is B 207) and creates rooms it does not know; the
 * preview matches plain codes only, so it marks other rows "not matched" and lets the server decide.
 */

export const COLUMNS = ["code", "capacity", "exam_capacity", "tags", "building", "floor", "bookable", "notes"] as const;
const TRUE = new Set(["1", "yes", "y", "true", "evet", "e", "x"]);
const FALSE = new Set(["0", "no", "n", "false", "hayır", "hayir", "h"]);

export interface MasterRow {
  line: number;
  code: string;
  capacity: number | null;
  exam_capacity: number | null;
  tags: string[] | null;
  building: string | null;
  floor: string | null;
  bookable: boolean | null;
}

export interface MasterParse {
  rows: MasterRow[];
  /** line errors and header notes, as the backend words them */
  errors: { line: number | null; message: string; value?: string }[];
}

const fold = (s: string) => s.toLocaleLowerCase("tr-TR").trim();
const upper = (s: string) => s.toLocaleUpperCase("tr-TR");
/** "A 101", "a-101", "A101" → "A101" (the backend's canonical room code for plain spellings) */
export const canonicalCode = (s: string) => upper(s).replace(/[\s.\-_/]+/g, "");

/** One CSV record per line, with quoted fields ("a;b", "say ""hi"""); the file has no multi-line cells. */
export function splitCsvLine(line: string, sep: string): string[] {
  const out: string[] = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]!;
    if (quoted) {
      if (ch === '"' && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else cur += ch;
    } else if (ch === '"' && cur.trim() === "") {
      quoted = true;
      cur = "";
    } else if (ch === sep) {
      out.push(cur);
      cur = "";
    } else cur += ch;
  }
  out.push(cur);
  return out;
}

function sniff(header: string): string {
  const counts = [",", ";", "\t"].map((c) => [c, header.split(c).length - 1] as const);
  return counts.sort((a, b) => b[1] - a[1])[0]![1] > 0 ? counts[0]![0] : ",";
}

function int(v: string | undefined): number | null {
  const s = (v ?? "").trim();
  if (!s) return null;
  const n = Number(s.replace(/\s/g, ""));
  if (!Number.isInteger(n) || n < 0) throw new Error(`not a non-negative integer: '${s}'`);
  return n;
}

function bool(v: string | undefined): boolean | null {
  const s = fold(v ?? "");
  if (!s) return null;
  if (TRUE.has(s)) return true;
  if (FALSE.has(s)) return false;
  throw new Error(`not a yes/no value: '${(v ?? "").trim()}'`);
}

function tags(v: string | undefined): string[] | null {
  const s = (v ?? "").trim();
  if (!s) return null;
  if (s === "-") return [];
  return [...new Set(s.replace(/[|;/]/g, " ").split(/\s+/).map((x) => upper(x.trim())).filter(Boolean))];
}

export function parseRoomMaster(text: string): MasterParse {
  const all = text.replace(/^﻿/, "").split(/\r?\n/);
  const lines = all.map((l, i) => ({ text: l, no: i + 1 })).filter((l) => l.text.trim() && !l.text.trimStart().startsWith("#"));
  if (!lines.length) return { rows: [], errors: [{ line: null, message: "empty room master" }] };
  const sep = sniff(lines[0]!.text);
  const header = splitCsvLine(lines[0]!.text, sep).map(fold);
  if (!header.includes("code")) return { rows: [], errors: [{ line: null, message: `room master needs a 'code' column; got ${header.join(", ")}` }] };
  const errors: MasterParse["errors"] = [];
  const unknown = header.filter((h) => h && !(COLUMNS as readonly string[]).includes(h));
  if (unknown.length) errors.push({ line: null, message: `unknown column(s) ignored: ${unknown.join(", ")}` });
  const rows: MasterRow[] = [];
  // the backend numbers data lines from 2 after dropping comments and blanks
  lines.slice(1).forEach((l, i) => {
    const line = i + 2;
    const cells = splitCsvLine(l.text, sep);
    const get = (col: string) => {
      const at = header.indexOf(col);
      return at < 0 ? undefined : cells[at];
    };
    const raw = (get("code") ?? "").trim();
    if (!raw || !/[0-9A-Za-zÇĞİÖŞÜçğıöşü]/.test(raw)) {
      errors.push({ line, message: "cannot read room code", value: raw });
      return;
    }
    try {
      rows.push({
        line,
        code: raw,
        capacity: int(get("capacity")),
        exam_capacity: int(get("exam_capacity")),
        tags: tags(get("tags")),
        building: (get("building") ?? "").trim().toUpperCase() || null,
        floor: (get("floor") ?? "").trim() || null,
        bookable: bool(get("bookable")),
      });
    } catch (e) {
      errors.push({ line, message: e instanceof Error ? e.message : String(e), value: raw });
    }
  });
  return { rows, errors };
}

export interface RoomLike {
  id: number;
  code: string;
  display_name: string;
  building_code: string;
  floor: number | string | null;
  capacity: number;
  exam_capacity: number;
  tags: readonly string[];
  is_bookable: boolean;
}

export type FieldChange = { field: "capacity" | "exam_capacity" | "tags" | "building" | "floor" | "bookable"; from: string; to: string };
export type DiffStatus = "changed" | "same" | "unmatched" | "duplicate";
export interface DiffRow {
  line: number;
  code: string;
  room: RoomLike | null;
  status: DiffStatus;
  changes: FieldChange[];
}

const show = (v: unknown) => (v === null || v === undefined || v === "" ? "–" : Array.isArray(v) ? (v.length ? v.join(" ") : "–") : String(v));

/** Compare the parsed rows with the stored rooms field by field, as the importer will apply them. */
export function diffRoomMaster(rows: readonly MasterRow[], rooms: readonly RoomLike[]): DiffRow[] {
  const byCode = new Map<string, RoomLike>();
  for (const r of rooms) {
    byCode.set(canonicalCode(r.code), r);
    byCode.set(canonicalCode(r.display_name), r);
  }
  const lastLine = new Map<string, number>();
  for (const r of rows) lastLine.set(canonicalCode(r.code), r.line);
  return rows.map((r): DiffRow => {
    const key = canonicalCode(r.code);
    const room = byCode.get(key) ?? null;
    if (lastLine.get(key) !== r.line) return { line: r.line, code: r.code, room, status: "duplicate", changes: [] }; // the last one wins
    if (!room) return { line: r.line, code: r.code, room: null, status: "unmatched", changes: [] };
    const changes: FieldChange[] = [];
    const cap = r.capacity ?? room.capacity;
    const exam = r.exam_capacity ?? room.exam_capacity;
    if (r.capacity !== null && r.capacity !== room.capacity) changes.push({ field: "capacity", from: show(room.capacity), to: show(r.capacity) });
    if (r.exam_capacity !== null && r.exam_capacity !== room.exam_capacity) changes.push({ field: "exam_capacity", from: show(room.exam_capacity), to: show(r.exam_capacity) });
    if (r.tags !== null && r.tags.join("|") !== [...room.tags].join("|")) changes.push({ field: "tags", from: show([...room.tags]), to: show(r.tags) });
    if (r.building && r.building !== upper(room.building_code)) changes.push({ field: "building", from: show(room.building_code), to: r.building });
    if (r.floor !== null && r.floor !== (room.floor === null ? null : String(room.floor))) changes.push({ field: "floor", from: show(room.floor), to: r.floor });
    const bookable = r.bookable ?? Boolean(cap || exam);
    if (bookable !== room.is_bookable) changes.push({ field: "bookable", from: room.is_bookable ? "1" : "0", to: bookable ? "1" : "0" });
    return { line: r.line, code: r.code, room, status: changes.length ? "changed" : "same", changes };
  });
}

export function diffCounts(diff: readonly DiffRow[]): Record<DiffStatus, number> {
  const out: Record<DiffStatus, number> = { changed: 0, same: 0, unmatched: 0, duplicate: 0 };
  for (const d of diff) out[d.status] += 1;
  return out;
}
