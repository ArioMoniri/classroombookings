import { render } from "@testing-library/react";
import * as echarts from "echarts/core";
import { describe, expect, it, vi } from "vitest";
import { findInstance } from "./chart-api";
import { BarForm } from "./chart-form-bar";
import type { ChartApi } from "./chart-form-types";
import { makeChartFormat } from "./chart-format";
import { categoricalConfig, engineOptions } from "./chart-tokens";
import { escapeHtml } from "./evil/ui/echarts-tooltip";

const f = makeChartFormat("tr");
const data = [
  { day: "2026-10-12", chat: 37120, rules: 1000 },
  { day: "2026-10-13", chat: 82300, rules: 2000 },
  { day: "2026-10-14", chat: 12000, rules: 500 },
];

function bar(onReady: (api: ChartApi) => void = () => undefined) {
  return (
    <BarForm
      data={data}
      config={categoricalConfig([
        { key: "chat", label: "Sohbet" },
        { key: "rules", label: "Kurallar" },
      ])}
      xKey="day"
      series={["chat", "rules"]}
      stackType="stacked"
      renderer="svg"
      engineOptions={engineOptions({ reduce: false, patterns: true })}
      valueFormatter={f.num}
      labelFormatter={f.dayLong}
      tickFormatter={f.compact}
      xTickFormatter={f.day}
      tooltipClassName="ch-tt"
      partialLast
      height={240}
      onReady={onReady}
    />
  );
}

describe("vendored EvilCharts ECharts, as the shell drives it", () => {
  it("mounts one SVG instance with animation off, decal on and the injected tooltip formatters; disposes on unmount", () => {
    const onReady = vi.fn();
    const { container, unmount } = render(bar(onReady));
    const inst = findInstance(container);
    expect(inst).toBeDefined();
    const opt = inst!.getOption() as Record<string, unknown> & { tooltip: { className?: string; formatter: (p: unknown) => string }[]; aria: unknown };
    expect(opt.animation).toBe(false);
    // `aria` is a global option (an object), not a component list
    const aria = (Array.isArray(opt.aria) ? opt.aria[0] : opt.aria) as { decal: { show: boolean }; label: { enabled: boolean } };
    expect(aria.decal.show).toBe(true);
    expect(aria.label.enabled).toBe(false);
    expect(container.querySelector("[aria-label]")).toBeNull(); // no generated English description
    expect(opt.tooltip[0]!.className).toBe("ch-tt");
    const html = opt.tooltip[0]!.formatter([{ axisValue: "2026-10-13", seriesId: "chat", value: 82300 }]);
    expect(html).toContain("13 Ekim Salı");
    expect(html).toContain("82.300");
    expect(html).toContain("Sohbet");
    expect(onReady).toHaveBeenCalledTimes(1);
    const api = onReady.mock.calls[0]![0] as ChartApi;
    expect(api.getDataURL({ type: "svg" })).toMatch(/^data:image\/svg\+xml/);
    unmount();
    expect(inst!.isDisposed()).toBe(true);
    expect(echarts.getInstanceByDom(container)).toBeUndefined();
  }, 30_000); // the real engine in jsdom, on a shared 4-core host

  it("escapes every text part of the tooltip HTML", () => {
    expect(escapeHtml(`<img src=x onerror="a()">&'`)).toBe("&lt;img src=x onerror=&quot;a()&quot;&gt;&amp;&#39;");
  });
});
