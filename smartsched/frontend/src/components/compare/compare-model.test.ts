/** Scenario comparison helpers on the real Bahar 2026 week 3 pair: #5 (A) vs #6 (B, A's busiest room A 204 closed on Wednesday). */
import { describe, expect, it } from "vitest";
import type { CompareData, RunLite } from "@/lib/api/analytics";
import fixture from "./__fixtures__/compare-bahar-w3.json";
import { classRows, comparableWith, defaultPair, metricValue, verdict } from "./compare-model";

const data = fixture as unknown as CompareData;

describe("compare model", () => {
  it("lists one bucket at a time, narrowed by change type and text", () => {
    const moved = classRows(data, "moved", "all", "");
    expect(moved.length).toBe(data.classes.moved.length);
    expect(moved.every((r) => r.bucket === "moved")).toBe(true);
    expect(classRows(data, "moved", "room", "").every((r) => r.change === "room")).toBe(true);
    expect(classRows(data, "moved", "split", "")).toEqual([]);
    // Turkish-insensitive search over the class, the rooms and the time
    const a = classRows(data, "only_in_a", "all", "a 204");
    expect(a.length).toBeGreaterThan(0);
    expect(a.every((r) => r.a?.rooms.includes("A 204"))).toBe(true);
    expect(classRows(data, "only_in_a", "all", "phy 102")[0]?.label).toBe("PHY 102 §1");
  });

  it("reads the backend's better / worse from B's side, never from colour", () => {
    expect(verdict({ better: "b", direction: -1, delta: -24 })).toBe("better");
    expect(verdict({ better: "a", direction: 1, delta: -1 })).toBe("worse");
    expect(verdict({ better: "same", direction: 1, delta: 0 })).toBe("same");
    expect(verdict({ better: null, direction: 0, delta: -0.2 })).toBe("neutral");
    expect(verdict({ better: null, direction: 1, delta: null })).toBe("na");
    const gaps = data.metrics.find((m) => m.key === "gaps_per_week_total")!;
    expect(verdict(gaps)).toBe("better"); // 349 → 325 idle gaps
  });

  it("formats percentages the Turkish way", () => {
    expect(metricValue("utilisation_pct", 21.5, "tr")).toBe("%21,5");
    expect(metricValue("utilisation_pct", 21.5, "en")).toBe("21.5%");
    expect(metricValue("placed", null, "tr")).toBe("—");
  });

  it("offers as B only runs of A's term and kind, and picks the published run as the default baseline", () => {
    const run = (id: number, term_id: number, kind: "COURSE" | "EXAM", is_active = false) => ({ id, term_id, kind, is_active, status: "FEASIBLE" }) as RunLite;
    const runs = [run(7, 2, "EXAM"), run(6, 1, "COURSE"), run(5, 1, "COURSE", true), run(2, 1, "EXAM")];
    expect(comparableWith(runs, runs[2]).map((r) => r.id)).toEqual([6]);
    expect(defaultPair(runs)).toEqual({ a: 5, b: 6 });
    expect(defaultPair([run(7, 2, "EXAM")])).toBeNull();
  });
});
