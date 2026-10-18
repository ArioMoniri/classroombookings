import { fireEvent, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { describe, expect, it, vi } from "vitest";
import { ChartCard } from "./chart-card";
import type { ChartColumn } from "./chart-csv";
import type { ChartApi } from "./chart-form-types";
import { keyMove } from "./chart-keyboard";

type Row = { run: string; soft: number };
const rows: Row[] = [
  { run: "#1", soft: 70 },
  { run: "#2", soft: 90 },
  { run: "#3", soft: 80 },
];
const columns: ChartColumn<Row>[] = [
  { key: "run", label: "Çalıştırma" },
  { key: "soft", label: "Yumuşak puan", kind: "number" },
];

function setup(onSelect?: (i: number) => void, indexAt: (x: number, y: number) => number | null = () => 1) {
  const api: ChartApi = { getDataURL: () => null, dispatchAction: vi.fn(), showTip: vi.fn(), hideTip: vi.fn(), indexAt: vi.fn(indexAt) };
  function Plot({ onReady }: { onReady: (a: ChartApi) => void }) {
    useEffect(() => onReady(api), [onReady]);
    return <div data-testid="plot" />;
  }
  render(
    <ChartCard<Row> id="sel" title="Yumuşak puan" summary="Özet." state="ready" columns={columns} rows={rows} onSelect={onSelect} selectHint="Bir noktaya dokunun.">
      {(ctx) => <Plot onReady={ctx.onReady} />}
    </ChartCard>,
  );
  return { api, group: screen.getByRole("group", { name: "Grafik, ok tuşlarıyla gezinin" }) };
}

describe("ChartCard select (CH-08 / CH-10)", { timeout: 20_000 }, () => {
  it("Enter and Space are not ours without a focused bucket", () => {
    expect(keyMove("Enter", null, 3)).toBeNull();
  });

  it("→ then Enter selects the focused bucket", () => {
    const onSelect = vi.fn();
    const { group } = setup(onSelect);
    fireEvent.keyDown(group, { key: "ArrowRight" });
    fireEvent.keyDown(group, { key: "ArrowRight" });
    fireEvent.keyDown(group, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith(1);
    fireEvent.keyDown(group, { key: " " });
    expect(onSelect).toHaveBeenCalledTimes(2);
  });

  it("Enter before any arrow does nothing", () => {
    const onSelect = vi.fn();
    const { group } = setup(onSelect);
    fireEvent.keyDown(group, { key: "Enter" });
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("a click or tap selects the bucket under the pointer; outside the grid nothing", () => {
    const onSelect = vi.fn();
    const { group } = setup(onSelect);
    fireEvent.click(group, { clientX: 40, clientY: 20 });
    expect(onSelect).toHaveBeenCalledWith(1);
    onSelect.mockClear();
    const second = vi.fn();
    document.body.innerHTML = "";
    const { group: g2 } = setup(second, () => null);
    fireEvent.click(g2, { clientX: 1, clientY: 1 });
    expect(second).not.toHaveBeenCalled();
  });

  it("shows the visible select hint (no hover-only affordance) and marks the plot selectable", () => {
    const { group } = setup(vi.fn());
    expect(screen.getByText("Bir noktaya dokunun.")).toBeVisible();
    expect(group).toHaveAttribute("data-selectable", "true");
  });

  it("without onSelect, a click does nothing and there is no hint", () => {
    const { api, group } = setup(undefined);
    fireEvent.click(group);
    expect(api.indexAt).not.toHaveBeenCalled();
    expect(screen.queryByText("Bir noktaya dokunun.")).toBeNull();
  });
});
