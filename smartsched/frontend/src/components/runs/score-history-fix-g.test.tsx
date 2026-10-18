import { fireEvent, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { describe, expect, it, vi } from "vitest";
import type { ChartApi } from "@/components/charts/chart-form-types";
import { ScheduleRun } from "@/lib/api/schemas";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/components/charts/chart-lazy", () => ({
  LazyLineChart: (p: { data: { label: string }[]; dots?: boolean; xTickFormatter: (s: string) => string; onReady: (a: ChartApi) => void }) => {
    useEffect(() => p.onReady({ getDataURL: () => null, dispatchAction: () => undefined, showTip: () => undefined, hideTip: () => undefined, indexAt: () => 0 }), [p]);
    return <div data-testid="line" data-dots={String(!!p.dots)} data-ticks={p.data.map((r) => p.xTickFormatter(r.label)).join("|")} />;
  },
}));

import { ScoreHistory } from "./score-history";

/* FIX-G CH12-F02: on touch the first tap on a dot previews it (the chart's tooltip), the second tap on the same dot
 * opens the run, so a scroll that starts on the chart cannot open a run by accident. Mouse and Enter open at once. */
const run = (id: number, soft: number, finished: string) =>
  ScheduleRun.parse({ id, term_id: 1, term_code: "B", kind: "COURSE", horizon: "TERM", horizon_params: { weeks: [] }, status: "FEASIBLE", params: {}, objective_value: null, soft_score: soft, hard_score: 100, stats: { solver: "cp-sat" }, diagnosis: [], parent_run_id: null, prompt_text: null, created_at: finished, finished_at: finished });
const runs = [run(9, 70, "2026-10-12T09:00:00Z"), run(12, 81, "2026-10-14T09:00:00Z"), run(15, 88, "2026-10-16T09:00:00Z")];

describe("CH12-F02 · /runs score line on touch", { timeout: 20_000 }, () => {
  it("a first tap previews, a second tap on the same dot opens; a mouse click opens at once", () => {
    push.mockClear();
    render(<ScoreHistory runs={runs} />);
    const group = screen.getByRole("group", { name: "Grafik, ok tuşlarıyla gezinin" });
    fireEvent.pointerDown(group, { pointerType: "touch" });
    fireEvent.click(group, { clientX: 10, clientY: 10 });
    expect(push).not.toHaveBeenCalled();
    fireEvent.pointerDown(group, { pointerType: "touch" });
    fireEvent.click(group, { clientX: 10, clientY: 10 });
    expect(push).toHaveBeenLastCalledWith("/runs/9");
    push.mockClear();
    fireEvent.pointerDown(group, { pointerType: "mouse" });
    fireEvent.click(group, { clientX: 10, clientY: 10 });
    expect(push).toHaveBeenLastCalledWith("/runs/9");
  });

  it("Enter after a tap still opens at once", () => {
    push.mockClear();
    render(<ScoreHistory runs={runs} />);
    const group = screen.getByRole("group", { name: "Grafik, ok tuşlarıyla gezinin" });
    fireEvent.pointerDown(group, { pointerType: "touch" });
    fireEvent.click(group, { clientX: 10, clientY: 10 });
    fireEvent.keyDown(group, { key: "ArrowRight" });
    fireEvent.keyDown(group, { key: "Enter" });
    expect(push).toHaveBeenLastCalledWith("/runs/9");
  });
});
