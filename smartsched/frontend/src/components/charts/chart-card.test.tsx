import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChartCard, type ChartCardProps, type ChartState } from "./chart-card";
import type { ChartColumn } from "./chart-csv";
import { setChartPatterns } from "./use-chart-patterns";

type Row = { day: string; chat: number; rules: number };
const rows: Row[] = [
  { day: "2026-10-12", chat: 37120, rules: 1000 },
  { day: "2026-10-13", chat: 82300, rules: 2000 },
  { day: "2026-10-14", chat: 12000, rules: 500 },
];
const columns: ChartColumn<Row>[] = [
  { key: "day", label: "Gün", kind: "date" },
  { key: "chat", label: "Sohbet", kind: "number" },
  { key: "rules", label: "Kurallar", kind: "number" },
];

function mockMedia(match: (q: string) => boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: match(query),
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }) as MediaQueryList,
  );
}

const plot = vi.fn();
function card(over: Partial<ChartCardProps<Row>> = {}) {
  return (
    <ChartCard<Row>
      id="ai-daily"
      title="Günlük token kullanımı"
      summary="Son 30 günde 131 bin token; en yoğun gün 13 Eki (82 bin)."
      state="ready"
      columns={columns}
      rows={rows}
      series={2}
      {...over}
    >
      {(ctx) => {
        plot(ctx);
        return <div data-testid="plot" data-renderer={ctx.renderer} />;
      }}
    </ChartCard>
  );
}

