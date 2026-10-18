import { describe, expect, it } from "vitest";
import { translate, type MessageKey, type Vars } from "@/lib/i18n";
import type { ChartColumn } from "./chart-csv";
import { makeChartFormat } from "./chart-format";
import { bucketSentence, keyMove } from "./chart-keyboard";

describe("keyMove", () => {
  it("arrows step, Home/End jump, Esc hides, other keys do nothing", () => {
    expect(keyMove("ArrowRight", null, 5)).toBe(0);
    expect(keyMove("ArrowLeft", null, 5)).toBe(4);
    expect(keyMove("ArrowRight", 2, 5)).toBe(3);
    expect(keyMove("ArrowRight", 4, 5)).toBe(4);
    expect(keyMove("ArrowLeft", 0, 5)).toBe(0);
    expect(keyMove("Home", 3, 5)).toBe(0);
    expect(keyMove("End", 1, 5)).toBe(4);
    expect(keyMove("Escape", 1, 5)).toBe("hide");
    expect(keyMove("a", 1, 5)).toBeNull();
    expect(keyMove("ArrowRight", null, 0)).toBeNull();
  });
});

describe("bucketSentence", () => {
  type Row = { day: string; chat: number; rules: number };
  const columns: ChartColumn<Row>[] = [
    { key: "day", label: "Gün", kind: "date" },
    { key: "chat", label: "Sohbet", kind: "number" },
    { key: "rules", label: "Kurallar", kind: "number" },
  ];
  const t = (key: MessageKey, vars?: Vars) => translate("tr", key, vars);

  it("several series: the bucket, the total with the unit, then each series", () => {
    const text = bucketSentence({ row: { day: "2026-10-14", chat: 37120, rules: 45180 }, columns, f: makeChartFormat("tr"), t, unit: "token" });
    expect(text).toBe("14 Ekim Çarşamba: toplam 82.300 token; Sohbet 37.120, Kurallar 45.180");
  });

  it("one series: the bucket and its value", () => {
    const text = bucketSentence({ row: { day: "2026-10-14", chat: 37120, rules: 0 }, columns: columns.slice(0, 2), f: makeChartFormat("tr"), t });
    expect(text).toBe("14 Ekim Çarşamba: 37.120");
  });

  it("the unfinished bucket says so", () => {
    const text = bucketSentence({ row: { day: "2026-10-14", chat: 1, rules: 2 }, columns, f: makeChartFormat("tr"), t, partial: "(eksik)" });
    expect(text.startsWith("14 Ekim Çarşamba (eksik): toplam 3")).toBe(true);
  });
});
