import { describe, expect, it } from "vitest";
import { fixtureIndex } from "@/test/fixtures/calendar-index";
import { buildModel, roomSeats } from "./index-model";
import { DEFAULT_ROOM_SORT, codeChunks, compareRoomCodes, readRoomSort, roomSortKey, sortRooms, writeRoomSort } from "./room-sort";

const room = (id: number, code: string, capacity: number, exam_capacity = 0) => ({ id, code, name: code, capacity, exam_capacity });

describe("room sort (owner report: natural code order and capacity)", () => {
  it("splits a code into text and numbers, ignoring spaces and case", () => {
    expect(codeChunks("A 101")).toEqual(["A", 101]);
    expect(codeChunks("a101")).toEqual(["A", 101]);
    expect(codeChunks("B-2a")).toEqual(["B-", 2, "A"]);
  });

  it("orders codes naturally: building letter, then number", () => {
    const codes = ["A110", "B101", "A102", "A 101", "A2", "A103"];
    expect([...codes].sort(compareRoomCodes)).toEqual(["A2", "A 101", "A102", "A103", "A110", "B101"]);
    expect(compareRoomCodes("A 101", "A101")).toBe(0);
    expect(compareRoomCodes("a101", "A101")).toBe(0);
  });

  it("uses Turkish collation for the letters (Ç after C, İ after I)", () => {
    expect(["D101", "Ç101", "C101"].sort(compareRoomCodes)).toEqual(["C101", "Ç101", "D101"]);
  });

  const rooms = [room(1, "A110", 40, 20), room(2, "A102", 120, 60), room(3, "B101", 40, 30), room(4, "A 101", 80, 0)];

  it("code A→Z and Z→A", () => {
    expect(sortRooms(rooms, "code-asc").map((r) => r.code)).toEqual(["A 101", "A102", "A110", "B101"]);
    expect(sortRooms(rooms, "code-desc").map((r) => r.code)).toEqual(["B101", "A110", "A102", "A 101"]);
  });

  it("capacity high→low and low→high, ties by natural code", () => {
    expect(sortRooms(rooms, "cap-desc").map((r) => r.code)).toEqual(["A102", "A 101", "A110", "B101"]);
    expect(sortRooms(rooms, "cap-asc").map((r) => r.code)).toEqual(["A110", "B101", "A 101", "A102"]);
  });

  it("an exam run sorts by exam seats, a room without them by its own seats", () => {
    // exam seats: A110 20, A102 60, B101 30, A 101 → 80 (no exam capacity: falls back to the room's own)
    expect(sortRooms(rooms, "cap-desc", true).map((r) => r.code)).toEqual(["A 101", "A102", "B101", "A110"]);
  });

  it("does not mutate the input", () => {
    const copy = [...rooms];
    sortRooms(rooms, "cap-asc");
    expect(rooms).toEqual(copy);
  });

  it("persists per user and survives a storage that throws", () => {
    const mem = new Map<string, string>();
    const store = { getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => void mem.set(k, v), removeItem: (k: string) => void mem.delete(k) };
    expect(readRoomSort("7", store)).toBe(DEFAULT_ROOM_SORT);
    writeRoomSort("7", "cap-desc", store);
    expect(mem.get(roomSortKey("7"))).toBe("cap-desc");
    expect(readRoomSort("7", store)).toBe("cap-desc");
    expect(readRoomSort("8", store)).toBe(DEFAULT_ROOM_SORT);
    writeRoomSort("7", DEFAULT_ROOM_SORT, store);
    expect(mem.has(roomSortKey("7"))).toBe(false);
    mem.set(roomSortKey("9"), "bogus");
    expect(readRoomSort("9", store)).toBe(DEFAULT_ROOM_SORT);
    const broken = { getItem: () => { throw new Error("denied"); }, setItem: () => { throw new Error("quota"); }, removeItem: () => { throw new Error("denied"); } };
    expect(readRoomSort("7", broken)).toBe(DEFAULT_ROOM_SORT);
    expect(() => writeRoomSort("7", "cap-asc", broken)).not.toThrow();
  });
});

describe("roomSeats (inspector: capacity and exam capacity)", () => {
  it("sums the rooms' own seats and exam seats; unknown ids count nothing", () => {
    const model = buildModel(fixtureIndex());
    expect(roomSeats(model, [1])).toEqual({ capacity: 156, exam: 74 });
    expect(roomSeats(model, [1, 2, 999])).toEqual({ capacity: 214, exam: 104 });
  });
  it("the fixture's rooms sort naturally by code", () => {
    const model = buildModel(fixtureIndex());
    expect(sortRooms(model.rooms, "code-asc").map((r) => r.code)).toEqual(["A101", "A104", "A204", "C201", "C202"]);
    expect(sortRooms(model.rooms, "cap-asc", true).map((r) => r.code)).toEqual(["A101", "C202", "A104", "C201", "A204"]);
  });
});
