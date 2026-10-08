import { describe, expect, it } from "vitest";
import { checkMove, slotFree } from "./check";
import { compareRuns } from "./compare";
import { dateOf, monthGrid, rangeTitle, weekDayOf } from "./dates";
import { EMPTY_FILTERS, eventPasses, fold, roomPasses } from "./filters";
import {
  anchoredScroll,
  layoutLanes,
  nowOffset,
  periodAt,
  rowTable,
  spanHeight,
  visibleRange,
  zoomDeltaFromWheel,
} from "./geometry";
import { computeHeat, heatStep } from "./heat";
import { buildModel, eventsOf, maskOf, weeksOfMask } from "./index-model";
import { assignment, fixtureIndex } from "./fixtures";
import { nearestValidStart, pullFactor, snapGhost } from "./magnet";
import { lensDirection, lensForKey, parseViewState, serializeViewState, weekInRun } from "./view-state";

describe("layout math", () => {
  const t = rowTable(40);
  it("P12 is a 0.6× transition row and tops are a prefix sum", () => {
    expect(t.heights[11]).toBe(24);
    expect(t.tops[6]).toBe(240);
    expect(t.total).toBe(17 * 40 + 24);
  });
  it("span height leaves the 1 px stacking gap and crosses P12", () => {
    expect(spanHeight(t, 7, 9)).toBe(119);
    expect(spanHeight(t, 11, 13)).toBe(40 + 24 + 40 - 1);
  });
  it("y → period by binary search, clamped", () => {
    expect(periodAt(t, 0)).toBe(1);
    expect(periodAt(t, 241)).toBe(7);
    expect(periodAt(t, 440 + 5)).toBe(12);
    expect(periodAt(t, 99999)).toBe(18);
  });
  it("now-line interpolates inside a period and parks on the boundary in a break", () => {
    expect(nowOffset(t, 13 * 60 + 47)).toBeCloseTo(240 + (17 / 40) * 40);
    expect(nowOffset(t, 14 * 60 + 15)).toBe(280); // 14:10–14:20 break → top of P8
    expect(nowOffset(t, 7 * 60)).toBeNull();
  });
  it("lanes are per overlapping cluster", () => {
    const lanes = layoutLanes([
      { id: "a", sp: 7, ep: 9 },
      { id: "b", sp: 8, ep: 9 },
      { id: "c", sp: 12, ep: 13 },
    ]);
    expect(lanes.get("a")).toEqual({ lane: 0, lanes: 2 });
    expect(lanes.get("b")).toEqual({ lane: 1, lanes: 2 });
    expect(lanes.get("c")).toEqual({ lane: 0, lanes: 1 });
  });
  it("virtual window with overscan", () => {
    expect(visibleRange(1200, 600, 120, 60, 4)).toEqual([6, 19]);
    expect(visibleRange(0, 600, 120, 3, 4)).toEqual([0, 2]);
  });
  it("zoom keeps the content under the pointer anchored (instant re-layout)", () => {
    const small = rowTable(32);
    const big = rowTable(52);
    // pointer 100 px into the viewport, scrolled to the middle of P7 at 32 px rows
    const scrollTop = small.tops[6] + 16 - 100;
    const next = anchoredScroll(small, big, scrollTop, 100);
    expect(next + 100).toBeCloseTo(big.tops[6] + 26);
  });
  it("wheel/pinch accumulates to one zoom step", () => {
    expect(zoomDeltaFromWheel(-30, 0)).toEqual({ step: 0, rest: -30 });
    expect(zoomDeltaFromWheel(-40, -30)).toEqual({ step: 1, rest: 0 });
    expect(zoomDeltaFromWheel(80, 0).step).toBe(-1);
  });
});

