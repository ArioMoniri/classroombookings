/**
 * F-CH-2 (fix-c-2026-10-18): the keyboard scrub (←/→, Home/End) shows the focused bucket's tooltip at every size.
 * At 390 × 844 touch the tooltip stayed empty (`.ch-tt` ""), at 1440 it read the bucket. The real engine runs here
 * (jsdom, SVG renderer) at the phone plot (350 × 200) and the desktop plot (900 × 240).
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ChartCard } from "./chart-card";
import type { ChartColumn } from "./chart-csv";
import { LazyBarChart } from "./chart-lazy";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { findInstance } from "./chart-api";
import { BarForm } from "./chart-form-bar";
import type { ChartApi } from "./chart-form-types";
import { makeChartFormat } from "./chart-format";
import { categoricalConfig, engineOptions, legendItems } from "./chart-tokens";

const f = makeChartFormat("tr");
const days = [
  ["2026-10-08", 20100, 10400],
  ["2026-10-09", 31000, 15200],
  ["2026-10-10", 12000, 9000],
  ["2026-10-11", 8000, 2000],
  ["2026-10-12", 41000, 22000],
  ["2026-10-13", 39000, 30000],
  ["2026-10-14", 37120, 45180],
].map(([day, chat, rules]) => ({ day: day as string, chat: chat as number, rules: rules as number }));

let size = { w: 900, h: 240 };
const restore: (() => void)[] = [];
beforeEach(() => {
  for (const prop of ["clientWidth", "clientHeight", "offsetWidth", "offsetHeight"] as const) {
    const before = Object.getOwnPropertyDescriptor(HTMLElement.prototype, prop);
    Object.defineProperty(HTMLElement.prototype, prop, { configurable: true, get: () => (prop.endsWith("Width") ? size.w : size.h) });
    restore.push(() => (before ? Object.defineProperty(HTMLElement.prototype, prop, before) : delete (HTMLElement.prototype as unknown as Record<string, unknown>)[prop]));
  }
});
afterEach(() => {
  restore.splice(0).forEach((r) => r());
});

async function scrub(w: number, h: number, index: number): Promise<string> {
  size = { w, h };
  const onReady = vi.fn();
  const { container, unmount } = render(
    <BarForm
      data={days}
      config={categoricalConfig([
        { key: "chat", label: "Sohbet" },
        { key: "rules", label: "Kurallar" },
      ])}
      xKey="day"
      series={["chat", "rules"]}
      stackType="stacked"
      renderer="svg"
      engineOptions={engineOptions({ reduce: false, patterns: false })}
      valueFormatter={f.num}
      labelFormatter={f.dayLong}
      tickFormatter={f.compact}
      xTickFormatter={f.day}
      tooltipClassName="ch-tt"
      partialLast={false}
      height={h}
      onReady={onReady}
    />,
  );
  await act(async () => new Promise((r) => setTimeout(r, 50)));
  const api = onReady.mock.calls[0]![0] as ChartApi;
  act(() => api.showTip(index));
  await act(async () => new Promise((r) => setTimeout(r, 50)));
  const text = Array.from(container.querySelectorAll(".ch-tt"))
    .map((el) => el.textContent ?? "")
    .join("|");
  unmount();
  return text.replace(/\s+/g, " ").trim();
}

describe("keyboard scrub tooltip (CH-03, F-CH-2)", () => {
  it("desktop plot: End shows the last bucket", async () => {
    const text = await scrub(900, 240, 6);
    expect(text).toContain("14 Ekim Çarşamba");
    expect(text).toContain("45.180");
  }, 30_000);

  it("phone plot (390 touch, 200 px): End shows the last bucket, ← the one before", async () => {
    expect(await scrub(350, 200, 6)).toContain("14 Ekim Çarşamba");
    expect(await scrub(350, 200, 5)).toContain("13 Ekim Salı");
  }, 30_000);

  it("a short bucket (11 Ekim, 10 000 of 100 000) still shows its tooltip", async () => {
    expect(await scrub(350, 200, 3)).toContain("11 Ekim Pazar");
  }, 30_000);

  for (const vp of [
    { name: "1440 mouse", w: 900, h: 240, phone: false },
    { name: "390 touch", w: 350, h: 200, phone: true },
  ]) {
    it(`through the card at ${vp.name}: focus, End, ← (the a11y spec's steps)`, async () => {
      size = { w: vp.w, h: vp.h };
      const mm = vi.spyOn(window, "matchMedia").mockImplementation((q: string) => ({ matches: vp.phone && /max-width|pointer: coarse|hover: none/.test(q), media: q, onchange: null, addListener: () => undefined, removeListener: () => undefined, addEventListener: () => undefined, removeEventListener: () => undefined, dispatchEvent: () => false }) as MediaQueryList);
      type Day = (typeof days)[number];
      const columns: ChartColumn<Day>[] = [
        { key: "day", label: "Gün", kind: "date" },
        { key: "chat", label: "Sohbet", kind: "number" },
        { key: "rules", label: "Kurallar", kind: "number" },
      ];
      const series = [
        { key: "chat", label: "Sohbet" },
        { key: "rules", label: "Kurallar" },
      ];
      const { container } = render(
        <ChartCard<Day> id="fx-bar" title="Günlük token kullanımı" summary="Özet." state="ready" columns={columns} rows={days} unit="token" legend={legendItems(series)} series={2}>
          {(ctx) => <LazyBarChart {...ctx} data={days} config={categoricalConfig(series)} xKey="day" series={["chat", "rules"]} stackType="stacked" />}
        </ChartCard>,
      );
      await waitFor(() => expect(container.querySelector("[data-chart-card='fx-bar'] svg")).not.toBeNull(), { timeout: 20_000 });
      await act(async () => new Promise((r) => setTimeout(r, 100)));
      const group = screen.getByRole("group", { name: "Grafik, ok tuşlarıyla gezinin" });
      act(() => group.focus());
      fireEvent.keyDown(group, { key: "End" });
      await act(async () => new Promise((r) => setTimeout(r, 100)));
      expect(container.querySelector(".ch-tt")?.textContent ?? "").toContain("14 Ekim Çarşamba");
      fireEvent.keyDown(group, { key: "ArrowLeft" });
      await act(async () => new Promise((r) => setTimeout(r, 100)));
      expect(container.querySelector(".ch-tt")?.textContent ?? "").toContain("13 Ekim Salı");
      mm.mockRestore();
    }, 30_000);
  }

  it("the shown bucket survives the engine re-pushing its option (a resize on the phone layout)", async () => {
    size = { w: 350, h: 200 };
    const onReady = vi.fn();
    const { container } = render(
      <BarForm data={days} config={categoricalConfig([{ key: "chat", label: "Sohbet" }, { key: "rules", label: "Kurallar" }])} xKey="day" series={["chat", "rules"]} stackType="stacked" renderer="svg" engineOptions={engineOptions({ reduce: false, patterns: false })} valueFormatter={f.num} labelFormatter={f.dayLong} tickFormatter={f.compact} xTickFormatter={f.day} tooltipClassName="ch-tt" partialLast={false} height={200} onReady={onReady} />,
    );
    await act(async () => new Promise((r) => setTimeout(r, 50)));
    const api = onReady.mock.calls[0]![0] as ChartApi;
    act(() => api.showTip(6));
    await act(async () => new Promise((r) => setTimeout(r, 50)));
    const inst = findInstance(container)!;
    // what EvilCharts' ResizeObserver does on a real resize: chart.resize() + a notMerge re-push
    act(() => {
      inst.resize();
      inst.setOption(inst.getOption(), true);
    });
    await act(async () => new Promise((r) => setTimeout(r, 100)));
    const shown = Array.from(container.querySelectorAll<HTMLElement>(".ch-tt")).filter((el) => el.style.display !== "none" && el.style.visibility !== "hidden");
    expect(shown.map((el) => el.textContent ?? "").join("|")).toContain("14 Ekim Çarşamba");
  }, 30_000);

  it("a key pressed before the chart's chunk is in shows its bucket once the chart is ready (the 390 race)", async () => {
    const api: ChartApi = { getDataURL: () => null, dispatchAction: vi.fn(), showTip: vi.fn(), hideTip: vi.fn() };
    let ready: ((a: ChartApi) => void) | null = null;
    function SlowPlot({ onReady }: { onReady: (a: ChartApi) => void }) {
      ready = onReady;
      return <div data-testid="plot" />;
    }
    type Day = (typeof days)[number];
    render(
      <ChartCard<Day> id="slow" title="Günlük" summary="Özet." state="ready" columns={[{ key: "day", label: "Gün", kind: "date" }, { key: "chat", label: "Sohbet", kind: "number" }]} rows={days}>
        {(ctx) => <SlowPlot onReady={ctx.onReady} />}
      </ChartCard>,
    );
    const group = screen.getByRole("group", { name: "Grafik, ok tuşlarıyla gezinin" });
    act(() => group.focus());
    fireEvent.keyDown(group, { key: "End" });
    expect(api.showTip).not.toHaveBeenCalled();
    act(() => ready!(api));
    expect(api.showTip).toHaveBeenCalledWith(6);
  });
});
