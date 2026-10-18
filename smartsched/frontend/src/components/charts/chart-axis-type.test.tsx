/**
 * F-CH-3 (fix-c-2026-10-18): axis text uses the smallest type token, `type-footnote` (12 px), on every form and
 * at every size. The vendored EvilCharts axes were 10 px (MOBILE.md M-03 failed at 390 on /dashboard, /admin/ai,
 * /admin/ops).
 */
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { findInstance } from "./chart-api";
import { AreaForm } from "./chart-form-area";
import { BarForm } from "./chart-form-bar";
import { LineForm } from "./chart-form-line";
import type { ChartFormProps } from "./chart-form-types";
import { makeChartFormat } from "./chart-format";
import { AXIS_FONT_PX, categoricalConfig, engineOptions } from "./chart-tokens";

const f = makeChartFormat("tr");
const data = [
  { day: "2026-10-12", chat: 37120 },
  { day: "2026-10-13", chat: 82300 },
  { day: "2026-10-14", chat: 12000 },
];
const props: ChartFormProps = {
  data,
  config: categoricalConfig([{ key: "chat", label: "Sohbet" }]),
  xKey: "day",
  series: ["chat"],
  renderer: "svg",
  engineOptions: engineOptions({ reduce: false, patterns: false }),
  valueFormatter: f.num,
  labelFormatter: f.dayLong,
  tickFormatter: f.compact,
  xTickFormatter: f.day,
  tooltipClassName: "ch-tt",
  partialLast: false,
  height: 200,
  onReady: () => undefined,
};

type Axis = { axisLabel?: { fontSize?: number; show?: boolean }; nameTextStyle?: { fontSize?: number } };

describe("chart axis text size", () => {
  it("is the type-footnote size, 12 px", () => {
    expect(AXIS_FONT_PX).toBe(12);
  });

  for (const [name, Form] of [
    ["bar", BarForm],
    ["line", LineForm],
    ["area", AreaForm],
  ] as const) {
    it(`${name}: both axes' labels and names are ≥ 12 px`, () => {
      const { container, unmount } = render(<Form {...props} />);
      const opt = findInstance(container)!.getOption() as { xAxis: Axis[]; yAxis: Axis[] };
      const axes = [...opt.xAxis, ...opt.yAxis];
      expect(axes.length).toBeGreaterThan(0);
      for (const a of axes) {
        if (a.axisLabel?.fontSize != null) expect(a.axisLabel.fontSize).toBeGreaterThanOrEqual(12);
        if (a.nameTextStyle?.fontSize != null) expect(a.nameTextStyle.fontSize).toBeGreaterThanOrEqual(12);
      }
      expect(axes.some((a) => a.axisLabel?.fontSize === AXIS_FONT_PX)).toBe(true);
      unmount();
    }, 30_000);
  }
});