describe("slot magnetism (16 px)", () => {
  const t = rowTable(40);
  it("pull factor is full inside radius/3 and fades to 0 at the radius", () => {
    expect(pullFactor(0)).toBe(1);
    expect(pullFactor(5)).toBe(1);
    expect(pullFactor(16)).toBe(0);
    expect(pullFactor(10.67)).toBeCloseTo(0.5, 1);
  });
  it("snaps the ghost's top-left to the nearest column and period start", () => {
    const s = snapGhost(122, 243, 120, 10, t, 3);
    expect([s.col, s.period]).toEqual([1, 7]);
    expect([s.x, s.y]).toEqual([120, 240]); // within 5 px → fully pulled
  });
  it("does not pull from farther than 16 px but still reports the nearest slot", () => {
    const s = snapGhost(150, 265, 120, 10, t, 3);
    expect([s.col, s.period, s.pull]).toEqual([1, 8, 0]);
    expect([s.x, s.y]).toEqual([150, 265]);
  });
  it("never lets a span run past P18", () => {
    expect(snapGhost(0, t.total - 5, 120, 10, t, 3).period).toBe(16);
  });
  it("valid-slot pull searches ±3 periods, earlier first", () => {
    expect(nearestValidStart(7, 3, (s) => s === 10 || s === 4)).toBe(4);
    expect(nearestValidStart(7, 3, () => false)).toBeNull();
    expect(nearestValidStart(17, 2, (s) => s === 18)).toBeNull();
  });
});

describe("index + live conflict preview", () => {
  const model = buildModel(fixtureIndex());
  const bme = model.eventByAid.get(1)?.[0];
  const eng = model.eventByAid.get(2)?.[0];
  const lab = model.eventByAid.get(3)?.[0];
  if (!bme || !eng || !lab) throw new Error("fixture");

  it("week masks round-trip", () => {
    expect(weeksOfMask(maskOf([1, 3, 14]))).toEqual([1, 3, 14]);
    expect(eventsOf(model, 7, 3).map((e) => e.a.id)).toEqual([1, 2]);
  });
  it("room overlap is hard with the Turkish sentence; capacity is soft", () => {
    const r = checkMove(model, bme, { room: 2, day: 3, sp: 7, ep: 9 });
    expect(r.ok).toBe(false);
    expect(r.hard.map((i) => i.code)).toEqual(["room_overlap"]);
    expect(r.hard[0].text.tr).toBe("ENG 102 §1 ile çakışıyor (A 101 Çar 14:20–15:50)");
    expect(r.soft[0].text.tr).toBe("A 101: 58 koltuk, bu ders 102 öğrenci");
    expect(r.culprits).toEqual(["2:2"]);
  });
  it("pre-occupied blocks, instructor and PC rules", () => {
    expect(checkMove(model, bme, { room: 5, day: 3, sp: 7, ep: 9 }).hard[0].code).toBe("block");
    const instr = checkMove(model, eng, { room: 4, day: 2, sp: 3, ep: 4 });
    expect(instr.hard.map((i) => i.code)).toEqual(["instructor"]);
    expect(instr.hard[0].text.tr).toMatch(/^Can Demir aynı saatte CSE 225 §1 dersinde/);
    const pc = checkMove(model, lab, { room: 4, day: 2, sp: 3, ep: 4 });
    expect(pc.hard.map((i) => i.code)).toEqual(["pc"]);
    expect(pc.soft.map((i) => i.code)).toContain("locked");
  });
  it("cohort clash ignores parallel sections of the same course", () => {
    const m2 = buildModel(fixtureIndex([assignment({ id: 9, label: "BME 419 §2", day: 1, sp: 1, ep: 2, rooms: [4], code: "BME 419" }), assignment({ id: 10, label: "MAT 112 §1", day: 1, sp: 5, ep: 6, rooms: [4] })]));
    const sec2 = m2.eventByAid.get(9)?.[0];
    const mat = m2.eventByAid.get(10)?.[0];
    if (!sec2 || !mat) throw new Error("fixture");
    expect(checkMove(m2, sec2, { room: 4, day: 3, sp: 7, ep: 9 }).hard.map((i) => i.code)).toEqual([]);
    expect(checkMove(m2, mat, { room: 4, day: 3, sp: 7, ep: 8 }).hard.map((i) => i.code)).toEqual(["cohort"]);
  });
  it("a one-week move only checks that week", () => {
    const m2 = buildModel(fixtureIndex([assignment({ id: 11, label: "FTR 412 §1", day: 4, sp: 7, ep: 9, rooms: [4], weeks: [3], prog_id: 9 })]));
    const ftr = m2.eventByAid.get(11)?.[0];
    if (!ftr) throw new Error("fixture");
    const bme2 = m2.eventByAid.get(1)?.[0];
    if (!bme2) throw new Error("fixture");
    expect(checkMove(m2, bme2, { room: 4, day: 4, sp: 7, ep: 9 }).ok).toBe(false);
    expect(checkMove(m2, bme2, { room: 4, day: 4, sp: 7, ep: 9, mask: maskOf([5]) }).ok).toBe(true);
  });
  it("out of range and P12 transition", () => {
    expect(checkMove(model, bme, { room: 4, day: 3, sp: 17, ep: 19 }).hard[0].code).toBe("out_of_range");
    expect(checkMove(model, bme, { room: 4, day: 5, sp: 11, ep: 13 }).soft.map((i) => i.code)).toEqual(["p12"]);
  });
  it("quick-create free-slot test sees blocks", () => {
    expect(slotFree(model, 5, 3, 8, 8, model.allMask)).toBe(false);
    expect(slotFree(model, 4, 3, 8, 8, model.allMask)).toBe(true);
  });
  it("preview stays under 1 ms per check on a 9,000-row, 60-room index (the Bahar board)", () => {
    const many = Array.from({ length: 9000 }, (_, i) => assignment({ id: 100 + i, label: `X ${i}`, day: (i % 5) + 1, sp: (i % 15) + 1, ep: (i % 15) + 2, rooms: [(i % 60) + 1], weeks: [(i % 14) + 1], instr_ids: [i % 300], prog_id: i % 50 }));
    const big = buildModel(fixtureIndex(many));
    const ev = big.eventByAid.get(1)?.[0];
    if (!ev) throw new Error("fixture");
    for (let i = 0; i < 50; i++) checkMove(big, ev, { room: (i % 5) + 1, day: (i % 5) + 1, sp: 7, ep: 9 }); // warm-up
    const t0 = performance.now();
    for (let i = 0; i < 200; i++) checkMove(big, ev, { room: (i % 5) + 1, day: (i % 5) + 1, sp: 7, ep: 9 });
    expect((performance.now() - t0) / 200).toBeLessThan(1);
  });
});