// a shared 4-core host: the first render warms up Base UI + jsdom; the repo CI budget is 30 s per test
beforeEach(() => {
  plot.mockClear();
  localStorage.clear();
});
afterEach(() => {
  delete document.documentElement.dataset.motion;
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("ChartCard a11y", { timeout: 20_000 }, () => {
  it("is a figure named by the title and described by the summary; reading order title → summary → table", () => {
    render(card());
    const fig = screen.getByRole("figure", { name: "Günlük token kullanımı" });
    expect(fig).toHaveAccessibleDescription("Son 30 günde 131 bin token; en yoğun gün 13 Eki (82 bin).");
    const title = screen.getByRole("heading", { name: "Günlük token kullanımı" });
    const summary = screen.getByText(/Son 30 günde/);
    const table = screen.getByRole("table");
    expect(title.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(summary.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps the table twin in the DOM (sr-only) while the chart shows; the plot is aria-hidden", () => {
    render(card());
    const table = screen.getByRole("table");
    expect(table.closest("[data-chart-table]")).toHaveClass("sr-only");
    expect(within(table).getByText("Günlük token kullanımı")).toBeInTheDocument(); // caption
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual(["Gün", "Sohbet", "Kurallar"]);
    expect(within(table).getAllByRole("rowheader")[1]).toHaveTextContent("13 Ekim Salı");
    expect(within(table).getAllByRole("row")[2]).toHaveTextContent("82.300");
    expect(screen.getByTestId("plot").closest("[aria-hidden='true']")).not.toBeNull();
  });

  it("the table toggle shows the table and hides the plot", () => {
    render(card());
    fireEvent.click(screen.getByRole("button", { name: "Tabloyu göster" }));
    expect(screen.getByRole("table").closest("[data-chart-table]")).not.toHaveClass("sr-only");
    expect(screen.queryByTestId("plot")).toBeNull();
    expect(screen.getByRole("button", { name: "Grafiği göster" })).toBeInTheDocument();
  });

  it("marks the unfinished bucket in the table", () => {
    render(card({ partial: true }));
    expect(within(screen.getByRole("table")).getAllByRole("rowheader")[2]).toHaveTextContent("14 Ekim Çarşamba (eksik)");
  });
});

describe("ChartCard CSV", { timeout: 20_000 }, () => {
  it("downloads a BOM CSV, swaps the label for 2 s and announces it", async () => {
    vi.useFakeTimers();
    const blobs: Blob[] = [];
    const create = vi.fn((b: Blob) => {
      blobs.push(b);
      return "blob:x";
    });
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    render(card({ range: { from: "2026-10-12", to: "2026-10-14" } }));
    fireEvent.click(screen.getByRole("button", { name: "Veriyi indir" }));
    expect(click).toHaveBeenCalledTimes(1);
    const bytes = new Uint8Array(await blobs[0]!.arrayBuffer());
    expect([...bytes.slice(0, 3)]).toEqual([0xef, 0xbb, 0xbf]); // UTF-8 BOM (Blob.text() would strip it)
    const text = await blobs[0]!.text();
    expect(text).toContain("Gün;Gün (ISO);Sohbet;Kurallar");
    expect(text.split("\r\n")).toHaveLength(4);
    expect(screen.getByRole("button", { name: "İndirildi ✓" })).toBeInTheDocument();
    expect(screen.getByTestId("chart-live-ai-daily")).toHaveTextContent("CSV indirildi");
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByRole("button", { name: "Veriyi indir" })).toBeInTheDocument();
  });
});

describe("ChartCard states", { timeout: 20_000 }, () => {
  const states: ChartState[] = ["loading", "empty", "error", "ready"];

  it.each(states)("%s keeps the same body height", (state) => {
    render(card({ state, height: 240 }));
    expect(screen.getByTestId("chart-body-ai-daily").style.minHeight).toBe("240px");
  });

  it("loading: aria-busy, skeleton, no plot, no table", () => {
    render(card({ state: "loading" }));
    expect(screen.getByRole("figure")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByTestId("chart-skeleton")).toBeInTheDocument();
    expect(screen.queryByTestId("plot")).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("loading pulses, but not under reduced motion", () => {
    const { unmount } = render(card({ state: "loading" }));
    expect(screen.getByTestId("chart-skeleton")).toHaveAttribute("data-pulse", "true");
    unmount();
    document.documentElement.dataset.motion = "reduced";
    render(card({ state: "loading" }));
    expect(screen.getByTestId("chart-skeleton")).toHaveAttribute("data-pulse", "false");
  });

  it("empty: one sentence, the reason and one action; no axes", () => {
    const onClick = vi.fn();
    render(card({ state: "empty", rows: [], empty: { action: { label: "Dönemi değiştir", onClick } } }));
    expect(screen.getByText("Henüz gösterilecek veri yok")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dönemi değiştir" }));
    expect(onClick).toHaveBeenCalled();
    expect(screen.queryByTestId("plot")).toBeNull();
    expect(screen.queryByRole("button", { name: "Veriyi indir" })).toBeNull();
  });

  it("error: status panel with the API message and a retry, no stale chart behind it", () => {
    const onRetry = vi.fn();
    render(card({ state: "error", error: "Sunucuya ulaşılamadı.", onRetry }));
    const panel = screen.getByRole("status");
    expect(panel).toHaveTextContent("Sunucuya ulaşılamadı.");
    fireEvent.click(within(panel).getByRole("button", { name: "Yeniden dene" }));
    expect(onRetry).toHaveBeenCalled();
    expect(screen.queryByTestId("plot")).toBeNull();
  });

  it("stale: the chart stays, with a text strip", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-17T18:00:00Z"));
    render(card({ stale: { since: new Date("2026-10-17T16:00:00Z"), reason: "Prometheus yanıt vermiyor" } }));
    expect(screen.getByTestId("chart-stale-ai-daily")).toHaveTextContent("Son güncelleme 2 saat önce · Prometheus yanıt vermiyor");
    expect(screen.getByTestId("plot")).toBeInTheDocument();
  });

  it("too few points (< 3): the number instead of a chart, the table stays", () => {
    render(card({ rows: rows.slice(0, 2) }));
    expect(screen.queryByTestId("plot")).toBeNull();
    const tiles = screen.getByTestId("chart-few-ai-daily");
    expect(tiles).toHaveTextContent("Sohbet");
    expect(tiles).toHaveTextContent("119.420");
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("updated time in Istanbul", () => {
    render(card({ updatedAt: new Date("2026-10-17T16:42:00Z") }));
    expect(screen.getByText("Güncellendi 19:42 · Europe/Istanbul")).toBeInTheDocument();
  });
});

describe("ChartCard plot context", { timeout: 20_000 }, () => {
  it("passes SVG for ≤ 300 marks, canvas above, animation off, tr-TR formatters", () => {
    render(card());
    const ctx = plot.mock.calls.at(-1)![0];
    expect(ctx.renderer).toBe("svg");
    expect(ctx.engineOptions.animation).toBe(false);
    expect(ctx.valueFormatter(82300)).toBe("82.300");
    expect(ctx.labelFormatter("2026-10-14")).toBe("14 Ekim Çarşamba");
    expect(ctx.tickFormatter(1_200_000)).toBe("1,2\u00a0Mn");
    const big = Array.from({ length: 151 }, (_, i) => ({ day: new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10), chat: i, rules: i }));
    render(card({ rows: big }));
    expect(plot.mock.calls.at(-1)![0].renderer).toBe("canvas");
  });

  it("hatch patterns are off by default and follow the per-user preference", () => {
    const { unmount } = render(card({ userId: 7 }));
    expect(plot.mock.calls.at(-1)![0].patterns).toBe(false);
    expect(plot.mock.calls.at(-1)![0].engineOptions.aria.decal.show).toBe(false);
    unmount();
    act(() => setChartPatterns(7, true));
    render(card({ userId: 7 }));
    expect(plot.mock.calls.at(-1)![0].patterns).toBe(true);
    expect(plot.mock.calls.at(-1)![0].engineOptions.aria.decal.show).toBe(true);
  });

  it("forced colours turn the patterns on", () => {
    mockMedia((q) => q.includes("forced-colors"));
    render(card());
    expect(plot.mock.calls.at(-1)![0].patterns).toBe(true);
  });

  it("hover emphasis is 120 ms, 0 under reduced motion", () => {
    const { unmount } = render(card());
    expect(plot.mock.calls.at(-1)![0].engineOptions.stateAnimation.duration).toBe(120);
    unmount();
    document.documentElement.dataset.motion = "reduced";
    render(card());
    expect(plot.mock.calls.at(-1)![0].engineOptions.stateAnimation.duration).toBe(0);
  });

  it("swaps the summary text with the free text-states-swap recipe, but not under reduced motion", () => {
    const { rerender, unmount } = render(card());
    expect(screen.getByText(/Son 30 günde/)).toHaveAttribute("data-swap", "false");
    rerender(card({ summary: "Son 7 günde 20 bin token." }));
    expect(screen.getByText("Son 7 günde 20 bin token.")).toHaveAttribute("data-swap", "true");
    unmount();
    document.documentElement.dataset.motion = "reduced";
    const again = render(card());
    again.rerender(card({ summary: "Son 7 günde 20 bin token." }));
    expect(screen.getByText("Son 7 günde 20 bin token.")).toHaveAttribute("data-swap", "false");
  });

  it("renders the period control when given and reports changes", () => {
    const onChange = vi.fn();
    render(
      card({
        period: {
          value: "30d",
          options: [
            { value: "7d", label: "7 gün" },
            { value: "30d", label: "30 gün" },
          ],
          onChange,
        },
      }),
    );
    fireEvent.click(screen.getByRole("tab", { name: "7 gün" }));
    expect(onChange).toHaveBeenCalledWith("7d");
  });
});

describe("ChartCard keyboard (CH-03)", { timeout: 20_000 }, () => {
  function keyed() {
    const dispatchAction = vi.fn();
    const api = { getDataURL: () => null, dispatchAction };
    function Plot({ onReady }: { onReady: (a: typeof api) => void }) {
      useEffect(() => onReady(api), [onReady]);
      return <div data-testid="plot" />;
    }
    render(
      <ChartCard<Row> id="kb" title="Günlük token" summary="Özet." state="ready" columns={columns} rows={rows} unit="token">
        {(ctx) => <Plot onReady={ctx.onReady} />}
      </ChartCard>,
    );
    return dispatchAction;
  }

  it("the plot is one tab stop: a named group that is not hidden; only the drawing inside is aria-hidden", () => {
    keyed();
    const group = screen.getByRole("group", { name: "Grafik, ok tuşlarıyla gezinin" });
    expect(group).toHaveAttribute("tabindex", "0");
    expect(group).not.toHaveAttribute("aria-hidden");
    expect(screen.getByTestId("plot").closest("[aria-hidden='true']")).not.toBeNull();
  });

  it("→ shows the first bucket's tooltip and reads it after 250 ms; End jumps; Esc hides", () => {
    vi.useFakeTimers();
    const dispatchAction = keyed();
    const group = screen.getByRole("group", { name: "Grafik, ok tuşlarıyla gezinin" });
    fireEvent.keyDown(group, { key: "ArrowRight" });
    expect(dispatchAction).toHaveBeenLastCalledWith({ type: "showTip", seriesIndex: 0, dataIndex: 0 });
    const live = screen.getByTestId("chart-live-kb");
    expect(live).toHaveTextContent("");
    act(() => {
      vi.advanceTimersByTime(250);
    });
    expect(live).toHaveTextContent("12 Ekim Pazartesi: toplam 38.120 token; Sohbet 37.120, Kurallar 1.000");
    fireEvent.keyDown(group, { key: "End" });
    expect(dispatchAction).toHaveBeenLastCalledWith({ type: "showTip", seriesIndex: 0, dataIndex: 2 });
    fireEvent.keyDown(group, { key: "Escape" });
    expect(dispatchAction).toHaveBeenLastCalledWith({ type: "hideTip" });
  });
});
