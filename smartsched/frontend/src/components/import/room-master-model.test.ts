import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { canonicalCode, diffCounts, diffRoomMaster, parseRoomMaster, splitCsvLine, type RoomLike } from "./room-master-model";

const FIXTURE = path.resolve(__dirname, "../../../../backend/tests/fixtures/room_master.csv");

const room = (code: string, over: Partial<RoomLike> = {}): RoomLike => ({ id: 1, code: canonicalCode(code), display_name: code, building_code: code[0]!, floor: 1, capacity: 58, exam_capacity: 30, tags: [], is_bookable: true, ...over });

describe("parseRoomMaster (mirrors app/importers/room_master.py)", () => {
  it("reads the repository's real room_master.csv: comments skipped, every row typed", () => {
    const { rows, errors } = parseRoomMaster(readFileSync(FIXTURE, "utf-8"));
    expect(errors).toEqual([]);
    expect(rows.length).toBeGreaterThan(80);
    expect(rows[0]).toEqual({ line: 2, code: "A 101", capacity: 58, exam_capacity: 30, tags: null, building: "A", floor: "1", bookable: true });
    expect(rows.find((r) => r.code === "A 103")?.tags).toEqual(["PC"]);
  });

  it("accepts ; and tabs, quoted cells, a BOM, - to clear tags and Turkish yes/no", () => {
    const { rows, errors } = parseRoomMaster('﻿Code;Capacity;tags;bookable;notes\nA 101;60;-;hayır;"a; b"\nB 207;;pc|tıp;evet;\n;;;;\nC z01;-3;;;\nD 1;5;;belki;');
    expect(rows.map((r) => [r.code, r.capacity, r.tags, r.bookable])).toEqual([
      ["A 101", 60, [], false],
      ["B 207", null, ["PC", "TIP"], true],
    ]);
    expect(errors.map((e) => e.line)).toEqual([4, 5, 6]);
    expect(errors[1]!.message).toMatch(/non-negative integer/);
    expect(errors[2]!.message).toMatch(/yes\/no/);
  });

  it("needs a code column", () => {
    expect(parseRoomMaster("room;capacity\nA 101;5").errors[0]!.message).toMatch(/needs a 'code' column/);
    expect(parseRoomMaster("# only a comment\n").errors[0]!.message).toBe("empty room master");
  });

  it("splits quoted CSV cells with doubled quotes", () => {
    expect(splitCsvLine('a,"b, ""c""",d', ",")).toEqual(["a", 'b, "c"', "d"]);
  });
});

describe("diffRoomMaster", () => {
  it("lists changed fields, unchanged rooms, rooms the preview cannot match and duplicates (last wins)", () => {
    const { rows } = parseRoomMaster("code,capacity,exam_capacity,tags,building,floor,bookable\nA 101,60,30,,A,1,1\nA 102,58,30,,A,1,\nZ 999,10,,,Z,0,\nA-102,58,30,PC,A,2,0");
    const diff = diffRoomMaster(rows, [room("A 101"), room("A 102")]);
    expect(diff.map((d) => [d.code, d.status])).toEqual([
      ["A 101", "changed"],
      ["A 102", "duplicate"],
      ["Z 999", "unmatched"],
      ["A-102", "changed"],
    ]);
    expect(diff[0]!.changes).toEqual([{ field: "capacity", from: "58", to: "60" }]);
    expect(diff[3]!.changes.map((c) => c.field)).toEqual(["tags", "floor", "bookable"]);
    expect(diffCounts(diff)).toEqual({ changed: 2, same: 0, unmatched: 1, duplicate: 1 });
  });

  it("derives bookable from the capacity when the cell is empty, like the importer", () => {
    const { rows } = parseRoomMaster("code,capacity,exam_capacity\nA 101,0,0");
    expect(diffRoomMaster(rows, [room("A 101")])[0]!.changes).toEqual([
      { field: "capacity", from: "58", to: "0" },
      { field: "exam_capacity", from: "30", to: "0" },
      { field: "bookable", from: "1", to: "0" },
    ]);
  });
});