describe("heat", () => {
  const model = buildModel(fixtureIndex());
  it("occupancy counts assignments and blocks over bookable rooms × 18 (same as the server)", () => {
    const heat = computeHeat(model);
    const wed = heat.get("1:3");
    expect(wed?.occupied).toBe(5);
    expect(wed?.blocked).toBe(3);
    expect(wed?.occupancy).toBeCloseTo(8 / 90);
    expect(heat.get("1:7")?.occupancy).toBe(0);
  });
  it("respects the room filter", () => {
    const heat = computeHeat(model, { rooms: new Set([1]) });
    expect(heat.get("1:3")?.occupancy).toBeCloseTo(3 / 18);
  });
  it("steps follow the legend thresholds", () => {
    expect([0, 0.1, 0.25, 0.26, 0.5, 0.75, 0.8, 0.95].map(heatStep)).toEqual([0, 1, 1, 2, 2, 3, 4, 5]);
  });
});

describe("filters", () => {
  const model = buildModel(fixtureIndex());
  it("Turkish fold matches with or without spaces and dotted İ", () => {
    expect(fold("PHAR 240")).toBe(fold("phar240"));
    expect(fold("BİF111")).toBe(fold("bif111"));
    expect(fold("Şube")).toBe("sube");
  });
  it("query matches code, instructor and programme", () => {
    const ev = model.eventByAid.get(1)?.[0];
    if (!ev) throw new Error("fixture");
    expect(eventPasses({ ...EMPTY_FILTERS, query: "bme419" }, ev)).toBe(true);
    expect(eventPasses({ ...EMPTY_FILTERS, query: "kaya" }, ev)).toBe(true);
    expect(eventPasses({ ...EMPTY_FILTERS, query: "eczacılık" }, ev)).toBe(false);
    expect(eventPasses({ ...EMPTY_FILTERS, status: ["locked"] }, ev)).toBe(false);
  });
  it("building / tag / capacity filters apply to rooms", () => {
    const r = model.roomById.get(3);
    if (!r) throw new Error("fixture");
    expect(roomPasses({ ...EMPTY_FILTERS, tags: ["PC"] }, r)).toBe(true);
    expect(roomPasses({ ...EMPTY_FILTERS, buildings: ["C"] }, r)).toBe(false);
    expect(roomPasses({ ...EMPTY_FILTERS, minCap: 58 }, r)).toBe(false);
  });
});

