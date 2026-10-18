import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DashboardSummary } from "@/lib/api/schemas";

// the engine is not under test here (components/charts/chart-form.test.tsx covers it): a stub plot
vi.mock("@/components/charts/chart-lazy", () => ({
  LazyAreaChart: (p: { data: unknown[]; renderer: string; valueFormatter: (v: number) => string }) => (
    <div data-testid="area" data-points={p.data.length} data-renderer={p.renderer} data-sample={p.valueFormatter(86)} />
  ),
}));

import { PeriodArea, periodSeries } from "./dashboard-charts";

function summary(cells: { building: string; period: number; utilisation: number }[]): DashboardSummary {
  return {
    utilisation_by_building: [
      { building: "A", utilisation: 0.5, rooms: 30 },
      { building: "B", utilisation: 0.4, rooms: 10 },
    ],
    utilisation_building_period: cells,
  } as unknown as DashboardSummary;
}

const busy = summary([
  { building: "A", period: 1, utilisation: 0.5 },
  { building: "B", period: 1, utilisation: 0.1 },
  { building: "A", period: 3, utilisation: 0.9 },
  { building: "B", period: 3, utilisation: 0.74 },
  { building: "A", period: 4, utilisation: 0.6 },
]);

describe("periodSeries (unchanged by CH-04)", () => {
  it("weights each building by its rooms, one point per period, in percent", () => {
    const s = periodSeries(busy);
    expect(s).toHaveLength(18);
    expect(s[0]).toEqual({ period: "08:30", index: 1, util: 40 });
    expect(s[2]).toEqual({ period: "10:10", index: 3, util: 86 });
    expect(s[3]).toEqual({ period: "11:00", index: 4, util: 60 });
    expect(s[5]!.util).toBe(0);
  });
});

describe("PeriodArea in the ChartCard shell", () => {
  it("names the chart, says the peak in one sentence and keeps the table twin", () => {
    render(<PeriodArea data={busy} />);
    const fig = screen.getByRole("figure", { name: "Gün boyunca doluluk" });
    expect(fig).toHaveAccessibleDescription("Ders saatine göre kullanılan derslik oranı. En yoğun saat 10:10 (%86).");
    const table = within(fig).getByRole("table");
    expect(within(table).getAllByRole("rowheader")).toHaveLength(18);
    expect(within(table).getAllByRole("row")[3]).toHaveTextContent("10:10%86");
    const area = screen.getByTestId("area");
    expect(area).toHaveAttribute("data-points", "18");
    expect(area).toHaveAttribute("data-renderer", "svg");
    expect(area).toHaveAttribute("data-sample", "%86");
    expect(screen.getByRole("button", { name: "Veriyi indir" })).toBeInTheDocument();
  });

  it("an empty week shows the sentence, no chart", () => {
    render(<PeriodArea data={summary([])} />);
    expect(screen.getByText("Henüz gösterilecek veri yok")).toBeInTheDocument();
    expect(screen.queryByTestId("area")).toBeNull();
  });

  it("loading while the summary is on its way", () => {
    render(<PeriodArea data={undefined} />);
    expect(screen.getByRole("figure", { name: "Gün boyunca doluluk" })).toHaveAttribute("aria-busy", "true");
  });
});