describe("lens switching and URL state", () => {
  it("keyboard letters map to lenses (Turkish İ/ı safe)", () => {
    expect(["b", "W", "d", "m", "y", "a", "x"].map(lensForKey)).toEqual(["board", "week", "day", "month", "term", "agenda", null]);
  });
  it("direction follows Board → Agenda order", () => {
    expect(lensDirection("board", "agenda")).toBe(1);
    expect(lensDirection("term", "week")).toBe(-1);
    expect(lensDirection("day", "day")).toBe(0);
  });
  it("round-trips through the URL and keeps unknown params", () => {
    const s = parseViewState(new URLSearchParams("lens=week&subject=room:12&week=7&day=3&zoom=4&sel=88&foo=1"));
    expect(s).toMatchObject({ lens: "week", subject: { kind: "room", id: "12" }, week: 7, day: 3, zoom: 4, sel: 88 });
    const back = serializeViewState({ ...s, lens: "board" }, new URLSearchParams("foo=1"));
    expect(back.get("lens")).toBeNull();
    expect(back.get("subject")).toBe("room:12");
    expect(back.get("foo")).toBe("1");
  });
  it("invalid values fall back to defaults", () => {
    const s = parseViewState(new URLSearchParams("lens=year&density=huge&zoom=99&day=9"));
    expect(s).toMatchObject({ lens: "board", density: "standard", zoom: 5, day: 7 });
  });
  it("opens a week the run covers (usability M1)", () => {
    expect(weekInRun([3], [1, 2, 3, 4], 7)).toBe(3);
    expect(weekInRun([], [1, 2, 3, 4], 2)).toBe(2);
    expect(weekInRun([2, 5, 9], [], 6)).toBe(5);
  });
});

describe("dates", () => {
  const idx = fixtureIndex();
  it("week/day ↔ date", () => {
    expect(dateOf(idx.weeks, 7, 3)).toBe("2026-03-18");
    expect(weekDayOf(idx.weeks, "2026-03-18")).toEqual({ week: 7, day: 3 });
    expect(weekDayOf(idx.weeks, "2025-01-01")).toBeNull();
  });
  it("Apple-style range titles", () => {
    expect(rangeTitle("2026-03-16", "2026-03-22", "tr")).toBe("16–22 Mart 2026");
    expect(rangeTitle("2026-03-30", "2026-04-05", "tr")).toBe("30 Mar–5 Nis 2026");
  });
  it("month grid starts on Monday and is whole weeks", () => {
    const g = monthGrid(2026, 3);
    expect(g[0]).toBe("2026-02-23");
    expect(g.length % 7).toBe(0);
    expect(g).toContain("2026-03-31");
  });
});

describe("compare runs", () => {
  it("moved / only here / only there by request + week", () => {
    const a = fixtureIndex().assignments;
    const b = [
      { ...a[0], id: 101, rooms: [4] },
      { ...a[1], id: 102 },
      assignment({ id: 103, label: "NEW 101", day: 1, sp: 1, ep: 2, rooms: [1], mr: 5555 }),
    ];
    const r = compareRuns(a, b, Array.from({ length: 14 }, (_, i) => i + 1));
    expect([r.moved, r.onlyA, r.onlyB]).toEqual([14, 14, 14]);
    expect([...r.movedAids]).toEqual([1]);
    expect(r.ghosts.get(3)?.map((g) => [g.kind, g.room])).toEqual([["moved", 4], ["onlyB", 1]]);
  });
});
